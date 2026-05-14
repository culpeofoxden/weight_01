# Weight Dashboard MVP

Simple dashboard for bucket-based amber weighing.

## Local Backend

```powershell
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

API:

- `POST /api/measurements`
- `GET /api/status`
- `GET /api/buckets?date=2026-05-08`

## Local Frontend

```powershell
cd frontend
npm run dev -- --host 0.0.0.0
```

Open:

```text
http://127.0.0.1:5173
```

## Raspberry Pi Sender

```sh
/home/admin1/weight_emulator/sender.py \
  --serial /tmp/weight_arduino \
  --api http://100.120.231.16:8000/api/measurements
```

The sender reads lines like:

```text
2026-05-08T13:01:15+03:00,0.008
```

and posts them to the backend.
