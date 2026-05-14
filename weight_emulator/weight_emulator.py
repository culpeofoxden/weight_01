#!/usr/bin/env python3
"""
Small serial-port emulator for Arduino weight scales.

It creates a pseudo terminal and writes lines in this format:

    2026-05-08T12:34:56+01:00,3.742

The symlink path can be used by readers as if it were a USB serial device.
"""

import argparse
import math
import os
import pty
import random
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emulate Arduino scale serial output with timestamp and weight."
    )
    parser.add_argument(
        "--link",
        default="/tmp/weight_arduino",
        help="Symlink path exposed as the virtual serial device.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Seconds between measurements.",
    )
    parser.add_argument(
        "--start",
        type=float,
        default=0.0,
        help="Starting amber weight in kg.",
    )
    parser.add_argument(
        "--bucket-weight",
        type=float,
        default=1.2,
        help="Empty bucket weight in kg.",
    )
    parser.add_argument(
        "--max",
        dest="max_weight",
        type=float,
        default=30.0,
        help="Maximum amber weight in kg before the full bucket is removed.",
    )
    parser.add_argument(
        "--cycle-minutes",
        type=float,
        default=60.0,
        help="Approximate full bucket cycle duration in minutes.",
    )
    parser.add_argument(
        "--noise",
        type=float,
        default=0.005,
        help="Measurement noise in kg.",
    )
    parser.add_argument(
        "--unit",
        choices=("kg", "g"),
        default="kg",
        help="Output unit for the numeric weight.",
    )
    parser.add_argument(
        "--mode",
        choices=("fill", "stable", "empty"),
        default="fill",
        help="Weight behavior profile.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for repeatable test runs.",
    )
    parser.add_argument(
        "--tare-file",
        default="/tmp/weight_button",
        help="Command file for button emulation. Write 'press' and then 'release'.",
    )
    parser.add_argument(
        "--tare-hold-seconds",
        type=float,
        default=2.0,
        help="Button hold duration required to apply tare.",
    )
    return parser.parse_args()


class BucketModel:
    def __init__(
        self,
        start: float,
        bucket_weight: float,
        max_weight: float,
        cycle_minutes: float,
        noise: float,
        mode: str,
    ) -> None:
        self.start_amber_weight = max(0.0, start)
        self.bucket_weight = max(0.0, bucket_weight)
        self.max_weight = max(0.0, max_weight)
        self.cycle_seconds = max(10.0, cycle_minutes * 60.0)
        self.noise = max(0.0, noise)
        self.mode = mode
        self.bucket_present = mode != "empty"
        self.cycle_started_at = time.monotonic()
        self.bucket_serial = 1

    def next_weight(self) -> float:
        now = time.monotonic()

        if self.mode == "empty":
            base = 0.0
        elif self.mode == "stable":
            base = self.bucket_weight + self.start_amber_weight
        else:
            base = self._cycle_weight(now)

        measured = max(0.0, base + random.uniform(-self.noise, self.noise))
        return measured

    def _cycle_weight(self, now: float) -> float:
        elapsed = now - self.cycle_started_at
        if elapsed >= self.cycle_seconds:
            self._start_new_bucket(now)
            elapsed = 0.0

        fill_until = self.cycle_seconds * 0.88
        remove_at = self.cycle_seconds * 0.92

        if elapsed >= remove_at:
            self.bucket_present = False
            return 0.0

        self.bucket_present = True
        if elapsed <= fill_until:
            progress = max(0.0, min(1.0, elapsed / fill_until))
            amber_weight = self.start_amber_weight + self.max_weight * self._fill_curve(progress)
        else:
            amber_weight = self.start_amber_weight + self.max_weight

        loaded_weight = self.bucket_weight + min(self.max_weight, amber_weight)
        wobble = math.sin(now * 11.0) * min(0.02, max(0.003, loaded_weight * 0.004))
        return max(0.0, loaded_weight + wobble)

    def _start_new_bucket(self, now: float) -> None:
        self.bucket_serial += 1
        self.cycle_started_at = now
        self.bucket_present = True
        self.bucket_weight = max(0.0, random.gauss(self.bucket_weight, 0.08))

    @staticmethod
    def _fill_curve(progress: float) -> float:
        stepped = math.floor(progress * 24.0) / 24.0
        smooth = (1.0 - math.cos(stepped * math.pi)) / 2.0
        return max(0.0, min(1.0, smooth))


