import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    viewer = "viewer"


class StationType(str, enum.Enum):
    primary = "primary"
    control = "control"


class AlertType(str, enum.Enum):
    primary_negative_delta = "primary_negative_delta"
    control_discrepancy = "control_discrepancy"


class AlertStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    roles: Mapped[list["RoleAssignment"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class RoleAssignment(Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("user_id", "role_name", name="uq_roles_user_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role_name: Mapped[UserRole] = mapped_column(Enum(UserRole))

    user: Mapped[User] = relationship(back_populates="roles")


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    station_type: Mapped[StationType] = mapped_column(Enum(StationType))
    display_name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class BucketSession(Base):
    __tablename__ = "bucket_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    bucket_session_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    bucket_id: Mapped[str] = mapped_column(String(120), index=True)
    station_id: Mapped[str] = mapped_column(String(100), index=True)
    station_type: Mapped[StationType] = mapped_column(Enum(StationType))
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    expected_final_weight_grams: Mapped[int] = mapped_column(Integer, default=0)
    last_logged_weight_grams: Mapped[int] = mapped_column(Integer, default=0)
    last_non_empty_weight_grams: Mapped[int] = mapped_column(Integer, default=0)
    source_device_id: Mapped[str | None] = mapped_column(String(120), nullable=True)


class WeightLog(Base):
    __tablename__ = "weight_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    bucket_id: Mapped[str] = mapped_column(String(120), index=True)
    bucket_session_id: Mapped[str] = mapped_column(String(120), index=True)
    station_id: Mapped[str] = mapped_column(String(100), index=True)
    station_type: Mapped[StationType] = mapped_column(Enum(StationType))
    recorded_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    weight_grams: Mapped[int] = mapped_column(Integer)
    delta_grams: Mapped[int] = mapped_column(Integer)
    raw_weight_grams: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(100))


class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    anomaly_event_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    bucket_id: Mapped[str] = mapped_column(String(120), index=True)
    bucket_session_id: Mapped[str] = mapped_column(String(120), index=True)
    station_id: Mapped[str] = mapped_column(String(100), index=True)
    station_type: Mapped[StationType] = mapped_column(Enum(StationType))
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    observed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    delta_grams: Mapped[int] = mapped_column(Integer)
    weight_before_grams: Mapped[int] = mapped_column(Integer)
    weight_after_grams: Mapped[int] = mapped_column(Integer)
    persistence_seconds: Mapped[int] = mapped_column(Integer)
    video_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class ControlWeightRecord(Base):
    __tablename__ = "control_weight_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    control_weight_record_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    bucket_id: Mapped[str] = mapped_column(String(120), index=True)
    station_id: Mapped[str] = mapped_column(String(100), index=True)
    station_type: Mapped[StationType] = mapped_column(Enum(StationType))
    recorded_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    control_weight_grams: Mapped[int] = mapped_column(Integer)
    operator_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class AlertRecord(Base):
    __tablename__ = "alert_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    alert_type: Mapped[AlertType] = mapped_column(Enum(AlertType), index=True)
    bucket_id: Mapped[str] = mapped_column(String(120), index=True)
    bucket_session_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    station_id: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[AlertStatus] = mapped_column(Enum(AlertStatus), default=AlertStatus.pending)
    detected_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expected_weight_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_weight_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delta_grams: Mapped[int] = mapped_column(Integer)
    message_text: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    telegram_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sent_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class GlobalSetting(Base):
    __tablename__ = "global_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    value: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(255))
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class DeviceHeartbeat(Base):
    __tablename__ = "device_heartbeats"

    id: Mapped[int] = mapped_column(primary_key=True)
    heartbeat_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    device_id: Mapped[str] = mapped_column(String(120), index=True)
    station_id: Mapped[str] = mapped_column(String(100), index=True)
    station_type: Mapped[StationType] = mapped_column(Enum(StationType))
    recorded_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    agent_version: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50))
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)


class IngestAudit(Base):
    __tablename__ = "ingest_audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    topic: Mapped[str] = mapped_column(String(100), index=True)
    entity_id: Mapped[str] = mapped_column(String(120), index=True)
    first_seen_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_seen_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict)
