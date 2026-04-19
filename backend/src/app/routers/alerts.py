from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models.models import AlertRecord, User
from app.schemas import AlertResponse


router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertResponse])
def list_alerts(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    bucket_id: str | None = Query(default=None),
    alert_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[AlertResponse]:
    query = db.query(AlertRecord)
    if bucket_id:
        query = query.filter(AlertRecord.bucket_id == bucket_id)
    if alert_type:
        query = query.filter(AlertRecord.alert_type == alert_type)
    if date_from:
        query = query.filter(AlertRecord.detected_at_utc >= date_from)
    if date_to:
        query = query.filter(AlertRecord.detected_at_utc <= date_to)
    rows = query.order_by(AlertRecord.detected_at_utc.desc()).all()
    return [
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
        for row in rows
    ]
