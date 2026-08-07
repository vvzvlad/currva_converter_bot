from typing import Any

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

    # Development convenience: restart the process whenever a file in src/ changes.
    # Off by default and pointless in a container (the code never changes under a
    # running image), and it is not free: the restart goes through os.execv() from the
    # watchdog observer thread, which replaces the process image immediately — main()'s
    # finally never runs, so the sqlite stores are never closed properly.
    watch_code_changes: bool = False

    # All mutable state lives under data/ (mounted as a docker volume).
    # The two *_db_path files are sqlite databases; on first start each one
    # imports the same-named .json left behind by the pickleDB era.
    exchange_rates_cache_path: str = "data/exchange_rates_cache.json"
    statistics_db_path: str = "data/statistics.db"
    user_settings_db_path: str = "data/user_settings.db"

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

    @field_validator("watch_code_changes", mode="before")
    @classmethod
    def _empty_flag_is_off(cls, value: Any) -> Any:
        """Treat an empty / whitespace-only value as "off", and tolerate padding.

        pydantic understands true/false, 1/0, yes/no, on/off (any case) and rejects
        everything else with a readable message, which load_settings_or_exit turns into
        a named-variable error. It does NOT accept an empty string, though, and
        `WATCH_CODE_CHANGES=` left over in a .env or a compose file is a perfectly
        ordinary way of writing "not set" — failing the whole bot at startup over an
        optional development flag would be a crash-loop for no reason. Stripping also
        makes ` true ` (trivially easy to produce in YAML) behave like `true`.
        """
        if isinstance(value, str):
            cleaned = value.strip()
            return False if not cleaned else cleaned
        return value

    @field_validator("statistics_db_path", "user_settings_db_path")
    @classmethod
    def _reject_json_db_path(cls, value: str) -> str:
        """Refuse the pre-migration defaults, which were *.json files.

        A deployment that pinned `STATISTICS_DB_PATH=data/statistics.json` in its
        compose file or .env keeps working until this image is rolled out, and then
        sqlite opens the JSON file and dies with `DatabaseError: file is not a
        database` on every start — an endless crash-loop under `restart: always`,
        with nothing in the message pointing at the variable. Raising here routes
        it through load_settings_or_exit, which names the variable instead.
        """
        cleaned = value.strip()
        if cleaned.lower().endswith(".json"):
            raise ValueError(
                "must point at a sqlite database file (e.g. data/statistics.db), not a .json file; "
                "the old .json store sitting next to it is imported automatically on first start"
            )
        # The stripped value, not the original: `data/statistics.db ` with a trailing
        # space (trivial to end up with in YAML or a .env line) passes the check above
        # and would then create a file whose name really does end in a space. Same
        # normalise-then-return shape as _normalise_log_level.
        return cleaned


settings = load_settings_or_exit(Settings)
