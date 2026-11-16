from __future__ import annotations

from typing import List, Optional

from ..db import Database
from ..models import Purchase


class PurchaseRepository:
    """Repository for purchase data access."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(
        self,
        refill_id: int,
        volunteer_id: int,
        office_id: int,
        amount_minor: int,
        currency: str,
        description: Optional[str] = None,
        receipt_reference: Optional[str] = None,
        txn=None,
    ) -> Purchase:
        """Create a new purchase."""
        params = (
            refill_id,
            volunteer_id,
            office_id,
            amount_minor,
            currency,
            description,
            receipt_reference,
        )
        if txn:
            self._db.conn.execute(
                "INSERT INTO purchases (refill_id, volunteer_id, office_id, amount_minor, currency, description, receipt_reference, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%d %H:%M:%f', 'now'))",
                params,
                txn,
            )
        else:
            self._db.conn.execute(
                "INSERT INTO purchases (refill_id, volunteer_id, office_id, amount_minor, currency, description, receipt_reference, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%d %H:%M:%f', 'now'))",
                params,
            )
        self._db.conn.commit()
        # Fetch the created purchase with its ID
        return self.get_by_refill_id(refill_id, txn=txn)

    def get_by_id(self, purchase_id: int, txn=None) -> Optional[Purchase]:
        """Get a purchase by ID."""
        cursor = self._db.conn.execute(
            "SELECT id, refill_id, volunteer_id, office_id, amount_minor, currency, description, receipt_reference, created_at FROM purchases WHERE id = ?",
            (purchase_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return Purchase(
            id=row[0],
            refill_id=row[1],
            volunteer_id=row[2],
            office_id=row[3],
            amount_minor=row[4],
            currency=row[5],
            description=row[6],
            receipt_reference=row[7],
        )

    def get_by_refill_id(self, refill_id: int, txn=None) -> Optional[Purchase]:
        """Get a purchase by refill ID."""
        cursor = self._db.conn.execute(
            "SELECT id, refill_id, volunteer_id, office_id, amount_minor, currency, description, receipt_reference, created_at FROM purchases WHERE refill_id = ?",
            (refill_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return Purchase(
            id=row[0],
            refill_id=row[1],
            volunteer_id=row[2],
            office_id=row[3],
            amount_minor=row[4],
            currency=row[5],
            description=row[6],
            receipt_reference=row[7],
        )

    def get_by_office_month(
        self, office_id: int, month: str, txn=None
    ) -> List[Purchase]:
        """Get purchases for an office and month (month format: YYYY-MM)."""
        cursor = self._db.conn.execute(
            """SELECT id, refill_id, volunteer_id, office_id, amount_minor, currency, description, receipt_reference, created_at 
               FROM purchases 
               WHERE office_id = ? AND strftime('%Y-%m', created_at) = ?
               ORDER BY created_at""",
            (office_id, month),
        )
        purchases = []
        for row in cursor:
            purchases.append(
                Purchase(
                    id=row[0],
                    refill_id=row[1],
                    volunteer_id=row[2],
                    office_id=row[3],
                    amount_minor=row[4],
                    currency=row[5],
                    description=row[6],
                    receipt_reference=row[7],
                )
            )
        return purchases

    def get_reconciled_spend(
        self, office_id: int, month: str, txn=None
    ) -> int:
        """Get reconciled spend for an office and month.

        Reconciled spend = purchases where receipt was submitted (has receipt_reference)
        and the corresponding refill is in a state that indicates the purchase was completed.
        """
        cursor = self._db.conn.execute(
            """SELECT COALESCE(SUM(p.amount_minor), 0) 
               FROM purchases p
               INNER JOIN refills r ON p.refill_id = r.id
               WHERE p.office_id = ? 
                 AND strftime('%Y-%m', p.created_at) = ?
                 AND p.receipt_reference IS NOT NULL 
                 AND r.status = 'REIMBURSED'""",
            (office_id, month),
        )
        row = cursor.fetchone()
        return row[0]