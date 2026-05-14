import csv
import io
from pathlib import Path
from datetime import date as date_cls, datetime
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
UKRAINE_TZ = ZoneInfo("Europe/Kyiv")


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
    today_buckets = db.list_buckets(today)
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
        current_bucket_max_weight=state["current_bucket_max_weight"],
        measurements=measurement_count,
        buckets=len(all_buckets),
        latest_measurement=Measurement(**latest.__dict__) if latest else None,
        current_bucket_started_at=state["current_bucket_started_at"],
    )


@app.get("/api/buckets", response_model=BucketList)
def get_buckets(
    bucket_date: Optional[date_cls] = Query(default=None, alias="date"),
    _user: AuthUser = Depends(require_user),
) -> BucketList:
    db.init_db()
    selected_date = bucket_date or datetime.now(UKRAINE_TZ).date()
    buckets = [Bucket(**bucket.__dict__) for bucket in db.list_buckets(selected_date)]
    return BucketList(
        date=selected_date,
        bucket_count=len(buckets),
        total_weight=sum(bucket.max_weight for bucket in buckets),
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
