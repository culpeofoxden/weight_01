from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user, require_role
from app.models.models import GlobalSetting, User
from app.schemas import GlobalSettingItem, GlobalSettingsUpdate
from app.services.settings_service import ensure_default_settings


router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("", response_model=list[GlobalSettingItem])
def list_settings(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[GlobalSettingItem]:
    ensure_default_settings(db)
    rows = db.query(GlobalSetting).order_by(GlobalSetting.key.asc()).all()
    return [GlobalSettingItem(key=row.key, value=row.value, description=row.description) for row in rows]


@router.put("", response_model=list[GlobalSettingItem])
def update_settings(
    payload: GlobalSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
) -> list[GlobalSettingItem]:
    ensure_default_settings(db)
    for item in payload.items:
        row = db.query(GlobalSetting).filter(GlobalSetting.key == item.key).one_or_none()
        if row:
            row.value = item.value
            row.description = item.description
        else:
            db.add(GlobalSetting(key=item.key, value=item.value, description=item.description))
    db.commit()
    rows = db.query(GlobalSetting).order_by(GlobalSetting.key.asc()).all()
    return [GlobalSettingItem(key=row.key, value=row.value, description=row.description) for row in rows]
