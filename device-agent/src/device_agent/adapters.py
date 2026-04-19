from collections import deque
from dataclasses import dataclass, field

from device_agent.domain import ControlSubmission
from device_agent.hardware import ButtonHandler, ControlInputHandler, ScaleReader


@dataclass
class MockScaleReader(ScaleReader):
    samples: deque[int] = field(default_factory=deque)
    tare_offset: int = 0

    def read_weight_grams(self) -> int:
        if self.samples:
            return self.samples.popleft() - self.tare_offset
        return 0

    def tare(self) -> None:
        current = self.samples[0] if self.samples else 0
        self.tare_offset = current


@dataclass
class MockButtonHandler(ButtonHandler):
    presses: deque[bool] = field(default_factory=deque)

    def poll_pressed(self) -> bool:
        if self.presses:
            return self.presses.popleft()
        return False


@dataclass
class MockControlInputHandler(ControlInputHandler):
    submissions: deque[ControlSubmission] = field(default_factory=deque)

    def poll_submission(self) -> ControlSubmission | None:
        if self.submissions:
            return self.submissions.popleft()
        return None
