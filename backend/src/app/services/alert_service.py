from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import AlertRecord, AlertType, BucketSession, ControlWeightRecord, StationType
from app.services.settings_service import get_setting_map
from app.services.telegram_service import TelegramService


class AlertService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.telegram = TelegramService()

    def handle_primary_negative_candidate(
        self,
        *,
        bucket_id: str,
        bucket_session_id: str,
        station_id: str,
        observed_at_utc: datetime,
        delta_grams: int,
        weight_before_grams: int,
        weight_after_grams: int,
        video_metadata: dict,
    ) -> AlertRecord | None:
        settings = get_setting_map(self.db)
        threshold = int(settings["negative_delta_threshold"])
        if delta_grams > threshold:
            return None

        alert_key = f"primary-negative:{bucket_session_id}:{observed_at_utc.isoformat()}:{delta_grams}"
        existing = self.db.query(AlertRecord).filter(AlertRecord.alert_key == alert_key).one_or_none()
        if existing:
            return existing

        message = (
            "ALERT: unexpected negative delta on primary station\n"
            f"bucket_id={bucket_id}\n"
            f"station_id={station_id}\n"
            f"timestamp_utc={observed_at_utc.isoformat()}\n"
            f"expected_weight={weight_before_grams} g\n"
            f"actual_weight={weight_after_grams} g\n"
            f"delta={delta_grams} g\n"
            "Reason: bucket got lighter while still active on the primary scale."
        )
        if video_metadata:
            message += f"\nvideo={video_metadata}"

        alert = AlertRecord(
            alert_key=alert_key,
            alert_type=AlertType.primary_negative_delta,
            bucket_id=bucket_id,
            bucket_session_id=bucket_session_id,
            station_id=station_id,
            detected_at_utc=observed_at_utc,
            expected_weight_grams=weight_before_grams,
            actual_weight_grams=weight_after_grams,
            delta_grams=delta_grams,
            message_text=message,
            payload_json={"video_metadata": video_metadata},
        )
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        success, detail = self.telegram.send_alert(alert)
        self.telegram.mark_result(alert, success, detail)
        self.db.commit()
        return alert

    def handle_control_weight(self, control_record: ControlWeightRecord) -> AlertRecord | None:
        settings = get_setting_map(self.db)
        tolerance = int(settings["comparison_tolerance_grams"])

        session = (
            self.db.query(BucketSession)
            .filter(BucketSession.bucket_id == control_record.bucket_id, BucketSession.station_type == StationType.primary)
            .order_by(BucketSession.started_at_utc.desc())
            .first()
        )
        if not session:
            return None

        delta = control_record.control_weight_grams - session.expected_final_weight_grams
        if delta >= -tolerance:
            return None

        alert_key = f"control-discrepancy:{control_record.control_weight_record_id}"
        existing = self.db.query(AlertRecord).filter(AlertRecord.alert_key == alert_key).one_or_none()
        if existing:
            return existing

        message = (
            "ALERT: control weighing discrepancy\n"
            f"bucket_id={control_record.bucket_id}\n"
            f"station_id={control_record.station_id}\n"
            f"timestamp_utc={control_record.recorded_at_utc.isoformat()}\n"
            f"expected_weight={session.expected_final_weight_grams} g\n"
            f"actual_weight={control_record.control_weight_grams} g\n"
            f"delta={delta} g\n"
            "Reason: control weight is lower than the final primary weight beyond tolerance."
        )

        alert = AlertRecord(
            alert_key=alert_key,
            alert_type=AlertType.control_discrepancy,
            bucket_id=control_record.bucket_id,
            bucket_session_id=session.bucket_session_id,
            station_id=control_record.station_id,
            detected_at_utc=datetime.now(timezone.utc),
            expected_weight_grams=session.expected_final_weight_grams,
            actual_weight_grams=control_record.control_weight_grams,
            delta_grams=delta,
            message_text=message,
            payload_json={"control_weight_record_id": control_record.control_weight_record_id},
        )
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        success, detail = self.telegram.send_alert(alert)
        self.telegram.mark_result(alert, success, detail)
        self.db.commit()
        return alert
