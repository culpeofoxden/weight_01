"""initial schema

Revision ID: 20260418_0001
Revises:
Create Date: 2026-04-18 23:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260418_0001"
down_revision = None
branch_labels = None
depends_on = None


user_role_enum = sa.Enum("admin", "viewer", name="userrole")
station_type_enum = sa.Enum("primary", "control", name="stationtype")
alert_type_enum = sa.Enum("primary_negative_delta", "control_discrepancy", name="alerttype")
alert_status_enum = sa.Enum("pending", "sent", "failed", name="alertstatus")


def upgrade() -> None:
    bind = op.get_bind()
    user_role_enum.create(bind, checkfirst=True)
    station_type_enum.create(bind, checkfirst=True)
    alert_type_enum.create(bind, checkfirst=True)
    alert_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_name", user_role_enum, nullable=False),
        sa.UniqueConstraint("user_id", "role_name", name="uq_roles_user_role"),
    )

    op.create_table(
        "stations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("station_id", sa.String(length=100), nullable=False),
        sa.Column("station_type", station_type_enum, nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_stations_station_id", "stations", ["station_id"], unique=True)

    op.create_table(
        "bucket_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bucket_session_id", sa.String(length=120), nullable=False),
        sa.Column("bucket_id", sa.String(length=120), nullable=False),
        sa.Column("station_id", sa.String(length=100), nullable=False),
        sa.Column("station_type", station_type_enum, nullable=False),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("expected_final_weight_grams", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_logged_weight_grams", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_non_empty_weight_grams", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_device_id", sa.String(length=120), nullable=True),
    )
    op.create_index("ix_bucket_sessions_bucket_session_id", "bucket_sessions", ["bucket_session_id"], unique=True)
    op.create_index("ix_bucket_sessions_bucket_id", "bucket_sessions", ["bucket_id"], unique=False)
    op.create_index("ix_bucket_sessions_station_id", "bucket_sessions", ["station_id"], unique=False)

    op.create_table(
        "weight_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(length=120), nullable=False),
        sa.Column("bucket_id", sa.String(length=120), nullable=False),
        sa.Column("bucket_session_id", sa.String(length=120), nullable=False),
        sa.Column("station_id", sa.String(length=100), nullable=False),
        sa.Column("station_type", station_type_enum, nullable=False),
        sa.Column("recorded_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("weight_grams", sa.Integer(), nullable=False),
        sa.Column("delta_grams", sa.Integer(), nullable=False),
        sa.Column("raw_weight_grams", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=False),
    )
    op.create_index("ix_weight_logs_event_id", "weight_logs", ["event_id"], unique=True)
    op.create_index("ix_weight_logs_bucket_id", "weight_logs", ["bucket_id"], unique=False)

    op.create_table(
        "anomaly_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("anomaly_event_id", sa.String(length=120), nullable=False),
        sa.Column("bucket_id", sa.String(length=120), nullable=False),
        sa.Column("bucket_session_id", sa.String(length=120), nullable=False),
        sa.Column("station_id", sa.String(length=100), nullable=False),
        sa.Column("station_type", station_type_enum, nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delta_grams", sa.Integer(), nullable=False),
        sa.Column("weight_before_grams", sa.Integer(), nullable=False),
        sa.Column("weight_after_grams", sa.Integer(), nullable=False),
        sa.Column("persistence_seconds", sa.Integer(), nullable=False),
        sa.Column("video_metadata", sa.JSON(), nullable=False),
    )
    op.create_index("ix_anomaly_events_anomaly_event_id", "anomaly_events", ["anomaly_event_id"], unique=True)

    op.create_table(
        "control_weight_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("control_weight_record_id", sa.String(length=120), nullable=False),
        sa.Column("bucket_id", sa.String(length=120), nullable=False),
        sa.Column("station_id", sa.String(length=100), nullable=False),
        sa.Column("station_type", station_type_enum, nullable=False),
        sa.Column("recorded_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("control_weight_grams", sa.Integer(), nullable=False),
        sa.Column("operator_note", sa.Text(), nullable=True),
    )
    op.create_index("ix_control_weight_records_control_weight_record_id", "control_weight_records", ["control_weight_record_id"], unique=True)
    op.create_index("ix_control_weight_records_bucket_id", "control_weight_records", ["bucket_id"], unique=False)

    op.create_table(
        "alert_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_key", sa.String(length=160), nullable=False),
        sa.Column("alert_type", alert_type_enum, nullable=False),
        sa.Column("bucket_id", sa.String(length=120), nullable=False),
        sa.Column("bucket_session_id", sa.String(length=120), nullable=True),
        sa.Column("station_id", sa.String(length=100), nullable=False),
        sa.Column("status", alert_status_enum, nullable=False, server_default="pending"),
        sa.Column("detected_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_weight_grams", sa.Integer(), nullable=True),
        sa.Column("actual_weight_grams", sa.Integer(), nullable=True),
        sa.Column("delta_grams", sa.Integer(), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("telegram_message_id", sa.String(length=120), nullable=True),
        sa.Column("sent_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
    )
    op.create_index("ix_alert_records_alert_key", "alert_records", ["alert_key"], unique=True)
    op.create_index("ix_alert_records_bucket_id", "alert_records", ["bucket_id"], unique=False)

    op.create_table(
        "global_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_global_settings_key", "global_settings", ["key"], unique=True)

    op.create_table(
        "device_heartbeats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("heartbeat_id", sa.String(length=120), nullable=False),
        sa.Column("device_id", sa.String(length=120), nullable=False),
        sa.Column("station_id", sa.String(length=100), nullable=False),
        sa.Column("station_type", station_type_enum, nullable=False),
        sa.Column("recorded_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agent_version", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_device_heartbeats_heartbeat_id", "device_heartbeats", ["heartbeat_id"], unique=True)

    op.create_table(
        "ingest_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("topic", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=False),
        sa.Column("first_seen_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_ingest_audit_idempotency_key", "ingest_audit", ["idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_ingest_audit_idempotency_key", table_name="ingest_audit")
    op.drop_table("ingest_audit")
    op.drop_index("ix_device_heartbeats_heartbeat_id", table_name="device_heartbeats")
    op.drop_table("device_heartbeats")
    op.drop_index("ix_global_settings_key", table_name="global_settings")
    op.drop_table("global_settings")
    op.drop_index("ix_alert_records_bucket_id", table_name="alert_records")
    op.drop_index("ix_alert_records_alert_key", table_name="alert_records")
    op.drop_table("alert_records")
    op.drop_index("ix_control_weight_records_bucket_id", table_name="control_weight_records")
    op.drop_index("ix_control_weight_records_control_weight_record_id", table_name="control_weight_records")
    op.drop_table("control_weight_records")
    op.drop_index("ix_anomaly_events_anomaly_event_id", table_name="anomaly_events")
    op.drop_table("anomaly_events")
    op.drop_index("ix_weight_logs_bucket_id", table_name="weight_logs")
    op.drop_index("ix_weight_logs_event_id", table_name="weight_logs")
    op.drop_table("weight_logs")
    op.drop_index("ix_bucket_sessions_station_id", table_name="bucket_sessions")
    op.drop_index("ix_bucket_sessions_bucket_id", table_name="bucket_sessions")
    op.drop_index("ix_bucket_sessions_bucket_session_id", table_name="bucket_sessions")
    op.drop_table("bucket_sessions")
    op.drop_index("ix_stations_station_id", table_name="stations")
    op.drop_table("stations")
    op.drop_table("roles")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    alert_status_enum.drop(bind, checkfirst=True)
    alert_type_enum.drop(bind, checkfirst=True)
    station_type_enum.drop(bind, checkfirst=True)
    user_role_enum.drop(bind, checkfirst=True)
