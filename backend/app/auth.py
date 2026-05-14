import hmac
import os
import secrets
from itsdangerous import BadSignature, TimestampSigner

USERNAME = os.getenv("WEIGHT_DASHBOARD_USER", "admin")
PASSWORD = os.getenv("WEIGHT_DASHBOARD_PASSWORD", "change-me")
API_KEY = os.getenv("WEIGHT_DASHBOARD_API_KEY", PASSWORD)
SESSION_COOKIE = "weight_dashboard_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 12

_secret = os.getenv("WEIGHT_DASHBOARD_SECRET", "dev-weight-dashboard-secret")
_signer = TimestampSigner(_secret)


def check_credentials(username: str, password: str) -> bool:
    return hmac.compare_digest(username, USERNAME) and hmac.compare_digest(password, PASSWORD)


def check_api_key(api_key: str | None) -> bool:
    return bool(api_key) and hmac.compare_digest(api_key, API_KEY)


def create_session_token() -> str:
    raw = f"{USERNAME}:{secrets.token_urlsafe(24)}"
    return _signer.sign(raw).decode("utf-8")


def check_session_token(token: str | None) -> bool:
    if not token:
        return False
    try:
        value = _signer.unsign(token, max_age=SESSION_MAX_AGE_SECONDS).decode("utf-8")
    except BadSignature:
        return False
    return value.startswith(f"{USERNAME}:")
