from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AMBER_BACKEND_", extra="ignore")

    env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    database_url: str = "postgresql+psycopg://amber:amber@postgres:5432/amber_monitor"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    token_expire_minutes: int = 720
    device_api_keys: str = ""
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    default_timezone: str = "UTC"

    @property
    def device_api_keys_list(self) -> list[str]:
        if self.device_api_keys is None or self.device_api_keys == "":
            return []
        return [item.strip() for item in self.device_api_keys.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
