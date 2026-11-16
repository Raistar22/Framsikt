# Framsikt Snack Counter Automation - Design Document

## 1. Refill Lifecycle

The refill workflow follows a deterministic state machine with 7 states and explicit transitions:

| State | Description | Valid Outbound Transitions |
|---|---|---|
| **OPEN** | Empty box reported, awaiting assignment | ASSIGNED, CANCELLED |
| **ASSIGNED** | Volunteer assigned, 96-hour expiry clock running | ACCEPTED, OPEN, CANCELLED |
| **ACCEPTED** | Volunteer accepted assignment, proceeding to purchase | PURCHASED |
| **PURCHASED** | Purchase submitted with receipt | CLAIM_SUBMITTED |
| **CLAIM_SUBMITTED** | HR reimbursement claim submitted | REIMBURSED, PURCHASED, CANCELLED |
| **REIMBURSED** | Claim approved, lifecycle complete | — |
| **CANCELLED** | Box not refilled, volunteer declined/expired | — |

### Key transitions and mechanisms:

- **Empty snack box** → `report_empty_box(snack_box_id)` creates an OPEN refill with an idempotency key. Duplicate detection prevents multiple refill requests for the same box.

- **Volunteer selection and assignment** → `assign_refill(refill_id, volunteer_id)` validates the refill is OPEN, sets status to ASSIGNED, records `assignment_expires_at` (96 hours from now via `Clock`), and increments `assignment_attempt`. A chat notification is sent. Only one active refill per snack box is allowed (enforced by `RefillRepository.get_active_by_snack_box()` and application logic).

- **Assignment expiry** → `expire_overdue_assignments()` releases expired ASSIGNED refills back to OPEN, audits the EXPIRED event, and triggers reassignment by fetching eligible volunteers via `VolunteerService.get_eligible_volunteers()` (sorted by fewest rolling 30-day reimbursed refills → oldest `last_assigned_at` → stable ID). The displaced volunteer's assignment is lost; they must re-qualify.

- **Purchase and receipt submission** → Volunteer submits a `Purchase` with `receipt_reference`. `BudgetService.reserve_budget()` atomically reserves funds within a transaction, raising `BudgetExceededError` if the office's remaining budget (monthly_budget - reconciled_spend - active_reservations) is insufficient. The reservation links `office_id`, `refill_id`, and `amount_minor`. `PurchaseRepository.get_reconciled_spend()` only counts purchases with a `receipt_reference` where the associated refill is REIMBURSED.

- **Budget validation** → Budget is checked atomically at reservation time. `calculate_available_budget()` computes `monthly_budget - reconciled_spend - active_reservations`. Cross-currency purchases are rejected by default (`CrossCurrencyError` unless office currency matches).

- **HR reimbursement claim submission** → `ReimbursementService.submit_claim()` is idempotent (same `idempotency_key` returns existing claim). A `Reimbursement` record is created with status NOT_SUBMITTED, then updated to PENDING after the HR simulator processes the claim. The claim includes `external_claim_id`, `amount_minor`, `currency`, `description`, and `receipt_reference`.

- **Reimbursement approval and completion** → `ReimbursementService.approve_claim()` updates the reimbursement to APPROVED, sets `resolved_at`, and transitions the associated refill to REIMBURSED (final state). The `BudgetService.reconcile_reservation()` marks the budget reservation as RECONCILED if `actual_amount_minor <= reserved_amount_minor`, releasing the unused portion.

## 2. Main Components and Data

