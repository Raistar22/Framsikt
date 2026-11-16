from __future__ import annotations

from typing import Optional

from ..db import Database
from ..models import Reimbursement


class ReimbursementRepository:
    """Repository for reimbursement data access."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, reimbursement: Reimbursement, txn=None) -> Reimbursement:
        """Create a new reimbursement."""
        params = (
            reimbursement.purchase_id,
            reimbursement.external_claim_id,
            reimbursement.status,
            reimbursement.submitted_at,
            reimbursement.resolved_at,
            reimbursement.last_error,
        )
        if txn:
            self._db.conn.execute(
                "INSERT INTO reimbursements (purchase_id, external_claim_id, status, submitted_at, resolved_at, last_error, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, strftime('%Y-%m-%d %H:%M:%f', 'now'), strftime('%Y-%m-%d %H:%M:%f', 'now'))",
                params,
                txn,
            )
        else:
            self._db.conn.execute(
                "INSERT INTO reimbursements (purchase_id, external_claim_id, status, submitted_at, resolved_at, last_error, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, strftime('%Y-%m-%d %H:%M:%f', 'now'), strftime('%Y-%m-%d %H:%M:%f', 'now'))",
                params,
            )
        self._db.conn.commit()
        return reimbursement

    def update(self, reimbursement: Reimbursement, txn=None) -> Reimbursement:
        """Update a reimbursement record."""
        params = (
            reimbursement.status,
            reimbursement.last_error,
            reimbursement.resolved_at,
            reimbursement.purchase_id,
        )
        if txn:
            self._db.conn.execute(
                "UPDATE reimbursements SET status = ?, last_error = ?, resolved_at = ?, updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now') WHERE purchase_id = ?",
                params,
                txn,
            )
        else:
            self._db.conn.execute(
                "UPDATE reimbursements SET status = ?, last_error = ?, resolved_at = ?, updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now') WHERE purchase_id = ?",
                params,
            )
        self._db.conn.commit()
        return reimbursement

    def get_by_id(self, reimbursement_id: int, txn=None) -> Optional[Reimbursement]:
        """Get a reimbursement by ID."""
        cursor = self._db.conn.execute(
            "SELECT id, purchase_id, external_claim_id, status, submitted_at, resolved_at, last_error, created_at, updated_at FROM reimbursements WHERE id = ?",
            (reimbursement_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return Reimbursement(
            id=row[0],
            purchase_id=row[1],
            external_claim_id=row[2],
            status=row[3],
            submitted_at=row[4],
            resolved_at=row[5],
            last_error=row[6],
        )

    def get_by_external_claim_id(self, external_claim_id: str, txn=None) -> Optional[Reimbursement]:
        """Get a reimbursement by external claim ID."""
        cursor = self._db.conn.execute(
            "SELECT id, purchase_id, external_claim_id, status, submitted_at, resolved_at, last_error, created_at, updated_at FROM reimbursements WHERE external_claim_id = ?",
            (external_claim_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return Reimbursement(
            id=row[0],
            purchase_id=row[1],
            external_claim_id=row[2],
            status=row[3],
            submitted_at=row[4],
            resolved_at=row[5],
            last_error=row[6],
        )

    def get_by_office_month(self, office_id: int, month: str, txn=None) -> dict:
        """Get reimbursement status counts for an office and month."""
        cursor = self._db.conn.execute(
            """SELECT status, COUNT(*) FROM reimbursements 
               WHERE purchase_id IN (SELECT id FROM purchases WHERE office_id = ? AND strftime('%Y-%m', created_at) = ?) 
               GROUP BY status""",
            (office_id, month),
        )
        result = {"pending": 0, "approved": 0, "rejected": 0}
        for row in cursor:
            if row[0] == "PENDING":
                result["pending"] = row[1]
            elif row[0] == "APPROVED":
                result["approved"] = row[1]
            elif row[0] == "REJECTED":
                result["rejected"] = row[1]
        return result

    def count_reimbursed_by_office(self, office_id: int, month: str, txn=None) -> int:
        """Count reimbursed refills for an office and month."""
        cursor = self._db.conn.execute(
            """SELECT COUNT(*) FROM reimbursements r 
               JOIN purchases p ON r.purchase_id = p.id 
               WHERE p.office_id = ? AND r.status = 'APPROVED' AND strftime('%Y-%m', p.created_at) = ?""",
            (office_id, month),
        )
        row = cursor.fetchone()
        return row[0] if row else 0