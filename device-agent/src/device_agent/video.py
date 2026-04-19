from device_agent.hardware import VideoProvider


class StubVideoProvider(VideoProvider):
    def build_clip_metadata(
        self,
        *,
        bucket_id: str,
        station_id: str,
        event_type: str,
        occurred_at_utc: str,
    ) -> dict:
        return {
            "provider": "stub",
            "status": "not_captured",
            "bucket_id": bucket_id,
            "station_id": station_id,
            "event_type": event_type,
            "occurred_at_utc": occurred_at_utc,
            "clip_window_seconds": 30,
            "pre_event_seconds": 15,
            "post_event_seconds": 15,
            "future_rtsp_provider": "dahua",
            "capture_command_template": "ffmpeg -rtsp_transport tcp -i <rtsp-url> ...",
        }
