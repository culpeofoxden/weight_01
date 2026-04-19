# Phase 1 API Contract Assumptions

The Raspberry Pi agent is built so the backend can accept idempotent, device-originated records. Every outbox message includes:

- `message_id`: unique UUID for the local message
- `idempotency_key`: stable key reused across retries
- `device_id`
- `station_id`
- `station_type`
- `occurred_at_utc`

## Assumed Endpoints

### `POST /api/v1/device/weight-logs`

Accepts one or more `weight_log` records.

Fields:

- `event_id`
- `bucket_id`
- `bucket_session_id`
- `station_id`
- `station_type`
- `recorded_at_utc`
- `weight_grams`
- `delta_grams`
- `raw_weight_grams`
- `reason`

### `POST /api/v1/device/bucket-sessions`

Accepts bucket session start/end updates.

Fields:

- `bucket_session_id`
- `bucket_id`
- `station_id`
- `station_type`
- `started_at_utc`
- `ended_at_utc`
- `status`
- `expected_final_weight_grams`

### `POST /api/v1/device/anomaly-candidates`

Accepts primary-station negative-change anomaly candidates for server-side evaluation.

Fields:

- `anomaly_event_id`
- `bucket_id`
- `bucket_session_id`
- `station_id`
- `station_type`
- `event_type`
- `observed_at_utc`
- `delta_grams`
- `weight_before_grams`
- `weight_after_grams`
- `persistence_seconds`
- `video_metadata`

### `POST /api/v1/device/control-weight-records`

Accepts control weighing submissions.

Fields:

- `control_weight_record_id`
- `bucket_id`
- `station_id`
- `station_type`
- `recorded_at_utc`
- `control_weight_grams`
- `operator_note`

### `POST /api/v1/device/heartbeats`

Accepts periodic health heartbeats.

Fields:

- `heartbeat_id`
- `device_id`
- `station_id`
- `station_type`
- `recorded_at_utc`
- `agent_version`
- `status`
- `details`

## Auth Assumption

Phase 1 assumes a device API key header:

- `Authorization: Bearer <api-key>`

## Idempotency Assumption

Phase 1 assumes the backend honors either:

- `Idempotency-Key` header, or
- unique record IDs inside the JSON payload,

and returns `200`, `201`, or `409` for safe duplicate retries.
