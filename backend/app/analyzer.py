from datetime import datetime
from typing import Iterable, List, Optional

from .models import BucketCandidate, DeviceStatusRecord, MeasurementRecord

NEAR_ZERO_THRESHOLD = 0.05
FILLING_START_THRESHOLD = 0.2
REMOVED_THRESHOLD = -0.5
STABLE_READING_COUNT = 5
STABLE_MAX_SPREAD_KG = 0.2
SUSPECT_DROP_THRESHOLD_KG = 1.0


def median(values: List[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def stable_weight(readings: List[float]) -> float:
    positive_readings = [weight for weight in readings if weight > FILLING_START_THRESHOLD]
    if not positive_readings:
        return 0.0

    if len(positive_readings) < STABLE_READING_COUNT:
        return median(positive_readings)

    accepted = None
    for index in range(0, len(positive_readings) - STABLE_READING_COUNT + 1):
        window = positive_readings[index:index + STABLE_READING_COUNT]
        if max(window) - min(window) > STABLE_MAX_SPREAD_KG:
            continue

        candidate = median(window)
        if accepted is not None and candidate < accepted - SUSPECT_DROP_THRESHOLD_KG:
            continue
        accepted = candidate

    if accepted is not None:
        return accepted

    return median(positive_readings[-STABLE_READING_COUNT:])


class BucketAnalyzer:
    def analyze(
        self,
        measurements: Iterable[MeasurementRecord],
        device_statuses: Iterable[DeviceStatusRecord] = (),
    ) -> List[BucketCandidate]:
        buckets: List[BucketCandidate] = []
        tare_seen = False
        filling = False
        start_timestamp: Optional[datetime] = None
        max_weight = 0.0
        readings: List[float] = []

        events = [
            ("measurement", item.timestamp, item.id, item)
            for item in measurements
        ] + [
            ("status", item.timestamp, item.id, item)
            for item in device_statuses
        ]

        for event_type, timestamp, _id, event in sorted(events, key=lambda item: (item[1], item[2], item[0])):
            if event_type == "status":
                if filling and event.status == "scale_waiting" and start_timestamp is not None:
                    buckets.append(
                        BucketCandidate(
                            start_timestamp=start_timestamp,
                            end_timestamp=timestamp,
                            max_weight=stable_weight(readings),
                            bucket_date=start_timestamp.date(),
                        )
                    )
                    filling = False
                    start_timestamp = None
                    max_weight = 0.0
                    readings = []
                    tare_seen = False
                continue

            weight = event.weight

            if not filling:
                if abs(weight) <= NEAR_ZERO_THRESHOLD:
                    tare_seen = True
                    continue

                if weight > FILLING_START_THRESHOLD:
                    filling = True
                    start_timestamp = timestamp
                    max_weight = weight
                    readings = [weight]
                continue

            if weight > max_weight:
                max_weight = weight
            readings.append(weight)

            if abs(weight) <= NEAR_ZERO_THRESHOLD:
                continue

            if weight < REMOVED_THRESHOLD and start_timestamp is not None:
                buckets.append(
                    BucketCandidate(
                        start_timestamp=start_timestamp,
                        end_timestamp=timestamp,
                        max_weight=stable_weight(readings),
                        bucket_date=start_timestamp.date(),
                    )
                )
                filling = False
                start_timestamp = None
                max_weight = 0.0
                readings = []
                tare_seen = False

        return buckets

    def current_state(
        self,
        measurements: Iterable[MeasurementRecord],
        device_statuses: Iterable[DeviceStatusRecord] = (),
    ) -> dict:
        events = [
            ("measurement", item.timestamp, item.id, item)
            for item in measurements
        ] + [
            ("status", item.timestamp, item.id, item)
            for item in device_statuses
        ]
        rows = sorted(events, key=lambda item: (item[1], item[2], item[0]))
        measurement_rows = sorted(measurements, key=lambda item: (item.timestamp, item.id))
        if not rows:
            return {
                "status": "no_data",
                "current_bucket_max_weight": 0.0,
                "current_bucket_started_at": None,
            }

        tare_seen = False
        filling = False
        current_bucket_started_at: Optional[datetime] = None
        current_bucket_max_weight = 0.0
        readings: List[float] = []

        latest_status: Optional[str] = None

        for event_type, _timestamp, _id, event in rows:
            if event_type == "status":
                latest_status = event.status
                if filling and event.status == "scale_waiting":
                    filling = False
                    tare_seen = False
                    current_bucket_started_at = None
                    current_bucket_max_weight = 0.0
                    readings = []
                continue

            weight = event.weight

            if not filling:
                if abs(weight) <= NEAR_ZERO_THRESHOLD:
                    tare_seen = True
                    continue

                if weight > FILLING_START_THRESHOLD:
                    filling = True
                    current_bucket_started_at = event.timestamp
                    current_bucket_max_weight = weight
                    readings = [weight]
                continue

            if weight > current_bucket_max_weight:
                current_bucket_max_weight = weight
            readings.append(weight)

            if weight < REMOVED_THRESHOLD:
                filling = False
                tare_seen = False
                current_bucket_started_at = None
                current_bucket_max_weight = 0.0
                readings = []

        latest_measurement = measurement_rows[-1] if measurement_rows else None
        if latest_status == "scale_waiting" and not filling:
            status = "scale_waiting"
        elif latest_measurement is not None and latest_measurement.weight < REMOVED_THRESHOLD:
            status = "bucket_removed"
        elif filling:
            status = "filling"
        elif tare_seen:
            status = "waiting_fill"
        elif latest_measurement is not None and latest_measurement.weight > FILLING_START_THRESHOLD:
            status = "waiting_tare"
        else:
            status = "waiting_tare"

        return {
            "status": status,
            "current_bucket_max_weight": stable_weight(readings) if filling else current_bucket_max_weight,
            "current_bucket_started_at": current_bucket_started_at,
        }
