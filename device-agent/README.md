# Device Agent Phase 1

This phase implements the Raspberry Pi software for the two weighing stations:

- `station_type = "primary"` for the conveyor scale where a bucket is filled.
- `station_type = "control"` for the building scale where the filled bucket is re-weighed.

The design is local-first and durable:

- every meaningful record is written to local SQLite before network sync,
- every server submission is queued in an outbox table,
- retries use exponential backoff,
- no business-critical data depends on live network access,
- timestamps are stored in UTC,
- gram values are handled as integers.

## Architecture

### Components

- `src/device_agent/main.py`
  Runs the service loop and background sync worker.
- `src/device_agent/config.py`
  Loads station configuration from TOML plus environment overrides.
- `src/device_agent/db.py`
  Owns the SQLite schema and durable local repository methods.
- `src/device_agent/services.py`
  Implements the primary/control station flows, heartbeat generation, anomaly detection, and sync worker.
- `src/device_agent/hardware.py`
  Defines hardware interfaces so GPIO, HX711, serial scales, or touch UI adapters can be plugged in later.
- `src/device_agent/video.py`
  Provides a stub clip metadata service for future Dahua RTSP support.
- `src/device_agent/adapters.py`
  Mock adapters used for development and unit tests.

### Runtime Model

The device process has two loops:

1. Foreground station loop running every second.
2. Background sync loop shipping queued outbox messages to the server.

This split keeps device capture independent from connectivity.

### Assumptions

- The primary operator presses a physical tare/reset button to begin each bucket cycle.
- On that press, the scale is tared and a new `bucket_id` is generated locally.
- Only one active primary bucket session exists per station at a time.
- The primary session ends when the measured weight stays at or below the configured empty threshold long enough to confirm removal.
- The control station operator supplies `bucket_id` manually using a future UI/input adapter. For MVP this is an abstraction with a mock implementation.
- Server-side alerting remains the source of truth, but the device sends enough anomaly context for that backend decision.
- Your sketch’s special heavier-stone branch can be added later as a dedicated derived event stream without changing the local-first pipeline.

## Local Storage Model

SQLite is used as the durable edge database.

### Local Tables

- `bucket_sessions`
  Tracks the lifecycle of a primary weighing session.
- `weight_logs`
  Stores meaningful weight changes only.
- `anomaly_events`
  Stores local anomaly candidates observed on the primary station.
- `control_weight_records`
  Stores confirmed control weighings.
- `device_heartbeats`
  Stores local heartbeats for auditability.
- `outbox_messages`
  Durable sync queue with `sync_status`, retry counters, error text, and next-attempt time.

### Sync Model

Every record follows this path:

1. Persist business row in SQLite.
2. Create one outbox message with a stable idempotency key.
3. Background worker sends the payload to the backend.
4. On success, mark message as `synced`.
5. On failure, keep it local and retry later with exponential backoff.

This means server downtime, reboots, or short network outages do not drop data.

## Event Lifecycle

### Primary Station Session Lifecycle

1. Operator presses tare/reset.
2. Device tares the scale.
3. Device generates a new `bucket_id`.
4. Device creates a new `bucket_session` with status `active`.
5. Weight is read once per second.
6. A median filter suppresses sensor noise.
7. If the filtered weight changes by at least `minimum_meaningful_log_delta`, a `weight_log` row is stored.
8. If a negative delta exceeds `negative_delta_threshold` and persists for `negative_persistence_seconds` while the session is active, an `anomaly_event` candidate is stored.
9. While the bucket remains on the scale, the session tracks the best known expected final weight.
10. When the weight stays below `empty_bucket_threshold` for `empty_confirmation_seconds`, the bucket is treated as removed and the session closes.
11. The closed session is queued for backend sync with the final expected primary weight.

### Control Station Lifecycle

1. Operator enters or selects `bucket_id`.
2. Device reads the current control scale weight.
3. Device stores a `control_weight_record`.
4. The record is queued for sync to the backend.

## Local Database Schema

The exact SQLite schema lives in [src/device_agent/db.py](/C:/Users/beher/weight_v1/weight_01/device-agent/src/device_agent/db.py).

Core fields include:

- `bucket_id`
- `station_id`
- `station_type`
- `bucket_session`
- `weight_log`
- `anomaly_event`
- `control_weight_record`
- `sync_status`

## API Contract Assumptions

See [docs/api-contract-phase1.md](/C:/Users/beher/weight_v1/weight_01/device-agent/docs/api-contract-phase1.md).

In short, the device assumes:

- API key authentication,
- idempotent create-style ingestion endpoints,
- backend acceptance of retries without duplicate side effects.

## Raspberry Pi Setup

### 1. Install Python dependencies

```bash
cd device-agent
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

### 2. Configure the station

Copy `.env.example` into your deployment environment and update values as needed.

Pick one station TOML:

- `configs/primary.station.toml`
- `configs/control.station.toml`

### 3. Run locally

```bash
amber-device-agent --config configs/primary.station.toml
```

### 4. Swap mock adapters for hardware adapters

For real Raspberry Pi deployment you will replace:

- `MockScaleReader`
- `MockButtonHandler`
- `MockControlInputHandler`

with hardware-specific adapters for:

- HX711 or serial scale input,
- GPIO button events,
- keypad, touchscreen, or local web form for control `bucket_id` entry.

## Testing

```bash
pytest
```

## Future-Ready Video Architecture

`src/device_agent/video.py` already provides a `VideoProvider` implementation that returns placeholder clip metadata with the correct 15-second-before and 15-second-after framing.

When camera integration is ready, a Dahua adapter can:

- resolve the RTSP URL for the relevant station camera,
- request a 30-second clip around the anomaly timestamp,
- attach resulting file metadata to the backend payload,
- optionally enqueue a separate clip-upload job using the same outbox pattern.

## Notes and TODOs

- GPIO and real scale I/O are intentionally abstract because hardware details were not provided yet.
- Control-station operator interaction is intentionally abstract and mock-backed for now.
- An optional local emergency alert queue can be added later if local fallback Telegram delivery becomes necessary, but server-side alert ownership remains the cleaner design for MVP.
