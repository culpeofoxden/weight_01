from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import require_device_api_key
from app.schemas import (
    DeviceAnomalyEventIn,
    DeviceBucketSessionIn,
    DeviceControlWeightIn,
    DeviceHeartbeatIn,
    DeviceWeightLogIn,
    IngestResponse,
)
from app.services.ingest_service import (
    ingest_anomaly_event,
    ingest_bucket_session,
    ingest_control_weight,
    ingest_heartbeat,
    ingest_weight_log,
)


router = APIRouter(prefix="/api/v1/device", tags=["device"])


def _make_key(topic: str, header_key: str | None, entity_id: str) -> str:
    return header_key or f"{topic}:{entity_id}"


@router.post("/weight-logs", response_model=IngestResponse)
def create_weight_log(
    payload: DeviceWeightLogIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_device_api_key),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> IngestResponse:
    key = _make_key("weight_log", idempotency_key, payload.event_id)
    duplicate = ingest_weight_log(db, payload, key)
    return IngestResponse(status="ok", entity_id=payload.event_id, duplicate=duplicate)


@router.post("/bucket-sessions", response_model=IngestResponse)
def create_bucket_session(
    payload: DeviceBucketSessionIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_device_api_key),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> IngestResponse:
    key = _make_key("bucket_session", idempotency_key, payload.bucket_session_id)
    duplicate = ingest_bucket_session(db, payload, key)
    return IngestResponse(status="ok", entity_id=payload.bucket_session_id, duplicate=duplicate)


@router.post("/anomaly-candidates", response_model=IngestResponse)
def create_anomaly_event(
    payload: DeviceAnomalyEventIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_device_api_key),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> IngestResponse:
    key = _make_key("anomaly_event", idempotency_key, payload.anomaly_event_id)
    duplicate = ingest_anomaly_event(db, payload, key)
    return IngestResponse(status="ok", entity_id=payload.anomaly_event_id, duplicate=duplicate)


@router.post("/control-weight-records", response_model=IngestResponse)
def create_control_weight(
    payload: DeviceControlWeightIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_device_api_key),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> IngestResponse:
    key = _make_key("control_weight_record", idempotency_key, payload.control_weight_record_id)
    duplicate = ingest_control_weight(db, payload, key)
    return IngestResponse(status="ok", entity_id=payload.control_weight_record_id, duplicate=duplicate)


@router.post("/heartbeats", response_model=IngestResponse)
def create_heartbeat(
    payload: DeviceHeartbeatIn,
    db: Session = Depends(get_db),
    _: str = Depends(require_device_api_key),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> IngestResponse:
    key = _make_key("heartbeat", idempotency_key, payload.heartbeat_id)
    duplicate = ingest_heartbeat(db, payload, key)
    return IngestResponse(status="ok", entity_id=payload.heartbeat_id, duplicate=duplicate)
