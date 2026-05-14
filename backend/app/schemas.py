from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthUser(BaseModel):
    username: str


class MeasurementCreate(BaseModel):
    timestamp: datetime
    weight: float = Field(..., description="Measured weight delta/value")
    source_event_id: Optional[str] = None


class Measurement(MeasurementCreate):
    id: int


class DeviceStatusCreate(BaseModel):
    timestamp: datetime
    status: str
    raw: str = ""
    source_event_id: Optional[str] = None


class DeviceStatus(DeviceStatusCreate):
    id: int


class Bucket(BaseModel):
    id: int
    start_timestamp: datetime
    end_timestamp: datetime
    max_weight: float
    bucket_date: date


class Status(BaseModel):
    current_weight: float = 0.0
    status: str
    device_status: Optional[str] = None
    device_status_timestamp: Optional[datetime] = None
    current_bucket: int
    today_bucket_count: int
    today_total_weight: float
    current_bucket_max_weight: float
    latest_measurement: Optional[Measurement] = None
    current_bucket_started_at: Optional[datetime] = None
    measurements: int
    buckets: int


class BucketList(BaseModel):
    date: date
    bucket_count: int
    total_weight: float
    buckets: List[Bucket]


class Health(BaseModel):
    ok: bool
    latest_measurement: Optional[Measurement] = None