| Component | Data Store / Management |
|---|---|
| **Core application / business logic** | 5 services (`RefillService`, `VolunteerService`, `BudgetService`, `ReimbursementService`, `ReportingService`) orchestrating repository operations with `Clock` injection for time independence. |
| **Database and persistence layer** | SQLite with WAL mode, foreign keys enabled, 5s busy_timeout. 9 tables: `offices`, `volunteers`, `volunteer_office_eligibility`, `snack_boxes`, `refills`, `purchases`, `budget_reservations`, `reimbursements`, `audit_events`. All monetary values stored as integer "minor units" (øre/paise) to avoid floating-point errors. |
| **Volunteer management** | `VolunteerService.is_eligible()` checks: (1) `available=True`, (2) assigned to office via home_office_id or valid `volunteer_office_eligibility` record (valid_from/valid_until), (3) no active ASSIGNED refills. `VolunteerService.get_eligible_volunteers()` sorts by fairness: fewest completed reimbursed refills in rolling 30 days → oldest `last_assigned_at` (null first) → stable ID. Only *reimbursed* refills count toward the fairness score. |
| **Budget management** | `BudgetService.calculate_available_budget()`: `monthly_budget_minor - reconciled_spend - active_reservations`. `reserve_budget()` atomically reserves within a transaction, raising `BudgetExceededError` if insufficient. `reconcile_reservation()` updates with actual purchase amount and marks RECONCILED if actual ≤ reserved. Reservations remain RESERVED until reconciliation; pending HR claims do not release budget commitments. |
| **Chat integration / simulator** | `ChatSimulator` records direct and office messages sent via `RefillService` and `ReimbursementService`. Messages include assignment notifications, decline notifications, and claim status updates. In production, would integrate with an actual chat platform (Slack, Teams). |
| **HR integration / simulator** | `HRSimulator` simulates external HR system: `submit_claim()` with idempotency, `approve_claim()`, `reject_claim()`. Claims have status PENDING/APPROVED/REJECTED. `ReimbursementService` bridges local state and the HR simulator. Idempotency keys prevent duplicate claims. |
| **Reporting** | `ReportingService.generate_monthly_report(month)` generates office-level reports with separate NOK/INR totals. Calculates: `budget` (monthly_budget_minor), `actual_spend` (sum of purchases with receipt_reference), `pending_commitments` (active RESERVED reservations), `remaining_budget`, `completed_refills` (count of APPROVED reimbursements), and claim counts (pending/approved/rejected). NOK and INR totals are maintained separately — no automatic FX conversion. |

## 3. How the System Prevents the Original Problems

| Problem | Mechanism in Code |
|---|---|
| **Empty snack boxes not getting refilled** | `expire_overdue_assignments()` automatically releases expired ASSIGNED refills back to OPEN and reassigns to the next eligible volunteer (sorted by fairness). One active refill per snack box is enforced — but if that refill expires, a new one can be created. |
| **Multiple volunteers purchasing for the same box** | DB constraint: `purchases.refill_id UNIQUE` ensures only one purchase per refill. The refill state machine ensures only one volunteer can be assigned at a time. If volunteer A declines/expires, the box returns to OPEN and gets assigned to volunteer B. |
| **Unequal distribution of refill responsibilities** | Fairness-driven volunteer selection: `get_eligible_volunteers()` counts only *reimbursed* refills in the rolling 30-day period and sorts by fewest first. Tie-breaks favor oldest `last_assigned_at` (null first) and then stable ID. One active assignment per volunteer is enforced by `VolunteerService.is_eligible()` checking `get_active_by_volunteer()`. |
| **Delayed reimbursement visibility** | `ReportingService.generate_monthly_report()` tracks reimbursement status counts (pending/approved/rejected) per office per month. `ReimbursementService.reject_claim()` releases the budget reservation on HR rejection, ensuring the budget is not locked indefinitely. Audit events track all state transitions. |
| **Monthly budget overruns** | Pre-purchase `reserve_budget()` atomically validates remaining budget before committing. `calculate_available_budget()` excludes both reconciled spend and active reservations. `BudgetExceededError` is raised if a reservation would exceed the monthly limit. Cross-currency reservations are rejected by default. |
| **Spending visibility across Oslo and Bengaluru** | `generate_monthly_report()` produces separate office reports with each office's `currency`, `budget`, `actual_spend`, and `remaining_budget`. Currency totals are aggregated separately (NOK total and INR total reported independently, no automatic conversion). Cross-currency purchases are rejected at the reservation step. |

