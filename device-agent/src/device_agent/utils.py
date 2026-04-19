from collections import deque
from datetime import UTC, datetime
from statistics import median
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def new_bucket_id(station_id: str, now: datetime) -> str:
    clean_station = station_id.replace("-", "").replace("_", "")
    return f"BKT-{now.strftime('%Y%m%dT%H%M%SZ')}-{clean_station[-6:].upper()}-{uuid4().hex[:6].upper()}"


class MedianFilter:
    def __init__(self, window_size: int) -> None:
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        self._samples: deque[int] = deque(maxlen=window_size)

    def add(self, value: int) -> int:
        self._samples.append(value)
        return int(median(self._samples))
