from ..db import Database
from ..models import SnackBox


class SnackBoxRepository:
    """Repository for snack box data access."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, snack_box: SnackBox, txn=None) -> SnackBox:
        """Create a new snack box."""
        params = (snack_box.office_id, snack_box.name, snack_box.status)
        if txn:
            self._db.conn.execute(
                "INSERT INTO snack_boxes (office_id, name, status, updated_at) VALUES (?, ?, ?, strftime('%Y-%m-%d %H:%M:%f', 'now'))",
                params,
                txn,
            )
        else:
            self._db.conn.execute(
                "INSERT INTO snack_boxes (office_id, name, status, updated_at) VALUES (?, ?, ?, strftime('%Y-%m-%d %H:%M:%f', 'now'))",
                params,
            )
        self._db.conn.commit()
        return snack_box

    def get_by_id(self, snack_box_id: int, txn=None) -> Optional[SnackBox]:
        """Get a snack box by ID."""
        cursor = self._db.conn.execute(
            "SELECT id, office_id, name, status, updated_at FROM snack_boxes WHERE id = ?",
            (snack_box_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return SnackBox(
            id=row[0],
            office_id=row[1],
            name=row[2],
            status=row[3],
        )

    def get_all(self, txn=None) -> list[SnackBox]:
        """Get all snack boxes."""
        cursor = self._db.conn.execute(
            "SELECT id, office_id, name, status, updated_at FROM snack_boxes"
        )
        boxes = []
        for row in cursor:
            boxes.append(
                SnackBox(
                    id=row[0],
                    office_id=row[1],
                    name=row[2],
                    status=row[3],
                )
            )
        return boxes

    def get_by_office(self, office_id: int, txn=None) -> list[SnackBox]:
        """Get snack boxes for an office."""
        cursor = self._db.conn.execute(
            "SELECT id, office_id, name, status, updated_at FROM snack_boxes WHERE office_id = ?",
            (office_id,),
        )
        boxes = []
        for row in cursor:
            boxes.append(
                SnackBox(
                    id=row[0],
                    office_id=row[1],
                    name=row[2],
                    status=row[3],
                )
            )
        return boxes