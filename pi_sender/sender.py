#!/usr/bin/env python3
import argparse
import json
import os
import time
import urllib.error
import urllib.request


def parse_args():
    parser = argparse.ArgumentParser(description="Send scale serial readings to the dashboard API.")
    parser.add_argument("--serial", default="/tmp/weight_arduino", help="Serial device path.")
    parser.add_argument(
        "--api",
        default="http://127.0.0.1:8000/api/measurements",
        help="Measurements API endpoint.",
    )
    parser.add_argument("--api-key", default=os.getenv("WEIGHT_DASHBOARD_API_KEY", ""), help="Dashboard ingest API key.")
    parser.add_argument("--retry-seconds", type=float, default=3.0)
    return parser.parse_args()


def parse_line(line):
    timestamp, weight_text = line.strip().split(",", 1)
    return {"timestamp": timestamp, "weight": float(weight_text)}


def post_json(url, payload, api_key):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        response.read()


def run(args):
    print(f"reading: {args.serial}", flush=True)
    print(f"posting: {args.api}", flush=True)

    while True:
        try:
            with open(args.serial, "r", encoding="utf-8", errors="ignore") as serial_file:
                for raw_line in serial_file:
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue

                    try:
                        payload = parse_line(raw_line)
                        post_json(args.api, payload, args.api_key)
                        print(f"sent {payload['timestamp']} {payload['weight']:.3f}", flush=True)
                    except (ValueError, urllib.error.URLError, TimeoutError) as exc:
                        print(f"send failed: {raw_line!r}: {exc}", flush=True)
                        time.sleep(args.retry_seconds)
        except OSError as exc:
            print(f"serial unavailable: {exc}", flush=True)
            time.sleep(args.retry_seconds)


if __name__ == "__main__":
    run(parse_args())
