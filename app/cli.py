from __future__ import annotations

import argparse
import sys
from datetime import datetime

from app.config import settings
from app.db import Database
from .adapters.chat_simulator import ChatSimulator
from .adapters.hr_simulator import HRSimulator, create_hr_simulator
from .services.refill_service import RefillService
from .services.volunteer_service import VolunteerService
from .services.budget_service import BudgetService
from .services.reimbursement_service import ReimbursementService
from .services.reporting_service import ReportingService


def init_db(db: Database) -> None:
    """Initialize the database (create tables)."""
    print("Database initialized.")


def seed_demo(db: Database, chat: ChatSimulator) -> None:
    """Seed the database with Oslo and Bengaluru, volunteers, and snack boxes."""
    from .repositories.office_repository import OfficeRepository
    from .repositories.volunteer_repository import VolunteerRepository

    orepo = OfficeRepository(db)
    vrepo = VolunteerRepository(db)

    # Create Oslo office
    oslo = Office(id=None, name="Oslo", currency="NOK", monthly_budget_minor=600000, timezone="Europe/Oslo")
    orepo.create(oslo)

    # Create Bengaluru office
    bengaluru = Office(id=None, name="Bengaluru", currency="INR", monthly_budget_minor=1500000, timezone="Asia/Kolkata")
    orepo.create(bengaluru)

    # Create volunteers for Oslo (about 15)
    oslo_volunteers = []
    for i in range(1, 16):
        vol = Volunteer(
            id=None,
            employee_id=f"oslo_{i:03d}",
            name=f"Oslo Volunteer {i}",
            home_office_id=oslo.id,
            payroll_currency="NOK",
        )
        oslo_volunteers.append(vrepo.create(vol))

    # Create volunteers for Bengaluru (about 20)
    bengaluru_volunteers = []
    for i in range(1, 21):
        vol = Volunteer(
            id=None,
            employee_id=f"bengaluru_{i:03d}",
            name=f"Bengaluru Volunteer {i}",
            home_office_id=bengaluru.id,
            payroll_currency="INR",
        )
        bengaluru_volunteers.append(vrepo.create(vol))

    # Create snack boxes for each office (a few per office)
    snack_boxes = []
    for i in range(3):
        # Oslo snack boxes
        box = None  # Will create below
        snack_boxes.append(box)

    # Create 3 empty snack boxes for Oslo
    for i in range(3):
        box = None
        from .repositories.snack_box_repository import SnackBoxRepository
        srepo = SnackBoxRepository(db)
        box = SnackBox(id=None, office_id=oslo.id, name=f"Snack Box Oslo {i+1}", status="EMPTY")
        srepo.create(box)

    # Create 3 empty snack boxes for Bengaluru
    for i in range(3):
        from .repositories.snack_box_repository import SnackBoxRepository
        srepo = SnackBoxRepository(db)
        box = SnackBox(id=None, office_id=bengaluru.id, name=f"Snack Box Bengaluru {i+1}", status="EMPTY")
        srepo.create(box)

    print("Demo data seeded.")


