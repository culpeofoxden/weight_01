from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal


StationType = Literal["primary", "control"]


@dataclass(slots=True)
class BucketSession:
    session_id: str
    bucket_id: str
    station_id: str
    station_type: StationType
    started_at_utc: datetime
    ended_at_utc: datetime | None
    status: Literal["active", "completed"]
    expected_final_weight_grams: int
    last_logged_weight_grams: int
    last_non_empty_weight_grams: int

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["started_at_utc"] = self.started_at_utc.isoformat()
        payload["ended_at_utc"] = self.ended_at_utc.isoformat() if self.ended_at_utc else None
        return payload


@dataclass(slots=True)
class WeightLogRecord:
    event_id: str
    bucket_id: str
    bucket_session_id: str
    station_id: str
    station_type: StationType
    recorded_at_utc: datetime
    weight_grams: int
    delta_grams: int
    raw_weight_grams: int
    reason: str

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["recorded_at_utc"] = self.recorded_at_utc.isoformat()
        return payload


@dataclass(slots=True)
class AnomalyEvent:
    anomaly_event_id: str
    bucket_id: str
    bucket_session_id: str
    station_id: str
    station_type: StationType
    event_type: str
    observed_at_utc: datetime
    delta_grams: int
    weight_before_grams: int
    weight_after_grams: int
    persistence_seconds: int
    video_metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["observed_at_utc"] = self.observed_at_utc.isoformat()
        return payload


@dataclass(slots=True)
class ControlWeightRecord:
    control_weight_record_id: str
    bucket_id: str
    station_id: str
    station_type: StationType
    recorded_at_utc: datetime
    control_weight_grams: int
    operator_note: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["recorded_at_utc"] = self.recorded_at_utc.isoformat()
        return payload


@dataclass(slots=True)
class DeviceHeartbeat:
    heartbeat_id: str
    device_id: str
    station_id: str
    station_type: StationType
    recorded_at_utc: datetime
    agent_version: str
    status: str
    details: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["recorded_at_utc"] = self.recorded_at_utc.isoformat()
        return payload


@dataclass(slots=True)
class ControlSubmission:
    bucket_id: str
    operator_note: str | None = None
