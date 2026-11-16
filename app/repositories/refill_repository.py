from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from ..db import Database
from ..models import Refill


class RefillRepository:
    """Repository for refill data access."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, refill: Refill, txn=None) -> Refill:
        """Create a new refill."""
        params = (
            refill.snack_box_id,
            refill.status,
            refill.assigned_volunteer_id,
            refill.assignment_expires_at.isoformat() if refill.assignment_expires_at else None,
            refill.assignment_attempt,
        )
        if txn:
            self._db.conn.execute(
                "INSERT INTO refills (snack_box_id, status, assigned_volunteer_id, assignment_expires_at, assignment_attempt, created_at, updated_at, completed_at, idempotency_key) VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%d %H:%M:%f', 'now'), strftime('%Y-%m-%d %H:%M:%f', 'now'), NULL, NULL)",
                params,
                txn,
            )
        else:
            self._db.conn.execute(
                "INSERT INTO refills (snack_box_id, status, assigned_volunteer_id, assignment_expires_at, assignment_attempt, created_at, updated_at, completed_at, idempotency_key) VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%d %H:%M:%f', 'now'), strftime('%Y-%m-%d %H:%M:%f', 'now'), NULL, NULL)",
                params,
            )
        self._db.conn.commit()
        # Fetch the created refill with its ID
        return self.get_by_id(refill.id or self._get_last_id(), txn)

    def _get_last_id(self) -> int:
        """Get the last inserted rowid."""
        cursor = self._db.conn.execute("SELECT last_insert_rowid()")
        return cursor.fetchone()[0]

    def get_by_id(self, refill_id: int, txn=None) -> Optional[Refill]:
        """Get a refill by ID."""
        cursor = self._db.conn.execute(
            "SELECT id, snack_box_id, status, assigned_volunteer_id, assignment_expires_at, assignment_attempt, created_at, updated_at, completed_at, idempotency_key FROM refills WHERE id = ?",
            (refill_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        # Parse assignment_expires_at from string to datetime if needed
        assignment_expires_at = row[4]
        if isinstance(assignment_expires_at, str):
            try:
                assignment_expires_at = datetime.fromisoformat(assignment_expires_at)
            except (ValueError, TypeError):
                assignment_expires_at = None
        return Refill(
            id=row[0],
            snack_box_id=row[1],
            status=row[2],
            assigned_volunteer_id=row[3],
            assignment_expires_at=assignment_expires_at,
            assignment_attempt=row[5],
            created_at=row[6],
            updated_at=row[7],
            completed_at=row[8],
        )

    def get_active_by_snack_box(self, snack_box_id: int, txn=None) -> Optional[Refill]:
        """Get the active refill for a snack box."""
        cursor = self._db.conn.execute(
            "SELECT id, snack_box_id, status, assigned_volunteer_id, assignment_expires_at, assignment_attempt, created_at, updated_at, completed_at, idempotency_key FROM refills WHERE snack_box_id = ? AND status IN ('OPEN', 'ASSIGNED', 'ACCEPTED')",
            (snack_box_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        assignment_expires_at = row[4]
        if isinstance(assignment_expires_at, str):
            try:
                assignment_expires_at = datetime.fromisoformat(assignment_expires_at)
            except (ValueError, TypeError):
                assignment_expires_at = None
        return Refill(
            id=row[0],
            snack_box_id=row[1],
            status=row[2],
            assigned_volunteer_id=row[3],
            assignment_expires_at=assignment_expires_at,
            assignment_attempt=row[5],
            created_at=row[6],
            updated_at=row[7],
            completed_at=row[8],
        )

    def get_active_by_volunteer(self, volunteer_id: int, txn=None) -> list[Refill]:
        """Get active refills for a volunteer."""
        cursor = self._db.conn.execute(
            "SELECT id, snack_box_id, status, assigned_volunteer_id, assignment_expires_at, assignment_attempt, created_at, updated_at, completed_at, idempotency_key FROM refills WHERE assigned_volunteer_id = ? AND status IN ('OPEN', 'ASSIGNED', 'ACCEPTED')",
            (volunteer_id,),
        )
        refills = []
        for row in cursor:
            assignment_expires_at = row[4]
            if isinstance(assignment_expires_at, str):
                try:
                    assignment_expires_at = datetime.fromisoformat(assignment_expires_at)
                except (ValueError, TypeError):
                    assignment_expires_at = None
            refills.append(
                Refill(
                    id=row[0],
                    snack_box_id=row[1],
                    status=row[2],
                    assigned_volunteer_id=row[3],
                    assignment_expires_at=assignment_expires_at,
                    assignment_attempt=row[5],
                    created_at=row[6],
                    updated_at=row[7],
                    completed_at=row[8],
                )
            )
        return refills

    def get_overdue(self, refill_expires_at_threshold, txn=None) -> list[Refill]:
        """Get refills with expired assignments."""
        cursor = self._db.conn.execute(
            "SELECT id, snack_box_id, status, assigned_volunteer_id, assignment_expires_at, assignment_attempt, created_at, updated_at, completed_at, idempotency_key FROM refills WHERE status = 'ASSIGNED' AND assignment_expires_at < ?",
            (refill_expires_at_threshold,),
        )
        refills = []
        for row in cursor:
            assignment_expires_at = row[4]
            if isinstance(assignment_expires_at, str):
                try:
                    assignment_expires_at = datetime.fromisoformat(assignment_expires_at)
                except (ValueError, TypeError):
                    assignment_expires_at = None
            refills.append(
                Refill(
                    id=row[0],
                    snack_box_id=row[1],
                    status=row[2],
                    assigned_volunteer_id=row[3],
                    assignment_expires_at=assignment_expires_at,
                    assignment_attempt=row[5],
                    created_at=row[6],
                    updated_at=row[7],
                    completed_at=row[8],
                )
            )
        return refills

    def count_reimbursed_in_period(
        self, volunteer_id: int, now, rolling_days: int = 30
    ) -> int:
        """Count reimbursed refills for a volunteer in a rolling period."""
        from datetime import timedelta
        cutoff = now - timedelta(days=rolling_days)
        cursor = self._db.conn.execute(
            """SELECT COUNT(*) FROM refills 
               WHERE assigned_volunteer_id = ? 
               AND status = 'REIMBURSED' 
               AND completed_at >= ?""",
            (volunteer_id, cutoff),
        )
        row = cursor.fetchone()
        return row[0] if row else 0

    def update(self, refill: Refill) -> None:
        """Update a refill's fields in the database."""
        self._db.conn.execute(
            "UPDATE refills SET status = ?, assigned_volunteer_id = ?, assignment_expires_at = ?, assignment_attempt = ?, updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now') WHERE id = ?",
            (refill.status, refill.assigned_volunteer_id, refill.assignment_expires_at.isoformat() if refill.assignment_expires_at else None, refill.assignment_attempt, refill.id),
        )
        self._db.conn.commit()