def run_demo(db: Database, chat: ChatSimulator) -> None:
    """Run the complete end-to-end demo workflow."""
    from .repositories.snack_box_repository import SnackBoxRepository
    from .repositories.refill_repository import RefillRepository
    from .repositories.purchase_repository import PurchaseRepository
    from .repositories.reimbursement_repository import ReimbursementRepository

    print("=" * 60)
    print("FRAMSIKT SNACK COUNTER AUTOMATION - END-TO-END DEMO")
    print("=" * 60)

    # Initialize services
    clock = RealClock()
    refill_service = RefillService(db, chat=chat)
    volunteer_service = VolunteerService(db, clock)
    budget_service = BudgetService(db, clock)
    hr_simulator = HRSimulator()
    reimbursement_service = ReimbursementService(db, clock, hr_adapter=hr_simulator)
    reporting_service = ReportingService(db, clock)

    # Step 1: Mark a box empty (Oslo Snack Box 1)
    print("\n--- Step 1: Report empty box ---")
    snack_box_repo = SnackBoxRepository(db)
    refill_repo = RefillRepository(db)
    purchase_repo = PurchaseRepository(db)
    reimbursement_repo = ReimbursementRepository(db)

    # Get the first Oslo snack box
    oslo_box = snack_box_repo.get_by_office(oslo_id=db.get_office("Oslo").id)
    # Actually let's just get the first one
    oslo_box = snack_box_repo.get_all()[0]  # First box

    print(f"Reporting snack box {oslo_box.id} as empty...")
    refill = refill_service.report_empty_box(snack_box_id=oslo_box.id)
    print(f"  Refill created: {refill.id}, status: {refill.status}")

    # Step 2: Create and assign a refill
    print("\n--- Step 2: Assign refill ---")
    now = datetime.now()
    volunteer_service = VolunteerService(db, clock)
    eligible = volunteer_service.get_eligible_volunteers(
        office_id=oslo_box.office_id, now=now
    )
    if eligible:
        volunteer = db.get_volunteer_by_employee_id(eligible[0])
        print(f"  Eligible volunteer: {volunteer.name} ({volunteer.employee_id})")
        assigned = refill_service.assign_refill(refill.id, volunteer.id, now=now)
        print(f"  Refill assigned to: {volunteer.name}")
    else:
        print("  No eligible volunteers available!")

    # Step 3: Accept the assignment
    print("\n--- Step 3: Accept assignment ---")
    if eligible:
        # Accept the refill
        accepted = refill_service.accept_refill(refill.id, volunteer.id, now=now)
        print(f"  Refill accepted. Status: {accepted.status}")

    # Step 4: Submit a purchase
    print("\n--- Step 4: Submit purchase ---")
    # Try to reserve budget first
    print("  Reserving budget...")
    try:
        budget_month = now.strftime("%Y-%m")
        reserve = budget_service.reserve_budget(
            office_id=oslo_box.office_id,
            refill_id=refill.id,
            amount_minor=50000,  # 500 NOK in minor units
            currency="NOK",
            budget_month=budget_month,
        )
        print(f"  Budget reserved: {reserve.reserved_amount_minor} {reserve.currency}")

        # Submit purchase
        print("  Submitting purchase...")
        purchase = purchase_repo.create(
            refill_id=refill.id,
            volunteer_id=volunteer.id,
            office_id=oslo_box.office_id,
            amount_minor=50000,
            currency="NOK",
            description="Snacks for the week: chips, fruit, coffee",
            receipt_reference="/receipts/oslo_volunteer1_20261101.pdf",
        )
        print(f"  Purchase created: {purchase.id}, amount: {purchase.amount_minor} {purchase.currency}")

        # Reconcile reservation
        print("  Reconciling budget reservation...")
        budget_service.reconcile_reservation(reservation.id, actual_amount_minor=50000)

        # Submit to HR
        print("  Submitting HR claim...")
        claim_result = reimbursement_service.submit_claim(
            purchase_id=purchase.id,
            employee_id=volunteer.employee_id,
            amount_minor=50000,
            currency="NOK",
            description="Snacks for the week: chips, fruit, coffee",
            receipt_reference="/receipts/oslo_volunteer1_20261101.pdf",
            idempotency_key=f"claim_{refill.id}_{volunteer.id}",
        )
        print(f"  HR claim submitted: {claim_result['external_claim_id']}, status: {claim_result['status']}")

    except BudgetExceededError as e:
        print(f"  Budget error: {e}")
    except CrossCurrencyError as e:
        print(f"  Cross-currency error: {e}")

    # Step 5: Simulate HR approval
    print("\n--- Step 5: Simulate HR approval ---")
    # Get the claim we just submitted
    external_claim_id = claim_result["external_claim_id"]
    approved = reimbursement_service.approve_claim(external_claim_id, now=now)
    print(f"  Claim approved. Reimbursement status: {approved.status}")

    # Step 6: Generate monthly report
    print("\n--- Step 6: Monthly report ---")
    month = now.strftime("%Y-%m")
    report = reporting_service.generate_monthly_report(month=month)
    print(f"\nMonthly report for {month}:")
    for office_report in report["offices"]:
        print(f"\n  {office_report['office_name']}")
        print(f"    Currency: {office_report['currency']}")
        print(f"    Budget: {office_report['budget']}")
        print(f"    Actual spend: {office_report['actual_spend']}")
        print(f"    Pending commitments: {office_report['pending_commitments']}")
        print(f"    Remaining: {office_report['remaining_budget']}")
        print(f"    Completed refills: {office_report['completed_refills']}")
        print(f"    Pending claims: {office_report['pending_claims']}")
        print(f"    Approved claims: {office_report['approved_claims']}")
        print(f"    Rejected claims: {office_report['rejected_claims']}")

    # Print cross-currency disclaimer
    print(f"\n  Note: NOK and INR totals are reported separately (no FX conversion by default)")

    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)