## 4. Trade-offs

- **Database choice (SQLite)**: Chosen for zero-dependency deployment (no external server, no ORM migration). WAL mode provides concurrent read safety. Limitations: no built-in row-level locking beyond SQLite's implicit serialization; heavy concurrent workloads may experience `database is locked` errors (mitigated by 5s busy_timeout and application-level transactions). No horizontal scaling — suitable for department-level use.

- **Integration simulations**: Chat and HR are simulated adapters (`ChatSimulator`, `HRSimulator`). This enables end-to-end workflow testing and demo without external dependencies. The trade-off: production integrations (Slack API, real HR system) must be plugged in via the same adapter interfaces (`chat_adapter`, `hr_adapter` constructor parameters).

- **Concurrency handling**: SQLite transactions with `BEGIN`/`COMMIT` wrap budget reservations and reconciliations. All state-changing operations read within the transaction to avoid race conditions. The `reserve_budget()` method checks availability and inserts the reservation atomically within a single `with self._db.begin()` block. Application-level checks supplement DB constraints (one active refill per box, one active assignment per volunteer).

- **Scheduling**: Assignment expiry is driven by `expire_overdue_assignments()` called explicitly (e.g., via cron or API). The 96-hour `assignment_expires_at` threshold is computed from the injected `Clock`. No automatic scheduler is built-in — the function must be invoked periodically.

- **Currency management**: Monetary values stored as integer minor units (1 NOK = 100 øre; 1 INR = 100 paise). No automatic FX conversion — cross-currency purchases are rejected unless the currency matches the office's currency. Budget tracking is currency-specific per office. Reporting separates NOK and INR totals without summing them (acknowledged limitation: a "grand total" would be misleading without an explicit exchange rate).

## 5. What I Deliberately Did Not Build

| Excluded Feature | Reason / Scope Note |
|---|---|
| **Production chat integrations** | `ChatSimulator` records messages for demo/testing. A real Slack/Teams webhook integration would replace the simulator but the service layer (`refill_service.py` lines 36-40, 69-73, etc.) already accepts any `chat_adapter` with a `send_direct_message()` method. |
| **Real HR API integration** | `HRSimulator` stands in for the external HR system. `ReimbursementService` is constructed with `hr_adapter=None`; when None, claims are marked PENDING locally without contacting an external system. The adapter interface (`submit_claim()`, `approve_claim()`, `reject_claim()`) is designed for future integration. |
| **Frontend / UI** | This is a backend-only CLI + service architecture. All interactions go through the CLI (`cli.py`) or direct service calls. No React/FastAPI/Flask frontend is included. |
| **Advanced inventory forecasting** | Snack boxes are modeled as simply EMPTY/STOCKED with no per-item inventory, expiry tracking, or predictive restocking. The system reactively refills when a box is reported empty. |
| **Automated currency conversion** | No FX rates or conversion logic is implemented. NOK and INR are tracked and reported completely separately. A cross-currency purchase raises `CrossCurrencyError`. Any conversion would need to be added at the service or config level. |
| **Bulk / batch operations** | All operations are per-refill/snack-box. No batch assignment of multiple volunteers, bulk budget checks, or bulk report generation beyond the single-month office report. |
| **Persistent scheduling / cron** | Assignment expiry and overdue handling require explicit invocation of `expire_overdue_assignments()`. No built-in scheduler or background job queue. |
| **Volunteer onboarding / eligibility expiration** | `volunteer_office_eligibility` records exist but the seed demo creates all volunteers as home-office-eligible. No automatic expiry or renewal logic for eligibility records is implemented beyond the `valid_until` field that exists in the schema. |
| **Idempotency at the purchase level** | `purchases.refill_id UNIQUE` prevents duplicate purchases for the same refill, but there is no application-level idempotency key on purchase creation like there is on refills. |

