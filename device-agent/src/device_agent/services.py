import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime

import httpx

from device_agent import __version__
from device_agent.config import AgentConfig
from device_agent.db import LocalStore
from device_agent.domain import (
    AnomalyEvent,
    BucketSession,
    ControlWeightRecord,
    DeviceHeartbeat,
    WeightLogRecord,
)
from device_agent.hardware import ButtonHandler, ControlInputHandler, ScaleReader, VideoProvider
from device_agent.utils import MedianFilter, new_bucket_id, new_id, utc_now


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class NegativeCandidateState:
    started_at_utc: datetime
    weight_before_grams: int
    weight_after_grams: int
    delta_grams: int
    triggered: bool = False


@dataclass(slots=True)
class DetectionResult:
    logs: list[WeightLogRecord]
    anomaly: AnomalyEvent | None
    session_closed: bool


class EventDetector:
    def __init__(self, config: AgentConfig, video_provider: VideoProvider) -> None:
        self.config = config
        self.video_provider = video_provider
        self._negative_candidate: NegativeCandidateState | None = None
        self._empty_started_at_utc: datetime | None = None

    def process_weight(
        self,
        *,
        session: BucketSession,
        previous_logged_weight_grams: int,
        filtered_weight_grams: int,
        raw_weight_grams: int,
        now: datetime,
    ) -> DetectionResult:
        logs: list[WeightLogRecord] = []
        anomaly: AnomalyEvent | None = None
        delta = filtered_weight_grams - previous_logged_weight_grams

        if abs(delta) >= self.config.minimum_meaningful_log_delta:
            logs.append(
                WeightLogRecord(
                    event_id=new_id("wl"),
                    bucket_id=session.bucket_id,
                    bucket_session_id=session.session_id,
                    station_id=session.station_id,
                    station_type=session.station_type,
                    recorded_at_utc=now,
                    weight_grams=filtered_weight_grams,
                    delta_grams=delta,
                    raw_weight_grams=raw_weight_grams,
                    reason="meaningful_change",
                )
            )

        if (
            delta <= self.config.negative_delta_threshold
            and session.status == "active"
            and filtered_weight_grams > self.config.empty_bucket_threshold
        ):
            if self._negative_candidate is None:
                self._negative_candidate = NegativeCandidateState(
                    started_at_utc=now,
                    weight_before_grams=previous_logged_weight_grams,
                    weight_after_grams=filtered_weight_grams,
                    delta_grams=delta,
                )
            else:
                self._negative_candidate.weight_after_grams = filtered_weight_grams
                self._negative_candidate.delta_grams = filtered_weight_grams - self._negative_candidate.weight_before_grams

            elapsed = int((now - self._negative_candidate.started_at_utc).total_seconds()) + 1
            if elapsed >= self.config.negative_persistence_seconds and not self._negative_candidate.triggered:
                clip_metadata = self.video_provider.build_clip_metadata(
                    bucket_id=session.bucket_id,
                    station_id=session.station_id,
                    event_type="unexpected_negative_primary_delta",
                    occurred_at_utc=now.isoformat(),
                )
                anomaly = AnomalyEvent(
                    anomaly_event_id=new_id("an"),
                    bucket_id=session.bucket_id,
                    bucket_session_id=session.session_id,
                    station_id=session.station_id,
                    station_type=session.station_type,
                    event_type="unexpected_negative_primary_delta",
                    observed_at_utc=now,
                    delta_grams=self._negative_candidate.delta_grams,
                    weight_before_grams=self._negative_candidate.weight_before_grams,
                    weight_after_grams=self._negative_candidate.weight_after_grams,
                    persistence_seconds=elapsed,
                    video_metadata=clip_metadata,
                )
                self._negative_candidate.triggered = True
        else:
            self._negative_candidate = None

        session_closed = False
        if filtered_weight_grams <= self.config.empty_bucket_threshold:
            if self._empty_started_at_utc is None:
                self._empty_started_at_utc = now
            empty_elapsed = int((now - self._empty_started_at_utc).total_seconds()) + 1
            if empty_elapsed >= self.config.empty_confirmation_seconds:
                session_closed = True
                self._empty_started_at_utc = None
                self._negative_candidate = None
        else:
            self._empty_started_at_utc = None

        return DetectionResult(logs=logs, anomaly=anomaly, session_closed=session_closed)


