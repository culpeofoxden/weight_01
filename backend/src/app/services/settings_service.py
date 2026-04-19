from sqlalchemy.orm import Session

from app.models.models import GlobalSetting


DEFAULT_SETTINGS = {
    "negative_delta_threshold": ("-100", "Primary station negative anomaly threshold in grams"),
    "negative_persistence_seconds": ("3", "Seconds a negative drop must persist"),
    "empty_bucket_threshold": ("150", "Threshold for bucket removal detection"),
    "comparison_tolerance_grams": ("100", "Allowed loss between primary and control"),
    "minimum_meaningful_log_delta": ("20", "Minimum absolute delta to log"),
    "noise_window_size": ("3", "Median filter window size"),
}


def ensure_default_settings(db: Session) -> None:
    for key, (value, description) in DEFAULT_SETTINGS.items():
        existing = db.query(GlobalSetting).filter(GlobalSetting.key == key).one_or_none()
        if not existing:
            db.add(GlobalSetting(key=key, value=value, description=description))
    db.commit()


def get_setting_map(db: Session) -> dict[str, str]:
    ensure_default_settings(db)
    rows = db.query(GlobalSetting).all()
    return {row.key: row.value for row in rows}
