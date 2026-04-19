import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from device_agent.domain import (
    AnomalyEvent,
    BucketSession,
    ControlWeightRecord,
    DeviceHeartbeat,
    WeightLogRecord,
)


SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS bucket_sessions (
    session_id TEXT PRIMARY KEY,
    bucket_id TEXT NOT NULL,
    station_id TEXT NOT NULL,
    station_type TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    ended_at_utc TEXT,
    status TEXT NOT NULL,
    expected_final_weight_grams INTEGER NOT NULL DEFAULT 0,
    last_logged_weight_grams INTEGER NOT NULL DEFAULT 0,
    last_non_empty_weight_grams INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_bucket_sessions_status
    ON bucket_sessions (station_id, status);

CREATE TABLE IF NOT EXISTS weight_logs (
    event_id TEXT PRIMARY KEY,
    bucket_id TEXT NOT NULL,
    bucket_session_id TEXT NOT NULL,
    station_id TEXT NOT NULL,
    station_type TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    weight_grams INTEGER NOT NULL,
    delta_grams INTEGER NOT NULL,
    raw_weight_grams INTEGER NOT NULL,
    reason TEXT NOT NULL,
    FOREIGN KEY(bucket_session_id) REFERENCES bucket_sessions(session_id)
);

CREATE TABLE IF NOT EXISTS anomaly_events (
    anomaly_event_id TEXT PRIMARY KEY,
    bucket_id TEXT NOT NULL,
    bucket_session_id TEXT NOT NULL,
    station_id TEXT NOT NULL,
    station_type TEXT NOT NULL,
    event_type TEXT NOT NULL,
    observed_at_utc TEXT NOT NULL,
    delta_grams INTEGER NOT NULL,
    weight_before_grams INTEGER NOT NULL,
    weight_after_grams INTEGER NOT NULL,
    persistence_seconds INTEGER NOT NULL,
    video_metadata_json TEXT NOT NULL,
    FOREIGN KEY(bucket_session_id) REFERENCES bucket_sessions(session_id)
);

CREATE TABLE IF NOT EXISTS control_weight_records (
    control_weight_record_id TEXT PRIMARY KEY,
    bucket_id TEXT NOT NULL,
    station_id TEXT NOT NULL,
    station_type TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    control_weight_grams INTEGER NOT NULL,
    operator_note TEXT
);

CREATE TABLE IF NOT EXISTS device_heartbeats (
    heartbeat_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    station_id TEXT NOT NULL,
    station_type TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    agent_version TEXT NOT NULL,
    status TEXT NOT NULL,
    details_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox_messages (
    message_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    sync_status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at_utc TEXT NOT NULL,
    last_error TEXT,
    created_at_utc TEXT NOT NULL,
    sent_at_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_outbox_next_attempt
    ON outbox_messages (sync_status, next_attempt_at_utc);
"""


@dataclass(slots=True)
class OutboxMessage:
    message_id: str
    topic: str
    entity_id: str
    idempotency_key: str
    payload_json: str
    attempt_count: int
    next_attempt_at_utc: str


class LocalStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA_SQL)

    def close(self) -> None:
        self._conn.close()

    def get_open_session(self, station_id: str) -> BucketSession | None:
        row = self._conn.execute(
            """
            SELECT *
            FROM bucket_sessions
            WHERE station_id = ? AND status = 'active'
            ORDER BY started_at_utc DESC
            LIMIT 1
            """,
            (station_id,),
        ).fetchone()
        if not row:
            return None
        return BucketSession(
            session_id=row["session_id"],
            bucket_id=row["bucket_id"],
            station_id=row["station_id"],
            station_type=row["station_type"],
            started_at_utc=datetime.fromisoformat(row["started_at_utc"]),
            ended_at_utc=datetime.fromisoformat(row["ended_at_utc"]) if row["ended_at_utc"] else None,
            status=row["status"],
            expected_final_weight_grams=row["expected_final_weight_grams"],
            last_logged_weight_grams=row["last_logged_weight_grams"],
            last_non_empty_weight_grams=row["last_non_empty_weight_grams"],
        )

    def upsert_bucket_session(self, session: BucketSession) -> None:
        self._conn.execute(
            """
            INSERT INTO bucket_sessions (
                session_id, bucket_id, station_id, station_type, started_at_utc,
                ended_at_utc, status, expected_final_weight_grams,
                last_logged_weight_grams, last_non_empty_weight_grams
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                ended_at_utc = excluded.ended_at_utc,
                status = excluded.status,
                expected_final_weight_grams = excluded.expected_final_weight_grams,
                last_logged_weight_grams = excluded.last_logged_weight_grams,
                last_non_empty_weight_grams = excluded.last_non_empty_weight_grams
            """,
            (
                session.session_id,
                session.bucket_id,
                session.station_id,
                session.station_type,
                session.started_at_utc.isoformat(),
                session.ended_at_utc.isoformat() if session.ended_at_utc else None,
                session.status,
                session.expected_final_weight_grams,
                session.last_logged_weight_grams,
                session.last_non_empty_weight_grams,
            ),
        )
        self._conn.commit()

    def add_weight_log(self, record: WeightLogRecord) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO weight_logs (
                event_id, bucket_id, bucket_session_id, station_id, station_type,
                recorded_at_utc, weight_grams, delta_grams, raw_weight_grams, reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.event_id,
                record.bucket_id,
                record.bucket_session_id,
                record.station_id,
                record.station_type,
                record.recorded_at_utc.isoformat(),
                record.weight_grams,
                record.delta_grams,
                record.raw_weight_grams,
                record.reason,
            ),
        )
        self._conn.commit()

    def add_anomaly_event(self, event: AnomalyEvent) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO anomaly_events (
                anomaly_event_id, bucket_id, bucket_session_id, station_id, station_type,
                event_type, observed_at_utc, delta_grams, weight_before_grams,
                weight_after_grams, persistence_seconds, video_metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.anomaly_event_id,
                event.bucket_id,
                event.bucket_session_id,
                event.station_id,
                event.station_type,
                event.event_type,
                event.observed_at_utc.isoformat(),
                event.delta_grams,
                event.weight_before_grams,
                event.weight_after_grams,
                event.persistence_seconds,
                json.dumps(event.video_metadata),
            ),
        )
        self._conn.commit()

    def add_control_weight_record(self, record: ControlWeightRecord) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO control_weight_records (
                control_weight_record_id, bucket_id, station_id, station_type,
                recorded_at_utc, control_weight_grams, operator_note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.control_weight_record_id,
                record.bucket_id,
                record.station_id,
                record.station_type,
                record.recorded_at_utc.isoformat(),
                record.control_weight_grams,
                record.operator_note,
            ),
        )
        self._conn.commit()

    def add_heartbeat(self, heartbeat: DeviceHeartbeat) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO device_heartbeats (
                heartbeat_id, device_id, station_id, station_type, recorded_at_utc,
                agent_version, status, details_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                heartbeat.heartbeat_id,
                heartbeat.device_id,
                heartbeat.station_id,
                heartbeat.station_type,
                heartbeat.recorded_at_utc.isoformat(),
                heartbeat.agent_version,
                heartbeat.status,
                json.dumps(heartbeat.details),
            ),
        )
        self._conn.commit()

    def enqueue(
        self,
        *,
        message_id: str,
        topic: str,
        entity_id: str,
        idempotency_key: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO outbox_messages (
                message_id, topic, entity_id, idempotency_key, payload_json,
                sync_status, attempt_count, next_attempt_at_utc, last_error, created_at_utc, sent_at_utc
            )
            VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, NULL, ?, NULL)
            """,
            (
                message_id,
                topic,
                entity_id,
                idempotency_key,
                json.dumps(payload),
                now.isoformat(),
                now.isoformat(),
            ),
        )
        self._conn.commit()

    def fetch_ready_outbox(self, now: datetime, limit: int) -> list[OutboxMessage]:
        rows = self._conn.execute(
            """
            SELECT message_id, topic, entity_id, idempotency_key, payload_json, attempt_count, next_attempt_at_utc
            FROM outbox_messages
            WHERE sync_status IN ('pending', 'retry')
              AND next_attempt_at_utc <= ?
            ORDER BY created_at_utc ASC
            LIMIT ?
            """,
            (now.isoformat(), limit),
        ).fetchall()
        return [
            OutboxMessage(
                message_id=row["message_id"],
                topic=row["topic"],
                entity_id=row["entity_id"],
                idempotency_key=row["idempotency_key"],
                payload_json=row["payload_json"],
                attempt_count=row["attempt_count"],
                next_attempt_at_utc=row["next_attempt_at_utc"],
            )
            for row in rows
        ]

    def mark_synced(self, message_id: str, now: datetime) -> None:
        self._conn.execute(
            """
            UPDATE outbox_messages
            SET sync_status = 'synced', sent_at_utc = ?, last_error = NULL
            WHERE message_id = ?
            """,
            (now.isoformat(), message_id),
        )
        self._conn.commit()

    def mark_retry(self, message_id: str, *, next_attempt_at: datetime, last_error: str) -> None:
        self._conn.execute(
            """
            UPDATE outbox_messages
            SET sync_status = 'retry',
                attempt_count = attempt_count + 1,
                next_attempt_at_utc = ?,
                last_error = ?
            WHERE message_id = ?
            """,
            (next_attempt_at.isoformat(), last_error[:500], message_id),
        )
        self._conn.commit()

    def count_pending_outbox(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS count FROM outbox_messages WHERE sync_status IN ('pending', 'retry')"
        ).fetchone()
        return int(row["count"])

    def get_schema_sql(self) -> str:
        return SCHEMA_SQL

    @staticmethod
    def compute_backoff(base_seconds: int, max_seconds: int, attempt_count: int) -> timedelta:
        delay = min(base_seconds * (2 ** max(attempt_count, 0)), max_seconds)
        return timedelta(seconds=delay)
