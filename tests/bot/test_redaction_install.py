# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""_install_token_redaction() itself — the only part of the layer that can quietly
stop being wired up.

Everything else in this package drives _redact / the filter / the traceback writer
directly, so gutting the body of _install_token_redaction() left the whole suite
green while the token went to the log in production.

Everything the function touches is process-wide, so the fixture below snapshots it,
restores it afterwards (pytest has its own threading.excepthook and its own handlers on
the root logger) and resets it to a pristine, not-yet-installed state — otherwise
the assertions would be satisfied by the install that already ran at import time.
"""

import inspect
import io
import logging
import sys
import threading
from types import SimpleNamespace
from unittest import mock

import pytest
import telebot

from tests.bot.doubles import FAKE_SECRET, FAKE_TOKEN


def _all_handlers():
    """Every handler attached to any logger in the process, the root one included."""
    handlers = list(logging.getLogger().handlers)
    for existing in list(logging.Logger.manager.loggerDict.values()):
        if isinstance(existing, logging.Logger):
            handlers.extend(existing.handlers)
    return handlers


def _is_redacted(bot, handler):
    return any(isinstance(f, bot._TokenRedactingFilter) for f in handler.filters)


def _api_failure():
    try:
        raise RuntimeError(f"Max retries exceeded with url: /bot{FAKE_TOKEN}/sendMessage")
    except RuntimeError:
        return sys.exc_info()


@pytest.fixture
def pristine(bot, pinned_token):
    """Snapshot everything process-wide the install touches, then un-install it."""
    saved_excepthook = sys.excepthook
    saved_thread_excepthook = threading.excepthook
    saved_add_handler = logging.Logger.addHandler
    saved_filters = [(handler, list(handler.filters)) for handler in _all_handlers()]
    saved_telebot_handlers = list(telebot.logger.handlers)

    # Back to the state the interpreter is in before the module is imported:
    # the stdlib addHandler, no redacting filters anywhere, and telebot's own
    # StreamHandler back on the `TeleBot` logger.
    logging.Logger.addHandler = getattr(saved_add_handler, "_original_add_handler", saved_add_handler)
    for handler in _all_handlers():
        handler.filters = [f for f in handler.filters if not isinstance(f, bot._TokenRedactingFilter)]
    telebot_stream = io.StringIO()
    telebot.logger.handlers[:] = [logging.StreamHandler(telebot_stream)]

    yield SimpleNamespace(
        telebot_stream=telebot_stream,
        saved_excepthook=saved_excepthook,
        saved_thread_excepthook=saved_thread_excepthook,
    )

    sys.excepthook = saved_excepthook
    threading.excepthook = saved_thread_excepthook
    logging.Logger.addHandler = saved_add_handler
    for handler, filters in saved_filters:
        handler.filters = filters
    telebot.logger.handlers[:] = saved_telebot_handlers


@pytest.fixture
def capture_root(request):
    """Add a capturing handler to the root logger and return its buffer."""
    def _capture_root():
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logging.getLogger().addHandler(handler)
        request.addfinalizer(lambda: logging.getLogger().removeHandler(handler))
        return stream

    return _capture_root


def test_every_handler_that_already_exists_gets_the_filter(bot, pristine, request):
    """Including handlers on OTHER loggers: Logger.callHandlers walks from the
    emitting logger up to the root, so a handler on a non-root logger sees the
    record first — before any filter on the root handlers could clean it."""
    third_party = logging.getLogger("tests.pretend_third_party")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    third_party.addHandler(handler)
    third_party.propagate = False
    request.addfinalizer(lambda: setattr(third_party, "propagate", True))
    request.addfinalizer(lambda: third_party.removeHandler(handler))
    assert not _is_redacted(bot, handler)

    bot._install_token_redaction()

    assert _is_redacted(bot, handler)
    assert [h for h in _all_handlers() if not _is_redacted(bot, h)] == []

    third_party.error(f"connection to https://api.telegram.org/bot{FAKE_TOKEN}/getMe failed")
    assert FAKE_TOKEN not in stream.getvalue()
    assert FAKE_SECRET not in stream.getvalue()
    assert bot.TOKEN_PLACEHOLDER in stream.getvalue()


def test_a_handler_attached_after_the_install_is_covered_too(bot, pristine, request):
    """A dependency imported later brings its own logger and its own handler, and
    so does any later logging.basicConfig()."""
    bot._install_token_redaction()

    late = logging.getLogger("tests.pretend_late_import")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    late.addHandler(handler)
    late.propagate = False
    request.addfinalizer(lambda: setattr(late, "propagate", True))
    request.addfinalizer(lambda: late.removeHandler(handler))

    assert _is_redacted(bot, handler)
    late.error(f"connection to https://api.telegram.org/bot{FAKE_TOKEN}/getMe failed")
    assert FAKE_TOKEN not in stream.getvalue()
    assert bot.TOKEN_PLACEHOLDER in stream.getvalue()


def test_a_record_logged_through_the_telebot_logger_is_redacted(bot, pristine, capture_root):
    """The canary that started all this: telebot adds a StreamHandler(sys.stderr)
    to the `TeleBot` logger at import, and that handler emits before the root ones.
    Asserted on the combined output, so it holds whether the handler is filtered or
    dropped in favour of propagation."""
    root_stream = capture_root()

    bot._install_token_redaction()

    telebot.logger.error(
        f"Polling exception: conn refused: https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage"
    )

    written = pristine.telebot_stream.getvalue() + root_stream.getvalue()
    assert "Polling exception" in written
    assert FAKE_TOKEN not in written
    assert FAKE_SECRET not in written
    assert bot.TOKEN_PLACEHOLDER in written


def test_an_exception_object_logged_as_the_message_is_redacted(bot, pristine, capture_root):
    """`logger.error(exc)` / `logger.exception(exc)`: the exception OBJECT ends up
    in record.msg and is rendered with str() only inside getMessage()."""
    root_stream = capture_root()

    bot._install_token_redaction()

    error = RuntimeError(f"Max retries exceeded with url: /bot{FAKE_TOKEN}/sendMessage")
    logging.getLogger("tests.pretend_caller").error(error)

    assert FAKE_TOKEN not in root_stream.getvalue()
    assert FAKE_SECRET not in root_stream.getvalue()
    assert bot.TOKEN_PLACEHOLDER in root_stream.getvalue()


def test_both_exception_hooks_are_replaced_and_redact(bot, pristine):
    bot._install_token_redaction()

    assert sys.excepthook is not pristine.saved_excepthook
    assert threading.excepthook is not pristine.saved_thread_excepthook

    exc_type, exc_value, exc_tb = _api_failure()
    stderr = io.StringIO()
    with mock.patch.object(sys, "stderr", stderr):
        sys.excepthook(exc_type, exc_value, exc_tb)
        threading.excepthook(threading.ExceptHookArgs(
            (exc_type, exc_value, exc_tb, threading.current_thread())
        ))

    written = stderr.getvalue()
    assert written.count("Traceback (most recent call last)") == 2
    assert f"Exception in thread {threading.current_thread().name}:" in written
    assert FAKE_TOKEN not in written
    assert FAKE_SECRET not in written
    assert bot.TOKEN_PLACEHOLDER in written


def test_a_handler_without_filters_does_not_break_add_handler(bot, pristine, request):
    """A handler is a duck type as far as Logger.callHandlers is concerned — it only
    touches `.level` and `.handle()` — so a dependency (or its dictConfig) may well
    attach an object that has no `.filters` at all. Our wrapper patches addHandler
    for the WHOLE process, so it must not turn that into an AttributeError at the
    dependency's import time, with the handler already half-attached."""
    bot._install_token_redaction()

    class DuckHandler:
        level = logging.NOTSET

        def __init__(self):
            self.records = []

        def handle(self, record):
            self.records.append(record)

    duck = DuckHandler()
    odd = logging.getLogger("tests.pretend_duck_handler")
    odd.addHandler(duck)
    request.addfinalizer(lambda: odd.removeHandler(duck))

    assert duck in odd.handlers
    odd.error("a record for the duck")
    assert [r.getMessage() for r in duck.records] == ["a record for the duck"]


