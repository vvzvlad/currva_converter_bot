# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Test doubles and payload builders for the src/bot.py tests.

A plain module rather than conftest.py, for the same reason tests/stubs.py is one:
importing helpers from a conftest only works under pytest's default `prepend` import
mode and breaks under `--import-mode=importlib`.

Keeping them out of tests/bot/conftest.py matters twice over here — that module
imports src.bot at import time, which is a one-shot side effect that refuses to run
twice, so it must not also be the module everyone pulls helpers from.

Nothing here touches the network or the real data/ directory.
"""

import time

from telebot import types

# A token that is obviously fake but has the shape of a real one: telebot's TeleBot()
# refuses anything without a colon, and the tests need a value they can search for in
# the output rather than whatever BOT_TOKEN happens to be in the environment (CI sets
# BOT_TOKEN=test-token, a developer may have a real one exported).
FAKE_TOKEN = "1234567890:AAFakeTokenForTestsOnly-0123456789abcdef"
FAKE_SECRET = FAKE_TOKEN.split(":", 1)[1]

# A DIFFERENT token, never known to the module — only the URL-shaped regex can catch it.
UNKNOWN_TOKEN = "987654321:BBSomeOtherBotSecret-9876543210zyxwvu"


def message(**extra):
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


def inline_query(text):
    """A real telebot InlineQuery, built from an API payload like message() is."""
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
