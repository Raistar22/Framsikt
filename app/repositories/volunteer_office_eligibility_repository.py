from __future__ import annotations

from typing import List, Optional

from ..db import Database
from ..models import Volunteer


class VolunteerOfficeEligibilityRepository:
    """Repository for volunteer-office eligibility records."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(
        self,
        volunteer_id: int,
        office_id: int,
        valid_from: str,
        valid_until: str,
        txn=None,
    ) -> None:
        """Create a volunteer-office eligibility record."""
        params = (volunteer_id, office_id, valid_from, valid_until)
        if txn:
            self._db.conn.execute(
                "INSERT INTO volunteer_office_eligibility (volunteer_id, office_id, valid_from, valid_until) VALUES (?, ?, ?, ?)",
                params,
                txn,
            )
        else:
            self._db.conn.execute(
                "INSERT INTO volunteer_office_eligibility (volunteer_id, office_id, valid_from, valid_until) VALUES (?, ?, ?, ?)",
                params,
            )
        self._db.conn.commit()

    def is_volunteer_eligible_for_office(
        self, volunteer_id: int, office_id: int, now: datetime
    ) -> bool:
        """Check if a volunteer has a valid eligibility record for an office."""
        cursor = self._db.conn.execute(
            """SELECT COUNT(*) FROM volunteer_office_eligibility 
               WHERE volunteer_id = ? AND office_id = ? 
                 AND valid_from <= ? 
                 AND (valid_until IS NULL OR valid_until > ?)""",
            (volunteer_id, office_id, now.isoformat(), now.isoformat()),
        )
        row = cursor.fetchone()
        return row[0] > 0

    def get_eligible_volunteers(self, office_id: int, now: datetime) -> List[int]:
        """Get volunteer IDs that have valid eligibility for an office."""
        cursor = self._db.conn.execute(
            """SELECT volunteer_id FROM volunteer_office_eligibility 
               WHERE office_id = ? 
                 AND valid_from <= ?
                 AND (valid_until IS NULL OR valid_until > ?)""",
            (office_id, now.isoformat(), now.isoformat()),
        )
        return [row[0] for row in cursor]