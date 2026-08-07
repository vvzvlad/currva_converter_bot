from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.config_errors import load_settings_or_exit


class Settings(BaseSettings):
    # Credentials — fields WITHOUT a default: a missing variable fails the app at startup.
    bot_token: str
    api_key: str

    # Telegram id of the admin allowed to run /stats. Required: without it the
    # command would silently be open to everyone.
    admin_user_id: int

    log_level: str = "INFO"

    # All mutable state lives under data/ (mounted as a docker volume).
    exchange_rates_cache_path: str = "data/exchange_rates_cache.json"
    statistics_db_path: str = "data/statistics.json"
    user_settings_db_path: str = "data/user_settings.json"

    # Optional InfluxDB metrics: reporting stays disabled while influx_version is unset.
    influx_version: str | None = None
    influx_url: str | None = None
    influx_topic: str | None = None
    influx_reporting_period: int = 300
    influx_token: str | None = None
    influx_org: str | None = None
    influx_bucket: str | None = None
    influx_db: str | None = None
    influx_user: str | None = None
    influx_password: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        """Accept any case, reject anything logging cannot use.

        Raising here routes the error through load_settings_or_exit, which prints
        the offending variable name instead of a raw traceback.
        """
        normalised = value.strip().upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if normalised not in allowed:
            raise ValueError(f"must be one of: {', '.join(sorted(allowed))}")
        return normalised


settings = load_settings_or_exit(Settings)
