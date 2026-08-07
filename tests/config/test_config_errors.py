# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""load_settings_or_exit(): a pydantic ValidationError turned into a startup message.

The settings classes below are built here on purpose rather than imported from
src.settings: the real Settings reads the repository-root .env and the ambient
environment, and these tests must depend on neither. Every field name is prefixed so
that no plausible environment variable can collide with it, and each test removes the
variables it cares about before running.
"""

import pytest
from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.config_errors import load_settings_or_exit


class RequiredOnlySettings(BaseSettings):
    """One required field — the "variable is missing" path."""

    model_config = SettingsConfigDict(extra="ignore")

    cfgtest_token: str


class TypedValueSettings(BaseSettings):
    """One int field — an unparsable value is the "invalid value" path."""

    model_config = SettingsConfigDict(extra="ignore")

    cfgtest_port: int = 8080


class BothKindsSettings(BaseSettings):
    """A missing variable AND an invalid one, to check both sections at once."""

    model_config = SettingsConfigDict(extra="ignore")

    cfgtest_token: str
    cfgtest_port: int = 8080


class ValidatedSettings(BaseSettings):
    """A field validator that raises — the same shape as Settings.log_level."""

    model_config = SettingsConfigDict(extra="ignore", validate_default=True)

    cfgtest_level: str = "LOUD"

    @field_validator("cfgtest_level")
    @classmethod
    def _reject(cls, value: str) -> str:
        raise ValueError("must be one of: DEBUG, INFO")


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    for name in ("CFGTEST_TOKEN", "CFGTEST_PORT", "CFGTEST_LEVEL"):
        monkeypatch.delenv(name, raising=False)


def test_a_missing_variable_exits_with_its_name_in_upper_case(capsys):
    with pytest.raises(SystemExit) as caught:
        load_settings_or_exit(RequiredOnlySettings)

    assert caught.value.code == 1
    err = capsys.readouterr().err
    assert "Configuration error in environment / .env:" in err
    assert "Missing required variable(s):" in err
    assert "CFGTEST_TOKEN" in err
    # The field name as written in Python must not leak into the message: the reader
    # has to find the variable in a .env file, where it is upper case.
    assert "cfgtest_token" not in err
    assert "Invalid value(s):" not in err
    assert "Set them in .env (see .env.example) and try again." in err


def test_an_invalid_value_names_the_variable_and_quotes_pydantic(monkeypatch, capsys):
    monkeypatch.setenv("CFGTEST_PORT", "not-a-number")

    with pytest.raises(SystemExit) as caught:
        load_settings_or_exit(TypedValueSettings)

    assert caught.value.code == 1
    err = capsys.readouterr().err
    assert "Invalid value(s):" in err
    assert "CFGTEST_PORT:" in err
    assert "valid integer" in err
    assert "Missing required variable(s):" not in err


def test_a_validator_message_is_carried_through(capsys):
    with pytest.raises(SystemExit):
        load_settings_or_exit(ValidatedSettings)

    err = capsys.readouterr().err
    assert "CFGTEST_LEVEL: " in err
    assert "must be one of: DEBUG, INFO" in err


def test_both_kinds_of_error_are_reported_together(monkeypatch, capsys):
    monkeypatch.setenv("CFGTEST_PORT", "not-a-number")

    with pytest.raises(SystemExit):
        load_settings_or_exit(BothKindsSettings)

    err = capsys.readouterr().err
    assert "Missing required variable(s):" in err
    assert "    - CFGTEST_TOKEN" in err
    assert "Invalid value(s):" in err
    assert "    - CFGTEST_PORT:" in err


def test_a_non_validation_error_propagates_untouched(capsys):
    class Boom(Exception):
        pass

    def factory():
        raise Boom("kaboom")

    with pytest.raises(Boom, match="kaboom"):
        load_settings_or_exit(factory)

    # Not swallowed into a SystemExit, and nothing printed: only configuration
    # problems get the friendly treatment.
    assert capsys.readouterr().err == ""


def test_a_successful_factory_result_is_passed_through(monkeypatch):
    monkeypatch.setenv("CFGTEST_TOKEN", "abc")
    settings = load_settings_or_exit(RequiredOnlySettings)
    assert isinstance(settings, RequiredOnlySettings)
    assert settings.cfgtest_token == "abc"


def test_the_return_value_is_returned_as_is():
    sentinel = object()
    assert load_settings_or_exit(lambda: sentinel) is sentinel


def test_the_error_is_really_a_validation_error(capsys):
    # Guards the assumption the whole module rests on: these factories fail through
    # pydantic's ValidationError, which is the only exception type the helper handles.
    with pytest.raises(ValidationError):
        RequiredOnlySettings()
    capsys.readouterr()
