import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Optional

from .models import BucketCandidate, BucketRecord, DeviceStatusRecord, MeasurementRecord

DB_PATH = Path(__file__).resolve().parents[1] / "weight_dashboard.sqlite3"


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                weight REAL NOT NULL
            )
            """
        )
        try:
            connection.execute("ALTER TABLE measurements ADD COLUMN source_event_id TEXT")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS buckets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_timestamp TEXT NOT NULL,
                end_timestamp TEXT NOT NULL,
                max_weight REAL NOT NULL,
                bucket_date TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS device_statuses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                status TEXT NOT NULL,
                raw TEXT NOT NULL DEFAULT '',
                source_event_id TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_measurements_timestamp
            ON measurements (timestamp)
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_measurements_source_event_id
            ON measurements (source_event_id)
            WHERE source_event_id IS NOT NULL
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_device_statuses_timestamp
            ON device_statuses (timestamp)
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_device_statuses_source_event_id
            ON device_statuses (source_event_id)
            WHERE source_event_id IS NOT NULL
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_buckets_date
            ON buckets (bucket_date)
            """
        )


def _measurement_from_row(row: sqlite3.Row) -> MeasurementRecord:
    return MeasurementRecord(
        id=row["id"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        weight=row["weight"],
        source_event_id=row["source_event_id"] if "source_event_id" in row.keys() else None,
    )


def _device_status_from_row(row: sqlite3.Row) -> DeviceStatusRecord:
    return DeviceStatusRecord(
        id=row["id"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        status=row["status"],
        raw=row["raw"],
        source_event_id=row["source_event_id"],
    )


def _bucket_from_row(row: sqlite3.Row) -> BucketRecord:
    return BucketRecord(
        id=row["id"],
        start_timestamp=datetime.fromisoformat(row["start_timestamp"]),
        end_timestamp=datetime.fromisoformat(row["end_timestamp"]),
        max_weight=row["max_weight"],
        bucket_date=date.fromisoformat(row["bucket_date"]),
    )


def add_measurement(timestamp: datetime, weight: float, source_event_id: Optional[str] = None) -> MeasurementRecord:
    with get_connection() as connection:
        if source_event_id:
            existing = connection.execute(
                "SELECT id, timestamp, weight, source_event_id FROM measurements WHERE source_event_id = ?",
                (source_event_id,),
            ).fetchone()
            if existing is not None:
                return _measurement_from_row(existing)

        cursor = connection.execute(
            "INSERT INTO measurements (timestamp, weight, source_event_id) VALUES (?, ?, ?)",
            (timestamp.isoformat(), weight, source_event_id),
        )
        row = connection.execute(
            "SELECT id, timestamp, weight, source_event_id FROM measurements WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return _measurement_from_row(row)


def list_measurements() -> List[MeasurementRecord]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, timestamp, weight, source_event_id
            FROM measurements
            ORDER BY timestamp ASC, id ASC
            """
        ).fetchall()
    return [_measurement_from_row(row) for row in rows]


def get_latest_measurement() -> Optional[MeasurementRecord]:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, timestamp, weight, source_event_id
            FROM measurements
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    return _measurement_from_row(row) if row is not None else None


def list_measurements_between(start: datetime, end: datetime) -> List[MeasurementRecord]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, timestamp, weight, source_event_id
            FROM measurements
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC, id ASC
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    return [_measurement_from_row(row) for row in rows]


def add_device_status(
    timestamp: datetime,
    status: str,
    raw: str = "",
    source_event_id: Optional[str] = None,
) -> DeviceStatusRecord:
    with get_connection() as connection:
        if source_event_id:
            existing = connection.execute(
                """
                SELECT id, timestamp, status, raw, source_event_id
                FROM device_statuses
                WHERE source_event_id = ?
                """,
                (source_event_id,),
            ).fetchone()
            if existing is not None:
                return _device_status_from_row(existing)

        cursor = connection.execute(
            """
            INSERT INTO device_statuses (timestamp, status, raw, source_event_id)
            VALUES (?, ?, ?, ?)
            """,
            (timestamp.isoformat(), status, raw, source_event_id),
        )
        row = connection.execute(
            """
            SELECT id, timestamp, status, raw, source_event_id
            FROM device_statuses
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return _device_status_from_row(row)


def get_latest_device_status() -> Optional[DeviceStatusRecord]:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, timestamp, status, raw, source_event_id
            FROM device_statuses
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    return _device_status_from_row(row) if row is not None else None


def list_device_statuses() -> List[DeviceStatusRecord]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, timestamp, status, raw, source_event_id
            FROM device_statuses
            ORDER BY timestamp ASC, id ASC
            """
        ).fetchall()
    return [_device_status_from_row(row) for row in rows]


def replace_buckets(buckets: Iterable[BucketCandidate]) -> None:
    bucket_list = list(buckets)
    with get_connection() as connection:
        existing_rows = connection.execute(
            """
            SELECT id, start_timestamp, end_timestamp
            FROM buckets
            """
        ).fetchall()
        existing_keys = {
            (row["start_timestamp"], row["end_timestamp"]): row["id"]
            for row in existing_rows
        }
        next_keys = set()

        for bucket in bucket_list:
            key = (bucket.start_timestamp.isoformat(), bucket.end_timestamp.isoformat())
            next_keys.add(key)

            if key in existing_keys:
                connection.execute(
                    """
                    UPDATE buckets
                    SET max_weight = ?, bucket_date = ?
                    WHERE id = ?
                    """,
                    (bucket.max_weight, bucket.bucket_date.isoformat(), existing_keys[key]),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO buckets (
                        start_timestamp,
                        end_timestamp,
                        max_weight,
                        bucket_date
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        bucket.start_timestamp.isoformat(),
                        bucket.end_timestamp.isoformat(),
                        bucket.max_weight,
                        bucket.bucket_date.isoformat(),
                    ),
                )

        stale_ids = [
            row["id"]
            for row in existing_rows
            if (row["start_timestamp"], row["end_timestamp"]) not in next_keys
        ]
        connection.executemany("DELETE FROM buckets WHERE id = ?", [(bucket_id,) for bucket_id in stale_ids])


def list_buckets(bucket_date: Optional[date] = None) -> List[BucketRecord]:
    query = """
        SELECT id, start_timestamp, end_timestamp, max_weight, bucket_date
        FROM buckets
    """
    params = ()
    if bucket_date is not None:
        query += " WHERE bucket_date = ?"
        params = (bucket_date.isoformat(),)
    query += " ORDER BY start_timestamp ASC, id ASC"

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    return [_bucket_from_row(row) for row in rows]


def get_bucket(bucket_id: int) -> Optional[BucketRecord]:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, start_timestamp, end_timestamp, max_weight, bucket_date
            FROM buckets
            WHERE id = ?
            """,
            (bucket_id,),
        ).fetchone()
    return _bucket_from_row(row) if row is not None else None


def count_rows(table_name: str) -> int:
    if table_name not in {"measurements", "buckets"}:
        raise ValueError("Unsupported table name")

    with get_connection() as connection:
        row = connection.execute(f"SELECT COUNT(*) AS total FROM {table_name}").fetchone()
    return row["total"]