class TareController:
    def __init__(self, tare_file: str, hold_seconds: float) -> None:
        self._tare_file = tare_file
        self._hold_seconds = max(0.0, hold_seconds)
        self._last_tare_file_mtime = self._file_mtime(tare_file)
        self._pressed_since: Optional[float] = None
        self._forced_request = False

    def request(self) -> None:
        self._forced_request = True

    def consume(self) -> bool:
        file_requested = self._consume_button_file()
        forced = self._forced_request
        self._forced_request = False
        return file_requested or forced

    def close(self) -> None:
        return None

    def _consume_button_file(self) -> bool:
        mtime = self._file_mtime(self._tare_file)
        if mtime is None or mtime == self._last_tare_file_mtime:
            return False
        self._last_tare_file_mtime = mtime

        command = self._read_command(self._tare_file)
        now = time.monotonic()
        if command == "press":
            self._pressed_since = now
            return False

        if command == "release":
            if self._pressed_since is None:
                return False
            held_for = now - self._pressed_since
            self._pressed_since = None
            return held_for >= self._hold_seconds

        if command == "tare":
            return True

        return False

    @staticmethod
    def _file_mtime(path: str) -> Optional[float]:
        try:
            return os.stat(path).st_mtime
        except FileNotFoundError:
            return None

    @staticmethod
    def _read_command(path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as file:
                return file.read().strip().lower()
        except OSError:
            return ""


def install_symlink(link_path: str, target_path: str) -> None:
    if os.path.lexists(link_path):
        os.unlink(link_path)
    os.symlink(target_path, link_path)


def main() -> int:
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    master_fd, slave_fd = pty.openpty()
    os.set_blocking(master_fd, False)
    slave_name = os.ttyname(slave_fd)
    install_symlink(args.link, slave_name)

    running = True
    tare_offset_kg = 0.0
    last_physical_weight_kg = 0.0
    tare = TareController(args.tare_file, args.tare_hold_seconds)

    def stop(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    def request_tare(_signum: int, _frame: object) -> None:
        tare.request()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGUSR1, request_tare)

    model = BucketModel(
        args.start,
        args.bucket_weight,
        args.max_weight,
        args.cycle_minutes,
        args.noise,
        args.mode,
    )
    print(f"virtual serial device: {args.link} -> {slave_name}", flush=True)
    print(f"tare trigger file: {args.tare_file}", flush=True)
    print("press Ctrl+C to stop", flush=True)

    try:
        while running:
            physical_weight_kg = model.next_weight()
            if tare.consume():
                tare_offset_kg = last_physical_weight_kg
                print(f"tare set: {tare_offset_kg:.3f} kg", flush=True)

            last_physical_weight_kg = physical_weight_kg
            net_weight_kg = physical_weight_kg - tare_offset_kg
            value = net_weight_kg * 1000.0 if args.unit == "g" else net_weight_kg
            timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
            line = f"{timestamp},{value:.3f}\n"
            try:
                os.write(master_fd, line.encode("ascii"))
            except BlockingIOError:
                pass
            time.sleep(max(0.05, args.interval))
    finally:
        try:
            if os.path.islink(args.link) and os.readlink(args.link) == slave_name:
                os.unlink(args.link)
        finally:
            tare.close()
            os.close(master_fd)
            os.close(slave_fd)

    return 0


if __name__ == "__main__":
    sys.exit(main())
