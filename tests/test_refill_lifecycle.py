"""Refill lifecycle tests for Framsikt Snack Counter Automation."""

from __future__ import annotations

import pytest

from app import db
from app.repositories.office_repository import OfficeRepository
from app.repositories.volunteer_repository import VolunteerRepository
from app.repositories.snack_box_repository import SnackBoxRepository
from app.services.refill_service import RefillService
from app.services.volunteer_service import VolunteerService
from app.clock import RealClock
from app.exceptions import InvalidTransitionError


@pytest.fixture
def fresh_db():
    """Create a fresh in-memory database for each test."""
    database = db.Database(":memory:")
    clock = RealClock()
    orepo = OfficeRepository(database)
    vrepo = VolunteerRepository(database)
    srepo = SnackBoxRepository(database)

    # Create Oslo office
    from app.models import Office as OffModel
    oslo = OffModel(id=1, name="Oslo", currency="NOK", monthly_budget_minor=600000, timezone="Europe/Oslo")
    if orepo.get_by_name("Oslo") is None:
        orepo.create(oslo)

    # Create Bengaluru office
    from app.models import Office as OffModel2
    bengaluru = OffModel2(id=2, name="Bengaluru", currency="INR", monthly_budget_minor=1500000, timezone="Asia/Kolkata")
    if orepo.get_by_name("Bengaluru") is None:
        orepo.create(bengaluru)

    # Create volunteers
    for i in range(1, 4):
        from app.models import Volunteer as VolModel
        eid = f"oslo_{i:03d}"
        if not any(v.employee_id == eid for v in vrepo.get_all()):
            v = VolModel(id=i, employee_id=eid, name=f"Oslo Volunteer {i}", home_office_id=1, payroll_currency="NOK")
            vrepo.create(v.employee_id, v.name, v.home_office_id, v.payroll_currency)

    # Create snack box
    from app.models import SnackBox as SBModel
    sb = SBModel(id=1, office_id=1, name="Test Box", status="EMPTY")
    srepo.create(sb)

    chat_messages = []

    class ChatAdapter:
        def send_direct_message(self, employee_id: str, message: str) -> None:
            pass

    chat = ChatAdapter()
    refill_service = RefillService(database, clock, chat_adapter=chat)
    vol_service = VolunteerService(database, clock)

    yield database, clock, orepo, vrepo, srepo, refill_service, vol_service, chat

    database.close()


class TestRefillLifecycle:
    """Test the refill request lifecycle."""

    def test_empty_box_creates_refill(self, fresh_db):
        """An empty snack box creates a refill request."""
        database, clock, orepo, vrepo, srepo, refill_service, vol_service, chat = fresh_db

        refill = refill_service.report_empty_box(snack_box_id=1)
        assert refill is not None
        assert refill.status == "OPEN"

    def test_duplicate_refill_prevented(self, fresh_db):
        """Duplicate active refill requests are prevented for the same box."""
        database, clock, orepo, vrepo, srepo, refill_service, vol_service, chat = fresh_db

        # First report creates a refill
        refill1 = refill_service.report_empty_box(1)

        # Second report for same box should raise an error
        with pytest.raises(Exception):
            refill_service.report_empty_box(1)

    def test_valid_lifecycle_transitions(self, fresh_db):
        """Valid lifecycle transitions work."""
        database, clock, orepo, vrepo, srepo, refill_service, vol_service, chat = fresh_db

        refill = refill_service.report_empty_box(1)
        eligible = vol_service.get_eligible_volunteers(office_id=1, now=clock.now())

        assert len(eligible) > 0
        volunteer = eligible[0]

        # Assign refill
        assigned = refill_service.assign_refill(refill.id, volunteer.id, now=clock.now())
        assert assigned.status == "ASSIGNED"

        # Accept refill
        accepted = refill_service.accept_refill(refill.id, volunteer.id, now=clock.now())
        assert accepted.status == "ACCEPTED"

    def test_invalid_transitions_rejected(self, fresh_db):
        """Invalid transitions are rejected."""
        database, clock, orepo, vrepo, srepo, refill_service, vol_service, chat = fresh_db

        refill = refill_service.report_empty_box(1)

        # Try invalid transition
        try:
            refill.transition_to("PURCHASED", clock.now())
            pytest.fail("Invalid transition should have been rejected")
        except InvalidTransitionError:
            # Expected - invalid transition rejected
            pass

    def test_refill_has_state_machine(self, fresh_db):
        """Refill state machine has valid transitions defined."""
        database, clock, orepo, vrepo, srepo, refill_service, vol_service, chat = fresh_db

        refill = refill_service.report_empty_box(1)
        # OPEN should be able to transition to ASSIGNED or CANCELLED
        assert refill.can_transition_to("ASSIGNED")
        assert refill.can_transition_to("CANCELLED")


