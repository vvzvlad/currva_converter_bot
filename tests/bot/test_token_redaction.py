# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""_redact() itself.

The most valuable tests in this package: they are what keeps the leak from coming back.
"""

from unittest import mock

import pytest

from tests.bot.doubles import FAKE_SECRET, FAKE_TOKEN, UNKNOWN_TOKEN

pytestmark = pytest.mark.usefixtures("pinned_token")


def test_full_token_in_an_api_url_is_masked(bot):
    text = f"HTTPSConnectionPool: Max retries exceeded with url: /bot{FAKE_TOKEN}/getMe"
    redacted = bot._redact(text)
    assert FAKE_TOKEN not in redacted
    assert FAKE_SECRET not in redacted
    assert bot.TOKEN_PLACEHOLDER in redacted


def test_secret_half_alone_is_masked(bot):
    redacted = bot._redact(f"telebot masked the id but kept {FAKE_SECRET} in the message")
    assert FAKE_SECRET not in redacted
    assert bot.TOKEN_PLACEHOLDER in redacted


def test_token_shaped_string_never_seen_before_is_masked(bot):
    """The regex net: a token this process was not started with still gets masked."""
    redacted = bot._redact(f"https://api.telegram.org/bot{UNKNOWN_TOKEN}/sendMessage")
    assert UNKNOWN_TOKEN not in redacted
    assert bot.TOKEN_PLACEHOLDER in redacted


def test_unrelated_text_is_left_alone(bot):
    text = "Error processing message in chat -100123"
    assert bot._redact(text) == text


def test_non_strings_without_a_secret_keep_their_type(bot):
    """record.args feed %-formatting, so an int that came back as a str would
    break "%d"."""
    for value in (42, None, 3.5, ["a"], {"b": 1}):
        redacted = bot._redact(value)
        assert redacted == value
        assert type(redacted) is type(value)


def test_an_exception_object_carrying_the_token_is_masked(bot):
    """`logger.error(exc)` puts the OBJECT into record.msg and getMessage() renders
    it with str() later, so returning non-strings untouched leaked the whole token."""
    error = RuntimeError(f"Max retries exceeded with url: /bot{FAKE_TOKEN}/sendMessage")
    redacted = bot._redact(error)
    assert FAKE_TOKEN not in str(redacted)
    assert FAKE_SECRET not in str(redacted)
    assert bot.TOKEN_PLACEHOLDER in str(redacted)


def test_a_value_whose_str_raises_is_left_alone(bot):
    class Unprintable:
        def __str__(self):
            raise ValueError("no")

    value = Unprintable()
    assert bot._redact(value) is value


def test_the_apilayer_key_is_masked(bot):
    """No live leak today — the key travels in a header — but _fetch_usd_rates puts
    the API response body into the text of the exception it raises."""
    with mock.patch.object(bot.settings, "api_key", "apilayer-secret-key-value"):
        redacted = bot._redact("API request failed. Response: {'key': 'apilayer-secret-key-value'}")
    assert "apilayer-secret-key-value" not in redacted
    assert bot.API_KEY_PLACEHOLDER in redacted


def test_the_influx_token_is_masked_and_an_unset_one_is_harmless(bot):
    with mock.patch.object(bot.settings, "influx_token", "influx-secret-token-value"):
        redacted = bot._redact("Authorization: Token influx-secret-token-value")
    assert "influx-secret-token-value" not in redacted
    assert bot.INFLUX_TOKEN_PLACEHOLDER in redacted

    # INFLUX_TOKEN is unset in every deployment without metrics, and API_KEY may be
    # short enough that searching for it would mangle ordinary text.
    with mock.patch.object(bot.settings, "influx_token", None), \
         mock.patch.object(bot.settings, "api_key", "k"):
        text = "a message that mentions a key and nothing else"
        assert bot._redact(text) == text
