import argparse
import logging
import threading
import time

from device_agent.adapters import MockButtonHandler, MockControlInputHandler, MockScaleReader
from device_agent.config import load_config
from device_agent.db import LocalStore
from device_agent.services import ApiClient, SyncWorker, build_runtime
from device_agent.video import StubVideoProvider


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Amber bucket device agent")
    parser.add_argument("--config", required=True, help="Path to station TOML config")
    return parser.parse_args()


def main() -> int:
    configure_logging()
    args = parse_args()
    config = load_config(args.config)
    store = LocalStore(config.db_path)

    scale_reader = MockScaleReader()
    button_handler = MockButtonHandler()
    control_input_handler = MockControlInputHandler()
    video_provider = StubVideoProvider()

    station_service, heartbeat_service = build_runtime(
        config,
        store,
        scale_reader,
        button_handler,
        control_input_handler,
        video_provider,
    )

    api_client = ApiClient(config)
    stop_event = threading.Event()
    sync_worker = SyncWorker(store, api_client, config, stop_event)
    sync_thread = threading.Thread(target=sync_worker.run, name="sync-worker", daemon=True)
    sync_thread.start()

    try:
        while True:
            station_service.tick()
            heartbeat_service.tick()
            time.sleep(config.read_interval_seconds)
    except KeyboardInterrupt:
        logging.info("shutting down device agent")
    finally:
        stop_event.set()
        sync_thread.join(timeout=5)
        api_client.close()
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
