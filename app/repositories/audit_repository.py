from __future__ import annotations

import json

from datetime import datetime, timezone
from typing import Optional

from ..db import Database
from ..models import AuditEvent


class AuditRepository:
    """Repository for audit event data access."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(
        self,
        aggregate_type: str,
        aggregate_id: int,
        event_type: str,
        actor_id: Optional[int],
        details_json: Optional[str],
        txn=None,
    ) -> AuditEvent:
        """Create a new audit event."""
        if details_json is not None and not isinstance(details_json, str):
            details_json = json.dumps(details_json)
        now = datetime.now(timezone.utc).isoformat()
        params = (aggregate_type, aggregate_id, event_type, actor_id, details_json, now)
        if txn:
            self._db.conn.execute(
                "INSERT INTO audit_events (aggregate_type, aggregate_id, event_type, actor_id, details_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                params,
                txn,
            )
        else:
            self._db.conn.execute(
                "INSERT INTO audit_events (aggregate_type, aggregate_id, event_type, actor_id, details_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                params,
            )
        self._db.conn.commit()
        # Deserialize details_json back from string if it was stored as string
        stored_details = json.loads(details_json) if details_json else None
        return AuditEvent(
            id=self._db.conn.execute("SELECT last_insert_rowid()").fetchone()[0],
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            actor_id=actor_id,
            details_json=stored_details,
            created_at=datetime.fromisoformat(now),
        )