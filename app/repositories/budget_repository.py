from __future__ import annotations

from typing import List, Optional

from ..db import Database
from ..models import BudgetReservation


class BudgetRepository:
    """Repository for budget reservation data access."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, reservation: BudgetReservation, txn=None) -> BudgetReservation:
        """Create a new budget reservation."""
        params = (
            reservation.office_id,
            reservation.refill_id,
            reservation.reserved_amount_minor,
            reservation.actual_amount_minor,
            reservation.currency,
            reservation.status,
            reservation.budget_month,
        )
        if txn:
            self._db.conn.execute(
                "INSERT INTO budget_reservations (office_id, refill_id, reserved_amount_minor, actual_amount_minor, currency, status, budget_month, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%d %H:%M:%f', 'now'), strftime('%Y-%m-%d %H:%M:%f', 'now'))",
                params,
                txn,
            )
        else:
            self._db.conn.execute(
                "INSERT INTO budget_reservations (office_id, refill_id, reserved_amount_minor, actual_amount_minor, currency, status, budget_month, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%d %H:%M:%f', 'now'), strftime('%Y-%m-%d %H:%M:%f', 'now'))",
                params,
            )
        self._db.conn.commit()
        return reservation

    def get_by_id(self, reservation_id: int, txn=None) -> Optional[BudgetReservation]:
        """Get a budget reservation by ID."""
        cursor = self._db.conn.execute(
            "SELECT id, office_id, refill_id, reserved_amount_minor, actual_amount_minor, currency, status, budget_month, created_at, updated_at FROM budget_reservations WHERE id = ?",
            (reservation_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return BudgetReservation(
            id=row[0],
            office_id=row[1],
            refill_id=row[2],
            reserved_amount_minor=row[3],
            actual_amount_minor=row[4],
            currency=row[5],
            status=row[6],
            budget_month=row[7],
        )

    def get_by_refill_id(self, refill_id: int, txn=None) -> Optional[BudgetReservation]:
        """Get a budget reservation by refill ID."""
        cursor = self._db.conn.execute(
            "SELECT id, office_id, refill_id, reserved_amount_minor, actual_amount_minor, currency, status, budget_month, created_at, updated_at FROM budget_reservations WHERE refill_id = ?",
            (refill_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return BudgetReservation(
            id=row[0],
            office_id=row[1],
            refill_id=row[2],
            reserved_amount_minor=row[3],
            actual_amount_minor=row[4],
            currency=row[5],
            status=row[6],
            budget_month=row[7],
        )

    def get_active_reservations(
        self, office_id: int, month: str, txn=None
    ) -> List[BudgetReservation]:
        """Get active (RESERVED) budget reservations for an office and month."""
        cursor = self._db.conn.execute(
            """SELECT id, office_id, refill_id, reserved_amount_minor, actual_amount_minor, currency, status, budget_month, created_at, updated_at 
               FROM budget_reservations 
               WHERE office_id = ? AND budget_month = ? AND status = 'RESERVED'""",
            (office_id, month),
        )
        reservations = []
        for row in cursor:
            reservations.append(
                BudgetReservation(
                    id=row[0],
                    office_id=row[1],
                    refill_id=row[2],
                    reserved_amount_minor=row[3],
                    actual_amount_minor=row[4],
                    currency=row[5],
                    status=row[6],
                    budget_month=row[7],
                )
            )
        return reservations

    def update_status(self, reservation_id: int, status: str, txn=None) -> None:
        """Update a reservation status."""
        self._db.conn.execute(
            "UPDATE budget_reservations SET status = ?, updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now') WHERE id = ?",
            (status, reservation_id),
            txn,
        )
        self._db.conn.commit()

    def update_actual_amount(
        self, reservation_id: int, actual_amount_minor: int, txn=None
    ) -> None:
        """Update a reservation's actual amount and status."""
        self._db.conn.execute(
            """UPDATE budget_reservations 
               SET actual_amount_minor = ?, status = 'RECONCILED', updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now') 
               WHERE id = ?""",
            (actual_amount_minor, reservation_id),
            txn,
        )
        self._db.conn.commit()