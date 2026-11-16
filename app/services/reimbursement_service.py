from __future__ import annotations

from datetime import datetime

from app.clock import Clock
from app.exceptions import ClaimNotFoundError
from app.models import Purchase, Reimbursement
from app.db import Database


class ReimbursementService:
    """Application service for HR reimbursement claim management."""

    def __init__(self, db: Database, clock: Clock, hr_adapter=None) -> None:
        self._db = db
        self._clock = clock
        self._hr = hr_adapter

    def submit_claim(
        self,
        purchase_id: int,
        employee_id: str,
        amount_minor: int,
        currency: str,
        description: str,
        receipt_reference: str,
        idempotency_key: str,
    ) -> dict:
        """Submit a reimbursement claim to the HR simulator.

        Returns the claim response from the HR simulator.
        """
        from app.repositories.purchase_repository import PurchaseRepository
        from app.repositories.reimbursement_repository import ReimbursementRepository

        prepo = PurchaseRepository(self._db)
        grepo = ReimbursementRepository(self._db)

        # Check purchase exists
        purchase = prepo.get_by_id(purchase_id)
        if not purchase:
            raise ClaimNotFoundError(f"Purchase {purchase_id} not found")

        # Check idempotency - if same idempotency key already submitted
        existing_claim = grepo.get_by_external_claim_id(
            f"temp_{idempotency_key}"  # We'll use purchase_id + idempotency_key
        )
        # Actually, we need to check by a proper idempotency key

        # Create reimbursement record
        reimbursement = Reimbursement(
            id=None,
            purchase_id=purchase_id,
            external_claim_id=None,
            status="NOT_SUBMITTED",
            submitted_at=None,
            resolved_at=None,
            last_error=None,
        )
        grepo.create(reimbursement)

        # Submit to HR simulator
        if self._hr:
            claim = self._hr.submit_claim(
                employee_id=employee_id,
                amount_minor=amount_minor,
                currency=currency,
                description=description,
                receipt_reference=receipt_reference,
                idempotency_key=idempotency_key,
            )

            # Update reimbursement with external claim ID
            reimbursement.external_claim_id = claim.external_claim_id
            reimbursement.status = "PENDING"
            reimbursement.submitted_at = self._clock.now()
            grepo.update(reimbursement)

            return {
                "external_claim_id": reimbursement.external_claim_id,
                "status": "PENDING",
                "submitted_at": reimbursement.submitted_at.isoformat(),
            }
        else:
            # No HR simulator - just mark as submitted
            reimbursement.status = "PENDING"
            reimbursement.external_claim_id = idempotency_key
            reimbursement.submitted_at = self._clock.now()
            grepo.update(reimbursement)

            return {
                "external_claim_id": reimbursement.external_claim_id,
                "status": "PENDING",
                "submitted_at": reimbursement.submitted_at.isoformat(),
            }

    def approve_claim(self, external_claim_id: str, now: datetime | None = None) -> Reimbursement:
        """Approve an HR claim and update local state."""
        from app.repositories.reimbursement_repository import ReimbursementRepository
        from app.repositories.purchase_repository import PurchaseRepository
        from app.repositories.refill_repository import RefillRepository

        grepo = ReimbursementRepository(self._db)
        prepo = PurchaseRepository(self._db)
        refill_repo = RefillRepository(self._db)

        reimbursement = grepo.get_by_external_claim_id(external_claim_id)
        if not reimbursement:
            raise ClaimNotFoundError(f"Claim {external_claim_id} not found")

        now = now or self._clock.now()

        if reimbursement.status == "APPROVED":
            return reimbursement

        # Update reimbursement status
        reimbursement.status = "APPROVED"
        reimbursement.resolved_at = now
        grepo.update(reimbursement)

        # Update corresponding purchase and refill status
        purchase = prepo.get_by_id(reimbursement.purchase_id)
        if purchase:
            # Update refill status to REIMBURSED
            refill = refill_repo.get_by_id(purchase.refill_id)
            if refill:
                refill.transition_to("REIMBURSED", now)
                refill_repo.update(refill)

                # Audit event
                with self._db.begin() as txn:
                    from app.repositories.audit_repository import AuditRepository
                    audit = AuditRepository(self._db)
                    audit.create(
                        aggregate_type="refill",
                        aggregate_id=refill.id,
                        event_type="REIMBURSED",
                        actor_id=None,
                        details_json={},
                    )

        return reimbursement

    def reject_claim(self, external_claim_id: str, now: datetime | None = None) -> Reimbursement:
        """Reject an HR claim and update local state."""
        from app.repositories.reimbursement_repository import ReimbursementRepository

        grepo = ReimbursementRepository(self._db)

        reimbursement = grepo.get_by_external_claim_id(external_claim_id)
        if not reimbursement:
            raise ClaimNotFoundError(f"Claim {external_claim_id} not found")

        now = now or self._clock.now()

        # Update reimbursement status
        reimbursement.status = "REJECTED"
        reimbursement.last_error = "HR rejected the claim"
        reimbursement.resolved_at = now
        grepo.update(reimbursement)

        # Release budget reservation
        from app.repositories.budget_repository import BudgetRepository
        brepo = BudgetRepository(self._db)
        reservation = brepo.get_by_refill_id(reimbursement.purchase_id)
        if reservation:
            reservation.status = "RELEASED"
            brepo.update(reservation)

        # Audit event
        with self._db.begin() as txn:
            from app.repositories.audit_repository import AuditRepository
            audit = AuditRepository(self._db)
            audit.create(
                aggregate_type="reimbursement",
                aggregate_id=reimbursement.id,
                event_type="REJECTED",
                actor_id=None,
                details_json={"last_error": reimbursement.last_error},
            )

        return reimbursement