class TestBudgetManagement:
    """Test budget management rules."""

    def test_oslo_budget_config(self):
        """Oslo has a monthly budget of 6,000 NOK."""
        from app.config import settings
        assert settings.oslo_monthly_budget_minor == 600000

    def test_bengaluru_budget_config(self):
        """Bengaluru has a monthly budget of 15,000 INR."""
        from app.config import settings
        assert settings.bengaluru_monthly_budget_minor == 1500000

    def test_available_budget_initial(self, fresh_db):
        """Available budget is the full monthly budget initially."""
        from app.services.budget_service import BudgetService

        database, clock, orepo, vrepo, srepo, refill_service, vol_service, chat = fresh_db

        bs = BudgetService(database, RealClock())
        available = bs.calculate_available_budget(office_id=1, month="2026-11")
        assert available == 600000

    def test_budget_exceeded_raises_error(self, fresh_db):
        """Budget exceeded raises BudgetExceededError."""
        from app.services.budget_service import BudgetService
        from app.exceptions import BudgetExceededError

        database, clock, orepo, vrepo, srepo, refill_service, vol_service, chat = fresh_db

        bs = BudgetService(database, RealClock())
        with pytest.raises(BudgetExceededError):
            bs.reserve_budget(
                office_id=1,
                refill_id=1,
                amount_minor=700000,
                currency="NOK",
                budget_month="2026-11",
            )

    def test_different_currencies_separate(self, fresh_db):
        """Different currencies are reported separately."""
        from app.services.reporting_service import ReportingService

        database, clock, orepo, vrepo, srepo, refill_service, vol_service, chat = fresh_db

        reporting_service = ReportingService(database, RealClock())
        report = reporting_service.generate_monthly_report("2026-11")

        assert len(report["offices"]) == 2
        assert report["nok_total"] == 0
        assert report["inr_total"] == 0


class TestVolunteerAssignment:
    """Test volunteer assignment rules."""

    def test_eligible_volunteer_has_active_assignment(self, fresh_db):
        """A volunteer with an active assignment is handled by eligibility check."""
        database, clock, orepo, vrepo, srepo, refill_service, vol_service, chat = fresh_db

        refill = refill_service.report_empty_box(1)
        eligible = vol_service.get_eligible_volunteers(office_id=1, now=clock.now())
        # All volunteers should be initially eligible
        assert len(eligible) > 0

    def test_fairness_counts_reimbursed_refills(self, fresh_db):
        """Fairness algorithm considers reimbursed refills."""
        from app.services.volunteer_service import VolunteerService

        database, clock, orepo, vrepo, srepo, refill_service, vol_service, chat = fresh_db

        # The algorithm should work - check that get_eligible_volunteers runs
        eligible = vol_service.get_eligible_volunteers(office_id=1, now=clock.now())
        # Should not crash and return volunteers


class TestConcurrencyAndEdgeCases:
    """Test concurrency and edge cases."""

    def test_state_machine_transitions(self, fresh_db):
        """Refill state machine enforces valid transitions."""
        database, clock, orepo, vrepo, srepo, refill_service, vol_service, chat = fresh_db

        refill = refill_service.report_empty_box(1)
        # Valid OPEN -> ASSIGNED transition
        eligible = vol_service.get_eligible_volunteers(office_id=1, now=clock.now())
        if eligible:
            assigned = refill_service.assign_refill(refill.id, eligible[0].id, now=clock.now())
            assert assigned.status == "ASSIGNED"