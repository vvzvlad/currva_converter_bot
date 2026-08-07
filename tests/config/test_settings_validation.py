# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Field validators of src/settings.py.

The db-path cases are the first line of defence against a real crash-loop; see the
comment above them.
"""

import pytest
from pydantic import ValidationError

from src.settings import Settings


def build(**overrides):
    """Build Settings without reading the developer's machine.

    `_env_file=None` switches off the `env_file=".env"` in Settings.model_config —
    otherwise every instance here would pick up the repository-root .env of whoever
    runs the suite. Every required field is passed explicitly for the same reason:
    init keyword arguments outrank the environment in pydantic-settings, so the
    result depends only on `overrides`.
    """
    return Settings(_env_file=None, bot_token="t", api_key="k", admin_user_id=1, **overrides)


# --- *_db_path ---------------------------------------------------------------
# A *.json database path fails at startup instead of at the first sqlite call: a
# deployment that pinned the pre-migration default keeps crash-looping on
# "file is not a database", which names nothing.

def test_json_statistics_path_is_rejected():
    with pytest.raises(ValidationError) as caught:
        build(statistics_db_path="data/statistics.json")
    message = str(caught.value)
    assert "statistics_db_path" in message
    assert ".db" in message


def test_json_user_settings_path_is_rejected():
    with pytest.raises(ValidationError) as caught:
        build(user_settings_db_path="data/user_settings.json")
    assert "user_settings_db_path" in str(caught.value)


def test_db_paths_are_accepted():
    settings = build(
        statistics_db_path="data/statistics.db",
        user_settings_db_path="data/user_settings.sqlite3",
    )
    assert settings.statistics_db_path == "data/statistics.db"
    assert settings.user_settings_db_path == "data/user_settings.sqlite3"


def test_the_rates_cache_may_still_be_json():
    # Only the two sqlite paths are constrained; the rates cache really is JSON.
    assert build(exchange_rates_cache_path="data/exchange_rates_cache.json").exchange_rates_cache_path == \
        "data/exchange_rates_cache.json"


@pytest.mark.parametrize("field", ["statistics_db_path", "user_settings_db_path"])
def test_a_trailing_space_is_stripped_from_an_accepted_path(field):
    # Trivially easy to produce in YAML or a .env line, and it would otherwise create
    # a file whose name really does end in a space.
    settings = build(**{field: "data/statistics.db "})
    assert getattr(settings, field) == "data/statistics.db"


# --- log_level ---------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("debug", "DEBUG"),
        (" info ", "INFO"),
        ("WARNING", "WARNING"),
        ("Error", "ERROR"),
        ("critical", "CRITICAL"),
    ],
)
def test_log_level_is_case_insensitive_and_normalised(raw, expected):
    assert build(log_level=raw).log_level == expected


def test_an_unusable_log_level_is_rejected():
    with pytest.raises(ValidationError) as caught:
        build(log_level="LOUD")
    message = str(caught.value)
    assert "log_level" in message
    assert "must be one of" in message


# --- watch_code_changes ------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        # `WATCH_CODE_CHANGES=` left in a .env or a compose file means "not set", not
        # "fail the whole bot at startup".
        ("", False),
        ("   ", False),
        # Padding is stripped, so ` true ` (trivial to produce in YAML) still works.
        (" true ", True),
        ("true", True),
        ("false", False),
        ("1", True),
        ("0", False),
        ("YES", True),
        ("off", False),
    ],
)
def test_watch_code_changes_accepts_the_usual_spellings(raw, expected):
    assert build(watch_code_changes=raw).watch_code_changes is expected


def test_watch_code_changes_still_rejects_a_genuinely_invalid_value():
    with pytest.raises(ValidationError) as caught:
        build(watch_code_changes="maybe")
    assert "watch_code_changes" in str(caught.value)


def test_watch_code_changes_defaults_to_off(monkeypatch):
    # The one case with no explicit override, so the ambient variable has to go: a
    # developer with WATCH_CODE_CHANGES exported would otherwise see this fail.
    monkeypatch.delenv("WATCH_CODE_CHANGES", raising=False)
    assert build().watch_code_changes is False
