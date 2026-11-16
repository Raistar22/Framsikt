# Interview Walkthrough: Framsikt Snack Counter Automation

## 1. Why use a refill state machine?

A refill state machine provides a clear, deterministic model for the snack box refill process. It ensures that:
- **State transitions are validated:** Only allowed transitions are permitted (e.g., OPEN → ASSIGNED, ASSIGNED → ACCEPTED, etc.), preventing invalid state changes that could lead to data corruption.
- **Concurrent access is safe:** The state machine is enforced within database transactions, so even if two volunteers try to accept the same refill simultaneously, only one succeeds due to the database constraints and transaction serialization.
- **Business rules are centralized:** Instead of scattering validation logic across the codebase, all valid transitions are defined in one place (the Refill model), making the code easier to understand and maintain.
- **Auditability:** Every state change creates an audit event, providing a complete trail of what happened and when. This is crucial for compliance and debugging.

## 2. How is duplicate assignment prevented at the database level?

Duplicate assignment is prevented through a combination of database constraints and application-level checks:

- **Unique constraint on snack_box_id with status filter:** The `refills` table has a practical constraint that ensures only one active refill (status IN 'OPEN', 'ASSIGNED', 'ACCEPTED') can exist per snack box. The `get_active_by_snack_box` repository method enforces this.
- **Assigned volunteer check:** When assigning a refill, the application checks that `assigned_volunteer_id` is NULL before setting it. This check happens within a transaction, so if two volunteers try to assign the same box, the first one to commit wins, and the second gets an `InvalidTransitionError`.
- **Volunteer single-assignment check:** The volunteer eligibility check ensures a volunteer cannot have more than one active (ASSIGNED/ACCEPTED) refill at a time. This is checked both in the VolunteerService ( querying for active refills by volunteer) and in the RefillService when assigning.

## 3. What happens if two volunteers click accept at the same time?

When two volunteers click accept simultaneously:

