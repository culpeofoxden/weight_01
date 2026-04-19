from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    roles: list[str]


class DeviceWeightLogIn(BaseModel):
    event_id: str
    bucket_id: str
    bucket_session_id: str
    station_id: str
    station_type: Literal["primary", "control"]
    recorded_at_utc: datetime
    weight_grams: int
    delta_grams: int
    raw_weight_grams: int
    reason: str


class DeviceBucketSessionIn(BaseModel):
    bucket_session_id: str
    bucket_id: str
    station_id: str
    station_type: Literal["primary", "control"]
    started_at_utc: datetime
    ended_at_utc: datetime | None = None
    status: str
    expected_final_weight_grams: int = 0
    last_logged_weight_grams: int = 0
    last_non_empty_weight_grams: int = 0
    source_device_id: str | None = None


class DeviceAnomalyEventIn(BaseModel):
    anomaly_event_id: str
    bucket_id: str
    bucket_session_id: str
    station_id: str
    station_type: Literal["primary", "control"]
    event_type: str
    observed_at_utc: datetime
    delta_grams: int
    weight_before_grams: int
    weight_after_grams: int
    persistence_seconds: int
    video_metadata: dict[str, Any] = Field(default_factory=dict)


class DeviceControlWeightIn(BaseModel):
    control_weight_record_id: str
    bucket_id: str
    station_id: str
    station_type: Literal["primary", "control"]
    recorded_at_utc: datetime
    control_weight_grams: int
    operator_note: str | None = None


class DeviceHeartbeatIn(BaseModel):
    heartbeat_id: str
    device_id: str
    station_id: str
    station_type: Literal["primary", "control"]
    recorded_at_utc: datetime
    agent_version: str
    status: str
    details: dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    status: str
    entity_id: str
    duplicate: bool = False


class AlertResponse(BaseModel):
    alert_type: str
    bucket_id: str
    station_id: str
    delta_grams: int
    expected_weight_grams: int | None
    actual_weight_grams: int | None
    status: str
    detected_at_utc: datetime
    message_text: str


class BucketSummaryResponse(BaseModel):
    bucket_id: str
    bucket_session_id: str | None
    primary_station_id: str | None
    primary_started_at_utc: datetime | None
    primary_ended_at_utc: datetime | None
    expected_final_weight_grams: int | None
    control_weight_grams: int | None
    discrepancy_grams: int | None
    status: str


class BucketDetailResponse(BaseModel):
    summary: BucketSummaryResponse
    weight_logs: list[DeviceWeightLogIn]
    anomaly_events: list[DeviceAnomalyEventIn]
    control_records: list[DeviceControlWeightIn]
    alerts: list[AlertResponse]


class AnalyticsSummaryResponse(BaseModel):
    total_buckets: int
    anomaly_alerts: int
    discrepancy_alerts: int
    average_discrepancy_grams: float
    common_loss_ranges: list[dict[str, Any]]


class GlobalSettingItem(BaseModel):
    key: str
    value: str
    description: str


class GlobalSettingsUpdate(BaseModel):
    items: list[GlobalSettingItem]


class TelegramTestRequest(BaseModel):
    message: str | None = None


class TelegramTestResponse(BaseModel):
    success: bool
    detail: str | None = None
    target_chat_id: str


class ScenarioRequest(BaseModel):
    bucket_id: str | None = None
    primary_station_id: str = "primary-line-01"
    control_station_id: str = "control-room-01"
    expected_final_weight_grams: int = 1200
    control_weight_grams: int = 1000
    negative_delta_grams: int = -180


class ScenarioResponse(BaseModel):
    scenario: str
    bucket_id: str
    bucket_session_id: str
    created_alert_types: list[str]
    notes: list[str]
