# Backend Phase 2

This folder contains the central FastAPI backend for the amber bucket monitoring MVP.

## What Is Implemented

- FastAPI application with OpenAPI-friendly routes
- PostgreSQL-ready SQLAlchemy models
- Alembic migration scaffold with an initial schema
- Device ingest API matching the Phase 1 Raspberry Pi contract
- Idempotent ingestion via `Idempotency-Key` and `ingest_audit`
- Email/password login with `admin` and `viewer` roles
- Global settings storage for thresholds and tolerances
- Alert engine for:
  - unexpected negative primary-scale delta
  - discrepancy between primary final weight and control weight
- Telegram integration service
- Bucket history, raw log export, alerts list, and analytics summary endpoints
- Docker Compose for local backend + PostgreSQL startup
- Seed data for users and stations

## Project Structure

- `src/app/main.py` app entrypoint
- `src/app/models/models.py` database models
- `src/app/routers/` API routes
- `src/app/services/` ingest, alerting, Telegram, seed, and settings logic
- `src/app/security.py` password hashing and JWT creation
- `src/app/schemas.py` request/response models
- `alembic/` migration environment and initial revision

## Database Schema

Phase 2 includes these tables:

- `users`
- `roles`
- `stations`
- `bucket_sessions`
- `weight_logs`
- `anomaly_events`
- `control_weight_records`
- `alert_records`
- `global_settings`
- `device_heartbeats`
- `ingest_audit`

## API Endpoint List

### Auth

- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`

### Device ingest

- `POST /api/v1/device/weight-logs`
- `POST /api/v1/device/bucket-sessions`
- `POST /api/v1/device/anomaly-candidates`
- `POST /api/v1/device/control-weight-records`
- `POST /api/v1/device/heartbeats`

### User-facing

- `GET /api/v1/buckets`
- `GET /api/v1/buckets/{bucket_id}`
- `GET /api/v1/buckets/{bucket_id}/raw-logs.csv`
- `GET /api/v1/alerts`
- `GET /api/v1/analytics/summary`
- `GET /api/v1/settings`
- `PUT /api/v1/settings`
- `POST /api/v1/test/telegram-alert`
- `POST /api/v1/test/scenarios/normal-cycle`
- `POST /api/v1/test/scenarios/primary-negative-delta`
- `POST /api/v1/test/scenarios/control-discrepancy`

## Alert Flow

### Type 1 alert: negative primary delta

1. Device sends anomaly candidate from the primary scale.
2. Backend stores the anomaly candidate.
3. Alert service checks `negative_delta_threshold`.
4. If threshold is exceeded, backend creates `alert_record`.
5. Telegram service sends a group message if enabled.
6. Send status is tracked in `alert_records.status`.

### Type 2 alert: control discrepancy

1. Device sends control weighing result.
2. Backend finds the latest primary `bucket_session` for the same `bucket_id`.
3. Backend compares `control_weight_grams` against `expected_final_weight_grams`.
4. If the discrepancy is below the configured tolerance, backend creates `alert_record`.
5. Telegram service sends the alert if enabled.

## Raw Log Export

The backend currently supports bucket-scoped CSV export:

- `GET /api/v1/buckets/{bucket_id}/raw-logs.csv`

Date-range export can be added in the same style in Phase 3 or as a small Phase 2 extension.

## Docker Compose Setup

### 1. Copy environment values

Use `.env.example` as your starting point.

For local Windows development without PostgreSQL, the checked-in `.env` can use SQLite as a temporary dev fallback.
Production and the intended Phase 2 stack remain PostgreSQL.

### 2. Start the stack

```bash
docker compose up --build
```

### 3. Open the API

- API root health: `http://localhost:8000/health`
- Swagger UI: `http://localhost:8000/docs`

## Default Seed Data

Created automatically on startup:

- `admin@example.com` / `admin123`
- `viewer@example.com` / `viewer123`
- stations:
  - `primary-line-01`
  - `control-room-01`

## Simulation Test Flow

These admin-only routes let you test the backend without real scales:

- `POST /api/v1/test/telegram-alert`
  Sends a direct Telegram test message.
- `POST /api/v1/test/scenarios/normal-cycle`
  Creates a completed primary session with a matching control weight. Expected result: no discrepancy alert.
- `POST /api/v1/test/scenarios/primary-negative-delta`
  Creates an active primary session plus anomaly candidate. Expected result: primary negative-delta alert and Telegram notification.
- `POST /api/v1/test/scenarios/control-discrepancy`
  Creates a completed primary session plus a lower control weight. Expected result: control discrepancy alert and Telegram notification.

Example flow:

1. Login as `admin@example.com`.
2. Call one of the scenario routes.
3. Inspect:
   - `GET /api/v1/alerts`
   - `GET /api/v1/buckets`
   - `GET /api/v1/buckets/{bucket_id}`
4. Confirm Telegram delivery in the group.

## Notes

- The app currently calls `Base.metadata.create_all()` on startup for convenience in local MVP development. Alembic migration files are also included, so this can be tightened later into migration-only startup.
- Telegram video sending is not implemented yet, but `payload_json` and anomaly metadata are already structured to hold future clip references.
- Device auth is currently API-key based as assumed in Phase 1; stronger per-device auth can be introduced later.
- `POST /api/v1/test/telegram-alert` is an admin-only helper endpoint for quickly verifying Telegram delivery during setup.
- Telegram delivery has been verified with the configured bot and target group during setup.
- For immediate local smoke testing on this Windows machine, SQLite can be used as a dev fallback when PostgreSQL installation is blocked. The backend code now supports both database URLs.
