#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
import time
import uuid
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import serial


WAITING_TEXT = "весы в режиме ожидания"


def parse_args():
    parser = argparse.ArgumentParser(description="Read Arduino scale data and reliably send it to the dashboard.")
    parser.add_argument("--serial", default="/dev/ttyUSB0", help="Arduino serial device.")
    parser.add_argument("--baud", type=int, default=9600, help="Arduino serial baudrate.")
    parser.add_argument("--api-base", default="https://beheramber.com", help="Dashboard base URL.")
    parser.add_argument("--api-key", default=os.getenv("WEIGHT_DASHBOARD_API_KEY", ""), help="Dashboard ingest API key.")
    parser.add_argument("--queue-db", default=str(Path.home() / "arduino_sender_queue.sqlite3"))
    parser.add_argument("--retry-seconds", type=float, default=3.0)
    parser.add_argument("--flush-limit", type=int, default=100)
    return parser.parse_args()


def now_iso():
    return datetime.now().astimezone().isoformat()


def init_db(path):
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_uuid TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                weight REAL,
                status TEXT,
                raw TEXT NOT NULL,
                sent_at TEXT
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_events_sent_id ON events (sent_at, id)")


def classify_line(raw):
    line = raw.strip()
    if not line:
        return None

    if line.startswith("WEIGHT:"):
        grams_text = line.split(":", 1)[1].strip()
        grams = float(grams_text)
        return {
            "kind": "measurement",
            "weight": grams / 1000.0,
            "status": None,
            "raw": line,
        }

    if line == WAITING_TEXT:
        return {
            "kind": "status",
            "weight": None,
            "status": "scale_waiting",
            "raw": line,
        }

    return {
        "kind": "status",
        "weight": None,
        "status": "device_message",
        "raw": line,
    }


def enqueue_event(db_path, parsed):
    event_uuid = str(uuid.uuid4())
    timestamp = now_iso()
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA synchronous=FULL")
        cursor = connection.execute(
            """
            INSERT INTO events (event_uuid, kind, timestamp, weight, status, raw)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event_uuid,
                parsed["kind"],
                timestamp,
                parsed["weight"],
                parsed["status"],
                parsed["raw"],
            ),
        )
    return cursor.lastrowid


def iter_unsent(db_path, limit):
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, event_uuid, kind, timestamp, weight, status, raw
            FROM events
            WHERE sent_at IS NULL
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows


def mark_sent(db_path, event_id):
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE events SET sent_at = ? WHERE id = ?", (now_iso(), event_id))


def post_json(url, payload, api_key):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        response.read()
        if response.status >= 400:
            raise urllib.error.HTTPError(url, response.status, response.reason, response.headers, None)


def send_event(args, row):
    if row["kind"] == "measurement":
        url = f"{args.api_base.rstrip('/')}/api/measurements"
        payload = {
            "timestamp": row["timestamp"],
            "weight": float(row["weight"]),
            "source_event_id": row["event_uuid"],
        }
    else:
        url = f"{args.api_base.rstrip('/')}/api/device-status"
        payload = {
            "timestamp": row["timestamp"],
            "status": row["status"],
            "raw": row["raw"],
            "source_event_id": row["event_uuid"],
        }

    post_json(url, payload, args.api_key)


def flush_queue(args):
    sent = 0
    for row in iter_unsent(args.queue_db, args.flush_limit):
        send_event(args, row)
        mark_sent(args.queue_db, row["id"])
        sent += 1
    return sent


def run(args):
    init_db(args.queue_db)
    print(f"serial={args.serial} baud={args.baud}", flush=True)
    print(f"api={args.api_base.rstrip('/')}", flush=True)
    print(f"queue={args.queue_db}", flush=True)

    while True:
        try:
            with serial.Serial(args.serial, args.baud, timeout=1) as arduino:
                time.sleep(2)
                while True:
                    try:
                        flush_queue(args)
                    except (OSError, urllib.error.URLError, TimeoutError) as exc:
                        print(f"flush failed: {exc}", flush=True)

                    raw_bytes = arduino.readline()
                    if not raw_bytes:
                        continue

                    raw = raw_bytes.decode("utf-8", errors="ignore").strip()
                    try:
                        parsed = classify_line(raw)
                    except ValueError as exc:
                        print(f"parse failed: {raw!r}: {exc}", flush=True)
                        parsed = {"kind": "status", "weight": None, "status": "parse_error", "raw": raw}

                    if parsed is None:
                        continue

                    event_id = enqueue_event(args.queue_db, parsed)
                    print(f"queued #{event_id}: {parsed['kind']} {raw}", flush=True)
        except serial.SerialException as exc:
            print(f"serial unavailable: {exc}", flush=True)
            try:
                flush_queue(args)
            except (OSError, urllib.error.URLError, TimeoutError) as flush_exc:
                print(f"flush failed: {flush_exc}", flush=True)
            time.sleep(args.retry_seconds)


if __name__ == "__main__":
    run(parse_args())
