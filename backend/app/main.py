import csv
import io
from pathlib import Path
from datetime import date as date_cls, datetime, time as datetime_time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .analyzer import BucketAnalyzer
from .auth import (
    SESSION_COOKIE,
    USERNAME,
    check_api_key,
    check_credentials,
    check_session_token,
    create_session_token,
)
from .schemas import (
    AuthUser,
    Bucket,
    BucketList,
    DeviceStatus,
    DeviceStatusCreate,
    Health,
    LoginRequest,
    Measurement,
    MeasurementCreate,
    Status,
)

app = FastAPI(title="Weight Bucket Dashboard API")
analyzer = BucketAnalyzer()
PUBLIC_DIR = Path(__file__).resolve().parents[2] / "public"
try:
    UKRAINE_TZ = ZoneInfo("Europe/Kyiv")
except Exception:
    UKRAINE_TZ = timezone(timedelta(hours=3))
SHIFTS = [
    {"code": "day_before_lunch", "label": "День до обіду", "start": 8 * 60, "end": 13 * 60},
    {"code": "day_after_lunch", "label": "День після обіду", "start": 14 * 60, "end": 20 * 60},
    {"code": "night_before_lunch", "label": "Ніч до обіду", "start": 20 * 60, "end": 1 * 60},
    {"code": "night_after_lunch", "label": "Ніч після обіду", "start": 2 * 60, "end": 8 * 60},
]


def _minutes_to_time(minutes: int) -> datetime_time:
    return datetime_time(hour=minutes // 60, minute=minutes % 60)


def _as_ukraine(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UKRAINE_TZ)
    return timestamp.astimezone(UKRAINE_TZ)


def _shift_window(shift: dict, window_date: date_cls) -> tuple[datetime, datetime]:
    start = datetime.combine(window_date, _minutes_to_time(shift["start"]), UKRAINE_TZ)
    end_date = window_date + timedelta(days=1) if shift["end"] <= shift["start"] else window_date
    end = datetime.combine(end_date, _minutes_to_time(shift["end"]), UKRAINE_TZ)
    return start, end


def bucket_shift(start_timestamp: datetime, end_timestamp: datetime) -> dict:
    start = _as_ukraine(start_timestamp)
    end = max(_as_ukraine(end_timestamp), start)
    best_shift = None
    best_seconds = 0
    day = start.date() - timedelta(days=1)
    last_day = end.date() + timedelta(days=1)

    while day <= last_day:
        for shift in SHIFTS:
            window_start, window_end = _shift_window(shift, day)
            overlap_start = max(start, window_start)
            overlap_end = min(end, window_end)
            overlap_seconds = max(0, int((overlap_end - overlap_start).total_seconds()))
            if overlap_seconds > best_seconds:
                best_seconds = overlap_seconds
                best_shift = {
                    "shift_code": shift["code"],
                    "shift_label": shift["label"],
                    "shift_date": window_start.date(),
                    "shift_overlap_seconds": overlap_seconds,
                }
        day += timedelta(days=1)

    if best_shift is None:
        return {
            "shift_code": "break",
            "shift_label": "Перерва",
            "shift_date": start.date(),
            "shift_overlap_seconds": 0,
        }
    return best_shift


def current_shift_at(moment: datetime) -> dict:
    moment = _as_ukraine(moment)
    day = moment.date() - timedelta(days=1)
    for offset in range(3):
        window_day = day + timedelta(days=offset)
        for shift in SHIFTS:
            window_start, window_end = _shift_window(shift, window_day)
            if window_start <= moment < window_end:
                return {
                    "shift_code": shift["code"],
                    "shift_label": shift["label"],
                    "shift_date": window_start.date(),
                    "shift_overlap_seconds": 0,
                }
    return {
        "shift_code": "break",
        "shift_label": "Перерва",
        "shift_date": moment.date(),
        "shift_overlap_seconds": 0,
    }


def bucket_to_schema(bucket) -> Bucket:
    return Bucket(**bucket.__dict__, **bucket_shift(bucket.start_timestamp, bucket.end_timestamp))


def filter_buckets_by_shift(buckets: list[Bucket], shift_code: str | None) -> list[Bucket]:
    if not shift_code or shift_code == "all":
        return buckets
    return [bucket for bucket in buckets if bucket.shift_code == shift_code]


@app.on_event("startup")
def on_startup() -> None:
    db.init_db()


def refresh_buckets() -> None:
    measurements = db.list_measurements()
    device_statuses = db.list_device_statuses()
    buckets = analyzer.analyze(measurements, device_statuses)
    db.replace_buckets(buckets)


def require_user(session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE)) -> AuthUser:
    if not check_session_token(session):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return AuthUser(username=USERNAME)


def require_ingest_access(
    session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE),
    api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> None:
    if check_session_token(session) or check_api_key(api_key):
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


@app.post("/api/login", response_model=AuthUser)
def login(payload: LoginRequest, response: Response) -> AuthUser:
    if not check_credentials(payload.username, payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad username or password")

    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 12,
    )
    return AuthUser(username=USERNAME)