class ApiClient:
    ROUTES = {
        "weight_log": "/api/v1/device/weight-logs",
        "bucket_session": "/api/v1/device/bucket-sessions",
        "anomaly_event": "/api/v1/device/anomaly-candidates",
        "control_weight_record": "/api/v1/device/control-weight-records",
        "heartbeat": "/api/v1/device/heartbeats",
    }

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self._client = httpx.Client(timeout=10.0)

    def close(self) -> None:
        self._client.close()

    def send(self, *, topic: str, idempotency_key: str, payload_json: str) -> None:
        route = self.ROUTES[topic]
        response = self._client.post(
            f"{self.config.api_base_url}{route}",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
            },
            content=payload_json,
        )
        if response.status_code not in (200, 201, 202, 409):
            raise RuntimeError(f"unexpected status {response.status_code}: {response.text}")


class SyncWorker:
    def __init__(self, store: LocalStore, api_client: ApiClient, config: AgentConfig, stop_event: threading.Event) -> None:
        self.store = store
        self.api_client = api_client
        self.config = config
        self.stop_event = stop_event

    def run(self) -> None:
        while not self.stop_event.is_set():
            now = utc_now()
            batch = self.store.fetch_ready_outbox(now, self.config.sync_batch_size)
            if not batch:
                self.stop_event.wait(1.0)
                continue

            for message in batch:
                if self.stop_event.is_set():
                    return
                try:
                    self.api_client.send(
                        topic=message.topic,
                        idempotency_key=message.idempotency_key,
                        payload_json=message.payload_json,
                    )
                    self.store.mark_synced(message.message_id, utc_now())
                except Exception as exc:  # pragma: no cover
                    next_attempt = utc_now() + self.store.compute_backoff(
                        self.config.sync_base_backoff_seconds,
                        self.config.sync_max_backoff_seconds,
                        message.attempt_count,
                    )
                    self.store.mark_retry(message.message_id, next_attempt_at=next_attempt, last_error=str(exc))
                    LOGGER.warning("sync retry scheduled for %s: %s", message.message_id, exc)


class PrimaryStationService:
    def __init__(
        self,
        *,
        config: AgentConfig,
        store: LocalStore,
        scale_reader: ScaleReader,
        button_handler: ButtonHandler,
        video_provider: VideoProvider,
    ) -> None:
        self.config = config
        self.store = store
        self.scale_reader = scale_reader
        self.button_handler = button_handler
        self.filter = MedianFilter(config.noise_window_size)
        self.detector = EventDetector(config, video_provider)
        self.current_session = store.get_open_session(config.station_id)

    def tick(self) -> None:
        now = utc_now()

        if self.button_handler.poll_pressed():
            self.scale_reader.tare()
            bucket_id = new_bucket_id(self.config.station_id, now)
            self.current_session = BucketSession(
                session_id=new_id("bs"),
                bucket_id=bucket_id,
                station_id=self.config.station_id,
                station_type="primary",
                started_at_utc=now,
                ended_at_utc=None,
                status="active",
                expected_final_weight_grams=0,
                last_logged_weight_grams=0,
                last_non_empty_weight_grams=0,
            )
            self.store.upsert_bucket_session(self.current_session)
            self._enqueue(
                "bucket_session",
                self.current_session.session_id,
                self.current_session.to_payload(),
                now,
                idempotency_suffix="active",
            )
            LOGGER.info("started bucket session %s for bucket %s", self.current_session.session_id, bucket_id)

        raw_weight = self.scale_reader.read_weight_grams()
        filtered_weight = self.filter.add(raw_weight)

        if not self.current_session:
            return

        if filtered_weight > self.config.empty_bucket_threshold:
            self.current_session.last_non_empty_weight_grams = filtered_weight

        result = self.detector.process_weight(
            session=self.current_session,
            previous_logged_weight_grams=self.current_session.last_logged_weight_grams,
            filtered_weight_grams=filtered_weight,
            raw_weight_grams=raw_weight,
            now=now,
        )

        for record in result.logs:
            self.store.add_weight_log(record)
            self.current_session.last_logged_weight_grams = record.weight_grams
            self.current_session.expected_final_weight_grams = max(
                self.current_session.expected_final_weight_grams,
                record.weight_grams,
            )
            self.store.upsert_bucket_session(self.current_session)
            self._enqueue("weight_log", record.event_id, record.to_payload(), now)

        if result.anomaly:
            self.store.add_anomaly_event(result.anomaly)
            self._enqueue("anomaly_event", result.anomaly.anomaly_event_id, result.anomaly.to_payload(), now)

        if result.session_closed:
            self.current_session.status = "completed"
            self.current_session.ended_at_utc = now
            self.current_session.expected_final_weight_grams = max(
                self.current_session.expected_final_weight_grams,
                self.current_session.last_non_empty_weight_grams,
            )
            self.store.upsert_bucket_session(self.current_session)
            self._enqueue(
                "bucket_session",
                self.current_session.session_id,
                self.current_session.to_payload(),
                now,
                idempotency_suffix="completed",
            )
            LOGGER.info(
                "completed bucket session %s with expected final weight %sg",
                self.current_session.session_id,
                self.current_session.expected_final_weight_grams,
            )
            self.current_session = None

    def _enqueue(
        self,
        topic: str,
        entity_id: str,
        payload: dict,
        now: datetime,
        *,
        idempotency_suffix: str | None = None,
    ) -> None:
        key = f"{topic}:{entity_id}"
        if idempotency_suffix:
            key = f"{key}:{idempotency_suffix}"
        self.store.enqueue(
            message_id=new_id("msg"),
            topic=topic,
            entity_id=entity_id,
            idempotency_key=key,
            payload=payload,
            now=now,
        )


