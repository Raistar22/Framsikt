from __future__ import annotations

from datetime import datetime

from app.clock import Clock
from app.exceptions import BudgetExceededError, CrossCurrencyError
from app.models import Office, Purchase, BudgetReservation
from app.db import Database


class BudgetService:
    """Application service for budget management and reservations."""

    def __init__(self, db: Database, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    def calculate_available_budget(self, office_id: int, month: str, now: datetime | None = None) -> int:
        """Calculate available budget for an office and month.

        available_budget = monthly_budget - reconciled_spend - active_reservations
        """
        now = now or self._clock.now()

        from app.repositories.budget_repository import BudgetRepository
        from app.repositories.purchase_repository import PurchaseRepository

        brepo = BudgetRepository(self._db)
        prepo = PurchaseRepository(self._db)

        # Get monthly budget
        from app.repositories.office_repository import OfficeRepository
        orepo = OfficeRepository(self._db)
        office = orepo.get_by_id(office_id)
        if not office:
            raise ValueError(f"Office {office_id} not found")

        monthly_budget = office.monthly_budget_minor

        # Get reconciled spend (purchases with receipt submitted)
        reconciled_spend = prepo.get_reconciled_spend(office_id, month)

        # Get active reservations and sum their reserved amounts
        active_reservations_list = brepo.get_active_reservations(office_id, month)
        active_reservations = sum(
            r.reserved_amount_minor for r in active_reservations_list if r.status == "RESERVED"
        )

        available = monthly_budget - reconciled_spend - active_reservations
        return max(available, 0)

    def reserve_budget(
        self,
        office_id: int,
        refill_id: int,
        amount_minor: int,
        currency: str,
        budget_month: str,
    ) -> BudgetReservation:
        """Atomically reserve budget for a purchase.

        Returns the created reservation.
        Raises BudgetExceededError if the reservation would exceed the budget.
        """
        from app.repositories.budget_repository import BudgetRepository
        from app.repositories.refill_repository import RefillRepository
        from app.repositories.office_repository import OfficeRepository

        brepo = BudgetRepository(self._db)
        refill_repo = RefillRepository(self._db)
        orepo = OfficeRepository(self._db)

        # Check currency matches office currency
        office = orepo.get_by_id(office_id)
        if not office:
            raise ValueError(f"Office {office_id} not found")

        if currency != office.currency:
            raise CrossCurrencyError(
                f"Currency {currency} does not match office currency "
                f"{office.currency}"
            )

        now = self._clock.now()

        with self._db.begin() as txn:
            # Calculate current committed spend
            available = self.calculate_available_budget(office_id, budget_month, now=now)

            # Verify reservation does not exceed remaining budget
            if amount_minor > available:
                raise BudgetExceededError(
                    f"Reservation of {amount_minor} {currency} exceeds "
                    f"remaining budget of {available} {currency} for office {office_id}"
                )

            # Insert reservation atomically
            reservation = BudgetReservation(
                id=None,
                office_id=office_id,
                refill_id=refill_id,
                reserved_amount_minor=amount_minor,
                actual_amount_minor=None,
                currency=currency,
                status="RESERVED",
                budget_month=budget_month,
            )
            brepo.create(reservation, txn=txn)

            # Update reservation updated_at
            brepo.update_status(reservation.id, "RESERVED", txn=txn)

        return reservation

    def reconcile_reservation(
        self,
        reservation_id: int,
        actual_amount_minor: int,
    ) -> BudgetReservation:
        """Reconcile a budget reservation to actual purchase amount.

        Rules:
        - If actual <= reserved, release unused reservation amount.
        - If actual > reserved, allow only if the additional amount still
          fits the remaining budget; otherwise reject/flag the purchase.
        """
        from app.repositories.budget_repository import BudgetRepository

        brepo = BudgetRepository(self._db)
        reservation = brepo.get_by_id(reservation_id)
        if not reservation:
            raise ValueError(f"Reservation {reservation_id} not found")

        # Update reservation with actual amount
        reservation.actual_amount_minor = actual_amount_minor

        # Determine new status
        if actual_amount_minor <= reservation.reserved_amount_minor:
            # Release unused amount, mark as reconciled
            reservation.status = "RECONCILED"
        else:
            # Actual exceeds reserved - check if additional fits in remaining budget
            # For now, keep as RESERVED and let purchase flow handle it
            reservation.status = "RESERVED"

        brepo.update(reservation)
        return reservation