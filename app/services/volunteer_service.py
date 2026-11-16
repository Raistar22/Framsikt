from __future__ import annotations

from datetime import datetime, timedelta

from app.clock import Clock
from app.exceptions import VolunteerNotEligibleError
from app.models import Volunteer, Office
from app.db import Database


class VolunteerService:
    """Application service for volunteer eligibility and assignment."""

    def __init__(self, db: Database, clock: Clock) -> None:
        self._db = db
        self._clock = clock

    def is_eligible(
        self,
        volunteer: Volunteer,
        office_id: int,
        now: datetime | None = None,
    ) -> bool:
        """Check if a volunteer is eligible for assignment to an office."""
        now = now or self._clock.now()

        # Must be available
        if not volunteer.available:
            return False

        # Must be assigned to the relevant office either as home or through valid eligibility
        # Check if it's their home office
        if volunteer.home_office_id == office_id:
            home_office_eligible = True
        else:
            # Check temporary eligibility
            from app.repositories.volunteer_office_eligibility_repository import (
                VolunteerOfficeEligibilityRepository,
            )
            repo = VolunteerOfficeEligibilityRepository(self._db)
            eligible = repo.is_volunteer_eligible_for_office(volunteer.id, office_id, now)
            if not eligible:
                return False

        # Must have no active assignment
        # Check if volunteer has any ASSIGNED refills
        from app.repositories.refill_repository import RefillRepository
        refill_repo = RefillRepository(self._db)
        active_refills = refill_repo.get_active_by_volunteer(volunteer.id)
        if active_refills:
            return False

        return True

    def get_eligible_volunteers(
        self,
        office_id: int,
        exclude_volunteer_id: int | None = None,
        now: datetime | None = None,
    ) -> list[Volunteer]:
        """Get eligible volunteers for an office, sorted by fairness score.

        Sort order: 1. Fewest completed refills in rolling period
                     2. Oldest last_assigned_at (null first)
                     3. Stable volunteer ID
        """
        now = now or self._clock.now()

        from app.repositories.volunteer_repository import VolunteerRepository
        from app.repositories.refill_repository import RefillRepository

        repo = VolunteerRepository(self._db)
        refill_repo = RefillRepository(self._db)

        # Get all volunteers
        all_volunteers = repo.get_all()

        eligible = []
        for v in all_volunteers:
            if v.id == exclude_volunteer_id:
                continue
            if self.is_eligible(v, office_id, now=now):
                # Count completed refills in rolling period
                completed_refills = refill_repo.count_reimbursed_in_period(
                    v.id, now, rolling_days=30
                )
                eligible.append((v, completed_refills))

        # Sort by fairness: fewest completed refills, then oldest last_assigned_at (null first), then ID
        eligible.sort(key=lambda x: (
            x[1],
            x[0].last_assigned_at or datetime.min.replace(tzinfo=self._clock.now().tzinfo),
            x[0].id,
        ))

        return [v for v, _ in eligible]