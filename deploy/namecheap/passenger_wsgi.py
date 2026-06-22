import csv
import io
import json
import os
import secrets
import sqlite3
import time
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from http import cookies
from pathlib import Path
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

from itsdangerous import BadSignature, TimestampSigner

APP_ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = APP_ROOT / "public"
DB_PATH = APP_ROOT / "weight_dashboard.sqlite3"
REFRESH_STAMP_PATH = APP_ROOT / ".last_bucket_refresh"
REFRESH_LOCK_PATH = APP_ROOT / ".bucket_refresh.lock"

USERNAME = os.getenv("WEIGHT_DASHBOARD_USER", "admin")
PASSWORD = os.getenv("WEIGHT_DASHBOARD_PASSWORD", "change-me")
API_KEY = os.getenv("WEIGHT_DASHBOARD_API_KEY", PASSWORD)
SECRET = os.getenv("WEIGHT_DASHBOARD_SECRET", "dev-weight-dashboard-secret")
SESSION_COOKIE = "weight_dashboard_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 12
try:
    UKRAINE_TZ = ZoneInfo("Europe/Kyiv")
except Exception:
    UKRAINE_TZ = timezone(timedelta(hours=3))

NEAR_ZERO_THRESHOLD = 0.05
FILLING_START_THRESHOLD = 0.2
REMOVED_THRESHOLD = -0.5
STABLE_READING_COUNT = 5
STABLE_MAX_SPREAD_KG = 0.2
SUSPECT_DROP_THRESHOLD_KG = 1.0
REFRESH_INTERVAL_SECONDS = 30
REFRESH_LOCK_STALE_SECONDS = 120
STATUS_DEDUP_SECONDS = 60
SQLITE_TIMEOUT_SECONDS = 30
SHIFTS = [
    {"code": "day_before_lunch", "label": "День до обіду", "start": 8 * 60, "end": 13 * 60},
    {"code": "day_after_lunch", "label": "День після обіду", "start": 14 * 60, "end": 20 * 60},
    {"code": "night_before_lunch", "label": "Ніч до обіду", "start": 20 * 60, "end": 1 * 60},
    {"code": "night_after_lunch", "label": "Ніч після обіду", "start": 2 * 60, "end": 8 * 60},
]

signer = TimestampSigner(SECRET)
_DB_READY = False


def median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def stable_weight(readings, context=None):
    positive_readings = [weight for weight in readings if weight > FILLING_START_THRESHOLD]
    if not positive_readings:
        return 0.0

    if len(positive_readings) < STABLE_READING_COUNT:
        return median(positive_readings)

    accepted = None
    ignored_drops = []
    for index in range(0, len(positive_readings) - STABLE_READING_COUNT + 1):
        window = positive_readings[index:index + STABLE_READING_COUNT]
        if max(window) - min(window) > STABLE_MAX_SPREAD_KG:
            continue

        candidate = median(window)
        if accepted is not None and candidate < accepted - SUSPECT_DROP_THRESHOLD_KG:
            ignored_drops.append((accepted, candidate))
            continue
        accepted = candidate

    if accepted is not None:
        if ignored_drops and context:
            previous, ignored = ignored_drops[-1]
            log_bucket_event(
                "ignored_weight_drop",
                context,
                {
                    "accepted_weight": round(previous, 3),
                    "ignored_weight": round(ignored, 3),
                    "drop_kg": round(previous - ignored, 3),
                },
            )
        return accepted

    return median(positive_readings[-STABLE_READING_COUNT:])


def parse_bucket_timestamp(value):
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UKRAINE_TZ)
    return timestamp.astimezone(UKRAINE_TZ)


