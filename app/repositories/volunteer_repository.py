from __future__ import annotations

from typing import List, Optional

from ..db import Database
from ..models import Volunteer


class VolunteerRepository:
    """Repository for volunteer data access."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(
        self,
        employee_id: str,
        name: str,
        home_office_id: int,
        payroll_currency: str,
        available: bool = True,
        txn=None,
    ) -> Volunteer:
        """Create a new volunteer."""
        params = (
            employee_id,
            name,
            home_office_id,
            payroll_currency,
            1 if available else 0,
        )
        if txn:
            self._db.conn.execute(
                "INSERT INTO volunteers (employee_id, name, home_office_id, payroll_currency, available, last_assigned_at, created_at) VALUES (?, ?, ?, ?, ?, NULL, strftime('%Y-%m-%d %H:%M:%f', 'now'))",
                params,
                txn,
            )
        else:
            self._db.conn.execute(
                "INSERT INTO volunteers (employee_id, name, home_office_id, payroll_currency, available, last_assigned_at, created_at) VALUES (?, ?, ?, ?, ?, NULL, strftime('%Y-%m-%d %H:%M:%f', 'now'))",
                params,
            )
        self._db.conn.commit()
        # Return a new Volunteer instance - ID will be set after commit
        # For simplicity, we fetch it back
        return self.get_by_employee_id(employee_id, txn)

    def get_by_employee_id(self, employee_id: str, txn=None) -> Optional[Volunteer]:
        """Get a volunteer by employee ID."""
        cursor = self._db.conn.execute(
            "SELECT id, employee_id, name, home_office_id, payroll_currency, available, last_assigned_at, created_at FROM volunteers WHERE employee_id = ?",
            (employee_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return Volunteer(
            id=row[0],
            employee_id=row[1],
            name=row[2],
            home_office_id=row[3],
            payroll_currency=row[4],
            available=bool(row[5]),
            last_assigned_at=row[6],
            created_at=row[7],
        )

    def get_by_id(self, volunteer_id: int, txn=None) -> Optional[Volunteer]:
        """Get a volunteer by ID."""
        cursor = self._db.conn.execute(
            "SELECT id, employee_id, name, home_office_id, payroll_currency, available, last_assigned_at, created_at FROM volunteers WHERE id = ?",
            (volunteer_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return Volunteer(
            id=row[0],
            employee_id=row[1],
            name=row[2],
            home_office_id=row[3],
            payroll_currency=row[4],
            available=bool(row[5]),
            last_assigned_at=row[6],
            created_at=row[7],
        )

    def get_all(self, txn=None) -> List[Volunteer]:
        """Get all volunteers."""
        cursor = self._db.conn.execute(
            "SELECT id, employee_id, name, home_office_id, payroll_currency, available, last_assigned_at, created_at FROM volunteers"
        )
        volunteers = []
        for row in cursor:
            volunteers.append(
                Volunteer(
                    id=row[0],
                    employee_id=row[1],
                    name=row[2],
                    home_office_id=row[3],
                    payroll_currency=row[4],
                    available=bool(row[5]),
                    last_assigned_at=row[6],
                    created_at=row[7],
                )
            )
        return volunteers

def update_available(self, volunteer_id: int, available: bool, txn=None) -> None:
    """Update volunteer availability."""
    self._db.conn.execute(
        "UPDATE volunteers SET available = ? WHERE id = ?",
        (1 if available else 0, volunteer_id),
    )
    self._db.conn.commit()