@app.post("/api/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/me", response_model=AuthUser)
def me(user: AuthUser = Depends(require_user)) -> AuthUser:
    return user


@app.post("/api/measurements", response_model=Measurement, status_code=201)
def create_measurement(
    payload: MeasurementCreate,
    _access: None = Depends(require_ingest_access),
) -> Measurement:
    db.init_db()
    measurement = db.add_measurement(payload.timestamp, payload.weight, payload.source_event_id)
    refresh_buckets()
    return Measurement(**measurement.__dict__)


@app.post("/api/device-status", response_model=DeviceStatus, status_code=201)
def create_device_status(
    payload: DeviceStatusCreate,
    _access: None = Depends(require_ingest_access),
) -> DeviceStatus:
    db.init_db()
    device_status = db.add_device_status(
        payload.timestamp,
        payload.status,
        payload.raw,
        payload.source_event_id,
    )
    refresh_buckets()
    return DeviceStatus(**device_status.__dict__)


@app.get("/api/health", response_model=Health)
def get_health() -> Health:
    db.init_db()
    latest = db.get_latest_measurement()
    return Health(ok=True, latest_measurement=Measurement(**latest.__dict__) if latest else None)


@app.get("/api/status", response_model=Status)
def get_status(_user: AuthUser = Depends(require_user)) -> Status:
    db.init_db()
    today = datetime.now(UKRAINE_TZ).date()
    measurements = db.list_measurements()
    latest = db.get_latest_measurement()
    latest_device_status = db.get_latest_device_status()
    device_statuses = db.list_device_statuses()
    measurement_count = db.count_rows("measurements")
    all_buckets = db.list_buckets()
    today_buckets = [bucket_to_schema(bucket) for bucket in db.list_buckets(today)]
    current_shift = current_shift_at(datetime.now(UKRAINE_TZ))
    current_shift_buckets = filter_buckets_by_shift(today_buckets, current_shift["shift_code"])
    state = analyzer.current_state(measurements, device_statuses)
    device_status_is_current = (
        latest_device_status is not None
        and (latest is None or latest_device_status.timestamp >= latest.timestamp)
    )

    return Status(
        current_weight=latest.weight if latest else 0.0,
        status=latest_device_status.status if device_status_is_current and latest_device_status.status == "scale_waiting" else state["status"],
        device_status=latest_device_status.status if latest_device_status else None,
        device_status_timestamp=latest_device_status.timestamp if latest_device_status else None,
        current_bucket=len(all_buckets) + 1,
        today_bucket_count=len(today_buckets),
        today_total_weight=sum(bucket.max_weight for bucket in today_buckets),
        current_shift=current_shift,
        current_shift_bucket_count=len(current_shift_buckets),
        current_shift_total_weight=sum(bucket.max_weight for bucket in current_shift_buckets),
        current_bucket_max_weight=state["current_bucket_max_weight"],
        measurements=measurement_count,
        buckets=len(all_buckets),
        latest_measurement=Measurement(**latest.__dict__) if latest else None,
        current_bucket_started_at=state["current_bucket_started_at"],
    )


@app.get("/api/buckets", response_model=BucketList)
def get_buckets(
    bucket_date: Optional[date_cls] = Query(default=None, alias="date"),
    shift: str = Query(default="all"),
    _user: AuthUser = Depends(require_user),
) -> BucketList:
    db.init_db()
    selected_date = bucket_date or datetime.now(UKRAINE_TZ).date()
    all_date_buckets = [bucket_to_schema(bucket) for bucket in db.list_buckets(selected_date)]
    buckets = filter_buckets_by_shift(all_date_buckets, shift)
    return BucketList(
        date=selected_date,
        shift=shift,
        shifts=SHIFTS,
        bucket_count=len(buckets),
        total_weight=sum(bucket.max_weight for bucket in buckets),
        all_bucket_count=len(all_date_buckets),
        all_total_weight=sum(bucket.max_weight for bucket in all_date_buckets),
        buckets=buckets,
    )


@app.get("/api/buckets/{bucket_id}/measurements.csv")
def get_bucket_measurements_csv(
    bucket_id: int,
    _user: AuthUser = Depends(require_user),
) -> StreamingResponse:
    db.init_db()
    bucket = db.get_bucket(bucket_id)
    if bucket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bucket not found")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "weight"])
    for measurement in db.list_measurements_between(bucket.start_timestamp, bucket.end_timestamp):
        writer.writerow([measurement.timestamp.isoformat(), f"{measurement.weight:.3f}"])

    filename = f"bucket_{bucket.id}_{bucket.bucket_date.isoformat()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


if (PUBLIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=PUBLIC_DIR / "assets"), name="assets")


@app.get("/{path:path}")
def serve_frontend(path: str) -> FileResponse:
    index_file = PUBLIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frontend is not deployed")
    return FileResponse(index_file)