def minutes_to_time(minutes):
    return datetime_time(hour=minutes // 60, minute=minutes % 60)


def shift_window_for_date(shift, window_date):
    start = datetime.combine(window_date, minutes_to_time(shift["start"]), UKRAINE_TZ)
    end_date = window_date + timedelta(days=1) if shift["end"] <= shift["start"] else window_date
    end = datetime.combine(end_date, minutes_to_time(shift["end"]), UKRAINE_TZ)
    return start, end


def bucket_shift(start_timestamp, end_timestamp):
    start = parse_bucket_timestamp(start_timestamp)
    end = parse_bucket_timestamp(end_timestamp)
    if end < start:
        end = start

    best_shift = None
    best_seconds = 0
    first_day = start.date() - timedelta(days=1)
    last_day = end.date() + timedelta(days=1)
    day = first_day

    while day <= last_day:
        for shift in SHIFTS:
            window_start, window_end = shift_window_for_date(shift, day)
            overlap_start = max(start, window_start)
            overlap_end = min(end, window_end)
            overlap_seconds = max(0, (overlap_end - overlap_start).total_seconds())
            if overlap_seconds > best_seconds:
                best_seconds = overlap_seconds
                best_shift = {
                    "shift_code": shift["code"],
                    "shift_label": shift["label"],
                    "shift_date": window_start.date().isoformat(),
                    "shift_overlap_seconds": int(overlap_seconds),
                }
        day += timedelta(days=1)

    if best_shift is None:
        return {
            "shift_code": "break",
            "shift_label": "Перерва",
            "shift_date": start.date().isoformat(),
            "shift_overlap_seconds": 0,
        }
    return best_shift


def current_shift_at(moment):
    moment = moment.astimezone(UKRAINE_TZ)
    first_day = moment.date() - timedelta(days=1)
    for offset in range(3):
        day = first_day + timedelta(days=offset)
        for shift in SHIFTS:
            window_start, window_end = shift_window_for_date(shift, day)
            if window_start <= moment < window_end:
                return {
                    "shift_code": shift["code"],
                    "shift_label": shift["label"],
                    "shift_date": window_start.date().isoformat(),
                    "shift_overlap_seconds": 0,
                }
    return {
        "shift_code": "break",
        "shift_label": "Перерва",
        "shift_date": moment.date().isoformat(),
        "shift_overlap_seconds": 0,
    }


def connect_db():
    connection = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT_SECONDS)
    connection.execute(f"PRAGMA busy_timeout = {SQLITE_TIMEOUT_SECONDS * 1000}")
    return connection


def init_db():
    with connect_db() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                weight REAL NOT NULL
            )
            """
        )
        try:
            connection.execute("ALTER TABLE measurements ADD COLUMN source_event_id TEXT")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS buckets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_timestamp TEXT NOT NULL,
                end_timestamp TEXT NOT NULL,
                max_weight REAL NOT NULL,
                bucket_date TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS device_statuses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                status TEXT NOT NULL,
                raw TEXT NOT NULL DEFAULT '',
                source_event_id TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS bucket_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_key TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                bucket_start_timestamp TEXT NOT NULL,
                bucket_end_timestamp TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_measurements_timestamp ON measurements (timestamp)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_buckets_date ON buckets (bucket_date)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_bucket_events_created_at ON bucket_events (created_at)")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_measurements_source_event_id
            ON measurements (source_event_id)
            WHERE source_event_id IS NOT NULL
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_device_statuses_timestamp ON device_statuses (timestamp)")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_device_statuses_source_event_id
            ON device_statuses (source_event_id)
            WHERE source_event_id IS NOT NULL
            """
        )


def ensure_db():
    global _DB_READY
    if _DB_READY:
        return

    last_error = None
    for attempt in range(5):
        try:
            init_db()
            _DB_READY = True
            return
        except sqlite3.OperationalError as exc:
            last_error = exc
            if "locked" not in str(exc).lower():
                raise
            time.sleep(0.2 * (attempt + 1))
    raise last_error


def query(sql, params=()):
    with connect_db() as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(sql, params).fetchall()


def execute(sql, params=()):
    with connect_db() as connection:
        cursor = connection.execute(sql, params)
        return cursor.lastrowid


