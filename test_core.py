from app import db, clock, models
from app.repositories.office_repository import OfficeRepository
from app.repositories.volunteer_repository import VolunteerRepository
from app.repositories.snack_box_repository import SnackBoxRepository
from app.services.refill_service import RefillService
from app.services.volunteer_service import VolunteerService
from app.adapters.chat_simulator import ChatSimulator
from app.adapters.hr_simulator import HRSimulator

print("=" * 60)
print("CORE REFILL LIFECYCLE TEST")
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

# Create snack box
srepo = SnackBoxRepository(database)
box = models.SnackBox(id=1, office_id=oslo.id, name='Test Box', status='EMPTY')
srepo.create(box)

# Create chat and HR simulator
chat = ChatSimulator()
hr_simulator = HRSimulator()

# Create services
refill_service = RefillService(database, clock.RealClock(), chat_adapter=chat)
vol_service = VolunteerService(database, clock.RealClock())

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

# Accept refill
if eligible:
    accepted = refill_service.accept_refill(refill.id, eligible[0].id, now=now)
    print(f"Refill accepted, status: {accepted.status}")

# ========== TEST 3: Verify refill status ==========
print("\n--- TEST 3: Verify refill status ---")
from app.repositories.refill_repository import RefillRepository
rrepo = RefillRepository(database)
refill_check = rrepo.get_by_id(refill.id)
print(f"Refill status after accept: {refill_check.status}")

# ========== TEST 4: HR claim submission and approval ==========
print("\n--- TEST 4: HR claim submission and approval ---")
# Submit claim to HR simulator
claim = hr_simulator.submit_claim(
    employee_id=eligible[0].employee_id,
    amount_minor=50000,
    currency="NOK",
    description="Snacks for the week",
    receipt_reference="/receipts/oslo_1_20261101.pdf",
    idempotency_key=f"claim_{refill.id}_{eligible[0].id}",
)
print(f"HR claim submitted: {claim.external_claim_id}, status: {claim.status}")

# Approve claim
approved = hr_simulator.approve_claim(claim.external_claim_id)
print(f"HR claim approved: {approved.status}")

# ========== TEST 5: Verify offices and budgets ==========
print("\n--- TEST 4: Verify offices and budgets ---")
orepo2 = OfficeRepository(database)
offices = orepo2.get_all()
for office in offices:
    print(f"  {office.name}: Budget={office.monthly_budget_minor}, Currency={office.currency}")

print("\n" + "=" * 60)
print("ALL TESTS COMPLETE")
print("=" * 60)