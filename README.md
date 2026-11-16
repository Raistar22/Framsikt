# Framsikt Snack Counter Automation

## Project Summary

A backend application that coordinates snack counter refills and tracks reimbursements
for Framsikt's two offices (Oslo and Bengaluru). Volunteers who notice an empty snack
box report it, the system assigns the refill to an eligible volunteer fairly, the volunteer
purchases snacks, and the system tracks reimbursement claims through a simulated HR system.

## Features

- **Refill lifecycle:** Empty box → refill request → assigned → accepted → purchased → HR claim pending → reimbursed
- **Volunteer fairness:** Deterministic selection based on fewest completed refills, oldest assignment, stable ID
- **Budget management:** Office-specific monthly budgets (Oslo: 6,000 NOK, Bengaluru: 15,000 INR) with atomic reservations and reconciliation
- **HR simulation:** Idempotent claim submission, approval/rejection tracking, budget commitment management
- **Monthly reporting:** Office-level totals in native currencies (NOK/INR reported separately, no automatic FX conversion)
- **Chat simulator:** Records notifications that would be sent to the internal chat tool
- **Concurrency safety:** Database-level atomicity and constraints prevent race conditions

## Architecture

```
CLI / Demo
   |
   v
Application Services
   |-- RefillService: refill lifecycle management
   |-- VolunteerService: eligibility and fairness-based assignment
   |-- BudgetService: budget accounting and reservations
   |-- ReimbursementService: HR claim management
   |-- ReportingService: monthly reports
   |
   v
Domain Models (Office, Volunteer, SnackBox, Refill, Purchase, BudgetReservation, Reimbursement, AuditEvent)
   |
   v
Repositories / SQLite Transaction Boundary
   |
   v
Adapters
   |-- ChatSimulator: records chat notifications
   |-- HRSimulator: fake external HR system
   |-- Clock: injectable time source
```

## Requirements

- Python 3.11+
- No external dependencies (SQLite built-in)

## Installation

```bash
# Clone and enter the directory
git clone <repository-url>
cd snack-counter-automation

# Install the package
pip install -e .

# Or install dependencies directly
pip install -r requirements.txt
```

## Database Initialization

```bash
# Initialize the database (creates tables with schema)
python -m app.cli init-db

# Or create the tables directly:
python -c "from app.db import Database; db = Database(); db.close()"
```

## Demo Instructions

```bash
# Initialize database
python -m app.cli init-db

# Seed demo data (offices, volunteers, snack boxes)
python -m app.cli seed-demo

# Run the end-to-end demo
python -m app.cli demo
```

The demo flows through the complete workflow:
1. Initialize the database
2. Seed Oslo and Bengaluru with budgets, volunteers, and snack boxes
3. Mark a box as empty (creates a refill request)
4. Eligible volunteer is assigned the refill
5. Volunteer accepts the assignment
6. Volunteer submits a purchase with receipt reference
7. Budget is reserved and reconciled
8. HR claim is submitted to the HR simulator
9. HR approval is simulated
10. Final refill status and monthly report are printed

## Test Instructions

```bash
# Run the test suite
pytest -q

# Run with verbose output
pytest -v
```

## Example Report

```text
Monthly report — 2026-11

Oslo
  Currency: NOK
  Budget: 6,000.00
  Actual spend: 2,400.00
  Pending commitments: 600.00
  Remaining: 3,000.00

Bengaluru
  Currency: INR
  Budget: 15,000.00
  Actual spend: 8,500.00
  Pending commitments: 1,500.00
  Remaining: 5,000.00

Note: NOK and INR totals are not added together.
```

## Assumptions and Limitations

- **Assignment deadline:** Default 96 hours (configurable). After expiry, the assignment is released and the next eligible volunteer is tried.
- **Volunteer fairness:** Fewest completed refills in rolling 30-day period; tie-broken by oldest last-assigned timestamp, then stable volunteer ID.
- **Availability:** Maintained explicitly by volunteer or administrator. Not inferred from hybrid work patterns.
- **One active assignment per volunteer:** A volunteer can have at most one active refill assignment at a time.
- **One active refill per snack box:** Only one refill request can be active for a given snack box.
- **Cross-currency:** By default, cross-currency purchases are rejected. A configured reimbursement policy would be needed to support them.
- **No FX conversion by default:** NOK and INR totals are reported separately. If an exchange rate is supplied, show the rate, base currency, conversion timestamp/source, and converted total separately.
- **Budget month:** Based on the office's local calendar month. Event timestamps stored in UTC and converted to office-local dates when determining the reporting month.
- **Pending HR claims count as committed spending:** Do not make budget appear available merely because HR approval is delayed.
- **Single-process/local application:** Backed by SQLite. Production multi-instance deployment would use a server database and stronger operational controls.

## Important Invariants

- Only one active refill per snack box
- Only one active assignment per volunteer
- Budget reservations are atomic and cannot overspend the monthly budget
- HR claim submission is idempotent (same idempotency key returns same claim)
- Pending HR claims count as committed budget (not re-released until rejection)
- NOK and INR are reported separately (no automatic FX conversion)
- Timestamps stored in UTC, converted to local dates for reporting

## Production Improvements

- Replace ChatSimulator with real internal chat API integration
- Replace HRSimulator with real payroll/HR system connection
- Add FX conversion with configurable exchange rates
- Migrate from SQLite to production server database (PostgreSQL/MySQL)
- Add connection pooling and migration tools (Alembic/Flask-Migrate)
- Add authentication and authorization
- Add frontend web interface
- Add inventory tracking and snack level monitoring
- Add audit trail and compliance reporting
- Add scheduled expiry processing worker
- Add multi-instance deployment with distributed lock management

## Commands Summary

```bash
# Initialize database
python -m app.cli init-db

# Seed demo data
python -m app.cli seed-demo

# Run end-to-end demo
python -m app.cli demo

# Generate monthly report
python -m app.cli report --month 2026-11

# Run tests
pytest -q

# Full end-to-end installation
pip install -e .
```