def log_bucket_event(event_type, context, details):
    event_key = (
        f"{event_type}:"
        f"{context.get('start_timestamp', '')}:"
        f"{context.get('end_timestamp', '')}:"
        f"{details.get('accepted_weight', '')}:"
        f"{details.get('ignored_weight', '')}"
    )
    execute(
        """
        INSERT OR IGNORE INTO bucket_events (
            event_key,
            event_type,
            bucket_start_timestamp,
            bucket_end_timestamp,
            details,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            event_key,
            event_type,
            context.get("start_timestamp", ""),
            context.get("end_timestamp", ""),
            json.dumps(details, ensure_ascii=False),
            datetime.now(UKRAINE_TZ).isoformat(),
        ),
    )


def json_response(start_response, status, payload, headers=None):
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    response_headers = [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body)))]
    if headers:
        response_headers.extend(headers)
    start_response(status, response_headers)
    return [body]


def text_response(start_response, status, body, content_type="text/plain; charset=utf-8", headers=None):
    encoded = body.encode("utf-8")
    response_headers = [("Content-Type", content_type), ("Content-Length", str(len(encoded)))]
    if headers:
        response_headers.extend(headers)
    start_response(status, response_headers)
    return [encoded]


def read_json(environ):
    size = int(environ.get("CONTENT_LENGTH") or 0)
    raw = environ["wsgi.input"].read(size) if size else b"{}"
    return json.loads(raw.decode("utf-8"))


def session_from_environ(environ):
    jar = cookies.SimpleCookie(environ.get("HTTP_COOKIE", ""))
    morsel = jar.get(SESSION_COOKIE)
    return morsel.value if morsel else None


def is_session_valid(token):
    if not token:
        return False
    try:
        value = signer.unsign(token, max_age=SESSION_MAX_AGE_SECONDS).decode("utf-8")
    except BadSignature:
        return False
    return value.startswith(f"{USERNAME}:")


def is_authorized(environ):
    return is_session_valid(session_from_environ(environ))


def is_ingest_authorized(environ):
    return is_authorized(environ) or secrets.compare_digest(environ.get("HTTP_X_API_KEY", ""), API_KEY)


def auth_required(start_response, environ):
    if is_authorized(environ):
        return None
    return json_response(start_response, "401 Unauthorized", {"detail": "Not authenticated"})


def list_measurements():
    return query("SELECT id, timestamp, weight FROM measurements ORDER BY timestamp ASC, id ASC")


def list_recent_measurements(limit=10000):
    rows = query(
        """
        SELECT id, timestamp, weight
        FROM measurements
        ORDER BY timestamp DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    )
    return list(reversed(rows))


def list_device_statuses():
    return query("SELECT id, timestamp, status, raw FROM device_statuses ORDER BY timestamp ASC, id ASC")


def list_recent_device_statuses(limit=2000):
    rows = query(
        """
        SELECT id, timestamp, status, raw
        FROM device_statuses
        ORDER BY timestamp DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    )
    return list(reversed(rows))


def analyze_buckets(measurements, device_statuses=()):
    buckets = []
    tare_seen = False
    filling = False
    start_timestamp = None
    max_weight = 0.0
    readings = []

    events = [
        ("measurement", measurement["timestamp"], measurement["id"], measurement)
        for measurement in measurements
    ] + [
        ("status", status["timestamp"], status["id"], status)
        for status in device_statuses
    ]

    for event_type, timestamp, _id, event in sorted(events, key=lambda item: (item[1], item[2], item[0])):
        if event_type == "status":
            if filling and event["status"] == "scale_waiting" and start_timestamp is not None:
                buckets.append(
                    {
                        "start_timestamp": start_timestamp,
                        "end_timestamp": timestamp,
                        "max_weight": stable_weight(
                            readings,
                            {"start_timestamp": start_timestamp, "end_timestamp": timestamp},
                        ),
                        "bucket_date": datetime.fromisoformat(start_timestamp).date().isoformat(),
                    }
                )
                tare_seen = False
                filling = False
                start_timestamp = None
                max_weight = 0.0
                readings = []
            continue

        weight = float(event["weight"])

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
                {
                    "start_timestamp": start_timestamp,
                    "end_timestamp": timestamp,
                    "max_weight": stable_weight(
                        readings,
                        {"start_timestamp": start_timestamp, "end_timestamp": timestamp},
                    ),
                    "bucket_date": datetime.fromisoformat(start_timestamp).date().isoformat(),
                }
            )
            tare_seen = False
            filling = False
            start_timestamp = None
            max_weight = 0.0
            readings = []

    return buckets


def refresh_buckets():
    latest_bucket_rows = query(
        "SELECT end_timestamp FROM buckets ORDER BY end_timestamp DESC, id DESC LIMIT 1"
    )
    cutoff = latest_bucket_rows[0]["end_timestamp"] if latest_bucket_rows else None

    if cutoff:
        measurements = query(
            """
            SELECT id, timestamp, weight
            FROM measurements
            WHERE timestamp > ?
            ORDER BY timestamp ASC, id ASC
            """,
            (cutoff,),
        )
        device_statuses = query(
            """
            SELECT id, timestamp, status, raw
            FROM device_statuses
            WHERE timestamp > ?
            ORDER BY timestamp ASC, id ASC
            """,
            (cutoff,),
        )
    else:
        measurements = list_measurements()
        device_statuses = list_device_statuses()

    bucket_list = analyze_buckets(measurements, device_statuses)
    if not bucket_list:
        return

    existing_rows = query(
        "SELECT id, start_timestamp, end_timestamp FROM buckets WHERE end_timestamp > ?",
        (cutoff or "",),
    )
    existing = {(row["start_timestamp"], row["end_timestamp"]): row["id"] for row in existing_rows}

    with connect_db() as connection:
        for bucket in bucket_list:
            key = (bucket["start_timestamp"], bucket["end_timestamp"])
            if key in existing:
                connection.execute(
                    "UPDATE buckets SET max_weight = ?, bucket_date = ? WHERE id = ?",
                    (bucket["max_weight"], bucket["bucket_date"], existing[key]),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO buckets (start_timestamp, end_timestamp, max_weight, bucket_date)
                    VALUES (?, ?, ?, ?)
                    """,
                    (bucket["start_timestamp"], bucket["end_timestamp"], bucket["max_weight"], bucket["bucket_date"]),
                )


