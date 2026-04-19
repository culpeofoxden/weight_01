from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import (
    AnomalyEvent,
    BucketSession,
    ControlWeightRecord,
    DeviceHeartbeat,
    IngestAudit,
    WeightLog,
)
from app.schemas import (
    DeviceAnomalyEventIn,
    DeviceBucketSessionIn,
    DeviceControlWeightIn,
    DeviceHeartbeatIn,
    DeviceWeightLogIn,
)
from app.services.alert_service import AlertService


def _touch_audit(db: Session, *, idempotency_key: str, topic: str, entity_id: str, payload: dict) -> bool:
    existing = db.query(IngestAudit).filter(IngestAudit.idempotency_key == idempotency_key).one_or_none()
    if existing:
        existing.last_seen_at_utc = datetime.now(timezone.utc)
        db.commit()
        return True

    db.add(
        IngestAudit(
            idempotency_key=idempotency_key,
            topic=topic,
            entity_id=entity_id,
            request_payload=payload,
        )
    )
    db.commit()
    return False


def ingest_weight_log(db: Session, payload: DeviceWeightLogIn, idempotency_key: str) -> bool:
    duplicate = _touch_audit(db, idempotency_key=idempotency_key, topic="weight_log", entity_id=payload.event_id, payload=payload.model_dump(mode="json"))
    if duplicate:
        return True

    db.merge(
        WeightLog(
            event_id=payload.event_id,
            bucket_id=payload.bucket_id,
            bucket_session_id=payload.bucket_session_id,
            station_id=payload.station_id,
            station_type=payload.station_type,
            recorded_at_utc=payload.recorded_at_utc,
            weight_grams=payload.weight_grams,
            delta_grams=payload.delta_grams,
            raw_weight_grams=payload.raw_weight_grams,
            reason=payload.reason,
        )
    )
    db.commit()
    return False


def ingest_bucket_session(db: Session, payload: DeviceBucketSessionIn, idempotency_key: str) -> bool:
    duplicate = _touch_audit(db, idempotency_key=idempotency_key, topic="bucket_session", entity_id=payload.bucket_session_id, payload=payload.model_dump(mode="json"))
    if duplicate:
        return True

    existing = db.query(BucketSession).filter(BucketSession.bucket_session_id == payload.bucket_session_id).one_or_none()
    if existing:
        existing.bucket_id = payload.bucket_id
        existing.station_id = payload.station_id
        existing.station_type = payload.station_type
        existing.started_at_utc = payload.started_at_utc
        existing.ended_at_utc = payload.ended_at_utc
        existing.status = payload.status
        existing.expected_final_weight_grams = payload.expected_final_weight_grams
        existing.last_logged_weight_grams = payload.last_logged_weight_grams
        existing.last_non_empty_weight_grams = payload.last_non_empty_weight_grams
        existing.source_device_id = payload.source_device_id
    else:
        db.add(
            BucketSession(
                bucket_session_id=payload.bucket_session_id,
                bucket_id=payload.bucket_id,
                station_id=payload.station_id,
                station_type=payload.station_type,
                started_at_utc=payload.started_at_utc,
                ended_at_utc=payload.ended_at_utc,
                status=payload.status,
                expected_final_weight_grams=payload.expected_final_weight_grams,
                last_logged_weight_grams=payload.last_logged_weight_grams,
                last_non_empty_weight_grams=payload.last_non_empty_weight_grams,
                source_device_id=payload.source_device_id,
            )
        )
    db.commit()
    return False


def ingest_anomaly_event(db: Session, payload: DeviceAnomalyEventIn, idempotency_key: str) -> bool:
    duplicate = _touch_audit(db, idempotency_key=idempotency_key, topic="anomaly_event", entity_id=payload.anomaly_event_id, payload=payload.model_dump(mode="json"))
    if duplicate:
        return True

    db.merge(
        AnomalyEvent(
            anomaly_event_id=payload.anomaly_event_id,
            bucket_id=payload.bucket_id,
            bucket_session_id=payload.bucket_session_id,
            station_id=payload.station_id,
            station_type=payload.station_type,
            event_type=payload.event_type,
            observed_at_utc=payload.observed_at_utc,
            delta_grams=payload.delta_grams,
            weight_before_grams=payload.weight_before_grams,
            weight_after_grams=payload.weight_after_grams,
            persistence_seconds=payload.persistence_seconds,
            video_metadata=payload.video_metadata,
        )
    )
    db.commit()
    AlertService(db).handle_primary_negative_candidate(
        bucket_id=payload.bucket_id,
        bucket_session_id=payload.bucket_session_id,
        station_id=payload.station_id,
        observed_at_utc=payload.observed_at_utc,
        delta_grams=payload.delta_grams,
        weight_before_grams=payload.weight_before_grams,
        weight_after_grams=payload.weight_after_grams,
        video_metadata=payload.video_metadata,
    )
    return False


def ingest_control_weight(db: Session, payload: DeviceControlWeightIn, idempotency_key: str) -> bool:
    duplicate = _touch_audit(db, idempotency_key=idempotency_key, topic="control_weight_record", entity_id=payload.control_weight_record_id, payload=payload.model_dump(mode="json"))
    if duplicate:
        return True

    record = ControlWeightRecord(
        control_weight_record_id=payload.control_weight_record_id,
        bucket_id=payload.bucket_id,
        station_id=payload.station_id,
        station_type=payload.station_type,
        recorded_at_utc=payload.recorded_at_utc,
        control_weight_grams=payload.control_weight_grams,
        operator_note=payload.operator_note,
    )
    db.merge(record)
    db.commit()
    record = db.query(ControlWeightRecord).filter(ControlWeightRecord.control_weight_record_id == payload.control_weight_record_id).one()
    AlertService(db).handle_control_weight(record)
    return False


def ingest_heartbeat(db: Session, payload: DeviceHeartbeatIn, idempotency_key: str) -> bool:
    duplicate = _touch_audit(db, idempotency_key=idempotency_key, topic="heartbeat", entity_id=payload.heartbeat_id, payload=payload.model_dump(mode="json"))
    if duplicate:
        return True

    db.merge(
        DeviceHeartbeat(
            heartbeat_id=payload.heartbeat_id,
            device_id=payload.device_id,
            station_id=payload.station_id,
            station_type=payload.station_type,
            recorded_at_utc=payload.recorded_at_utc,
            agent_version=payload.agent_version,
            status=payload.status,
            details_json=payload.details,
        )
    )
    db.commit()
    return False