class ControlStationService:
    def __init__(
        self,
        *,
        config: AgentConfig,
        store: LocalStore,
        scale_reader: ScaleReader,
        control_input_handler: ControlInputHandler,
    ) -> None:
        self.config = config
        self.store = store
        self.scale_reader = scale_reader
        self.control_input_handler = control_input_handler
        self.filter = MedianFilter(config.noise_window_size)

    def tick(self) -> None:
        raw_weight = self.scale_reader.read_weight_grams()
        filtered_weight = self.filter.add(raw_weight)
        submission = self.control_input_handler.poll_submission()
        if not submission:
            return

        now = utc_now()
        record = ControlWeightRecord(
            control_weight_record_id=new_id("cw"),
            bucket_id=submission.bucket_id,
            station_id=self.config.station_id,
            station_type="control",
            recorded_at_utc=now,
            control_weight_grams=filtered_weight,
            operator_note=submission.operator_note,
        )
        self.store.add_control_weight_record(record)
        self.store.enqueue(
            message_id=new_id("msg"),
            topic="control_weight_record",
            entity_id=record.control_weight_record_id,
            idempotency_key=f"control_weight_record:{record.control_weight_record_id}",
            payload=record.to_payload(),
            now=now,
        )
        LOGGER.info("captured control weight %sg for bucket %s", filtered_weight, submission.bucket_id)


class HeartbeatService:
    def __init__(self, config: AgentConfig, store: LocalStore) -> None:
        self.config = config
        self.store = store
        self._last_sent_monotonic = 0.0

    def tick(self) -> None:
        now_monotonic = time.monotonic()
        if now_monotonic - self._last_sent_monotonic < self.config.heartbeat_interval_seconds:
            return
        self._last_sent_monotonic = now_monotonic
        now = utc_now()
        heartbeat = DeviceHeartbeat(
            heartbeat_id=new_id("hb"),
            device_id=self.config.device_id,
            station_id=self.config.station_id,
            station_type=self.config.station_type,
            recorded_at_utc=now,
            agent_version=__version__,
            status="ok",
            details={
                "pending_outbox_count": self.store.count_pending_outbox(),
                "environment": "device",
            },
        )
        self.store.add_heartbeat(heartbeat)
        self.store.enqueue(
            message_id=new_id("msg"),
            topic="heartbeat",
            entity_id=heartbeat.heartbeat_id,
            idempotency_key=f"heartbeat:{heartbeat.heartbeat_id}",
            payload=heartbeat.to_payload(),
            now=now,
        )


def build_runtime(
    config: AgentConfig,
    store: LocalStore,
    scale_reader: ScaleReader,
    button_handler: ButtonHandler,
    control_input_handler: ControlInputHandler,
    video_provider: VideoProvider,
):
    heartbeat = HeartbeatService(config, store)
    if config.is_primary:
        station_service = PrimaryStationService(
            config=config,
            store=store,
            scale_reader=scale_reader,
            button_handler=button_handler,
            video_provider=video_provider,
        )
    else:
        station_service = ControlStationService(
            config=config,
            store=store,
            scale_reader=scale_reader,
            control_input_handler=control_input_handler,
        )
    return station_service, heartbeat