def test_a_failing_redactor_does_not_break_add_handler(bot, pristine, request):
    """The same guarantee from the other side: whatever goes wrong INSIDE the
    redaction layer, attaching a handler still has to succeed."""
    bot._install_token_redaction()

    target = logging.getLogger("tests.pretend_broken_redactor")
    handler = logging.StreamHandler(io.StringIO())
    request.addfinalizer(lambda: target.removeHandler(handler))

    with mock.patch.object(bot, "_attach_redactor", side_effect=RuntimeError("boom")):
        target.addHandler(handler)

    assert handler in target.handlers


def test_the_wrapper_keeps_the_stdlib_name_and_signature(bot, pristine, request):
    """The wrapper stands in for logging.Logger.addHandler process-wide, so a caller
    passing the argument by keyword (the stdlib name is `hdlr`) must keep working,
    and __name__ / signature must not start lying about whose method this is."""
    bot._install_token_redaction()

    target = logging.getLogger("tests.pretend_keyword_caller")
    handler = logging.StreamHandler(io.StringIO())
    target.addHandler(hdlr=handler)
    request.addfinalizer(lambda: target.removeHandler(handler))

    assert handler in target.handlers
    assert _is_redacted(bot, handler)
    assert logging.Logger.addHandler.__name__ == "addHandler"
    assert list(inspect.signature(logging.Logger.addHandler).parameters) == ["self", "hdlr"]


def test_installing_twice_does_not_stack_filters_or_wrappers(bot, pristine):
    bot._install_token_redaction()
    wrapper = logging.Logger.addHandler
    bot._install_token_redaction()

    assert logging.Logger.addHandler is wrapper
    for handler in _all_handlers():
        redactors = [f for f in handler.filters if isinstance(f, bot._TokenRedactingFilter)]
        assert len(redactors) == 1
