from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class MeasurementRecord:
    id: int
    timestamp: datetime
    weight: float
    source_event_id: str | None = None


@dataclass(frozen=True)
class DeviceStatusRecord:
    id: int
    timestamp: datetime
    status: str
    raw: str = ""
    source_event_id: str | None = None


@dataclass(frozen=True)
class BucketRecord:
    id: int
    start_timestamp: datetime
    end_timestamp: datetime
    max_weight: float
    bucket_date: date


@dataclass(frozen=True)
class BucketCandidate:
    start_timestamp: datetime
    end_timestamp: datetime
    max_weight: float
    bucket_date: date
