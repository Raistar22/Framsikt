from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.clock import Clock
from app.models import Office, Purchase, Refill, Reimbursement, BudgetReservation
from app.db import Database


class ReportingService:
    """Application service for monthly reporting."""

    def __init__(self, db: Database, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    def generate_monthly_report(self, month: str) -> dict:
        """Generate a monthly report for a given month (format: YYYY-MM)."""
        from app.repositories.office_repository import OfficeRepository
        from app.repositories.purchase_repository import PurchaseRepository
        from app.repositories.budget_repository import BudgetRepository
        from app.repositories.reimbursement_repository import ReimbursementRepository

        orepo = OfficeRepository(self._db)
        prepo = PurchaseRepository(self._db)
        brepo = BudgetRepository(self._db)
        grepo = ReimbursementRepository(self._db)

        # Get all offices
        offices = orepo.get_all()

        report = {
            "month": month,
            "generated_at": self._clock.now().isoformat(),
            "offices": [],
            "nok_total": 0,
            "inr_total": 0,
        }

        for office in offices:
            office_id = office.id
            currency = office.currency
            monthly_budget = office.monthly_budget_minor

            # Get purchases for this office and month
            purchases = prepo.get_by_office_month(office_id, month)

            # Get active budget reservations
            reservations = brepo.get_active_reservations(office_id, month)

            # Get reimbursements status counts
            reimbursements = grepo.get_by_office_month(office_id, month)

            # Calculate reconciled spend (actual amounts from purchases with receipt submitted)
            # "Actual spend" = sum of purchase amounts where receipt was submitted
            actual_spend = sum(p.amount_minor for p in purchases if p.receipt_reference)

            # Calculate pending commitments (reservations + pending claims)
            pending_commitments = sum(r.reserved_amount_minor for r in reservations if r.status == "RESERVED")

            # Count refills completed (reimbursed)
            completed_refills = grepo.count_reimbursed_by_office(office_id, month)

            # Remaining budget
            remaining_budget = monthly_budget - actual_spend - pending_commitments

            office_report = {
                "office_id": office_id,
                "office_name": office.name,
                "currency": currency,
                "budget": monthly_budget,
                "actual_spend": actual_spend,
                "pending_commitments": pending_commitments,
                "remaining_budget": remaining_budget,
                "completed_refills": completed_refills,
                "pending_claims": reimbursements.get("pending", 0),
                "approved_claims": reimbursements.get("approved", 0),
                "rejected_claims": reimbursements.get("rejected", 0),
            }

            report["offices"].append(office_report)

            # Add to currency totals (not summing NOK and INR)
            if currency == "NOK":
                report["nok_total"] += actual_spend
            elif currency == "INR":
                report["inr_total"] += actual_spend

        # Do not sum NOK and INR without explicit exchange rate
        # report["grand_total"] would be misleading

        return report