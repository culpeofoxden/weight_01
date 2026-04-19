from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models.models import AlertRecord, AlertType, BucketSession, ControlWeightRecord, StationType, User
from app.schemas import AnalyticsSummaryResponse


router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummaryResponse)
def get_analytics_summary(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> AnalyticsSummaryResponse:
    total_buckets = db.query(func.count(BucketSession.id)).filter(BucketSession.station_type == StationType.primary).scalar() or 0
    anomaly_alerts = db.query(func.count(AlertRecord.id)).filter(AlertRecord.alert_type == AlertType.primary_negative_delta).scalar() or 0
    discrepancy_alerts = db.query(func.count(AlertRecord.id)).filter(AlertRecord.alert_type == AlertType.control_discrepancy).scalar() or 0

    joined = (
        db.query(BucketSession.expected_final_weight_grams, ControlWeightRecord.control_weight_grams)
        .join(ControlWeightRecord, ControlWeightRecord.bucket_id == BucketSession.bucket_id)
        .filter(BucketSession.station_type == StationType.primary)
        .all()
    )
    deltas = [control - expected for expected, control in joined]
    average_discrepancy = (sum(deltas) / len(deltas)) if deltas else 0.0

    ranges = [
        {"label": "0-99g", "count": len([d for d in deltas if -99 <= d <= 0])},
        {"label": "-100 to -299g", "count": len([d for d in deltas if -299 <= d <= -100])},
        {"label": "< -300g", "count": len([d for d in deltas if d < -300])},
    ]

    return AnalyticsSummaryResponse(
        total_buckets=int(total_buckets),
        anomaly_alerts=int(anomaly_alerts),
        discrepancy_alerts=int(discrepancy_alerts),
        average_discrepancy_grams=float(average_discrepancy),
        common_loss_ranges=ranges,
    )
