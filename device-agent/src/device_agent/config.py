import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


StationType = Literal["primary", "control"]


@dataclass(slots=True)
class AgentConfig:
    station_id: str
    station_type: StationType
    device_id: str
    timezone: str
    read_interval_seconds: int
    noise_window_size: int
    minimum_meaningful_log_delta: int
    negative_delta_threshold: int
    negative_persistence_seconds: int
    empty_bucket_threshold: int
    empty_confirmation_seconds: int
    heartbeat_interval_seconds: int
    db_path: Path
    api_base_url: str
    api_key: str
    sync_batch_size: int
    sync_base_backoff_seconds: int
    sync_max_backoff_seconds: int
    video_provider: str
    scale_adapter: str
    button_adapter: str
    control_input_adapter: str

    @property
    def is_primary(self) -> bool:
        return self.station_type == "primary"

    @property
    def is_control(self) -> bool:
        return self.station_type == "control"


def load_config(config_path: str | Path) -> AgentConfig:
    path = Path(config_path)
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    db_override = os.getenv("AMBER_AGENT_DB_PATH")
    api_base_url = os.getenv("AMBER_AGENT_API_BASE_URL", data["api_base_url"])
    api_key = os.getenv("AMBER_AGENT_API_KEY", data["api_key"])

    return AgentConfig(
        station_id=data["station_id"],
        station_type=data["station_type"],
        device_id=data["device_id"],
        timezone=data.get("timezone", "UTC"),
        read_interval_seconds=int(data.get("read_interval_seconds", 1)),
        noise_window_size=int(data.get("noise_window_size", 3)),
        minimum_meaningful_log_delta=int(data.get("minimum_meaningful_log_delta", 20)),
        negative_delta_threshold=int(data.get("negative_delta_threshold", -100)),
        negative_persistence_seconds=int(data.get("negative_persistence_seconds", 3)),
        empty_bucket_threshold=int(data.get("empty_bucket_threshold", 150)),
        empty_confirmation_seconds=int(data.get("empty_confirmation_seconds", 2)),
        heartbeat_interval_seconds=int(data.get("heartbeat_interval_seconds", 30)),
        db_path=Path(db_override or data["db_path"]).expanduser(),
        api_base_url=api_base_url.rstrip("/"),
        api_key=api_key,
        sync_batch_size=int(os.getenv("AMBER_AGENT_SYNC_BATCH_SIZE", data.get("sync_batch_size", 100))),
        sync_base_backoff_seconds=int(
            os.getenv(
                "AMBER_AGENT_SYNC_BASE_BACKOFF_SECONDS",
                data.get("sync_base_backoff_seconds", 2),
            )
        ),
        sync_max_backoff_seconds=int(
            os.getenv(
                "AMBER_AGENT_SYNC_MAX_BACKOFF_SECONDS",
                data.get("sync_max_backoff_seconds", 300),
            )
        ),
        video_provider=data.get("video_provider", "stub"),
        scale_adapter=data.get("scale_adapter", "mock"),
        button_adapter=data.get("button_adapter", "mock"),
        control_input_adapter=data.get("control_input_adapter", "mock"),
    )
