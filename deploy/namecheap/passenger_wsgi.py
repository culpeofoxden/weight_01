import csv
import io
import json
import os
import secrets
import sqlite3
from datetime import date, datetime
from http import cookies
from pathlib import Path
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

from itsdangerous import BadSignature, TimestampSigner

APP_ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = APP_ROOT / "public"
DB_PATH = APP_ROOT / "weight_dashboard.sqlite3"

USERNAME = os.getenv("WEIGHT_DASHBOARD_USER", "admin")
PASSWORD = os.getenv("WEIGHT_DASHBOARD_PASSWORD", "change-me")
API_KEY = os.getenv("WEIGHT_DASHBOARD_API_KEY", PASSWORD)
SECRET = os.getenv("WEIGHT_DASHBOARD_SECRET", "dev-weight-dashboard-secret")
SESSION_COOKIE = "weight_dashboard_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 12
UKRAINE_TZ = ZoneInfo("Europe/Kyiv")

NEAR_ZERO_THRESHOLD = 0.05
FILLING_START_THRESHOLD = 0.2
REMOVED_THRESHOLD = -0.5
STABLE_READING_COUNT = 5

signer = TimestampSigner(SECRET)


def stable_weight(readings):
    positive_readings = [weight for weight in readings if weight > FILLING_START_THRESHOLD]
    if not positive_readings:
        return 0.0

    tail = sorted(positive_readings[-STABLE_READING_COUNT:])
    middle = len(tail) // 2
    if len(tail) % 2:
        return tail[middle]
    return (tail[middle - 1] + tail[middle]) / 2


def init_db():
    with sqlite3.connect(DB_PATH) as connection:
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
        connection.execute("CREATE INDEX IF NOT EXISTS idx_measurements_timestamp ON measurements (timestamp)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_buckets_date ON buckets (bucket_date)")
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


def query(sql, params=()):
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(sql, params).fetchall()


def execute(sql, params=()):
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.execute(sql, params)
        return cursor.lastrowid


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


def list_device_statuses():
    return query("SELECT id, timestamp, status, raw FROM device_statuses ORDER BY timestamp ASC, id ASC")


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
                        "max_weight": stable_weight(readings),
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
                    "max_weight": stable_weight(readings),
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
    bucket_list = analyze_buckets(list_measurements(), list_device_statuses())
    existing_rows = query("SELECT id, start_timestamp, end_timestamp FROM buckets")
    existing = {(row["start_timestamp"], row["end_timestamp"]): row["id"] for row in existing_rows}
    next_keys = set()

    with sqlite3.connect(DB_PATH) as connection:
        for bucket in bucket_list:
            key = (bucket["start_timestamp"], bucket["end_timestamp"])
            next_keys.add(key)
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

        stale_ids = [row["id"] for row in existing_rows if (row["start_timestamp"], row["end_timestamp"]) not in next_keys]
        connection.executemany("DELETE FROM buckets WHERE id = ?", [(bucket_id,) for bucket_id in stale_ids])


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
    return [
        {
            "id": row["id"],
            "start_timestamp": row["start_timestamp"],
            "end_timestamp": row["end_timestamp"],
            "max_weight": row["max_weight"],
            "bucket_date": row["bucket_date"],
        }
        for row in rows
    ]


def serve_file(start_response, path, content_type):
    if not path.exists() or not path.is_file():
        return text_response(start_response, "404 Not Found", "Not found")
    body = path.read_bytes()
    start_response("200 OK", [("Content-Type", content_type), ("Content-Length", str(len(body)))])
    return [body]


def application(environ, start_response):
    init_db()
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
        refresh_buckets()
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
        status_id = execute(
            """
            INSERT INTO device_statuses (timestamp, status, raw, source_event_id)
            VALUES (?, ?, ?, ?)
            """,
            (payload["timestamp"], payload["status"], payload.get("raw", ""), source_event_id),
        )
        refresh_buckets()
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
        measurements = list_measurements()
        latest = measurements[-1] if measurements else None
        device_statuses = list_device_statuses()
        latest_status_rows = query("SELECT * FROM device_statuses ORDER BY timestamp DESC, id DESC LIMIT 1")
        latest_device_status = latest_status_rows[0] if latest_status_rows else None
        all_buckets = query("SELECT * FROM buckets ORDER BY start_timestamp ASC, id ASC")
        today = datetime.now(UKRAINE_TZ).date().isoformat()
        today_buckets = query("SELECT * FROM buckets WHERE bucket_date = ? ORDER BY start_timestamp ASC, id ASC", (today,))
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
                "current_bucket_max_weight": state["current_bucket_max_weight"],
                "latest_measurement": dict(latest) if latest else None,
                "current_bucket_started_at": state["current_bucket_started_at"],
                "measurements": len(measurements),
                "buckets": len(all_buckets),
            },
        )

    if method == "GET" and path == "/api/buckets":
        denied = auth_required(start_response, environ)
        if denied:
            return denied
        params = parse_qs(environ.get("QUERY_STRING", ""))
        selected_date = params.get("date", [datetime.now(UKRAINE_TZ).date().isoformat()])[0]
        bucket_rows = query("SELECT * FROM buckets WHERE bucket_date = ? ORDER BY start_timestamp ASC, id ASC", (selected_date,))
        buckets = rows_to_buckets(bucket_rows)
        return json_response(
            start_response,
            "200 OK",
            {"date": selected_date, "bucket_count": len(buckets), "total_weight": sum(float(b["max_weight"]) for b in buckets), "buckets": buckets},
        )

    if method == "GET" and path.startswith("/api/buckets/") and path.endswith("/measurements.csv"):
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
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["timestamp", "weight"])
        for row in measurement_rows:
            writer.writerow([row["timestamp"], f"{float(row['weight']):.3f}"])
        filename = f"bucket_{bucket_id}_{bucket['bucket_date']}.csv"
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
