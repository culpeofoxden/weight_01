from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.models import models  # noqa: F401
from app.routers import alerts, analytics, auth, buckets, device, settings, test_tools
from app.services.seed import seed_initial_data
from app.services.settings_service import ensure_default_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_default_settings(db)
        seed_initial_data(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Amber Bucket Monitoring API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(device.router)
app.include_router(settings.router)
app.include_router(alerts.router)
app.include_router(buckets.router)
app.include_router(analytics.router)
app.include_router(test_tools.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
