from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import require_role
from app.models.models import AlertRecord, AlertStatus, AlertType, User
from app.schemas import (
    DeviceAnomalyEventIn,
    DeviceBucketSessionIn,
    DeviceControlWeightIn,
    DeviceWeightLogIn,
    ScenarioRequest,
    ScenarioResponse,
    TelegramTestRequest,
    TelegramTestResponse,
)
from app.services.ingest_service import (
    ingest_anomaly_event,
    ingest_bucket_session,
    ingest_control_weight,
    ingest_weight_log,
)
from app.services.telegram_service import TelegramService


router = APIRouter(prefix="/api/v1/test", tags=["test"])


def _bucket_id(prefix: str, bucket_id: str | None) -> str:
    return bucket_id or f"{prefix}-{uuid4().hex[:8].upper()}"


def _session_id() -> str:
    return f"bs_test_{uuid4().hex}"


def _event_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _recent_alert_types(db: Session, bucket_id: str) -> list[str]:
    rows = (
        db.query(AlertRecord)
        .filter(AlertRecord.bucket_id == bucket_id)
        .order_by(AlertRecord.detected_at_utc.asc())
        .all()
    )
    return [row.alert_type.value for row in rows]


@router.post("/telegram-alert", response_model=TelegramTestResponse)
def send_test_telegram_alert(
    payload: TelegramTestRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
) -> TelegramTestResponse:
    now = datetime.now(timezone.utc)
    message = payload.message or (
        "TEST ALERT: amber monitoring backend\n"
        "This is a manual Telegram delivery test.\n"
        f"timestamp_utc={now.isoformat()}\n"
        "status=connectivity_check"
    )

    alert = AlertRecord(
        alert_key=f"test-telegram:{now.isoformat()}",
        alert_type=AlertType.primary_negative_delta,
        bucket_id="TEST-BUCKET",
        bucket_session_id=None,
        station_id="test-station",
        status=AlertStatus.pending,
        detected_at_utc=now,
        expected_weight_grams=None,
        actual_weight_grams=None,
        delta_grams=0,
        message_text=message,
        payload_json={"kind": "telegram_test"},
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    telegram = TelegramService()
    success, detail = telegram.send_alert(alert)
    telegram.mark_result(alert, success, detail)
    db.commit()

    return TelegramTestResponse(
        success=success,
        detail=detail,
        target_chat_id=telegram.settings.telegram_chat_id,
    )


@router.post("/scenarios/normal-cycle", response_model=ScenarioResponse)
def create_normal_cycle_scenario(
    payload: ScenarioRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
) -> ScenarioResponse:
    now = datetime.now(timezone.utc)
    bucket_id = _bucket_id("NORMAL", payload.bucket_id)
    bucket_session_id = _session_id()

    ingest_bucket_session(
        db,
        DeviceBucketSessionIn(
            bucket_session_id=bucket_session_id,
            bucket_id=bucket_id,
            station_id=payload.primary_station_id,
            station_type="primary",
            started_at_utc=now - timedelta(minutes=3),
            ended_at_utc=now - timedelta(minutes=1),
            status="completed",
            expected_final_weight_grams=payload.expected_final_weight_grams,
            last_logged_weight_grams=payload.expected_final_weight_grams,
            last_non_empty_weight_grams=payload.expected_final_weight_grams,
            source_device_id="sim-primary-01",
        ),
        f"test:bucket_session:{bucket_session_id}:normal",
    )

    ingest_weight_log(
        db,
        DeviceWeightLogIn(
            event_id=_event_id("wl"),
            bucket_id=bucket_id,
            bucket_session_id=bucket_session_id,
            station_id=payload.primary_station_id,
            station_type="primary",
            recorded_at_utc=now - timedelta(minutes=2, seconds=30),
            weight_grams=600,
            delta_grams=600,
            raw_weight_grams=600,
            reason="simulation_fill",
        ),
        f"test:weight_log:{bucket_session_id}:1",
    )
    ingest_weight_log(
        db,
        DeviceWeightLogIn(
            event_id=_event_id("wl"),
            bucket_id=bucket_id,
            bucket_session_id=bucket_session_id,
            station_id=payload.primary_station_id,
            station_type="primary",
            recorded_at_utc=now - timedelta(minutes=2),
            weight_grams=payload.expected_final_weight_grams,
            delta_grams=payload.expected_final_weight_grams - 600,
            raw_weight_grams=payload.expected_final_weight_grams,
            reason="simulation_fill",
        ),
        f"test:weight_log:{bucket_session_id}:2",
    )
    ingest_control_weight(
        db,
        DeviceControlWeightIn(
            control_weight_record_id=_event_id("cw"),
            bucket_id=bucket_id,
            station_id=payload.control_station_id,
            station_type="control",
            recorded_at_utc=now,
            control_weight_grams=payload.expected_final_weight_grams,
            operator_note="simulation_normal_cycle",
        ),
        f"test:control_weight:{bucket_session_id}:normal",
    )

    return ScenarioResponse(
        scenario="normal-cycle",
        bucket_id=bucket_id,
        bucket_session_id=bucket_session_id,
        created_alert_types=_recent_alert_types(db, bucket_id),
        notes=["Created completed primary session and matching control weight.", "Expected result: no discrepancy alert."],
    )


@router.post("/scenarios/primary-negative-delta", response_model=ScenarioResponse)
def create_primary_negative_delta_scenario(
    payload: ScenarioRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
) -> ScenarioResponse:
    now = datetime.now(timezone.utc)
    bucket_id = _bucket_id("NEG", payload.bucket_id)
    bucket_session_id = _session_id()
    weight_after = payload.expected_final_weight_grams + payload.negative_delta_grams

    ingest_bucket_session(
        db,
        DeviceBucketSessionIn(
            bucket_session_id=bucket_session_id,
            bucket_id=bucket_id,
            station_id=payload.primary_station_id,
            station_type="primary",
            started_at_utc=now - timedelta(minutes=2),
            ended_at_utc=None,
            status="active",
            expected_final_weight_grams=payload.expected_final_weight_grams,
            last_logged_weight_grams=weight_after,
            last_non_empty_weight_grams=payload.expected_final_weight_grams,
            source_device_id="sim-primary-01",
        ),
        f"test:bucket_session:{bucket_session_id}:negative",
    )
    ingest_weight_log(
        db,
        DeviceWeightLogIn(
            event_id=_event_id("wl"),
            bucket_id=bucket_id,
            bucket_session_id=bucket_session_id,
            station_id=payload.primary_station_id,
            station_type="primary",
            recorded_at_utc=now - timedelta(seconds=20),
            weight_grams=payload.expected_final_weight_grams,
            delta_grams=payload.expected_final_weight_grams,
            raw_weight_grams=payload.expected_final_weight_grams,
            reason="simulation_fill",
        ),
        f"test:weight_log:{bucket_session_id}:negative:1",
    )
    ingest_anomaly_event(
        db,
        DeviceAnomalyEventIn(
            anomaly_event_id=_event_id("an"),
            bucket_id=bucket_id,
            bucket_session_id=bucket_session_id,
            station_id=payload.primary_station_id,
            station_type="primary",
            event_type="unexpected_negative_primary_delta",
            observed_at_utc=now,
            delta_grams=payload.negative_delta_grams,
            weight_before_grams=payload.expected_final_weight_grams,
            weight_after_grams=weight_after,
            persistence_seconds=3,
            video_metadata={"provider": "stub", "scenario": "primary_negative_delta"},
        ),
        f"test:anomaly:{bucket_session_id}",
    )

    return ScenarioResponse(
        scenario="primary-negative-delta",
        bucket_id=bucket_id,
        bucket_session_id=bucket_session_id,
        created_alert_types=_recent_alert_types(db, bucket_id),
        notes=["Created active primary session and anomaly candidate.", "Expected result: primary_negative_delta alert and Telegram message."],
    )


@router.post("/scenarios/control-discrepancy", response_model=ScenarioResponse)
def create_control_discrepancy_scenario(
    payload: ScenarioRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
) -> ScenarioResponse:
    now = datetime.now(timezone.utc)
    bucket_id = _bucket_id("DISC", payload.bucket_id)
    bucket_session_id = _session_id()

    ingest_bucket_session(
        db,
        DeviceBucketSessionIn(
            bucket_session_id=bucket_session_id,
            bucket_id=bucket_id,
            station_id=payload.primary_station_id,
            station_type="primary",
            started_at_utc=now - timedelta(minutes=4),
            ended_at_utc=now - timedelta(minutes=2),
            status="completed",
            expected_final_weight_grams=payload.expected_final_weight_grams,
            last_logged_weight_grams=payload.expected_final_weight_grams,
            last_non_empty_weight_grams=payload.expected_final_weight_grams,
            source_device_id="sim-primary-01",
        ),
        f"test:bucket_session:{bucket_session_id}:discrepancy",
    )
    ingest_weight_log(
        db,
        DeviceWeightLogIn(
            event_id=_event_id("wl"),
            bucket_id=bucket_id,
            bucket_session_id=bucket_session_id,
            station_id=payload.primary_station_id,
            station_type="primary",
            recorded_at_utc=now - timedelta(minutes=3),
            weight_grams=payload.expected_final_weight_grams,
            delta_grams=payload.expected_final_weight_grams,
            raw_weight_grams=payload.expected_final_weight_grams,
            reason="simulation_fill",
        ),
        f"test:weight_log:{bucket_session_id}:discrepancy:1",
    )
    ingest_control_weight(
        db,
        DeviceControlWeightIn(
            control_weight_record_id=_event_id("cw"),
            bucket_id=bucket_id,
            station_id=payload.control_station_id,
            station_type="control",
            recorded_at_utc=now,
            control_weight_grams=payload.control_weight_grams,
            operator_note="simulation_discrepancy",
        ),
        f"test:control_weight:{bucket_session_id}:discrepancy",
    )

    return ScenarioResponse(
        scenario="control-discrepancy",
        bucket_id=bucket_id,
        bucket_session_id=bucket_session_id,
        created_alert_types=_recent_alert_types(db, bucket_id),
        notes=["Created completed primary session and lower control weight.", "Expected result: control_discrepancy alert and Telegram message."],
    )
