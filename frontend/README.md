# Frontend Phase 3

This folder contains the React dashboard for the amber bucket monitoring system.

## Stack

- React + TypeScript
- Vite
- React Router
- Custom industrial desktop-first UI

## Implemented Pages

- `Login`
- `Dashboard`
- `Bucket Details`
- `Analytics`
- `Admin Settings`

## Local Run

```bash
npm install
npm run dev
```

Use `VITE_API_BASE_URL` to point the UI at a backend other than `http://localhost:8000`.

## Temporary Mock Mode

The frontend currently defaults to mock mode when `VITE_USE_MOCK_API` is not set to `false`.

To force real backend mode:

```bash
VITE_USE_MOCK_API=false npm run dev
```
