# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Tests for the pure / easily substitutable helpers in src/bot.py.

The handlers themselves are network-bound, but the pieces they are built from are not:
token redaction, the forward detection, the rate pre-fetch and the message-parsing entry
point all take plain arguments and can be driven directly.

Importing src.bot is the only awkward part — see _import_bot_module below. Nothing here
touches the network or the real data/ directory: the three managers the module builds at
import time are neutralised for the duration of the import, and every test that needs one
puts its own recorder in the module global.
"""

import importlib
import inspect
import io
import logging
import sys
import threading
import time
import unittest
from unittest import mock

import telebot
from telebot import types

from src import exchange_rates_manager as exchange_rates_manager_module
from src import statistics_manager as statistics_manager_module
from src import user_settings_manager as user_settings_manager_module
from src.settings import settings

# A token that is obviously fake but has the shape of a real one: telebot's TeleBot()
# refuses anything without a colon, and the tests below need a value they can search for
# in the output rather than whatever BOT_TOKEN happens to be in the environment (CI sets
# BOT_TOKEN=test-token, a developer may have a real one exported).
FAKE_TOKEN = "1234567890:AAFakeTokenForTestsOnly-0123456789abcdef"
FAKE_SECRET = FAKE_TOKEN.split(":", 1)[1]

# A DIFFERENT token, never known to the module — only the URL-shaped regex can catch it.
UNKNOWN_TOKEN = "987654321:BBSomeOtherBotSecret-9876543210zyxwvu"


def _import_bot_module():
    """Import src.bot without letting its import-time side effects out.

    At import the module constructs an ExchangeRatesManager (which downloads rates over
    the network and starts a background thread), a StatisticsManager and a
    UserSettingsManager (which each open a sqlite database under data/), and a TeleBot.
    The three managers get a no-op __init__ for the duration of the import; the tests
    replace the resulting empty instances with their own doubles where they need one.

    settings.bot_token is pinned to FAKE_TOKEN for the import as well: TeleBot validates
    the shape of the token, and _TOKEN_SECRET is derived from it once, at import time.
    Both are put back afterwards so the rest of the suite sees the settings object it
    would have seen anyway.
    """
    if "src.bot" in sys.modules:
        # import_module would hand back the cached module and quietly skip the patches
        # below — meaning src.bot was imported by somebody else with the REAL managers,
        # so the rates manager went to apilayer over the network and the other two
        # opened the live databases. Nothing in this file would notice.
        raise RuntimeError(
            "src.bot was already imported before tests/test_bot_helpers.py ran; its "
            "import-time side effects (network + the sqlite stores) were therefore not "
            "neutralised. Import src.bot only through _import_bot_module()."
        )

    def _noop_init(self, *args, **kwargs):
        return None

    original_token = settings.bot_token
    settings.bot_token = FAKE_TOKEN
    # _install_token_redaction() replaces both interpreter-wide exception hooks. pytest
    # installs its own threading.excepthook to report unhandled thread exceptions, so the
    # originals are restored once the module is loaded — the hooks are tested by calling
    # the function they delegate to, not by leaving them wired up for the whole session.
    saved_hooks = (sys.excepthook, threading.excepthook)
    try:
        with mock.patch.object(exchange_rates_manager_module.ExchangeRatesManager, "__init__", _noop_init), \
             mock.patch.object(statistics_manager_module.StatisticsManager, "__init__", _noop_init), \
             mock.patch.object(user_settings_manager_module.UserSettingsManager, "__init__", _noop_init):
            return importlib.import_module("src.bot")
    finally:
        sys.excepthook, threading.excepthook = saved_hooks
        settings.bot_token = original_token


bot = _import_bot_module()


def _message(**extra):
    """Build a real telebot Message from an API payload.

    de_json rather than a hand-rolled fake: the whole point of the forward tests is which
    fields Telegram actually sends, and telebot's own deserialisation is what decides
    whether forward_from ends up set.
    """
    payload = {
        "message_id": 1,
        "date": int(time.time()),
        "chat": {"id": -1001234567890, "type": "supergroup", "title": "Test chat"},
        "from": {"id": 42, "is_bot": False, "first_name": "Tester", "username": "tester"},
        "text": "hello",
    }
    payload.update(extra)
    return types.Message.de_json(payload)


def _inline_query(text):
    """A real telebot InlineQuery, built from an API payload like _message() is."""
    return types.InlineQuery.de_json({
        "id": "inline-1",
        "from": {"id": 42, "is_bot": False, "first_name": "Tester", "username": "tester"},
        "query": text,
        "offset": "",
    })


class LegacyMessage:
    """A message object from a telebot old enough to have no forward_origin at all."""

    def __init__(self, **fields):
        for name in ("forward_from", "forward_from_chat", "forward_sender_name", "forward_date"):
            setattr(self, name, fields.get(name))


class RecordingRatesManager:
    """Records every pair asked for, so a test can assert on the size of the request."""

    def __init__(self, missing=()):
        self.requested = []
        self._missing = set(missing)

    def get_rate(self, from_currency, to_currency):
        self.requested.append((from_currency, to_currency))
        if (from_currency, to_currency) in self._missing:
            return None
        return 1.0

    @property
    def requested_targets(self):
        return {target for _source, target in self.requested}


class RecordingBot:
    """The bits of TeleBot the handlers use, with the network taken out."""

    def __init__(self):
        self.replies = []
        self.sent = []
        self.answered = []

    def reply_to(self, message, text):
        self.replies.append((message, text))
        return None

    def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))
        return None

    def answer_inline_query(self, inline_query_id, results, **kwargs):
        self.answered.append((inline_query_id, results))
        return None


class StubUserSettings:
    def __init__(self, currencies=None, disabled=False):
        self._currencies = currencies
        self._disabled = disabled

    def get_currencies(self, entity_id, is_chat=False):
        return self._currencies

    def is_chat_disabled(self, chat_id):
        return self._disabled

    def set_chat_disabled(self, chat_id, duration):
        return None


class StubStatistics:
    def __init__(self):
        self.logged = []

    def log_request(self, user=None, chat_id=None, chat_title=None, is_inline=False):
        self.logged.append((user, chat_id, chat_title, is_inline))


class TokenRedactionTestCase(unittest.TestCase):
    """The most valuable tests in this file: they are what keeps the leak from coming back."""

    def setUp(self):
        # _redact() reads settings.bot_token on every call, while _TOKEN_SECRET was bound
        # once at import. Both are pinned so the assertions do not depend on the ambient
        # BOT_TOKEN.
        for patcher in (
            mock.patch.object(bot.settings, "bot_token", FAKE_TOKEN),
            mock.patch.object(bot, "_TOKEN_SECRET", FAKE_SECRET),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_full_token_in_an_api_url_is_masked(self):
        text = f"HTTPSConnectionPool: Max retries exceeded with url: /bot{FAKE_TOKEN}/getMe"
        redacted = bot._redact(text)
        self.assertNotIn(FAKE_TOKEN, redacted)
        self.assertNotIn(FAKE_SECRET, redacted)
        self.assertIn(bot.TOKEN_PLACEHOLDER, redacted)

    def test_secret_half_alone_is_masked(self):
        redacted = bot._redact(f"telebot masked the id but kept {FAKE_SECRET} in the message")
        self.assertNotIn(FAKE_SECRET, redacted)
        self.assertIn(bot.TOKEN_PLACEHOLDER, redacted)

    def test_token_shaped_string_never_seen_before_is_masked(self):
        """The regex net: a token this process was not started with still gets masked."""
        redacted = bot._redact(f"https://api.telegram.org/bot{UNKNOWN_TOKEN}/sendMessage")
        self.assertNotIn(UNKNOWN_TOKEN, redacted)
        self.assertIn(bot.TOKEN_PLACEHOLDER, redacted)

    def test_unrelated_text_is_left_alone(self):
        text = "Error processing message in chat -100123"
        self.assertEqual(bot._redact(text), text)

    def test_non_strings_without_a_secret_keep_their_type(self):
        """record.args feed %-formatting, so an int that came back as a str would
        break "%d"."""
        for value in (42, None, 3.5, ["a"], {"b": 1}):
            redacted = bot._redact(value)
            self.assertEqual(redacted, value)
            self.assertIs(type(redacted), type(value))

    def test_an_exception_object_carrying_the_token_is_masked(self):
        """`logger.error(exc)` puts the OBJECT into record.msg and getMessage() renders
        it with str() later, so returning non-strings untouched leaked the whole token."""
        error = RuntimeError(f"Max retries exceeded with url: /bot{FAKE_TOKEN}/sendMessage")
        redacted = bot._redact(error)
        self.assertNotIn(FAKE_TOKEN, str(redacted))
        self.assertNotIn(FAKE_SECRET, str(redacted))
        self.assertIn(bot.TOKEN_PLACEHOLDER, str(redacted))

    def test_a_value_whose_str_raises_is_left_alone(self):
        class Unprintable:
            def __str__(self):
                raise ValueError("no")

        value = Unprintable()
        self.assertIs(bot._redact(value), value)

    def test_the_apilayer_key_is_masked(self):
        """No live leak today — the key travels in a header — but _fetch_usd_rates puts
        the API response body into the text of the exception it raises."""
        with mock.patch.object(bot.settings, "api_key", "apilayer-secret-key-value"):
            redacted = bot._redact("API request failed. Response: {'key': 'apilayer-secret-key-value'}")
        self.assertNotIn("apilayer-secret-key-value", redacted)
        self.assertIn(bot.API_KEY_PLACEHOLDER, redacted)

    def test_the_influx_token_is_masked_and_an_unset_one_is_harmless(self):
        with mock.patch.object(bot.settings, "influx_token", "influx-secret-token-value"):
            redacted = bot._redact("Authorization: Token influx-secret-token-value")
        self.assertNotIn("influx-secret-token-value", redacted)
        self.assertIn(bot.INFLUX_TOKEN_PLACEHOLDER, redacted)

        # INFLUX_TOKEN is unset in every deployment without metrics, and API_KEY may be
        # short enough that searching for it would mangle ordinary text.
        with mock.patch.object(bot.settings, "influx_token", None), \
             mock.patch.object(bot.settings, "api_key", "k"):
            text = "a message that mentions a key and nothing else"
            self.assertEqual(bot._redact(text), text)


class TokenRedactingFilterTestCase(unittest.TestCase):
    def setUp(self):
        for patcher in (
            mock.patch.object(bot.settings, "bot_token", FAKE_TOKEN),
            mock.patch.object(bot, "_TOKEN_SECRET", FAKE_SECRET),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.filter = bot._TokenRedactingFilter()
        self.formatter = logging.Formatter("%(levelname)s - %(message)s")

    def _record(self, msg, args=None, exc_info=None):
        return logging.LogRecord(
            name="bot", level=logging.ERROR, pathname=__file__, lineno=1,
            msg=msg, args=args, exc_info=exc_info,
        )

    @staticmethod
    def _api_failure():
        """An exception whose text carries the token, the way requests produces it."""
        try:
            raise RuntimeError(
                "HTTPSConnectionPool(host='api.telegram.org', port=443): Max retries "
                f"exceeded with url: /bot{FAKE_TOKEN}/sendMessage"
            )
        except RuntimeError:
            return sys.exc_info()

    def test_message_text_is_scrubbed(self):
        record = self._record(f"failed to call /bot{FAKE_TOKEN}/getMe")
        self.assertTrue(self.filter.filter(record))
        self.assertNotIn(FAKE_TOKEN, self.formatter.format(record))
        self.assertIn(bot.TOKEN_PLACEHOLDER, self.formatter.format(record))

    def test_positional_args_are_scrubbed(self):
        record = self._record("request failed: %s", args=(f"https://api.telegram.org/bot{FAKE_TOKEN}/getMe",))
        self.assertTrue(self.filter.filter(record))
        formatted = self.formatter.format(record)
        self.assertNotIn(FAKE_TOKEN, formatted)
        self.assertNotIn(FAKE_SECRET, formatted)
        self.assertIn(bot.TOKEN_PLACEHOLDER, formatted)

    def test_dict_args_are_scrubbed(self):
        # A mapping is passed to LogRecord wrapped in a one-element tuple — that is how
        # logging.debug("%(url)s", {...}) reaches it, and LogRecord unwraps it itself.
        record = self._record("request failed: %(url)s", args=({"url": f"/bot{FAKE_TOKEN}/getMe"},))
        self.assertIsInstance(record.args, dict)
        self.assertTrue(self.filter.filter(record))
        self.assertNotIn(FAKE_TOKEN, self.formatter.format(record))

    def test_rendered_traceback_is_scrubbed(self):
        record = self._record("Bot crashed with unexpected error", exc_info=self._api_failure())
        self.assertTrue(self.filter.filter(record))
        formatted = self.formatter.format(record)
        self.assertIn("Traceback (most recent call last)", formatted)
        self.assertNotIn(FAKE_TOKEN, formatted)
        self.assertNotIn(FAKE_SECRET, formatted)
        self.assertIn(bot.TOKEN_PLACEHOLDER, formatted)

    def test_filtering_twice_does_not_double_mask(self):
        """Two handlers see the same record; the second pass must be a no-op."""
        record = self._record("boom", exc_info=self._api_failure())
        self.filter.filter(record)
        once = self.formatter.format(record)
        self.filter.filter(record)
        self.assertEqual(self.formatter.format(record), once)

    def test_an_exception_object_as_the_message_is_scrubbed(self):
        """logger.error(exc): record.msg is the exception, not a string."""
        record = self._record(RuntimeError(f"failed to call /bot{FAKE_TOKEN}/getMe"))
        self.assertTrue(self.filter.filter(record))
        formatted = self.formatter.format(record)
        self.assertNotIn(FAKE_TOKEN, formatted)
        self.assertNotIn(FAKE_SECRET, formatted)
        self.assertIn(bot.TOKEN_PLACEHOLDER, formatted)

    def test_a_non_string_arg_is_scrubbed_without_breaking_numeric_formats(self):
        record = self._record(
            "call %r failed after %d attempts",
            args=(RuntimeError(f"/bot{FAKE_TOKEN}/getMe"), 3),
        )
        self.assertTrue(self.filter.filter(record))
        formatted = self.formatter.format(record)
        self.assertNotIn(FAKE_TOKEN, formatted)
        self.assertIn(bot.TOKEN_PLACEHOLDER, formatted)
        # The int survived as an int — "%d" against a str raises TypeError.
        self.assertIn("after 3 attempts", formatted)

    def test_a_rendered_traceback_does_not_gain_a_blank_line(self):
        """Formatter.formatException() strips the trailing newline before the formatter
        adds its own separator; exc_text filled in by the filter has to match."""
        record = self._record("boom", exc_info=self._api_failure())
        self.assertTrue(self.filter.filter(record))
        formatted = self.formatter.format(record)
        self.assertFalse(formatted.endswith("\n"))
        self.assertNotIn("\n\n", formatted)

    def test_stack_info_is_scrubbed(self):
        record = self._record("boom")
        record.stack_info = f"  File \"x.py\", line 1, in f\n    call('/bot{FAKE_TOKEN}/getMe')"
        self.assertTrue(self.filter.filter(record))
        self.assertNotIn(FAKE_TOKEN, record.stack_info)

    def test_uncaught_traceback_written_to_stderr_is_scrubbed(self):
        """The excepthook path: same text, but printed by the interpreter, not logged."""
        exc_type, exc_value, exc_tb = self._api_failure()
        stderr = io.StringIO()
        with mock.patch.object(sys, "stderr", stderr):
            bot._write_redacted_traceback(exc_type, exc_value, exc_tb, header="Exception in thread worker:\n")
        written = stderr.getvalue()
        self.assertIn("Exception in thread worker:", written)
        self.assertIn("Traceback (most recent call last)", written)
        self.assertNotIn(FAKE_TOKEN, written)
        self.assertNotIn(FAKE_SECRET, written)
        self.assertIn(bot.TOKEN_PLACEHOLDER, written)


def _all_handlers():
    """Every handler attached to any logger in the process, the root one included."""
    handlers = list(logging.getLogger().handlers)
    for existing in list(logging.Logger.manager.loggerDict.values()):
        if isinstance(existing, logging.Logger):
            handlers.extend(existing.handlers)
    return handlers


def _is_redacted(handler):
    return any(isinstance(f, bot._TokenRedactingFilter) for f in handler.filters)


class InstallTokenRedactionTestCase(unittest.TestCase):
    """_install_token_redaction() itself — the only part of the layer that can quietly
    stop being wired up.

    Everything else in this file drives _redact / the filter / the traceback writer
    directly, so gutting the body of _install_token_redaction() left the whole suite
    green while the token went to the log in production.

    Everything the function touches is process-wide, so setUp snapshots it, restores it
    through addCleanup (pytest has its own threading.excepthook and its own handlers on
    the root logger) and resets it to a pristine, not-yet-installed state — otherwise
    the assertions would be satisfied by the install that already ran at import time.
    """

    def setUp(self):
        for patcher in (
            mock.patch.object(bot.settings, "bot_token", FAKE_TOKEN),
            mock.patch.object(bot, "_TOKEN_SECRET", FAKE_SECRET),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        self.saved_excepthook = sys.excepthook
        self.saved_thread_excepthook = threading.excepthook
        saved_add_handler = logging.Logger.addHandler
        saved_filters = [(handler, list(handler.filters)) for handler in _all_handlers()]
        saved_telebot_handlers = list(telebot.logger.handlers)

        def restore():
            sys.excepthook = self.saved_excepthook
            threading.excepthook = self.saved_thread_excepthook
            logging.Logger.addHandler = saved_add_handler
            for handler, filters in saved_filters:
                handler.filters = filters
            telebot.logger.handlers[:] = saved_telebot_handlers

        self.addCleanup(restore)

        # Back to the state the interpreter is in before the module is imported:
        # the stdlib addHandler, no redacting filters anywhere, and telebot's own
        # StreamHandler back on the `TeleBot` logger.
        logging.Logger.addHandler = getattr(saved_add_handler, "_original_add_handler", saved_add_handler)
        for handler in _all_handlers():
            handler.filters = [f for f in handler.filters if not isinstance(f, bot._TokenRedactingFilter)]
        self.telebot_stream = io.StringIO()
        telebot.logger.handlers[:] = [logging.StreamHandler(self.telebot_stream)]

    def _capture_root(self):
        """Add a capturing handler to the root logger and return its buffer."""
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logging.getLogger().addHandler(handler)
        self.addCleanup(logging.getLogger().removeHandler, handler)
        return stream

    @staticmethod
    def _api_failure():
        try:
            raise RuntimeError(f"Max retries exceeded with url: /bot{FAKE_TOKEN}/sendMessage")
        except RuntimeError:
            return sys.exc_info()

    def test_every_handler_that_already_exists_gets_the_filter(self):
        """Including handlers on OTHER loggers: Logger.callHandlers walks from the
        emitting logger up to the root, so a handler on a non-root logger sees the
        record first — before any filter on the root handlers could clean it."""
        third_party = logging.getLogger("tests.pretend_third_party")
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        third_party.addHandler(handler)
        third_party.propagate = False
        self.addCleanup(setattr, third_party, "propagate", True)
        self.addCleanup(third_party.removeHandler, handler)
        self.assertFalse(_is_redacted(handler))

        bot._install_token_redaction()

        self.assertTrue(_is_redacted(handler))
        self.assertEqual([h for h in _all_handlers() if not _is_redacted(h)], [])

        third_party.error(f"connection to https://api.telegram.org/bot{FAKE_TOKEN}/getMe failed")
        self.assertNotIn(FAKE_TOKEN, stream.getvalue())
        self.assertNotIn(FAKE_SECRET, stream.getvalue())
        self.assertIn(bot.TOKEN_PLACEHOLDER, stream.getvalue())

    def test_a_handler_attached_after_the_install_is_covered_too(self):
        """A dependency imported later brings its own logger and its own handler, and
        so does any later logging.basicConfig()."""
        bot._install_token_redaction()

        late = logging.getLogger("tests.pretend_late_import")
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        late.addHandler(handler)
        late.propagate = False
        self.addCleanup(setattr, late, "propagate", True)
        self.addCleanup(late.removeHandler, handler)

        self.assertTrue(_is_redacted(handler))
        late.error(f"connection to https://api.telegram.org/bot{FAKE_TOKEN}/getMe failed")
        self.assertNotIn(FAKE_TOKEN, stream.getvalue())
        self.assertIn(bot.TOKEN_PLACEHOLDER, stream.getvalue())

    def test_a_record_logged_through_the_telebot_logger_is_redacted(self):
        """The canary that started all this: telebot adds a StreamHandler(sys.stderr)
        to the `TeleBot` logger at import, and that handler emits before the root ones.
        Asserted on the combined output, so it holds whether the handler is filtered or
        dropped in favour of propagation."""
        root_stream = self._capture_root()

        bot._install_token_redaction()

        telebot.logger.error(
            f"Polling exception: conn refused: https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage"
        )

        written = self.telebot_stream.getvalue() + root_stream.getvalue()
        self.assertIn("Polling exception", written)
        self.assertNotIn(FAKE_TOKEN, written)
        self.assertNotIn(FAKE_SECRET, written)
        self.assertIn(bot.TOKEN_PLACEHOLDER, written)

    def test_an_exception_object_logged_as_the_message_is_redacted(self):
        """`logger.error(exc)` / `logger.exception(exc)`: the exception OBJECT ends up
        in record.msg and is rendered with str() only inside getMessage()."""
        root_stream = self._capture_root()

        bot._install_token_redaction()

        error = RuntimeError(f"Max retries exceeded with url: /bot{FAKE_TOKEN}/sendMessage")
        logging.getLogger("tests.pretend_caller").error(error)

        self.assertNotIn(FAKE_TOKEN, root_stream.getvalue())
        self.assertNotIn(FAKE_SECRET, root_stream.getvalue())
        self.assertIn(bot.TOKEN_PLACEHOLDER, root_stream.getvalue())

    def test_both_exception_hooks_are_replaced_and_redact(self):
        bot._install_token_redaction()

        self.assertIsNot(sys.excepthook, self.saved_excepthook)
        self.assertIsNot(threading.excepthook, self.saved_thread_excepthook)

        exc_type, exc_value, exc_tb = self._api_failure()
        stderr = io.StringIO()
        with mock.patch.object(sys, "stderr", stderr):
            sys.excepthook(exc_type, exc_value, exc_tb)
            threading.excepthook(threading.ExceptHookArgs(
                (exc_type, exc_value, exc_tb, threading.current_thread())
            ))

        written = stderr.getvalue()
        self.assertEqual(written.count("Traceback (most recent call last)"), 2)
        self.assertIn(f"Exception in thread {threading.current_thread().name}:", written)
        self.assertNotIn(FAKE_TOKEN, written)
        self.assertNotIn(FAKE_SECRET, written)
        self.assertIn(bot.TOKEN_PLACEHOLDER, written)

    def test_a_handler_without_filters_does_not_break_add_handler(self):
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
        self.addCleanup(odd.removeHandler, duck)

        self.assertIn(duck, odd.handlers)
        odd.error("a record for the duck")
        self.assertEqual([r.getMessage() for r in duck.records], ["a record for the duck"])

    def test_a_failing_redactor_does_not_break_add_handler(self):
        """The same guarantee from the other side: whatever goes wrong INSIDE the
        redaction layer, attaching a handler still has to succeed."""
        bot._install_token_redaction()

        target = logging.getLogger("tests.pretend_broken_redactor")
        handler = logging.StreamHandler(io.StringIO())
        self.addCleanup(target.removeHandler, handler)

        with mock.patch.object(bot, "_attach_redactor", side_effect=RuntimeError("boom")):
            target.addHandler(handler)

        self.assertIn(handler, target.handlers)

    def test_the_wrapper_keeps_the_stdlib_name_and_signature(self):
        """The wrapper stands in for logging.Logger.addHandler process-wide, so a caller
        passing the argument by keyword (the stdlib name is `hdlr`) must keep working,
        and __name__ / signature must not start lying about whose method this is."""
        bot._install_token_redaction()

        target = logging.getLogger("tests.pretend_keyword_caller")
        handler = logging.StreamHandler(io.StringIO())
        target.addHandler(hdlr=handler)
        self.addCleanup(target.removeHandler, handler)

        self.assertIn(handler, target.handlers)
        self.assertTrue(_is_redacted(handler))
        self.assertEqual(logging.Logger.addHandler.__name__, "addHandler")
        self.assertEqual(
            list(inspect.signature(logging.Logger.addHandler).parameters),
            ["self", "hdlr"],
        )

    def test_installing_twice_does_not_stack_filters_or_wrappers(self):
        bot._install_token_redaction()
        wrapper = logging.Logger.addHandler
        bot._install_token_redaction()

        self.assertIs(logging.Logger.addHandler, wrapper)
        for handler in _all_handlers():
            redactors = [f for f in handler.filters if isinstance(f, bot._TokenRedactingFilter)]
            self.assertEqual(len(redactors), 1)


class IsForwardedTestCase(unittest.TestCase):
    def test_forward_from_a_user_with_an_open_profile(self):
        message = _message(forward_origin={
            "type": "user",
            "date": int(time.time()),
            "sender_user": {"id": 7, "is_bot": False, "first_name": "Author"},
        })
        self.assertTrue(bot._is_forwarded(message))

    def test_forward_from_a_hidden_profile(self):
        message = _message(forward_origin={
            "type": "hidden_user",
            "date": int(time.time()),
            "sender_user_name": "Someone",
        })
        # The reason the old forward_from check was not enough: Telegram sends no sender
        # for a hidden profile, so the legacy field stays empty on a forwarded message.
        self.assertIsNone(message.forward_from)
        self.assertTrue(bot._is_forwarded(message))

    def test_forward_from_a_channel(self):
        message = _message(forward_origin={
            "type": "channel",
            "date": int(time.time()),
            "chat": {"id": -1009876543210, "type": "channel", "title": "Some channel"},
            "message_id": 17,
        })
        self.assertIsNone(message.forward_from)
        self.assertTrue(bot._is_forwarded(message))

    def test_an_ordinary_message_is_not_a_forward(self):
        self.assertFalse(bot._is_forwarded(_message()))

    def test_legacy_message_without_forward_origin(self):
        """Older telebot: the flat forward_* fields are the only thing available."""
        self.assertTrue(bot._is_forwarded(LegacyMessage(forward_sender_name="Someone")))
        self.assertTrue(bot._is_forwarded(LegacyMessage(forward_date=1700000000)))
        self.assertFalse(bot._is_forwarded(LegacyMessage()))


class CollectRatesTestCase(unittest.TestCase):
    def setUp(self):
        self.rates = RecordingRatesManager()
        patcher = mock.patch.object(bot, "rates_manager", self.rates)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.defaults = set(bot.currency_formatter.default_currencies)

    def test_no_user_settings_fetches_only_the_default_currencies(self):
        found = [(100.0, "GEL", "100 лари")]
        for user_currencies in (None, []):
            with self.subTest(user_currencies=user_currencies):
                self.rates.requested.clear()
                rates = bot._collect_rates(found, user_currencies)
                self.assertEqual(self.rates.requested_targets, self.defaults)
                # The whole reference book is ~142 entries; the point of the fallback is
                # that a message costs a handful of lookups, not all of them.
                self.assertLess(len(self.rates.requested), len(bot.currency_formatter.target_currencies) // 2)
                self.assertEqual(set(rates), {f"GEL_{target}" for target in self.defaults})

    def test_usd_is_requested_even_when_the_user_left_it_out(self):
        rates = bot._collect_rates([(100.0, "GEL", "100 лари")], ["EUR", "GBP"])
        self.assertEqual(self.rates.requested_targets, {"EUR", "GBP", "USD"})
        self.assertIn("GEL_USD", rates)

    def test_usd_is_not_requested_twice_when_the_user_asked_for_it(self):
        bot._collect_rates([(100.0, "GEL", "100 лари")], ["USD", "EUR"])
        self.assertEqual(self.rates.requested, [("GEL", "USD"), ("GEL", "EUR")])

    def test_the_source_currency_is_not_converted_into_itself(self):
        bot._collect_rates([(100.0, "EUR", "100 евро")], ["EUR", "GBP"])
        self.assertNotIn(("EUR", "EUR"), self.rates.requested)
        self.assertEqual(self.rates.requested_targets, {"GBP", "USD"})

    def test_repeated_amounts_in_the_same_currency_are_fetched_once(self):
        """Twelve sums in roubles used to mean 7 x 12 lookups, each taking the
        manager's lock, all writing the same twelve keys."""
        found = [(float(index), "RUB", f"{index} рублей") for index in range(1, 13)]
        rates = bot._collect_rates(found, ["EUR", "USD"])

        self.assertEqual(self.rates.requested, [("RUB", "EUR"), ("RUB", "USD")])
        self.assertEqual(set(rates), {"RUB_EUR", "RUB_USD"})

    def test_several_source_currencies_are_all_fetched(self):
        found = [(1.0, "RUB", "1 рубль"), (2.0, "GEL", "2 лари"), (3.0, "RUB", "3 рубля")]
        bot._collect_rates(found, ["EUR"])

        self.assertEqual(self.rates.requested, [("RUB", "EUR"), ("RUB", "USD"), ("GEL", "EUR"), ("GEL", "USD")])

    def test_a_missing_rate_is_left_out_of_the_result(self):
        self.rates = RecordingRatesManager(missing=[("GEL", "GBP")])
        with mock.patch.object(bot, "rates_manager", self.rates):
            rates = bot._collect_rates([(100.0, "GEL", "100 лари")], ["GBP", "EUR"])
        self.assertNotIn("GEL_GBP", rates)
        self.assertIn("GEL_EUR", rates)