---

**Files Inspected:**

- `app/models.py` — Domain models (Office, Volunteer, SnackBox, Refill, Purchase, BudgetReservation, Reimbursement, AuditEvent), Refill state machine (VALID_TRANSITIONS)
- `app/db.py` — SQLite database wrapper, schema (9 tables), WAL mode, foreign keys, busy_timeout
- `app/config.py` — Settings (Oslo 600,000 minor / 6,000 NOK, Bengaluru 1,500,000 minor / 15,000 INR, 96h assignment deadline, 30-day fairness rolling period)
- `app/exceptions.py` — Custom exception hierarchy (11 exceptions)
- `app/clock.py` — Injectable Clock interface (RealClock, FixedClock)
- `app/services/refill_service.py` — Refill lifecycle: report_empty_box, assign_refill, accept_refill, decline_refill, expire_overdue_assignments
- `app/services/volunteer_service.py` — Eligibility checks, fairness-based volunteer selection (rolling 30-day reimbursed count, last_assigned_at tie-break)
- `app/services/budget_service.py` — Budget calculation, atomic reservation, BudgetExceededError, reconcile_reservation
- `app/services/reimbursement_service.py` — Claim submission (idempotent), approval, rejection, budget release on rejection
- `app/services/reporting_service.py` — Monthly report generation, separate NOK/INR totals, actual_spend, pending_commitments, remaining_budget
- `app/repositories/` — 8 repository files for data access (office, volunteer, snack_box, refill, purchase, budget, reimbursement, audit, volunteer_office_eligibility)
- `app/adapters/chat_simulator.py` — Message recording for chat notifications
- `app/adapters/hr_simulator.py` — HR claim simulation with idempotency, approve/reject
- `app/cli.py` — CLI commands (init-db, seed-demo, demo, report)
- `test_core.py` — Core refill lifecycle test (reference implementation)
- `test_e2e.py` — End-to-end test (full workflow: empty box → refill → purchase → HR claim → approval → report)
- `test_basic.py` — Basic setup and flow test
- `app/repositories/refill_repository.py` — Active refill by snack box, overdue detection, reimbursed-in-period counting
- `app/repositories/volunteer_repository.py` — Volunteer CRUD, availability update
- `app/repositories/budget_repository.py` — Reservation CRUD, active reservations by office/month
- `app/repositories/purchase_repository.py` — Purchase CRUD, reconciled spend calculation (receipt_reference + REIMBURSED status)
- `app/repositories/reimbursement_repository.py` — Reimbursement CRUD, status counts by office/month, reimbursed-by-office counting
- `app/repositories/snack_box_repository.py` — Snack box CRUD
- `app/repositories/office_repository.py` — Office CRUD
- `app/repositories/volunteer_office_eligibility_repository.py` — Eligibility record CRUD, valid_from/valid_until checking
- `app/repositories/audit_repository.py` — Audit event logging

**Assumptions for confirmation:**

1. The `tests/` directory is empty and pytest tests should be placed there (per `pyproject.toml` configuration). The three root-level test scripts (`test_basic.py`, `test_core.py`, `test_e2e.py`) serve as reference implementation but are not in the expected test directory.
2. The project uses in-memory SQLite for tests and can be configured for file-based persistence via `Database(path)`.
3. The `Clock` injection pattern (`RealClock`/`FixedClock`) is the intended way to make time deterministic for testing and scheduling.
4. The `ChatSimulator` and `HRSimulator` adapters are designed to be swapped for real integrations without changing service logic — the services accept `chat_adapter` and `hr_adapter` constructor arguments.
5. "One active refill per snack box" is enforced by application logic in `RefillService.report_empty_box()` checking `RefillRepository.get_active_by_snack_box()` and by the `ASSIGNED`/`OPEN` status filter in the repository query.
6. Budget reservations are per-office-per-month; the `budget_month` field uses `YYYY-MM` format derived from the transaction timestamp.