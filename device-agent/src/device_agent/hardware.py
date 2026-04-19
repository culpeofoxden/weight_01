from typing import Protocol

from device_agent.domain import ControlSubmission


class ScaleReader(Protocol):
    def read_weight_grams(self) -> int:
        ...

    def tare(self) -> None:
        ...


class ButtonHandler(Protocol):
    def poll_pressed(self) -> bool:
        ...


class ControlInputHandler(Protocol):
    def poll_submission(self) -> ControlSubmission | None:
        ...


class VideoProvider(Protocol):
    def build_clip_metadata(
        self,
        *,
        bucket_id: str,
        station_id: str,
        event_type: str,
        occurred_at_utc: str,
    ) -> dict:
        ...
