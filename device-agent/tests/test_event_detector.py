from datetime import UTC, datetime, timedelta
from pathlib import Path

from device_agent.config import AgentConfig
from device_agent.domain import BucketSession
from device_agent.services import EventDetector
from device_agent.video import StubVideoProvider


def make_config() -> AgentConfig:
    return AgentConfig(
        station_id="primary-line-01",
        station_type="primary",
        device_id="pi-primary-01",
        timezone="UTC",
        read_interval_seconds=1,
        noise_window_size=3,
        minimum_meaningful_log_delta=20,
        negative_delta_threshold=-100,
        negative_persistence_seconds=3,
        empty_bucket_threshold=150,
        empty_confirmation_seconds=2,
        heartbeat_interval_seconds=30,
        db_path=Path("test.db"),
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


def make_session() -> BucketSession:
    now = datetime(2026, 4, 18, 12, 0, 0, tzinfo=UTC)
    return BucketSession(
        session_id="bs_1",
        bucket_id="bucket_1",
        station_id="primary-line-01",
        station_type="primary",
        started_at_utc=now,
        ended_at_utc=None,
        status="active",
        expected_final_weight_grams=1000,
        last_logged_weight_grams=1000,
        last_non_empty_weight_grams=1000,
    )


def test_negative_drop_requires_persistence() -> None:
    config = make_config()
    detector = EventDetector(config, StubVideoProvider())
    session = make_session()
    start = datetime(2026, 4, 18, 12, 0, 0, tzinfo=UTC)

    first = detector.process_weight(
        session=session,
        previous_logged_weight_grams=1000,
        filtered_weight_grams=850,
        raw_weight_grams=850,
        now=start,
    )
    second = detector.process_weight(
        session=session,
        previous_logged_weight_grams=1000,
        filtered_weight_grams=840,
        raw_weight_grams=840,
        now=start + timedelta(seconds=1),
    )
    third = detector.process_weight(
        session=session,
        previous_logged_weight_grams=1000,
        filtered_weight_grams=830,
        raw_weight_grams=830,
        now=start + timedelta(seconds=2),
    )

    assert first.anomaly is None
    assert second.anomaly is None
    assert third.anomaly is not None
    assert third.anomaly.delta_grams == -170


def test_empty_bucket_closes_session_after_confirmation() -> None:
    config = make_config()
    detector = EventDetector(config, StubVideoProvider())
    session = make_session()
    start = datetime(2026, 4, 18, 12, 0, 0, tzinfo=UTC)

    first = detector.process_weight(
        session=session,
        previous_logged_weight_grams=1000,
        filtered_weight_grams=100,
        raw_weight_grams=100,
        now=start,
    )
    second = detector.process_weight(
        session=session,
        previous_logged_weight_grams=1000,
        filtered_weight_grams=90,
        raw_weight_grams=90,
        now=start + timedelta(seconds=1),
    )

    assert first.session_closed is False
    assert second.session_closed is True
