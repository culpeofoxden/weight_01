from __future__ import annotations

import json
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox, ttk
from urllib import error, request
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "tmp" / "bucket-simulator.log"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_bucket_id() -> str:
    return f"SIM-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def new_session_id() -> str:
    return f"bs_sim_{uuid4().hex}"


def new_event_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


@dataclass
class SessionState:
    bucket_id: str
    bucket_session_id: str
    started_at_utc: str
    current_weight_grams: int = 0
    expected_final_weight_grams: int = 0
    status: str = "active"


class ApiClient:
    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()

    def post(self, path: str, payload: dict, idempotency_key: str) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self.base_url}{path}",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
            },
        )
        try:
            with request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {"status": resp.status}
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Connection error: {exc.reason}") from exc


class SimulatorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Amber Bucket Simulator")
        self.root.geometry("860x720")

        self.api_base_var = tk.StringVar(value="http://127.0.0.1:8000")
        self.primary_key_var = tk.StringVar(value="primary-key")
        self.control_key_var = tk.StringVar(value="control-key")
        self.primary_station_var = tk.StringVar(value="primary-line-01")
        self.control_station_var = tk.StringVar(value="control-room-01")

        self.bucket_id_var = tk.StringVar(value="")
        self.session_id_var = tk.StringVar(value="")
        self.weight_var = tk.StringVar(value="1200")
        self.note_var = tk.StringVar(value="manual_control_check")
        self.status_var = tk.StringVar(value="Ready")

        self.session: SessionState | None = None

        self._build_ui()
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.log("Simulator started")

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)

        self._build_connection_frame(container)
        self._build_session_frame(container)
        self._build_actions_frame(container)
        self._build_log_frame(container)

        status_bar = ttk.Label(container, textvariable=self.status_var, anchor="w")
        status_bar.grid(row=4, column=0, sticky="ew", pady=(12, 0))

    def _build_connection_frame(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Connection", padding=12)
        frame.grid(row=0, column=0, sticky="ew")
        for idx in range(1, 4):
            frame.columnconfigure(idx, weight=1)

        ttk.Label(frame, text="API base").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.api_base_var).grid(row=0, column=1, columnspan=3, sticky="ew", padx=(8, 0))

        ttk.Label(frame, text="Primary API key").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.primary_key_var).grid(row=1, column=1, sticky="ew", padx=(8, 8), pady=(8, 0))
        ttk.Label(frame, text="Control API key").grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.control_key_var).grid(row=1, column=3, sticky="ew", padx=(8, 0), pady=(8, 0))

        ttk.Label(frame, text="Primary station").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.primary_station_var).grid(row=2, column=1, sticky="ew", padx=(8, 8), pady=(8, 0))
        ttk.Label(frame, text="Control station").grid(row=2, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.control_station_var).grid(row=2, column=3, sticky="ew", padx=(8, 0), pady=(8, 0))

    def _build_session_frame(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Bucket Session", padding=12)
        frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Bucket ID").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.bucket_id_var).grid(row=0, column=1, sticky="ew", padx=(8, 0))

        ttk.Label(frame, text="Session ID").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.session_id_var).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))

        ttk.Label(frame, text="Weight (g)").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.weight_var).grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))

        ttk.Label(frame, text="Control note").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.note_var).grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))

    def _build_actions_frame(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Actions", padding=12)
        frame.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        for idx in range(4):
            frame.columnconfigure(idx, weight=1)

        ttk.Button(frame, text="New Bucket", command=self.start_session).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(frame, text="Send Weight", command=self.send_weight).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(frame, text="Complete Bucket", command=self.complete_session).grid(row=0, column=2, sticky="ew", padx=8)
        ttk.Button(frame, text="Send Control Weight", command=self.send_control_weight).grid(row=0, column=3, sticky="ew", padx=(8, 0))

        ttk.Button(frame, text="Health Check", command=self.check_health).grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(10, 0))
        ttk.Button(frame, text="Open Frontend URL", command=self.open_frontend_hint).grid(row=1, column=1, columnspan=2, sticky="ew", padx=8, pady=(10, 0))
        ttk.Button(frame, text="Clear Log", command=self.clear_log).grid(row=1, column=3, sticky="ew", padx=(8, 0), pady=(10, 0))

    def _build_log_frame(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Event Log", padding=12)
        frame.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        parent.rowconfigure(3, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.log_box = tk.Text(frame, wrap="word", height=18)
        self.log_box.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.log_box.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_box.configure(yscrollcommand=scrollbar.set)

    def client(self, api_key: str) -> ApiClient:
        return ApiClient(base_url=self.api_base_var.get(), api_key=api_key)

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        self.log_box.insert("end", line + "\n")
        self.log_box.see("end")
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        self.status_var.set(message)

    def clear_log(self) -> None:
        self.log_box.delete("1.0", "end")
        self.status_var.set("Log cleared")

    def parse_weight(self) -> int:
        try:
            return int(self.weight_var.get().strip())
        except ValueError as exc:
            raise RuntimeError("Weight must be an integer in grams") from exc

    def ensure_session(self) -> SessionState:
        if not self.session:
            raise RuntimeError("Start a bucket session first")
        return self.session

    def start_session(self) -> None:
        try:
            weight = self.parse_weight()
            bucket_id = self.bucket_id_var.get().strip() or new_bucket_id()
            session_id = self.session_id_var.get().strip() or new_session_id()
            started_at = utc_now_iso()
            self.session = SessionState(
                bucket_id=bucket_id,
                bucket_session_id=session_id,
                started_at_utc=started_at,
                current_weight_grams=weight,
                expected_final_weight_grams=max(weight, 0),
                status="active",
            )
            self.bucket_id_var.set(bucket_id)
            self.session_id_var.set(session_id)

            payload = {
                "bucket_session_id": session_id,
                "bucket_id": bucket_id,
                "station_id": self.primary_station_var.get().strip(),
                "station_type": "primary",
                "started_at_utc": started_at,
                "ended_at_utc": None,
                "status": "active",
                "expected_final_weight_grams": max(weight, 0),
                "last_logged_weight_grams": weight,
                "last_non_empty_weight_grams": weight,
                "source_device_id": "bucket-simulator-ui",
            }
            result = self.client(self.primary_key_var.get()).post(
                "/api/v1/device/bucket-sessions",
                payload,
                idempotency_key=f"bucket_session:{session_id}:active",
            )
            self.log(f"Started bucket {bucket_id} session {session_id}: {result}")
        except Exception as exc:
            self.show_error(exc)

    def send_weight(self) -> None:
        try:
            session = self.ensure_session()
            weight = self.parse_weight()
            now = utc_now_iso()
            delta = weight - session.current_weight_grams
            session.current_weight_grams = weight
            session.expected_final_weight_grams = max(session.expected_final_weight_grams, weight)

            session_payload = {
                "bucket_session_id": session.bucket_session_id,
                "bucket_id": session.bucket_id,
                "station_id": self.primary_station_var.get().strip(),
                "station_type": "primary",
                "started_at_utc": session.started_at_utc,
                "ended_at_utc": None,
                "status": session.status,
                "expected_final_weight_grams": session.expected_final_weight_grams,
                "last_logged_weight_grams": weight,
                "last_non_empty_weight_grams": max(weight, 0),
                "source_device_id": "bucket-simulator-ui",
            }
            self.client(self.primary_key_var.get()).post(
                "/api/v1/device/bucket-sessions",
                session_payload,
                idempotency_key=f"bucket_session:{session.bucket_session_id}:update:{new_event_id('upd')}",
            )

            log_payload = {
                "event_id": new_event_id("wl"),
                "bucket_id": session.bucket_id,
                "bucket_session_id": session.bucket_session_id,
                "station_id": self.primary_station_var.get().strip(),
                "station_type": "primary",
                "recorded_at_utc": now,
                "weight_grams": weight,
                "delta_grams": delta,
                "raw_weight_grams": weight,
                "reason": "manual_simulator_entry",
            }
            result = self.client(self.primary_key_var.get()).post(
                "/api/v1/device/weight-logs",
                log_payload,
                idempotency_key=f"weight_log:{log_payload['event_id']}",
            )
            self.log(f"Sent weight {weight}g for {session.bucket_id}: {result}")
        except Exception as exc:
            self.show_error(exc)

    def complete_session(self) -> None:
        try:
            session = self.ensure_session()
            weight = self.parse_weight()
            session.current_weight_grams = weight
            session.status = "completed"

            payload = {
                "bucket_session_id": session.bucket_session_id,
                "bucket_id": session.bucket_id,
                "station_id": self.primary_station_var.get().strip(),
                "station_type": "primary",
                "started_at_utc": session.started_at_utc,
                "ended_at_utc": utc_now_iso(),
                "status": "completed",
                "expected_final_weight_grams": session.expected_final_weight_grams,
                "last_logged_weight_grams": weight,
                "last_non_empty_weight_grams": session.expected_final_weight_grams,
                "source_device_id": "bucket-simulator-ui",
            }
            result = self.client(self.primary_key_var.get()).post(
                "/api/v1/device/bucket-sessions",
                payload,
                idempotency_key=f"bucket_session:{session.bucket_session_id}:completed",
            )
            self.log(f"Completed bucket {session.bucket_id}: {result}")
        except Exception as exc:
            self.show_error(exc)

    def send_control_weight(self) -> None:
        try:
            session = self.ensure_session()
            weight = self.parse_weight()
            payload = {
                "control_weight_record_id": new_event_id("cw"),
                "bucket_id": session.bucket_id,
                "station_id": self.control_station_var.get().strip(),
                "station_type": "control",
                "recorded_at_utc": utc_now_iso(),
                "control_weight_grams": weight,
                "operator_note": self.note_var.get().strip() or "manual_control_check",
            }
            result = self.client(self.control_key_var.get()).post(
                "/api/v1/device/control-weight-records",
                payload,
                idempotency_key=f"control_weight_record:{payload['control_weight_record_id']}",
            )
            self.log(f"Sent control weight {weight}g for {session.bucket_id}: {result}")
        except Exception as exc:
            self.show_error(exc)

    def check_health(self) -> None:
        try:
            result = self.client(self.primary_key_var.get()).post(
                "/api/v1/device/heartbeats",
                {
                    "heartbeat_id": new_event_id("hb"),
                    "device_id": "bucket-simulator-ui",
                    "station_id": self.primary_station_var.get().strip(),
                    "station_type": "primary",
                    "recorded_at_utc": utc_now_iso(),
                    "agent_version": "simulator-ui",
                    "status": "ok",
                    "details": {"source": "bucket_simulator"},
                },
                idempotency_key=f"heartbeat:{new_event_id('hbcheck')}",
            )
            self.log(f"Heartbeat sent: {result}")
        except Exception as exc:
            self.show_error(exc)

    def open_frontend_hint(self) -> None:
        messagebox.showinfo(
            "Frontend URL",
            "Frontend is running at:\nhttp://127.0.0.1:5173\n\nLogin:\nadmin@example.com / admin123",
        )

    def show_error(self, exc: Exception) -> None:
        self.log(f"Error: {exc}")
        messagebox.showerror("Simulator Error", str(exc))


def main() -> None:
    root = tk.Tk()
    app = SimulatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
