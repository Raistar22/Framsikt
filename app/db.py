from __future__ import annotations

import sqlite3
from pathlib import Path


class Database:
    """SQLite database wrapper with transaction support."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._create_tables()
        self._models: dict[type, list] = {
            "Office": [],
            "Volunteer": [],
            "SnackBox": [],
            "Refill": [],
            "Purchase": [],
            "BudgetReservation": [],
            "Reimbursement": [],
            "AuditEvent": [],
        }

    def _create_tables(self) -> None:
        schema_sql = """
        CREATE TABLE IF NOT EXISTS offices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            currency TEXT NOT NULL,
            monthly_budget_minor INTEGER NOT NULL,
            timezone TEXT NOT NULL DEFAULT 'UTC'
        );

        CREATE TABLE IF NOT EXISTS volunteers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            home_office_id INTEGER NOT NULL,
            payroll_currency TEXT NOT NULL,
            available BOOLEAN NOT NULL DEFAULT 1,
            last_assigned_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
            FOREIGN KEY (home_office_id) REFERENCES offices(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS volunteer_office_eligibility (
            volunteer_id INTEGER NOT NULL,
            office_id INTEGER NOT NULL,
            valid_from TIMESTAMP NOT NULL,
            valid_until TIMESTAMP,
            PRIMARY KEY (volunteer_id, office_id),
            FOREIGN KEY (volunteer_id) REFERENCES volunteers(id) ON DELETE CASCADE,
            FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS snack_boxes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            office_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'STOCKED',
            updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
            FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS refills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snack_box_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            assigned_volunteer_id INTEGER,
            assignment_expires_at TIMESTAMP,
            assignment_attempt INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
            updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
            completed_at TIMESTAMP,
            idempotency_key TEXT UNIQUE,
            FOREIGN KEY (snack_box_id) REFERENCES snack_boxes(id) ON DELETE CASCADE,
            FOREIGN KEY (assigned_volunteer_id) REFERENCES volunteers(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            refill_id INTEGER UNIQUE,
            volunteer_id INTEGER NOT NULL,
            office_id INTEGER NOT NULL,
            amount_minor INTEGER NOT NULL,
            currency TEXT NOT NULL,
            description TEXT,
            receipt_reference TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
            FOREIGN KEY (refill_id) REFERENCES refills(id) ON DELETE CASCADE,
            FOREIGN KEY (volunteer_id) REFERENCES volunteers(id) ON DELETE RESTRICT,
            FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS budget_reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            office_id INTEGER NOT NULL,
            refill_id INTEGER UNIQUE,
            reserved_amount_minor INTEGER NOT NULL,
            actual_amount_minor INTEGER,
            currency TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'RESERVED',
            budget_month TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
            updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
            FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE,
            FOREIGN KEY (refill_id) REFERENCES refills(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reimbursements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_id INTEGER UNIQUE,
            external_claim_id TEXT UNIQUE,
            status TEXT NOT NULL DEFAULT 'NOT_SUBMITTED',
            submitted_at TIMESTAMP,
            resolved_at TIMESTAMP,
            last_error TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
            updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
            FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aggregate_type TEXT NOT NULL,
            aggregate_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            actor_id INTEGER,
            details_json TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now'))
        );

        CREATE INDEX IF NOT EXISTS idx_refills_snack_box ON refills(snack_box_id);
        CREATE INDEX IF NOT EXISTS idx_refills_status ON refills(status);
        CREATE INDEX IF NOT EXISTS idx_refills_expires ON refills(assignment_expires_at);
        CREATE INDEX IF NOT EXISTS idx_refills_assigned ON refills(assigned_volunteer_id);
        CREATE INDEX IF NOT EXISTS idx_purchases_refill ON purchases(refill_id);
        CREATE INDEX IF NOT EXISTS idx_purchases_office_month ON purchases(office_id, strftime('%Y-%m', created_at));
        CREATE INDEX IF NOT EXISTS idx_budget_reservations_office ON budget_reservations(office_id);
        CREATE INDEX IF NOT EXISTS idx_budget_reservations_refill ON budget_reservations(refill_id);
        CREATE INDEX IF NOT EXISTS idx_reimbursements_claim ON reimbursements(external_claim_id);
        CREATE INDEX IF NOT EXISTS idx_audit_aggregate ON audit_events(aggregate_type, aggregate_id);
        """

        self._conn.executescript(schema_sql)
        self._conn.commit()

    def begin(self) -> "sqlite3.Connection":
        return self._conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        self._conn.close()