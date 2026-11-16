from app import db, clock, models
from app.repositories.office_repository import OfficeRepository
from app.repositories.volunteer_repository import VolunteerRepository
from app.repositories.snack_box_repository import SnackBoxRepository
from app.services.refill_service import RefillService
from app.services.volunteer_service import VolunteerService
from app.adapters.chat_simulator import ChatSimulator

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

# Test refill service
chat = ChatSimulator()
refill_service = RefillService(database, clock.RealClock(), chat_adapter=chat)

# Report empty box with error handling
try:
    refill = refill_service.report_empty_box(1)
    print(f'Refill created: {refill.id}, status: {refill.status}')
except Exception as e:
    print(f'Error reporting empty box: {type(e).__name__}: {e}')

# Test volunteer selection
vol_service = VolunteerService(database, clock.RealClock())
now = clock.RealClock().now()
eligible = vol_service.get_eligible_volunteers(oslo.id, now=now)
print(f'Eligible volunteers: {len(eligible)}')
if eligible:
    print(f'Most eligible: {eligible[0].name} ({eligible[0].employee_id})')

# Assign refill
try:
    assigned = refill_service.assign_refill(refill.id, eligible[0].id, now=now)
    print(f'Refill assigned to: {eligible[0].name}')
    print(f'Refill status: {assigned.status}')
except Exception as e:
    print(f'Error assigning refill: {type(e).__name__}: {e}')

# Accept refill
try:
    accepted = refill_service.accept_refill(refill.id, eligible[0].id, now=now)
    print(f'Refill accepted. Status: {accepted.status}')
except Exception as e:
    print(f'Error accepting refill: {type(e).__name__}: {e}')

print('\nTest complete!')