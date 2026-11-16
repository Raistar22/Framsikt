from __future__ import annotations

from datetime import datetime, timezone, timedelta

from app.clock import Clock
from app.exceptions import InvalidTransitionError
from app.models import Refill
from app.db import Database


class RefillService:
    def __init__(self, db, clock, chat_adapter=None):
        self._db = db
        self._clock = clock
        self._chat = chat_adapter

    def report_empty_box(self, snack_box_id, idempotency_key=None):
        from app.repositories.refill_repository import RefillRepository
        repo = RefillRepository(self._db)
        existing = repo.get_active_by_snack_box(snack_box_id)
        if existing:
            from app.exceptions import RefillAlreadyExistsError
            raise RefillAlreadyExistsError(f"A refill is already active for snack box {snack_box_id}")
        refill = Refill(id=None, snack_box_id=snack_box_id, status="OPEN")
        created_refill = repo.create(refill)
        refill = created_refill
        from app.repositories.audit_repository import AuditRepository
        audit = AuditRepository(self._db)
        audit.create(
            aggregate_type="refill",
            aggregate_id=refill.id,
            event_type="REPORTED_EMPTY",
            actor_id=None,
            details_json={"snack_box_id": snack_box_id, "idempotency_key": idempotency_key},
        )
        if self._chat:
            self._chat.send_direct_message(
                employee_id="",
                message=f"Snack box reported empty, refill request created: {refill.id}",
            )
        return refill

    def assign_refill(self, refill_id, volunteer_id, now=None):
        from app.repositories.refill_repository import RefillRepository
        repo = RefillRepository(self._db)
        refill = repo.get_by_id(refill_id)
        if not refill:
            from app.exceptions import RefillNotFoundError
            raise RefillNotFoundError(f"Refill {refill_id} not found")
        now = now or self._clock.now()
        if refill.assigned_volunteer_id is not None:
            raise InvalidTransitionError(f"Refill {refill_id} is already assigned")
        assignment_expires_at = now + timedelta(hours=96)
        refill.status = "ASSIGNED"
        refill.assigned_volunteer_id = volunteer_id
        refill.assignment_expires_at = assignment_expires_at
        refill.assignment_attempt += 1
        refill.updated_at = now
        repo.update(refill)
        from app.repositories.audit_repository import AuditRepository
        audit = AuditRepository(self._db)
        audit.create(
            aggregate_type="refill",
            aggregate_id=refill.id,
            event_type="ASSIGNED",
            actor_id=volunteer_id,
            details_json={"volunteer_id": volunteer_id, "assignment_expires_at": assignment_expires_at.isoformat()},
        )
        if self._chat:
            self._chat.send_direct_message(
                employee_id=str(volunteer_id),
                message=f"You have been assigned a refill request: {refill_id}. Please accept or decline within 96 hours.",
            )
        return refill

    def accept_refill(self, refill_id, volunteer_id, now=None):
        from app.repositories.refill_repository import RefillRepository
        repo = RefillRepository(self._db)
        refill = repo.get_by_id(refill_id)
        if not refill:
            from app.exceptions import RefillNotFoundError
            raise RefillNotFoundError(f"Refill {refill_id} not found")
        now = now or self._clock.now()
        if refill.assigned_volunteer_id != volunteer_id:
            from app.exceptions import VolunteerNotEligibleError
            raise VolunteerNotEligibleError(f"Volunteer {volunteer_id} is not assigned to refill {refill_id}")
        if refill.assignment_expires_at and self._clock.now() > refill.assignment_expires_at:
            from app.exceptions import AssignmentExpiredError
            raise AssignmentExpiredError(f"Refill {refill_id} assignment has expired")
        if not refill.can_transition_to("ACCEPTED"):
            raise InvalidTransitionError(f"Cannot transition refill {refill_id} from {refill.status} to ACCEPTED")
        refill.transition_to("ACCEPTED", now)
        repo.update(refill)
        from app.repositories.audit_repository import AuditRepository
        audit = AuditRepository(self._db)
        audit.create(
            aggregate_type="refill",
            aggregate_id=refill.id,
            event_type="ACCEPTED",
            actor_id=volunteer_id,
            details_json={},
        )
        if self._chat:
            self._chat.send_direct_message(
                employee_id=str(volunteer_id),
                message=f"Refill {refill_id} accepted. Please proceed with purchase.",
            )
        return refill

    def decline_refill(self, refill_id, volunteer_id, now=None):
        from app.repositories.refill_repository import RefillRepository
        repo = RefillRepository(self._db)
        refill = repo.get_by_id(refill_id)
        if not refill:
            from app.exceptions import RefillNotFoundError
            raise RefillNotFoundError(f"Refill {refill_id} not found")
        now = now or self._clock.now()
        if refill.assigned_volunteer_id != volunteer_id:
            from app.exceptions import VolunteerNotEligibleError
            raise VolunteerNotEligibleError(f"Volunteer {volunteer_id} is not assigned to refill {refill_id}")
        if not refill.can_transition_to("OPEN"):
            raise InvalidTransitionError(f"Cannot transition refill {refill_id} from {refill.status} to OPEN")
        refill.transition_to("OPEN", now)
        repo.update(refill)
        from app.repositories.audit_repository import AuditRepository
        audit = AuditRepository(self._db)
        audit.create(
            aggregate_type="refill",
            aggregate_id=refill.id,
            event_type="DECLINED",
            actor_id=volunteer_id,
            details_json={},
        )
        if self._chat:
            self._chat.send_direct_message(
                employee_id=str(volunteer_id),
                message=f"Refill {refill_id} declined.",
            )
        return refill

    def expire_overdue_assignments(self, now=None):
        from app.repositories.refill_repository import RefillRepository
        repo = RefillRepository(self._db)
        now = now or self._clock.now()
        overdue = repo.get_overdue(refill_expires_at_threshold=now)
        expired_refills = []
        for refill in overdue:
            if refill.status == "ASSIGNED":
                refill.transition_to("OPEN", now)
                repo.update(refill)
                from app.repositories.audit_repository import AuditRepository
                audit = AuditRepository(self._db)
                audit.create(
                    aggregate_type="refill",
                    aggregate_id=refill.id,
                    event_type="EXPIRED",
                    actor_id=refill.assigned_volunteer_id,
                    details_json={},
                )
                from app.services.volunteer_service import VolunteerService
                vs = VolunteerService(self._db, self._clock)
                eligible = vs.get_eligible_volunteers(
                    office_id=refill.office_id,
                    exclude_volunteer_id=refill.assigned_volunteer_id,
                )
                if eligible:
                    next_vol = eligible[0]
                    self.assign_refill(refill.id, next_vol.id, now=now)
                expired_refills.append(refill)
        return expired_refills