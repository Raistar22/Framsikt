"""Demo script: Complete refill lifecycle workflow for Framsikt Snack Counter."""

from __future__ import annotations

from datetime import datetime

from app import db
from app.repositories.office_repository import OfficeRepository
from app.repositories.volunteer_repository import VolunteerRepository
from app.repositories.snack_box_repository import SnackBoxRepository
from app.repositories.refill_repository import RefillRepository
from app.repositories.purchase_repository import PurchaseRepository
from app.services.refill_service import RefillService
from app.services.volunteer_service import VolunteerService
from app.services.budget_service import BudgetService
from app.services.reimbursement_service import ReimbursementService
from app.services.reporting_service import ReportingService
from app.adapters.chat_simulator import ChatSimulator
from app.adapters.hr_simulator import HRSimulator
from app.models import Office, Volunteer, SnackBox
from app.clock import RealClock


def main():
    """Demonstrate the complete refill lifecycle workflow."""
    print("=" * 60)
    print("FRAMSIKT SNACK COUNTER AUTOMATION - COMPLETE WORKFLOW")
    print("=" * 60)

    # Create in-memory database
    database = db.Database(":memory:")
    clock = RealClock()

    # === Create offices ===
    orepo = OfficeRepository(database)
    oslo_office = Office(id=1, name="Oslo", currency="NOK", monthly_budget_minor=600000, timezone="Europe/Oslo")
    orepo.create(oslo_office)
    bengaluru_office = Office(id=2, name="Bengaluru", currency="INR", monthly_budget_minor=1500000, timezone="Asia/Kolkata")
    orepo.create(bengaluru_office)

    # === Create volunteers ===
    vrepo = VolunteerRepository(database)
    for i in range(1, 4):
        v = Volunteer(id=i, employee_id=f"oslo_{i:03d}", name=f"Oslo Volunteer {i}",
                      home_office_id=1, payroll_currency="NOK")
        vrepo.create(v.employee_id, v.name, v.home_office_id, v.payroll_currency)
    for i in range(1, 4):
        v = Volunteer(id=i + 10, employee_id=f"bengaluru_{i:03d}", name=f"Bengaluru Volunteer {i}",
                      home_office_id=2, payroll_currency="INR")
        vrepo.create(v.employee_id, v.name, v.home_office_id, v.payroll_currency)

    # === Create snack box ===
    srepo = SnackBoxRepository(database)
    box = SnackBox(id=1, office_id=1, name="Snack Box Oslo 1", status="EMPTY")
    srepo.create(box)

    # === Create chat and HR simulator ===
    chat = ChatSimulator()
    hr_simulator = HRSimulator()

    # === Create services ===
    refill_service = RefillService(database, clock, chat_adapter=chat)
    vol_service = VolunteerService(database, clock)
    budget_service = BudgetService(database, clock)
    reimbursement_service = ReimbursementService(database, clock, hr_adapter=hr_simulator)

    now = clock.now()

    # --- Step 1: Report empty box ---
    print("\n--- Step 1: Report empty box ---")
    refill = refill_service.report_empty_box(snack_box_id=1)
    print(f"  Refill created: {refill.id}, status: {refill.status}")

    # --- Step 2: Volunteer selection ---
    print("\n--- Step 2: Volunteer selection ---")
    eligible = vol_service.get_eligible_volunteers(office_id=1, now=now)
    print(f"  Eligible volunteers: {len(eligible)}")
    if eligible:
        print(f"  Most eligible: {eligible[0].name} ({eligible[0].employee_id})")

    # --- Step 3: Assign refill ---
    print("\n--- Step 3: Assign refill ---")
    if eligible:
        volunteer = eligible[0]
        assigned = refill_service.assign_refill(refill.id, volunteer.id, now=now)
        print(f"  Refill assigned to: {volunteer.name} ({volunteer.employee_id})")
        print(f"  Refill status: {assigned.status}")
        print(f"  Assignment expires at: {assigned.assignment_expires_at}")

    # --- Step 4: Accept assignment ---
    print("\n--- Step 4: Accept assignment ---")
    if eligible:
        volunteer = eligible[0]
        accepted = refill_service.accept_refill(refill.id, volunteer.id, now=now)
        print(f"  Refill accepted. Status: {accepted.status}")

    # --- Step 5: Submit purchase ---
    print("\n--- Step 5: Submit purchase ---")
    purchase = PurchaseRepository(database).create(
        refill_id=refill.id,
        volunteer_id=volunteer.id,
        office_id=1,
        amount_minor=50000,  # 500 NOK
        currency="NOK",
        description="Snacks for the week: chips, fruit, coffee",
        receipt_reference="/receipts/oslo_volunteer1_20261101.pdf",
    )
    print(f"  Purchase created: {purchase.id}, amount: {purchase.amount_minor} {purchase.currency}")

    # --- Budget validation ---
    print("\n--- Step 5b: Budget validation ---")
    office = orepo.get_by_id(1)
    available = budget_service.calculate_available_budget(office_id=1, month="2026-11", now=now)
    print(f"  Oslo monthly budget: {office.monthly_budget_minor} {office.currency}")
    print(f"  Available budget: {available} {office.currency}")
    if 50000 <= available:
        print(f"  OK Budget sufficient for 50000 NOK purchase")
    else:
        print(f"  ! Budget insufficient: need 50000, have {available}")

    # --- Step 6: Submit HR claim ---
    print("\n--- Step 6: Submit HR claim ---")
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

    # --- Step 7: Monthly report (shows reimbursement state) ---
    print("\n--- Step 7: Monthly report ---")
    month = now.strftime("%Y-%m")
    reporting_service = ReportingService(database, clock)
    report = reporting_service.generate_monthly_report(month=month)
    print(f"\n  Monthly report for {month}:")
    for office_report in report["offices"]:
        print(f"    {office_report['office_name']}:")
        print(f"      Currency: {office_report['currency']}")
        print(f"      Budget: {office_report['budget']}")
        print(f"      Actual spend: {office_report['actual_spend']}")
        print(f"      Pending commitments: {office_report['pending_commitments']}")
        print(f"      Remaining: {office_report['remaining_budget']}")
        print(f"      Completed refills: {office_report['completed_refills']}")
        print(f"      Pending claims: {office_report['pending_claims']}")
        print(f"      Approved claims: {office_report['approved_claims']}")
        print(f"      Rejected claims: {office_report['rejected_claims']}")

    print(f"\n  NOK total: {report['nok_total']}")
    print(f"  INR total: {report['inr_total']}")
    print(f"  (Note: NOK and INR reported separately, no FX conversion)")

    # --- Step 8: Refill status ---
    print("\n--- Step 8: Refill status ---")
    refill_check = RefillRepository(database).get_by_id(refill.id)
    print(f"  Refill status: {refill_check.status}")
    if refill_check.status == "REIMBURSED":
        print(f"  ✓ Refill fully reimbursed - lifecycle complete")
    else:
        print(f"  ! Refill awaiting HR approval")

    print("\n" + "=" * 60)
    print("WORKFLOW COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()