class ParseTextTestCase(unittest.TestCase):
    """parse_text is where every message handler ends up, so it is worth driving directly."""

    def setUp(self):
        self.fake_bot = RecordingBot()
        self.rates = RecordingRatesManager()
        self.statistics = StubStatistics()
        self.user_settings = StubUserSettings()
        for patcher in (
            mock.patch.object(bot, "bot", self.fake_bot),
            mock.patch.object(bot, "rates_manager", self.rates),
            mock.patch.object(bot, "statistics_manager", self.statistics),
            mock.patch.object(bot, "user_settings_manager", self.user_settings),
            mock.patch.object(bot, "BOT_USER_ID", 555),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def _reply_from_a_channel():
        """A replied-to message posted on behalf of a channel: `from` is absent."""
        return {
            "message_id": 2,
            "date": int(time.time()),
            "chat": {"id": -1001234567890, "type": "supergroup", "title": "Test chat"},
            "sender_chat": {"id": -1009876543210, "type": "channel", "title": "Some channel"},
            "text": "исходное сообщение",
        }

    def test_reply_to_a_message_without_an_author_is_handled(self):
        message = _message(text="я купил телевизор за 100 долларов",
                           reply_to_message=self._reply_from_a_channel())
        self.assertIsNone(message.reply_to_message.from_user)

        with self.assertNoLogs("bot", level="ERROR"):
            bot.parse_text(message.text, message)

        self.assertEqual(len(self.fake_bot.replies), 1)
        self.assertEqual(len(self.statistics.logged), 1)

    def test_reply_without_an_author_in_a_private_chat_with_nothing_to_convert(self):
        payload_chat = {"id": 42, "type": "private"}
        message = _message(chat=payload_chat, text="просто текст",
                           reply_to_message=self._reply_from_a_channel())

        with self.assertNoLogs("bot", level="ERROR"):
            bot.parse_text(message.text, message)

        self.assertEqual(len(self.fake_bot.replies), 1)
        self.assertIn("Не нашел ничего", self.fake_bot.replies[0][1])

    def test_reply_before_get_me_has_answered_is_handled(self):
        """BOT_USER_ID is None until _start_telegram_session() runs."""
        with mock.patch.object(bot, "BOT_USER_ID", None):
            message = _message(text="100 долларов", reply_to_message=self._reply_from_a_channel())
            with self.assertNoLogs("bot", level="ERROR"):
                bot.parse_text(message.text, message)
        self.assertEqual(len(self.fake_bot.replies), 1)

    def test_a_forward_into_a_group_chat_is_ignored(self):
        message = _message(text="100 долларов", forward_origin={
            "type": "hidden_user",
            "date": int(time.time()),
            "sender_user_name": "Someone",
        })
        bot.parse_text(message.text, message)
        self.assertEqual(self.fake_bot.replies, [])


class InlineQueryTestCase(unittest.TestCase):
    """The "Дополняй" result: the user's own text with a conversion after every amount.

    It used to be built with str.replace(original, conversion) once per match, which
    rewrites EVERY equal substring rather than the match it was called for. Two amounts
    of the same size therefore got two conversions each, and a shorter amount replaced
    itself inside the conversion a longer one had already inserted. The text the user
    then sent into the chat was mangled, so these tests assert on the exact string.

    Every expectation is written as a template — literal gap, conversion, literal gap —
    so the text between the matches is part of what is checked.
    """

    def setUp(self):
        self.fake_bot = RecordingBot()
        self.rates = RecordingRatesManager()
        self.statistics = StubStatistics()
        self.user_settings = StubUserSettings()
        for patcher in (
            mock.patch.object(bot, "bot", self.fake_bot),
            mock.patch.object(bot, "rates_manager", self.rates),
            mock.patch.object(bot, "statistics_manager", self.statistics),
            mock.patch.object(bot, "user_settings_manager", self.user_settings),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _complete(self, text):
        """Run the handler and return the message text of the "Дополняй" result."""
        with self.assertNoLogs("bot", level="ERROR"):
            bot.handle_inline_query(_inline_query(text))
        self.assertEqual(len(self.fake_bot.answered), 1)
        results = self.fake_bot.answered[0][1]
        self.assertEqual([result.id for result in results], ["1", "2"])
        return results[1].input_message_content.message_text

    @staticmethod
    def _conversion(amount_text):
        """What the formatter alone produces for a text holding exactly one amount.

        Built through the formatter rather than spelled out, because the wording of a
        conversion is the formatter's business and is covered by its own tests. What is
        being tested here is only WHERE those strings end up.
        """
        found = bot.currency_parser.find_currencies(amount_text)
        assert len(found) == 1, amount_text
        rates = bot._collect_rates(found, None)
        return bot.currency_formatter.format_conversion(found[0], rates, mode="inline", user_currencies=None)

    def test_two_identical_amounts_are_each_replaced_by_one_conversion(self):
        conversion = self._conversion("100$")
        completed = self._complete("дай 100$ и еще 100$")

        self.assertEqual(completed, f"дай {conversion} и еще {conversion}")
        # The symptom the user saw: "100$ (…) (…)". Counting the blocks catches it even
        # if the wording of a conversion ever changes.
        self.assertEqual(completed.count("("), 2 * conversion.count("("))
        self.assertNotIn(") (", completed)

    def test_a_shorter_amount_is_not_replaced_inside_the_conversion_of_a_longer_one(self):
        """"100$" is a substring of "1100$" — and of the conversion inserted for it."""
        completed = self._complete("взял 1100$ и 100$")

        self.assertEqual(completed, f"взял {self._conversion('1100$')} и {self._conversion('100$')}")

    def test_an_amount_at_the_start_of_the_text(self):
        self.assertEqual(self._complete("100$ и всё"), f"{self._conversion('100$')} и всё")

    def test_an_amount_at_the_end_of_the_text(self):
        self.assertEqual(self._complete("итого 100$"), f"итого {self._conversion('100$')}")

    def test_the_whole_text_is_one_amount(self):
        self.assertEqual(self._complete("100$"), self._conversion("100$"))

    def test_a_single_amount_in_the_middle_behaves_as_before(self):
        completed = self._complete("я купил телевизор за 100 долларов и доволен")
        self.assertEqual(completed, f"я купил телевизор за {self._conversion('100 долларов')} и доволен")

    def test_text_without_amounts_is_passed_through_untouched(self):
        text = "просто текст без денег"
        with self.assertNoLogs("bot", level="ERROR"):
            bot.handle_inline_query(_inline_query(text))

        results = self.fake_bot.answered[0][1]
        self.assertEqual([result.input_message_content.message_text for result in results], [text, text])

    def test_everything_outside_the_matches_survives_verbatim(self):
        """Punctuation, doubled spaces and non-BMP characters, character for character.

        The emoji matter for more than decoration: they are one character each in
        Python but four bytes, so an offset computed anywhere other than on the string
        itself would slice the text apart in the wrong place.
        """
        text = "💰 цена:  100$,  а не 200 евро!  💶"
        completed = self._complete(text)

        self.assertEqual(
            completed,
            f"💰 цена:  {self._conversion('100$')},  а не {self._conversion('200 евро')}!  💶",
        )

        # Same claim from the other side, without a template: putting the originals back
        # in place of the conversions must return the input unchanged.
        restored = completed
        for original in ("100$", "200 евро"):
            restored = restored.replace(self._conversion(original), original, 1)
        self.assertEqual(restored, text)

    def test_the_conversion_belongs_to_the_amount_it_follows(self):
        """Different amounts, so a mixed-up assembly cannot pass by accident."""
        completed = self._complete("сначала 100$, потом 200$, снова 100$")

        self.assertEqual(
            completed,
            f"сначала {self._conversion('100$')}, потом {self._conversion('200$')}, "
            f"снова {self._conversion('100$')}",
        )


if __name__ == "__main__":
    unittest.main()
