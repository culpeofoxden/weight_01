from collections import deque
from pathlib import Path

from device_agent.adapters import MockButtonHandler, MockScaleReader
from device_agent.config import AgentConfig
from device_agent.db import LocalStore
from device_agent.services import PrimaryStationService
from device_agent.video import StubVideoProvider


def make_config(db_path: Path) -> AgentConfig:
    return AgentConfig(
        station_id="primary-line-01",
        station_type="primary",
        device_id="pi-primary-01",
        timezone="UTC",
        read_interval_seconds=1,
        noise_window_size=1,
        minimum_meaningful_log_delta=20,
        negative_delta_threshold=-100,
        negative_persistence_seconds=2,
        empty_bucket_threshold=150,
        empty_confirmation_seconds=2,
        heartbeat_interval_seconds=30,
        db_path=db_path,
        api_base_url="http://localhost:8000",
        api_key="test",
        sync_batch_size=100,
        sync_base_backoff_seconds=2,
        sync_max_backoff_seconds=300,
        video_provider="stub",
        scale_adapter="mock",
        button_adapter="mock",
        control_input_adapter="mock",
    )


def test_primary_station_creates_session_logs_changes_and_queues_messages(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.db"
    store = LocalStore(db_path)
    config = make_config(db_path)
    scale = MockScaleReader(samples=deque([0, 300, 600, 80, 50]))
    button = MockButtonHandler(presses=deque([True, False, False, False, False]))
    service = PrimaryStationService(
        config=config,
        store=store,
        scale_reader=scale,
        button_handler=button,
        video_provider=StubVideoProvider(),
    )

    for _ in range(5):
        service.tick()

    assert store.get_open_session(config.station_id) is None
    assert store.count_pending_outbox() >= 4
    store.close()
