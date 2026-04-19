import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models.models import AlertRecord, AnomalyEvent, BucketSession, ControlWeightRecord, StationType, User, WeightLog
from app.schemas import (
    AlertResponse,
    BucketDetailResponse,
    BucketSummaryResponse,
    DeviceAnomalyEventIn,
    DeviceControlWeightIn,
    DeviceWeightLogIn,
)


router = APIRouter(prefix="/api/v1/buckets", tags=["buckets"])


@router.get("", response_model=list[BucketSummaryResponse])
def list_buckets(
    bucket_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    station_id: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[BucketSummaryResponse]:
    query = db.query(BucketSession).filter(BucketSession.station_type == StationType.primary)
    if bucket_id:
        query = query.filter(BucketSession.bucket_id == bucket_id)
    if status:
        query = query.filter(BucketSession.status == status)
    if station_id:
        query = query.filter(BucketSession.station_id == station_id)
    if date_from:
        query = query.filter(BucketSession.started_at_utc >= date_from)
    if date_to:
        query = query.filter(BucketSession.started_at_utc <= date_to)

    sessions = query.order_by(BucketSession.started_at_utc.desc()).all()
    result = []
    for session in sessions:
        control = (
            db.query(ControlWeightRecord)
            .filter(ControlWeightRecord.bucket_id == session.bucket_id)
            .order_by(ControlWeightRecord.recorded_at_utc.desc())
            .first()
        )
        control_weight = control.control_weight_grams if control else None
        discrepancy = None if control_weight is None else control_weight - session.expected_final_weight_grams
        result.append(
            BucketSummaryResponse(
                bucket_id=session.bucket_id,
                bucket_session_id=session.bucket_session_id,
                primary_station_id=session.station_id,
                primary_started_at_utc=session.started_at_utc,
                primary_ended_at_utc=session.ended_at_utc,
                expected_final_weight_grams=session.expected_final_weight_grams,
                control_weight_grams=control_weight,
                discrepancy_grams=discrepancy,
                status=session.status,
            )
        )
    return result


@router.get("/{bucket_id}", response_model=BucketDetailResponse)
def get_bucket_detail(
    bucket_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> BucketDetailResponse:
    session = (
        db.query(BucketSession)
        .filter(BucketSession.bucket_id == bucket_id, BucketSession.station_type == StationType.primary)
        .order_by(BucketSession.started_at_utc.desc())
        .first()
    )
    control_rows = db.query(ControlWeightRecord).filter(ControlWeightRecord.bucket_id == bucket_id).order_by(ControlWeightRecord.recorded_at_utc.asc()).all()
    alert_rows = db.query(AlertRecord).filter(AlertRecord.bucket_id == bucket_id).order_by(AlertRecord.detected_at_utc.asc()).all()
    log_rows = db.query(WeightLog).filter(WeightLog.bucket_id == bucket_id).order_by(WeightLog.recorded_at_utc.asc()).all()
    anomaly_rows = db.query(AnomalyEvent).filter(AnomalyEvent.bucket_id == bucket_id).order_by(AnomalyEvent.observed_at_utc.asc()).all()

    control_weight = control_rows[-1].control_weight_grams if control_rows else None
    discrepancy = None
    if session and control_weight is not None:
        discrepancy = control_weight - session.expected_final_weight_grams

    summary = BucketSummaryResponse(
        bucket_id=bucket_id,
        bucket_session_id=session.bucket_session_id if session else None,
        primary_station_id=session.station_id if session else None,
        primary_started_at_utc=session.started_at_utc if session else None,
        primary_ended_at_utc=session.ended_at_utc if session else None,
        expected_final_weight_grams=session.expected_final_weight_grams if session else None,
        control_weight_grams=control_weight,
        discrepancy_grams=discrepancy,
        status=session.status if session else "unknown",
    )

    return BucketDetailResponse(
        summary=summary,
        weight_logs=[
            DeviceWeightLogIn(
                event_id=row.event_id,
                bucket_id=row.bucket_id,
                bucket_session_id=row.bucket_session_id,
                station_id=row.station_id,
                station_type=row.station_type.value,
                recorded_at_utc=row.recorded_at_utc,
                weight_grams=row.weight_grams,
                delta_grams=row.delta_grams,
                raw_weight_grams=row.raw_weight_grams,
                reason=row.reason,
            )
            for row in log_rows
        ],
        anomaly_events=[
            DeviceAnomalyEventIn(
                anomaly_event_id=row.anomaly_event_id,
                bucket_id=row.bucket_id,
                bucket_session_id=row.bucket_session_id,
                station_id=row.station_id,
                station_type=row.station_type.value,
                event_type=row.event_type,
                observed_at_utc=row.observed_at_utc,
                delta_grams=row.delta_grams,
                weight_before_grams=row.weight_before_grams,
                weight_after_grams=row.weight_after_grams,
                persistence_seconds=row.persistence_seconds,
                video_metadata=row.video_metadata,
            )
            for row in anomaly_rows
        ],
        control_records=[
            DeviceControlWeightIn(
                control_weight_record_id=row.control_weight_record_id,
                bucket_id=row.bucket_id,
                station_id=row.station_id,
                station_type=row.station_type.value,
                recorded_at_utc=row.recorded_at_utc,
                control_weight_grams=row.control_weight_grams,
                operator_note=row.operator_note,
            )
            for row in control_rows
        ],
        alerts=[
            AlertResponse(
                alert_type=row.alert_type.value,
                bucket_id=row.bucket_id,
                station_id=row.station_id,
                delta_grams=row.delta_grams,
                expected_weight_grams=row.expected_weight_grams,
                actual_weight_grams=row.actual_weight_grams,
                status=row.status.value,
                detected_at_utc=row.detected_at_utc,
                message_text=row.message_text,
            )
            for row in alert_rows
        ],
    )


@router.get("/{bucket_id}/raw-logs.csv")
def export_bucket_logs_csv(
    bucket_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> StreamingResponse:
    rows = db.query(WeightLog).filter(WeightLog.bucket_id == bucket_id).order_by(WeightLog.recorded_at_utc.asc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["event_id", "bucket_id", "bucket_session_id", "station_id", "station_type", "recorded_at_utc", "weight_grams", "delta_grams", "raw_weight_grams", "reason"])
    for row in rows:
        writer.writerow([row.event_id, row.bucket_id, row.bucket_session_id, row.station_id, row.station_type.value, row.recorded_at_utc.isoformat(), row.weight_grams, row.delta_grams, row.raw_weight_grams, row.reason])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{bucket_id}-raw-logs.csv"'})
