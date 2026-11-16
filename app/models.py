from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from app.clock import Clock
from app.exceptions import (
    InvalidTransitionError,
    BudgetExceededError,
    VolunteerNotEligibleError,
    VolunteerAlreadyAssignedError,
    RefillNotFoundError,
    RefillAlreadyExistsError,
    PurchaseNotFoundError,
    ClaimNotFoundError,
    CrossCurrencyError,
    AssignmentExpiredError,
)


class Office:
    """Domain model for an office."""

    def __init__(
        self,
        id: int,
        name: str,
        currency: str,
        monthly_budget_minor: int,
        timezone: str,
    ) -> None:
        self.id = id
        self.name = name
        self.currency = currency
        self.monthly_budget_minor = monthly_budget_minor
        self.timezone = timezone


class Volunteer:
    """Domain model for a volunteer."""

    def __init__(
        self,
        id: int,
        employee_id: str,
        name: str,
        home_office_id: int,
        payroll_currency: str,
        available: bool = True,
        last_assigned_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
    ) -> None:
        self.id = id
        self.employee_id = employee_id
        self.name = name
        self.home_office_id = home_office_id
        self.payroll_currency = payroll_currency
        self.available = available
        self.last_assigned_at = last_assigned_at
        self.created_at = created_at


class SnackBox:
    """Domain model for a snack box."""

    def __init__(
        self,
        id: int,
        office_id: int,
        name: str,
        status: str = "STOCKED",
    ) -> None:
        self.id = id
        self.office_id = office_id
        self.name = name
        self.status = status


class Refill:
    """Domain model for a refill request."""

    VALID_TRANSITIONS = {
        "OPEN": ["ASSIGNED", "CANCELLED"],
        "ASSIGNED": ["ACCEPTED", "OPEN", "CANCELLED"],
        "ACCEPTED": ["PURCHASED"],
        "PURCHASED": ["CLAIM_SUBMITTED"],
        "CLAIM_SUBMITTED": ["REIMBURSED", "PURCHASED", "CANCELLED"],
        "REIMBURSED": [],
        "CANCELLED": [],
    }

    def __init__(
        self,
        id: int,
        snack_box_id: int,
        status: str = "OPEN",
        assigned_volunteer_id: Optional[int] = None,
        assignment_expires_at: Optional[datetime] = None,
        assignment_attempt: int = 1,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> None:
        self.id = id
        self.snack_box_id = snack_box_id
        self.status = status
        self.assigned_volunteer_id = assigned_volunteer_id
        self.assignment_expires_at = assignment_expires_at
        self.assignment_attempt = assignment_attempt
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)
        self.completed_at = completed_at

    def can_transition_to(self, new_status: str) -> bool:
        """Check if the transition is valid."""
        allowed = self.VALID_TRANSITIONS.get(self.status, [])
        return new_status in allowed

    def transition_to(self, new_status: str, now: datetime) -> None:
        """Transition to a new status, raising if invalid."""
        if not self.can_transition_to(new_status):
            raise InvalidTransitionError(
                f"Cannot transition refill {self.id} from {self.status} to {new_status}"
            )
        self.status = new_status
        self.updated_at = now
        if new_status in ("REIMBURSED", "CANCELLED", "PURCHASED"):
            self.completed_at = now


class Purchase:
    """Domain model for a purchase."""

    def __init__(
        self,
        id: int,
        refill_id: int,
        volunteer_id: int,
        office_id: int,
        amount_minor: int,
        currency: str,
        description: Optional[str] = None,
        receipt_reference: Optional[str] = None,
    ) -> None:
        self.id = id
        self.refill_id = refill_id
        self.volunteer_id = volunteer_id
        self.office_id = office_id
        self.amount_minor = amount_minor
        self.currency = currency
        self.description = description
        self.receipt_reference = receipt_reference


class BudgetReservation:
    """Domain model for a budget reservation."""

    def __init__(
        self,
        id: int,
        office_id: int,
        refill_id: int,
        reserved_amount_minor: int,
        actual_amount_minor: Optional[int],
        currency: str,
        status: str,
        budget_month: str,
    ) -> None:
        self.id = id
        self.office_id = office_id
        self.refill_id = refill_id
        self.reserved_amount_minor = reserved_amount_minor
        self.actual_amount_minor = actual_amount_minor
        self.currency = currency
        self.status = status
        self.budget_month = budget_month


class Reimbursement:
    """Domain model for a reimbursement claim."""

    def __init__(
        self,
        id: int,
        purchase_id: int,
        external_claim_id: Optional[str],
        status: str,
        submitted_at: Optional[datetime],
        resolved_at: Optional[datetime],
        last_error: Optional[str],
    ) -> None:
        self.id = id
        self.purchase_id = purchase_id
        self.external_claim_id = external_claim_id
        self.status = status
        self.submitted_at = submitted_at
        self.resolved_at = resolved_at
        self.last_error = last_error


class AuditEvent:
    """Domain model for an audit event."""

    def __init__(
        self,
        id: int,
        aggregate_type: str,
        aggregate_id: int,
        event_type: str,
        actor_id: Optional[int],
        details_json: Optional[str],
        created_at: datetime,
    ) -> None:
        self.id = id
        self.aggregate_type = aggregate_type
        self.aggregate_id = aggregate_id
        self.event_type = event_type
        self.actor_id = actor_id
        self.details_json = details_json
        self.created_at = created_at