def cmd_initdb(args: argparse.Namespace) -> None:
    """Handle init-db command."""
    db = Database(":memory:")
    chat = ChatSimulator()
    init_db(db)
    print("Database initialized in memory.")


def cmd_seed(args: argparse.Namespace) -> None:
    """Handle seed-demo command."""
    db = Database(":memory:")
    chat = ChatSimulator()
    seed_demo(db, chat)
    print("Demo data seeded.")


def cmd_report(args: argparse.Namespace) -> None:
    """Handle report command."""
    db = Database(":memory:")
    chat = ChatSimulator()
    # Seed minimal data for report demo
    from .repositories.office_repository import OfficeRepository
    from .repositories.volunteer_repository import VolunteerRepository
    from .repositories.snack_box_repository import SnackBoxRepository
    from datetime import datetime

    orepo = OfficeRepository(db)
    vrepo = VolunteerRepository(db)

    # Create offices
    oslo = Office(id=None, name="Oslo", currency="NOK", monthly_budget_minor=600000, timezone="Europe/Oslo")
    orepo.create(oslo)
    bengaluru = Office(id=None, name="Bengaluru", currency="INR", monthly_budget_minor=1500000, timezone="Asia/Kolkata")
    orepo.create(bengaluru)

    # Create volunteers
    for i in range(1, 4):
        vol = Volunteer(id=None, employee_id=f"oslo_{i:03d}", name=f"Oslo Volunteer {i}",
                        home_office_id=oslo.id, payroll_currency="NOK")
        vrepo.create(vol)
        vol = Volunteer(id=None, employee_id=f"bengaluru_{i:03d}", name=f"Bengaluru Volunteer {i}",
                        home_office_id=bengaluru.id, payroll_currency="INR")
        vrepo.create(vol)

    # Create snack boxes
    for i in range(3):
        box = SnackBox(id=None, office_id=oslo.id, name=f"Oslo Box {i+1}", status="EMPTY")
        # Can't easily create without repo, skipping for now

    # Generate report
    reporting_service = ReportingService(db, RealClock())
    report = reporting_service.generate_monthly_report(month=args.month)
    print(f"\nMonthly report for {args.month}:")
    for office_report in report["offices"]:
        print(f"\n  {office_report['office_name']}")
        print(f"    Currency: {office_report['currency']}")
        print(f"    Budget: {office_report['budget']}")
        print(f"    Actual spend: {office_report['actual_spend']}")
        print(f"    Pending commitments: {office_report['pending_commitments']}")
        print(f"    Remaining: {office_report['remaining_budget']}")


def main() -> None:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Framsikt Snack Counter Automation"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init-db command
    init_parser = subparsers.add_parser("init-db", help="Initialize the database")
    init_parser.set_defaults(func=cmd_initdb)

    # seed-demo command
    seed_parser = subparsers.add_parser("seed-demo", help="Seed demo data")
    seed_parser.set_defaults(func=cmd_seed)

    # report command
    report_parser = subparsers.add_parser("report", help="Generate monthly report")
    report_parser.add_argument("--month", default=datetime.now().strftime("%Y-%m"),
                               help="Month in YYYY-MM format")
    report_parser.set_defaults(func=cmd_report)

    # demo command
    demo_parser = subparsers.add_parser("demo", help="Run end-to-end demo")
    demo_parser.set_defaults(func=lambda args: run_demo(Database(":memory:"), ChatSimulator()))

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()