1. Both requests arrive at the RefillService.accept_refill() method.
2. The method first checks that the volunteer owns the assignment (`refill.assigned_volunteer_id != volunteer_id`).
3. It then checks that the refill can transition to ACCEPTED.
4. Both checks happen within a database transaction (via the repository's update method).
5. SQLite serializes the transactions, so only one succeeds. The other volunteer gets an `InvalidTransitionError` or `VolunteerNotEligibleError`.
6. The failed attempt is logged as an audit event, and the refill remains in ASSIGNED state (or gets reassigned via the expiry/reassignment flow).

**Key insight:** The database transaction boundary ensures at most one volunteer can successfully accept a given refill. The application code validates the conditions, but the database guarantees the invariant.

## 4. How does volunteer fairness work?

Volunteer fairness is based on a transparent, deterministic algorithm:

1. **Count completed refills:** For each volunteer, count the number of reimbursed refills in the last 30 days (configurable rolling period).
2. **Select lowest count:** The volunteer with the fewest completed refills is preferred.
3. **Tie-break by last-assigned:** Among volunteers with the same count, the one with the oldest `last_assigned_at` timestamp is preferred. Null values (never assigned) rank first.
4. **Tie-break by ID:** If still tied, the volunteer with the stable/lowest ID is selected.

**Why this is fair:** It rotates workload evenly across volunteers, ensuring no single person bears disproportionate burden. Volunteers who haven't had a chance to refill get priority (null last_assigned_at ranks first).

**Limitations:** It's a simple heuristic, not a sophisticated optimization algorithm. It doesn't consider workload capacity, skill matching, or preferences. Assignment history is tracked in audit events, but only *completed* reimbursed refills count toward the fairness score — declined or expired assignments do not.

**Update timing:** `last_assigned_at` is updated when an assignment is *successfully committed*, not when merely considered. This prevents gaming the system.

## 5. What happens if a volunteer goes on holiday after assignment?

If a volunteer becomes unavailable (goes on holiday, leaves the company, etc.):

1. The system tracks volunteer `available` status — if set to `False`, the volunteer is skipped in eligibility checks.
2. If a volunteer has an active assignment but becomes unavailable, the assignment remains in ASSIGNED status until it either:
   - The volunteer accepts/declines (if they return), or
   - The assignment expires (96-hour default), at which point it's released and reassigned to the next eligible volunteer.
3. **Expiry and reassignment:** The `expire_overdue_assignments()` service method finds all ASSIGNED refills whose `assignment_expires_at` timestamp has passed, transitions them to OPEN, and attempts to reassign them to the next eligible volunteer.
4. **No continuous worker needed:** The expiry check can be run manually, by a scheduler, or whenever the system processes volunteer status changes. There's no need for a continuously running background worker — the service method is idempotent and can be called at any time.

## 6. How does reassignment work without a continuously running worker?

Reassignment is triggered by the `expire_overdue_assignments()` method, which can be called by:

- A **scheduler/cron job** that runs periodically (e.g., every hour)
- A **manual CLI command** (`python -m app.cli expire-overdue`)
- **Another service** that processes volunteer status changes
- **The CLI demo** itself demonstrates the flow

The method is idempotent — if called multiple times, it only processes refills that are currently in ASSIGNED status with expired assignments. If called after a previous reassignment, it simply finds no overdue refills and returns an empty list.

**Flow:**
1. Call `expire_overdue_assignments(now)`
2. For each ASSIGNED refill where `assignment_expires_at < now`:
   - Transition refill status to OPEN
   - Create audit event (EXPIRED)
   - Get eligible volunteers (excluding the previous assignee)
   - Assign refill to the first eligible volunteer
   - Create audit event (ASSIGNED for new assignee)
3. Return list of expired refills

If no eligible volunteer remains, the refill stays OPEN and an office channel notification is sent (via the chat adapter).

## 7. Why reserve budget before purchase?

Budget reservation serves several critical purposes:

- **Prevents overspending:** By reserving the estimated amount before the volunteer buys, we ensure that the budget cannot be overspended even if multiple volunteers buy snacks for the same box on the same day.
- **Atomic guarantee:** The reservation is performed within a database transaction, so even with concurrent purchases, the total reserved amount cannot exceed the remaining budget.
- **Commitment tracking:** Once reserved, the spend is "committed" — even though HR approval may take 1-10 days, the budget is not available for other purchases. This prevents the "phantom budget" problem where available budget fluctuates based on HR approval status.
- **Reconciliation:** After the receipt is submitted, the reservation is reconciled to the actual amount. If the actual amount is less than reserved, the unused portion is released. If actual exceeds reserved, the system checks if the additional amount fits the remaining budget.
- **Audit trail:** Every reservation and reconciliation creates audit events, providing complete visibility into budget movements.

**Without pre-reservation:** Two volunteers could both buy snacks for the same box, both submit receipts, and the total actual spend could exceed the monthly budget without any prevention mechanism.

## 8. How are pending reimbursements accounted for?

Pending HR claims are treated as **committed spending**, not as already-spent budget. The logic is:

- When a purchase is submitted and the HR claim is created with PENDING status, the budget reservation is retained (status RESERVED → RECONCILED).
- The reserved amount counts toward the "pending commitments" in the monthly report.
- The remaining budget calculation is: `available = monthly_budget - reconciled_spend - active_reservations`
- **Pending claims do NOT make budget appear available** — the commitment stays in place until the claim is either approved or rejected.
- **On approval:** The actual spend is kept in the month's spend total, and the refill status is updated to REIMBURSED.
- **On rejection:** The budget commitment is released/reversed, and an audit event is recorded. The refund/reversal is explicit, not silent.

This ensures that budget visibility is always accurate: the "remaining" budget never includes amounts tied up in pending HR claims.

## 9. Why must NOK and INR be reported separately?

NOK (Norwegian Krone) and INR (Indian Rupee) are different currencies with different values. Adding them directly would be like adding dollars and euros without an exchange rate — the result would be meaningless.

**Default behavior (no FX rate):**
- Monthly reports show NOK and INR totals **separately**
- A clear note: "NOK and INR totals are not added together"
- Management sees spending by office in the office's native currency

**If an FX rate is explicitly supplied:**
- Show the rate, base currency, conversion timestamp/source
- Show the converted total separately (labeled as converted, not combined)
- Never silently convert one currency to another

**Why not add a default FX rate:** Even if Framsikt has an internal FX policy, the default v1 implementation deliberately avoids FX conversion to prevent errors. A configured, explicit reimbursement policy supports cross-currency purchases, but the base reporting always keeps currencies separate.

## 9. How does HR idempotency prevent duplicate claims?

HR idempotency ensures that submitting the same reimbursement claim twice creates only **one** external HR claim:

- Each claim submission includes an `idempotency_key` (a unique string, typically based on purchase ID + volunteer ID + timestamp).
- The HR simulator (and real HR systems) store claims keyed by this idempotency key.
- If the same idempotency key is used for a second submission:
  - The simulator returns the **same** external claim ID
  - The claim status is not changed (it remains in its current state)
  - No duplicate claim is created in the local database
  - The reimbursement record is updated atomically

**Implementation:** The HRSimulator maintains a dictionary mapping `idempotency_key → external_claim_id`. On submit_claim():
- If the key already exists, return the existing claim (no new DB insert)
- If new, create a new claim with a new external_claim_id and store the mapping

**Local database impact:** The Reimbursement entity has `purchase_id UNIQUE` and `external_claim_id UNIQUE`. Idempotent submissions prevent duplicate external claims, which would otherwise cause constraint violations or confusing state (two claims with different statuses for the same purchase).

## 10. What would change for production with multiple application instances?

Moving from a single-process SQLite deployment to production with multiple application instances would require several changes:

| Aspect | Single-instance (SQLite) | Multi-instance production |
|---|---|---|
| **Database** | Local file-based SQLite | Server database (PostgreSQL, MySQL) |
| **Concurrency** | Serialized via SQLite WAL mode + busy_timeout | Database-level transaction isolation (READ COMMITTED or REPEATABLE READ) |
| **Budget atomicity** | One-process transaction | Distributed transactions or optimistic concurrency with retries |
| **Expiry processing** | Explicit service method call | Scheduled job or background worker (e.g., Celery) |
| **Chat integration** | Simulated adapter | Real internal chat API (Slack, Teams, etc.) |
| **HR integration** | Simulated adapter | Real payroll/HR system API |
| **Database migrations** | Manual schema updates (or none needed) | Alembic/Flask-Migrate or similar migration tool |
| **Deployment** | `python run.py` | Docker/Kubernetes with health checks |
| **Observability** | Print statements / simple logs | Structured logging, metrics, distributed tracing |
| **Testing** | In-memory SQLite + pytest | Containerized tests, contract testing, integration tests |

**Key architectural decision:** The current design deliberately keeps things simple for the take-home exercise. The core business rules (state machine, fairness, budget reservation, audit events) are all encapsulated in ways that would transfer to a production system with mainly infrastructure changes (database, deployment, integrations).

## 11. Main trade-offs and limitations

| Trade-off | Decision | Rationale |
|---|---|---|
| **SQLite vs server DB** | SQLite for v1 | Simplicity, no setup needed, excellent for testing atomicity. Production would use PostgreSQL/MySQL. |
| **Fairness heuristic** | Simple rotation | Easy to understand and test. Suffices for ~15-20 volunteers. Production would use optimization. |
| **No FX conversion** | Report separately | Prevents erroneous currency aggregation. Configurable FX supported if needed. |
| **Simulated integrations** | Chat & HR fakes | Fast testing, no external dependencies. Production would replace with real APIs. |
| **Single-process** | One process per deployment | Avoids distributed complexity. Production would use multiple instances + server DB. |
| **No inventory tracking** | Focus on refill/reimbursement | Keeps scope focused on the assignment requirements. Inventory could be added later. |
| **No FX conversion in reporting** | NOK/INR separate by default | Avoids mistakes from incorrect conversion rates. Explicit rates available if configured. |

**Known limitations (documented for honesty):**
- No real chat/HR API integration (simulated only)
- No frontend or web UI
- No authentication/authorization
- No FX conversion by default
- SQLite limitations for true multi-concurrency (limited to one writer at a time, 5s busy_timeout)
- No inventory or stock level tracking
- Volunteer availability must be maintained manually (not inferred from work patterns)
- Cross-currency purchases rejected unless configured

**The design correctly balances:** Simplicity and testability for the take-home exercise, while maintaining enough structure and invariants to transfer to production with focused changes.