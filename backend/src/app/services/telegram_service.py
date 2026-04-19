from datetime import datetime, timezone

import httpx

from app.config import get_settings
from app.models.models import AlertRecord, AlertStatus


class TelegramService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def send_alert(self, alert: AlertRecord) -> tuple[bool, str | None]:
        if not self.settings.telegram_enabled:
            return True, None

        message = alert.message_text
        bot_token = self.settings.telegram_bot_token
        chat_id = self.settings.telegram_chat_id
        if not bot_token or not chat_id:
            return False, "Telegram is enabled but bot token or chat id is missing"

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        try:
            response = httpx.post(url, json={"chat_id": chat_id, "text": message}, timeout=10.0)
            if response.status_code >= 400:
                return False, response.text
            body = response.json()
            if not body.get("ok", False):
                return False, str(body)
            return True, str(body.get("result", {}).get("message_id"))
        except Exception as exc:
            return False, str(exc)

    def mark_result(self, alert: AlertRecord, success: bool, detail: str | None) -> None:
        if success:
            alert.status = AlertStatus.sent
            alert.sent_at_utc = datetime.now(timezone.utc)
            alert.telegram_message_id = detail
            alert.error_text = None
        else:
            alert.status = AlertStatus.failed
            alert.error_text = detail
