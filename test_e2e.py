from app import db, clock, models
from app.repositories.office_repository import OfficeRepository
from app.repositories.volunteer_repository import VolunteerRepository
from app.repositories.snack_box_repository import SnackBoxRepository
from app.repositories.purchase_repository import PurchaseRepository
from app.repositories.budget_repository import BudgetRepository
from app.repositories.reimbursement_repository import ReimbursementRepository
from app.repositories.audit_repository import AuditRepository
from app.services.refill_service import RefillService
from app.services.volunteer_service import VolunteerService
from app.services.budget_service import BudgetService
from app.services.reimbursement_service import ReimbursementService
from app.services.reporting_service import ReportingService
from app.adapters.chat_simulator import ChatSimulator
from app.adapters.hr_simulator import HRSimulator
from app.repositories.refill_repository import RefillRepository

print("=" * 60)
print("FULL END-TO-END TEST")
print("=" * 60)

# Create in-memory database
database = db.Database(':memory:')

# Create offices
orepo = OfficeRepository(database)
oslo = models.Office(id=1, name='Oslo', currency='NOK', monthly_budget_minor=600000, timezone='Europe/Oslo')
orepo.create(oslo)
bengaluru = models.Office(id=2, name='Bengaluru', currency='INR', monthly_budget_minor=1500000, timezone='Asia/Kolkata')
orepo.create(bengaluru)

# Create volunteers
vrepo = VolunteerRepository(database)
for i in range(1, 4):
    v = models.Volunteer(id=i, employee_id=f'oslo_{i:03d}', name=f'Oslo Volunteer {i}', home_office_id=oslo.id, payroll_currency='NOK')
    vrepo.create(v.employee_id, v.name, v.home_office_id, v.payroll_currency)
for i in range(1, 4):
    v = models.Volunteer(id=i+10, employee_id=f'bengaluru_{i:03d}', name=f'Bengaluru Volunteer {i}', home_office_id=bengaluru.id, payroll_currency='INR')
    vrepo.create(v.employee_id, v.name, v.home_office_id, v.payroll_currency)

# Create chat and HR simulator
chat = ChatSimulator()
hr_simulator = HRSimulator()

# Create services
refill_service = RefillService(database, clock.RealClock(), chat_adapter=chat)
vol_service = VolunteerService(database, clock.RealClock())
budget_service = BudgetService(database, clock.RealClock())
reimbursement_service = ReimbursementService(database, clock.RealClock(), hr_adapter=hr_simulator)
reporting_service = ReportingService(database, clock.RealClock())

# ========== TEST 1: Report empty box and assign refill ==========
print("\n--- TEST 1: Report empty box and assign refill ---")
refill = refill_service.report_empty_box(1)
print(f"Refill created: {refill.id}, status: {refill.status}")

# Assign refill to eligible volunteer
now = clock.RealClock().now()
eligible = vol_service.get_eligible_volunteers(oslo.id, now=now)
print(f"Eligible volunteers: {len(eligible)}")
if eligible:
    assigned = refill_service.assign_refill(refill.id, eligible[0].id, now=now)
    print(f"Refill assigned to: {assigned.assigned_volunteer_id}, status: {assigned.status}")

# ========== TEST 2: Accept refill and submit purchase ==========
print("\n--- TEST 2: Accept refill and submit purchase ---")
if eligible:
    accepted = refill_service.accept_refill(refill.id, eligible[0].id, now=now)
    print(f"Refill accepted, status: {accepted.status}")
    
    # Submit purchase
    purchase = PurchaseRepository(database).create(
        refill_id=refill.id,
        volunteer_id=eligible[0].id,
        office_id=oslo.id,
        amount_minor=50000,
        currency="NOK",
        description="Snacks for the week",
        receipt_reference="/receipts/oslo_1_20261101.pdf",
    )
    print(f"Purchase submitted: {purchase.id}, amount: {purchase.amount_minor} {purchase.currency}")
    
    # Reserve budget
    budget_month = now.strftime("%Y-%m")
    try:
        reserve = budget_service.reserve_budget(
            office_id=oslo.id,
            refill_id=refill.id,
            amount_minor=50000,
            currency="NOK",
            budget_month=budget_month,
        )
        print(f"Budget reserved: {reserve.reserved_amount_minor} {reserve.currency}, status: {reserve.status}")
    except Exception as e:
        print(f"Budget reservation error: {e}")
    
    # Reconcile reservation
    reservation = BudgetRepository(database).get_by_refill_id(refill.id)
    if reservation:
        BudgetService(database, clock.RealClock()).reconcile_reservation(reservation.id, actual_amount_minor=50000)
        print(f"Budget reconciled: status={reservation.status}")
    
    # Submit HR claim
    claim_result = reimbursement_service.submit_claim(
        purchase_id=purchase.id,
        employee_id=eligible[0].employee_id,
        amount_minor=50000,
        currency="NOK",
        description="Snacks for the week",
        receipt_reference="/receipts/oslo_1_20261101.pdf",
        idempotency_key=f"claim_{refill.id}_{eligible[0].id}",
    )
    print(f"HR claim submitted: {claim_result['external_claim_id']}, status: {claim_result['status']}")

# ========== TEST 5: HR approval ==========
print("\n--- TEST 5: HR approval ---")
external_claim_id = claim_result["external_claim_id"]
approved = reimbursement_service.approve_claim(external_claim_id, now=now)
print(f"Claim approved, reimbursement status: {approved.status}")

# Check refill status
refill_check = RefillRepository(database).get_by_id(refill.id)
print(f"Refill status after HR approval: {refill_check.status}")

# ========== TEST 6: Monthly report ==========
print("\n--- TEST 6: Monthly report ---")
month = now.strftime("%Y-%m")
report = reporting_service.generate_monthly_report(month)
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

print(f"\nNOK total: {report['nok_total']}")
print(f"INR total: {report['inr_total']}")
print(f"\nNote: NOK and INR are reported separately (no FX conversion by default)")

print("\n" + "=" * 60)
print("ALL TESTS COMPLETE")
print("=" * 60)