# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""_TokenRedactingFilter driven directly, record by record."""

import io
import logging
import sys
from unittest import mock

import pytest

from tests.bot.doubles import FAKE_SECRET, FAKE_TOKEN

pytestmark = pytest.mark.usefixtures("pinned_token")


@pytest.fixture
def redacting_filter(bot):
    return bot._TokenRedactingFilter()


@pytest.fixture
def formatter():
    return logging.Formatter("%(levelname)s - %(message)s")


def _record(msg, args=None, exc_info=None):
    return logging.LogRecord(
        name="bot", level=logging.ERROR, pathname=__file__, lineno=1,
        msg=msg, args=args, exc_info=exc_info,
    )


def _api_failure():
    """An exception whose text carries the token, the way requests produces it."""
    try:
        raise RuntimeError(
            "HTTPSConnectionPool(host='api.telegram.org', port=443): Max retries "
            f"exceeded with url: /bot{FAKE_TOKEN}/sendMessage"
        )
    except RuntimeError:
        return sys.exc_info()


def test_message_text_is_scrubbed(bot, redacting_filter, formatter):
    record = _record(f"failed to call /bot{FAKE_TOKEN}/getMe")
    assert redacting_filter.filter(record)
    assert FAKE_TOKEN not in formatter.format(record)
    assert bot.TOKEN_PLACEHOLDER in formatter.format(record)


def test_positional_args_are_scrubbed(bot, redacting_filter, formatter):
    record = _record("request failed: %s", args=(f"https://api.telegram.org/bot{FAKE_TOKEN}/getMe",))
    assert redacting_filter.filter(record)
    formatted = formatter.format(record)
    assert FAKE_TOKEN not in formatted
    assert FAKE_SECRET not in formatted
    assert bot.TOKEN_PLACEHOLDER in formatted


def test_dict_args_are_scrubbed(redacting_filter, formatter):
    # A mapping is passed to LogRecord wrapped in a one-element tuple — that is how
    # logging.debug("%(url)s", {...}) reaches it, and LogRecord unwraps it itself.
    record = _record("request failed: %(url)s", args=({"url": f"/bot{FAKE_TOKEN}/getMe"},))
    assert isinstance(record.args, dict)
    assert redacting_filter.filter(record)
    assert FAKE_TOKEN not in formatter.format(record)


def test_rendered_traceback_is_scrubbed(bot, redacting_filter, formatter):
    record = _record("Bot crashed with unexpected error", exc_info=_api_failure())
    assert redacting_filter.filter(record)
    formatted = formatter.format(record)
    assert "Traceback (most recent call last)" in formatted
    assert FAKE_TOKEN not in formatted
    assert FAKE_SECRET not in formatted
    assert bot.TOKEN_PLACEHOLDER in formatted


def test_filtering_twice_does_not_double_mask(redacting_filter, formatter):
    """Two handlers see the same record; the second pass must be a no-op."""
    record = _record("boom", exc_info=_api_failure())
    redacting_filter.filter(record)
    once = formatter.format(record)
    redacting_filter.filter(record)
    assert formatter.format(record) == once


def test_an_exception_object_as_the_message_is_scrubbed(bot, redacting_filter, formatter):
    """logger.error(exc): record.msg is the exception, not a string."""
    record = _record(RuntimeError(f"failed to call /bot{FAKE_TOKEN}/getMe"))
    assert redacting_filter.filter(record)
    formatted = formatter.format(record)
    assert FAKE_TOKEN not in formatted
    assert FAKE_SECRET not in formatted
    assert bot.TOKEN_PLACEHOLDER in formatted


def test_a_non_string_arg_is_scrubbed_without_breaking_numeric_formats(bot, redacting_filter, formatter):
    record = _record(
        "call %r failed after %d attempts",
        args=(RuntimeError(f"/bot{FAKE_TOKEN}/getMe"), 3),
    )
    assert redacting_filter.filter(record)
    formatted = formatter.format(record)
    assert FAKE_TOKEN not in formatted
    assert bot.TOKEN_PLACEHOLDER in formatted
    # The int survived as an int — "%d" against a str raises TypeError.
    assert "after 3 attempts" in formatted


def test_a_rendered_traceback_does_not_gain_a_blank_line(redacting_filter, formatter):
    """Formatter.formatException() strips the trailing newline before the formatter
    adds its own separator; exc_text filled in by the filter has to match."""
    record = _record("boom", exc_info=_api_failure())
    assert redacting_filter.filter(record)
    formatted = formatter.format(record)
    assert not formatted.endswith("\n")
    assert "\n\n" not in formatted


def test_stack_info_is_scrubbed(redacting_filter):
    record = _record("boom")
    record.stack_info = f"  File \"x.py\", line 1, in f\n    call('/bot{FAKE_TOKEN}/getMe')"
    assert redacting_filter.filter(record)
    assert FAKE_TOKEN not in record.stack_info


def test_uncaught_traceback_written_to_stderr_is_scrubbed(bot):
    """The excepthook path: same text, but printed by the interpreter, not logged."""
    exc_type, exc_value, exc_tb = _api_failure()
    stderr = io.StringIO()
    with mock.patch.object(sys, "stderr", stderr):
        bot._write_redacted_traceback(exc_type, exc_value, exc_tb, header="Exception in thread worker:\n")
    written = stderr.getvalue()
    assert "Exception in thread worker:" in written
    assert "Traceback (most recent call last)" in written
    assert FAKE_TOKEN not in written
    assert FAKE_SECRET not in written
    assert bot.TOKEN_PLACEHOLDER in written