def refresh_buckets_if_stale(force=False):
    now = time.time()
    if not force and REFRESH_STAMP_PATH.exists():
        try:
            if now - REFRESH_STAMP_PATH.stat().st_mtime < REFRESH_INTERVAL_SECONDS:
                return
        except OSError:
            pass

    try:
        fd = os.open(REFRESH_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            if now - REFRESH_LOCK_PATH.stat().st_mtime > REFRESH_LOCK_STALE_SECONDS:
                REFRESH_LOCK_PATH.unlink()
        except OSError:
            pass
        return

    try:
        os.close(fd)
        refresh_buckets()
        REFRESH_STAMP_PATH.write_text(str(now), encoding="utf-8")
    finally:
        try:
            REFRESH_LOCK_PATH.unlink()
        except OSError:
            pass


def current_state(measurements, device_statuses=()):
    events = [
        ("measurement", measurement["timestamp"], measurement["id"], measurement)
        for measurement in measurements
    ] + [
        ("status", status["timestamp"], status["id"], status)
        for status in device_statuses
    ]
    events = sorted(events, key=lambda item: (item[1], item[2], item[0]))
    if not events:
        return {"status": "no_data", "current_bucket_max_weight": 0.0, "current_bucket_started_at": None}

    tare_seen = False
    filling = False
    started_at = None
    max_weight = 0.0
    readings = []
    latest_status = None

    for event_type, timestamp, _id, event in events:
        if event_type == "status":
            latest_status = event["status"]
            if filling and event["status"] == "scale_waiting":
                filling = False
                tare_seen = False
                started_at = None
                max_weight = 0.0
                readings = []
            continue

        weight = float(event["weight"])

        if not filling:
            if abs(weight) <= NEAR_ZERO_THRESHOLD:
                tare_seen = True
                continue

            if weight > FILLING_START_THRESHOLD:
                filling = True
                started_at = timestamp
                max_weight = weight
                readings = [weight]
            continue

        if weight > max_weight:
            max_weight = weight
        readings.append(weight)

        if weight < REMOVED_THRESHOLD:
            filling = False
            tare_seen = False
            started_at = None
            max_weight = 0.0
            readings = []

    latest_weight = float(measurements[-1]["weight"]) if measurements else None
    if latest_status == "scale_waiting" and not filling:
        status = "scale_waiting"
    elif latest_weight is not None and latest_weight < REMOVED_THRESHOLD:
        status = "bucket_removed"
    elif filling:
        status = "filling"
    elif tare_seen:
        status = "waiting_fill"
    else:
        status = "waiting_tare"

    return {
        "status": status,
        "current_bucket_max_weight": stable_weight(readings) if filling else max_weight,
        "current_bucket_started_at": started_at,
    }


def rows_to_buckets(rows):
    buckets = []
    for row in rows:
        shift = bucket_shift(row["start_timestamp"], row["end_timestamp"])
        buckets.append({
            "id": row["id"],
            "start_timestamp": row["start_timestamp"],
            "end_timestamp": row["end_timestamp"],
            "max_weight": row["max_weight"],
            "bucket_date": row["bucket_date"],
            **shift,
        })
    return buckets


def filter_buckets_by_shift(buckets, shift_code):
    if not shift_code or shift_code == "all":
        return buckets
    return [bucket for bucket in buckets if bucket.get("shift_code") == shift_code]


def write_measurement_rows(writer, measurement_rows, only_changes=False):
    writer.writerow(["timestamp", "weight"])
    previous_weight_text = None
    pending_last_row = None

    for row in measurement_rows:
        weight_text = f"{float(row['weight']):.3f}"
        csv_row = [row["timestamp"], weight_text]

        if not only_changes:
            writer.writerow(csv_row)
            continue

        if previous_weight_text is None or weight_text != previous_weight_text:
            writer.writerow(csv_row)
            previous_weight_text = weight_text
            pending_last_row = None
        else:
            pending_last_row = csv_row

    if only_changes and pending_last_row is not None:
        writer.writerow(pending_last_row)


def serve_file(start_response, path, content_type):
    if not path.exists() or not path.is_file():
        return text_response(start_response, "404 Not Found", "Not found")
    body = path.read_bytes()
    start_response("200 OK", [("Content-Type", content_type), ("Content-Length", str(len(body)))])
    return [body]


def application(environ, start_response):
    ensure_db()
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/")

    if method == "POST" and path == "/api/login":
        payload = read_json(environ)
        if payload.get("username") != USERNAME or payload.get("password") != PASSWORD:
            return json_response(start_response, "401 Unauthorized", {"detail": "Bad username or password"})
        token = signer.sign(f"{USERNAME}:{secrets.token_urlsafe(24)}").decode("utf-8")
        return json_response(
            start_response,
            "200 OK",
            {"username": USERNAME},
            [("Set-Cookie", f"{SESSION_COOKIE}={token}; Max-Age={SESSION_MAX_AGE_SECONDS}; HttpOnly; SameSite=Lax; Path=/")],
        )

    if method == "POST" and path == "/api/logout":
        return json_response(start_response, "200 OK", {"ok": True}, [("Set-Cookie", f"{SESSION_COOKIE}=; Max-Age=0; Path=/")])

    if method == "GET" and path == "/api/me":
        denied = auth_required(start_response, environ)
        if denied:
            return denied
        return json_response(start_response, "200 OK", {"username": USERNAME})

    if method == "GET" and path == "/api/health":
        latest = query("SELECT id, timestamp, weight FROM measurements ORDER BY timestamp DESC, id DESC LIMIT 1")
        return json_response(start_response, "200 OK", {"ok": True, "latest_measurement": dict(latest[0]) if latest else None})

    if method == "POST" and path == "/api/measurements":
        if not is_ingest_authorized(environ):
            return json_response(start_response, "401 Unauthorized", {"detail": "Not authenticated"})
        payload = read_json(environ)
        source_event_id = payload.get("source_event_id")
        if source_event_id:
            existing = query(
                "SELECT id, timestamp, weight FROM measurements WHERE source_event_id = ?",
                (source_event_id,),
            )
            if existing:
                row = existing[0]
                return json_response(
                    start_response,
                    "200 OK",
                    {"id": row["id"], "timestamp": row["timestamp"], "weight": float(row["weight"])},
                )
        measurement_id = execute(
            "INSERT INTO measurements (timestamp, weight, source_event_id) VALUES (?, ?, ?)",
            (payload["timestamp"], float(payload["weight"]), source_event_id),
        )
        return json_response(start_response, "201 Created", {"id": measurement_id, "timestamp": payload["timestamp"], "weight": float(payload["weight"])})

    if method == "POST" and path == "/api/device-status":
        if not is_ingest_authorized(environ):
            return json_response(start_response, "401 Unauthorized", {"detail": "Not authenticated"})
        payload = read_json(environ)
        source_event_id = payload.get("source_event_id")
        if source_event_id:
            existing = query(
                "SELECT id, timestamp, status, raw FROM device_statuses WHERE source_event_id = ?",
                (source_event_id,),
            )
            if existing:
                return json_response(start_response, "200 OK", dict(existing[0]))

        latest_status_rows = query(
            """
            SELECT id, timestamp, status, raw
            FROM device_statuses
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
            """
        )
        if latest_status_rows:
            latest_status = latest_status_rows[0]
            try:
                current_timestamp = datetime.fromisoformat(payload["timestamp"])
                previous_timestamp = datetime.fromisoformat(latest_status["timestamp"])
                seconds_since_previous = (current_timestamp - previous_timestamp).total_seconds()
            except (TypeError, ValueError):
                seconds_since_previous = STATUS_DEDUP_SECONDS + 1

            if (
                latest_status["status"] == payload["status"]
                and latest_status["raw"] == payload.get("raw", "")
                and 0 <= seconds_since_previous < STATUS_DEDUP_SECONDS
            ):
                return json_response(
                    start_response,
                    "200 OK",
                    {
                        "id": latest_status["id"],
                        "timestamp": payload["timestamp"],
                        "status": payload["status"],
                        "raw": payload.get("raw", ""),
                        "deduplicated": True,
                    },
                )

        status_id = execute(
            """
            INSERT INTO device_statuses (timestamp, status, raw, source_event_id)
            VALUES (?, ?, ?, ?)
            """,
            (payload["timestamp"], payload["status"], payload.get("raw", ""), source_event_id),
        )
        if payload["status"] == "scale_waiting":
            refresh_buckets_if_stale()
        return json_response(
            start_response,
            "201 Created",
            {
                "id": status_id,
                "timestamp": payload["timestamp"],
                "status": payload["status"],
                "raw": payload.get("raw", ""),
            },
        )

    if method == "GET" and path == "/api/status":
        denied = auth_required(start_response, environ)
        if denied:
            return denied
        measurements = list_recent_measurements()
        latest = measurements[-1] if measurements else None
        device_statuses = list_recent_device_statuses()
        latest_status_rows = query("SELECT * FROM device_statuses ORDER BY timestamp DESC, id DESC LIMIT 1")
        latest_device_status = latest_status_rows[0] if latest_status_rows else None
        all_buckets = rows_to_buckets(query("SELECT * FROM buckets ORDER BY start_timestamp ASC, id ASC"))
        now_ukraine = datetime.now(UKRAINE_TZ)
        today = now_ukraine.date().isoformat()
        today_buckets = rows_to_buckets(query("SELECT * FROM buckets WHERE bucket_date = ? ORDER BY start_timestamp ASC, id ASC", (today,)))
        current_shift = current_shift_at(now_ukraine)
        current_shift_buckets = filter_buckets_by_shift(today_buckets, current_shift["shift_code"])
        state = current_state(measurements, device_statuses)
        device_status_is_current = latest_device_status is not None and (
            latest is None or latest_device_status["timestamp"] >= latest["timestamp"]
        )
        status_name = (
            latest_device_status["status"]
            if device_status_is_current and latest_device_status["status"] == "scale_waiting"
            else state["status"]
        )
        return json_response(
            start_response,
            "200 OK",
            {
                "current_weight": float(latest["weight"]) if latest else 0.0,
                "status": status_name,
                "device_status": latest_device_status["status"] if latest_device_status else None,
                "device_status_timestamp": latest_device_status["timestamp"] if latest_device_status else None,
                "current_bucket": len(all_buckets) + 1,
                "today_bucket_count": len(today_buckets),
                "today_total_weight": sum(float(bucket["max_weight"]) for bucket in today_buckets),
                "current_shift": current_shift,
                "current_shift_bucket_count": len(current_shift_buckets),
                "current_shift_total_weight": sum(float(bucket["max_weight"]) for bucket in current_shift_buckets),
                "current_bucket_max_weight": state["current_bucket_max_weight"],
                "latest_measurement": dict(latest) if latest else None,
                "current_bucket_started_at": state["current_bucket_started_at"],
                "measurements": query("SELECT COUNT(*) AS total FROM measurements")[0]["total"],
                "buckets": len(all_buckets),
            },
        )

    if method == "GET" and path == "/api/buckets":
        denied = auth_required(start_response, environ)
        if denied:
            return denied
        refresh_buckets_if_stale()
        params = parse_qs(environ.get("QUERY_STRING", ""))
        selected_date = params.get("date", [datetime.now(UKRAINE_TZ).date().isoformat()])[0]
        selected_shift = params.get("shift", ["all"])[0]
        bucket_rows = query("SELECT * FROM buckets WHERE bucket_date = ? ORDER BY start_timestamp ASC, id ASC", (selected_date,))
        all_date_buckets = rows_to_buckets(bucket_rows)
        buckets = filter_buckets_by_shift(all_date_buckets, selected_shift)
        return json_response(
            start_response,
            "200 OK",
            {
                "date": selected_date,
                "shift": selected_shift,
                "shifts": SHIFTS,
                "bucket_count": len(buckets),
                "total_weight": sum(float(b["max_weight"]) for b in buckets),
                "all_bucket_count": len(all_date_buckets),
                "all_total_weight": sum(float(b["max_weight"]) for b in all_date_buckets),
                "buckets": buckets,
            },
        )

    if method == "GET" and path == "/api/bucket-events":
        denied = auth_required(start_response, environ)
        if denied:
            return denied
        params = parse_qs(environ.get("QUERY_STRING", ""))
        limit = min(500, max(1, int(params.get("limit", ["100"])[0])))
        rows = query(
            """
            SELECT id, event_type, bucket_start_timestamp, bucket_end_timestamp, details, created_at
            FROM bucket_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return json_response(
            start_response,
            "200 OK",
            {
                "events": [
                    {
                        "id": row["id"],
                        "event_type": row["event_type"],
                        "bucket_start_timestamp": row["bucket_start_timestamp"],
                        "bucket_end_timestamp": row["bucket_end_timestamp"],
                        "details": json.loads(row["details"]),
                        "created_at": row["created_at"],
                    }
                    for row in rows
                ]
            },
        )

    if method == "GET" and path.startswith("/api/buckets/") and (
        path.endswith("/measurements.csv") or path.endswith("/changes.csv")
    ):
        denied = auth_required(start_response, environ)
        if denied:
            return denied
        try:
            bucket_id = int(path.split("/")[3])
        except (ValueError, IndexError):
            return json_response(start_response, "404 Not Found", {"detail": "Bucket not found"})
        bucket_rows = query("SELECT * FROM buckets WHERE id = ?", (bucket_id,))
        if not bucket_rows:
            return json_response(start_response, "404 Not Found", {"detail": "Bucket not found"})
        bucket = bucket_rows[0]
        measurement_rows = query(
            "SELECT timestamp, weight FROM measurements WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp ASC, id ASC",
            (bucket["start_timestamp"], bucket["end_timestamp"]),
        )
        only_changes = path.endswith("/changes.csv")
        output = io.StringIO()
        writer = csv.writer(output)
        write_measurement_rows(writer, measurement_rows, only_changes=only_changes)
        suffix = "_changes" if only_changes else ""
        filename = f"bucket_{bucket_id}_{bucket['bucket_date']}{suffix}.csv"
        return text_response(
            start_response,
            "200 OK",
            output.getvalue(),
            "text/csv; charset=utf-8",
            [("Content-Disposition", f'attachment; filename="{filename}"')],
        )

    if method == "GET" and path.startswith("/assets/"):
        suffix = path.removeprefix("/assets/")
        content_type = "text/css" if suffix.endswith(".css") else "application/javascript"
        return serve_file(start_response, PUBLIC_DIR / "assets" / suffix, content_type)

    if method == "GET":
        return serve_file(start_response, PUBLIC_DIR / "index.html", "text/html; charset=utf-8")

    return text_response(start_response, "405 Method Not Allowed", "Method not allowed")
