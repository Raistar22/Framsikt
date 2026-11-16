from __future__ import annotations

from typing import List, Optional

from ..db import Database
from ..models import Office


class OfficeRepository:
    """Repository for office data access."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, office: Office, txn=None) -> Office:
        """Create a new office."""
        params = (
            office.name,
            office.currency,
            office.monthly_budget_minor,
            office.timezone,
        )
        if txn:
            self._db.conn.execute(
                "INSERT INTO offices (name, currency, monthly_budget_minor, timezone) VALUES (?, ?, ?, ?)",
                params,
                txn,
            )
        else:
            self._db.conn.execute(
                "INSERT INTO offices (name, currency, monthly_budget_minor, timezone) VALUES (?, ?, ?, ?)",
                params,
            )
        self._db.conn.commit()
        return office

    def get_by_id(self, office_id: int, txn=None) -> Optional[Office]:
        """Get an office by ID."""
        cursor = self._db.conn.execute(
            "SELECT id, name, currency, monthly_budget_minor, timezone FROM offices WHERE id = ?",
            (office_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return Office(
            id=row[0],
            name=row[1],
            currency=row[2],
            monthly_budget_minor=row[3],
            timezone=row[4],
        )

    def get_by_name(self, name: str, txn=None) -> Optional[Office]:
        """Get an office by name."""
        cursor = self._db.conn.execute(
            "SELECT id, name, currency, monthly_budget_minor, timezone FROM offices WHERE name = ?",
            (name,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return Office(
            id=row[0],
            name=row[1],
            currency=row[2],
            monthly_budget_minor=row[3],
            timezone=row[4],
        )

    def get_all(self, txn=None) -> List[Office]:
        """Get all offices."""
        cursor = self._db.conn.execute(
            "SELECT id, name, currency, monthly_budget_minor, timezone FROM offices"
        )
        offices = []
        for row in cursor:
            offices.append(
                Office(
                    id=row[0],
                    name=row[1],
                    currency=row[2],
                    monthly_budget_minor=row[3],
                    timezone=row[4],
                )
            )
        return offices