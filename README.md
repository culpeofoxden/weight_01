# Amber Bucket Monitoring Monorepo

This repository is organized as a staged monorepo for the amber bucket monitoring system.

## Folders

- `device-agent/` Raspberry Pi software for weighing stations. Phase 1 is implemented here.
- `backend/` Reserved for the FastAPI + PostgreSQL backend in Phase 2.
- `frontend/` Reserved for the React dashboard in Phase 3.
- `infra/` Shared Docker and deployment assets.

## Current Status

Phase 1 is implemented in `device-agent/` and includes:

- a local-first Raspberry Pi device service,
- SQLite persistence with durable outbox sync,
- primary and control station modes,
- session lifecycle management,
- anomaly candidate detection,
- heartbeat generation,
- future-ready video clip provider interface,
- Raspberry Pi setup documentation and sample configuration.

See [device-agent/README.md](/C:/Users/beher/weight_v1/weight_01/device-agent/README.md) for Phase 1 details.
