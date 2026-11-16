from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Any


class HRClaim:
    """Represents an HR reimbursement claim."""

    def __init__(
        self,
        external_claim_id: str,
        employee_id: str,
        amount_minor: int,
        currency: str,
        description: str,
        receipt_reference: str,
        status: str = "PENDING",
        submitted_at: Optional[datetime] = None,
        resolved_at: Optional[datetime] = None,
    ) -> None:
        self.external_claim_id = external_claim_id
        self.employee_id = employee_id
        self.amount_minor = amount_minor
        self.currency = currency
        self.description = description
        self.receipt_reference = receipt_reference
        self.status = status
        self.submitted_at = submitted_at
        self.resolved_at = resolved_at


class HRSimulator:
    """Simulated external HR reimbursement system.

    Acts like an external system:
    - Accept a claim with employee ID, amount, currency, description, and receipt reference.
    - Return a unique external claim ID.
    - Keep claim status such as PENDING, APPROVED, or REJECTED.
    - Allow tests/demo code to transition a claim to approved or rejected.
    - Support idempotency so retrying a submission does not create duplicate claims.
    - Never automatically mark a claim reimbursed just because it was submitted.
    """

    def __init__(self) -> None:
        self._claims: Dict[str, HRClaim] = {}
        self._idempotency_keys: Dict[str, str] = {}  # idempotency_key -> external_claim_id

    def submit_claim(
        self,
        *,
        employee_id: str,
        amount_minor: int,
        currency: str,
        description: str,
        receipt_reference: str,
        idempotency_key: str,
    ) -> HRClaim:
        """Submit a reimbursement claim.

        Returns the claim. If the same idempotency key is used,
        the existing claim is returned (no duplicates).
        """
        # Check idempotency
        if idempotency_key in self._idempotency_keys:
            existing_id = self._idempotency_keys[idempotency_key]
            return self._claims[existing_id]

        # Generate a stable unique claim ID
        external_claim_id = f"claim_{idempotency_key}"

        claim = HRClaim(
            external_claim_id=external_claim_id,
            employee_id=employee_id,
            amount_minor=amount_minor,
            currency=currency,
            description=description,
            receipt_reference=receipt_reference,
            status="PENDING",
            submitted_at=datetime.now(timezone.utc),
        )

        self._claims[external_claim_id] = claim
        self._idempotency_keys[idempotency_key] = external_claim_id

        return claim

    def get_claim(self, external_claim_id: str) -> Optional[HRClaim]:
        """Get a claim by its external ID."""
        return self._claims.get(external_claim_id)

    def approve_claim(self, external_claim_id: str) -> HRClaim:
        """Approve a claim."""
        claim = self._claims.get(external_claim_id)
        if claim:
            claim.status = "APPROVED"
            claim.resolved_at = datetime.now(timezone.utc)
        return claim

    def reject_claim(self, external_claim_id: str, error: str = "HR rejected the claim") -> HRClaim:
        """Reject a claim."""
        claim = self._claims.get(external_claim_id)
        if claim:
            claim.status = "REJECTED"
            claim.resolved_at = datetime.now(timezone.utc)
            claim.last_error = error  # type: ignore[attr-defined]
        return claim


# For compatibility with the service layer
def create_hr_simulator() -> HRSimulator:
    """Factory function to create an HR simulator instance."""
    return HRSimulator()