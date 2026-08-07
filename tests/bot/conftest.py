# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Fixtures for the src/bot.py tests.

The handlers themselves are network-bound, but the pieces they are built from are not:
token redaction, the forward detection, the rate pre-fetch and the message-parsing entry
point all take plain arguments and can be driven directly.

Importing src.bot is the only awkward part — see _import_bot_module below. Nothing here
touches the network or the real data/ directory: the three managers the module builds at
import time are neutralised for the duration of the import, and every test that needs one
puts its own recorder in the module global.

The test doubles and payload builders live in tests/bot/doubles.py, not here: this module
carries a one-shot side effect (the src.bot import) and must not double as the place
everyone imports helpers from.
"""

import importlib
import sys
import threading
from unittest import mock

import pytest

from src import exchange_rates_manager as exchange_rates_manager_module
from src import statistics_manager as statistics_manager_module
from src import user_settings_manager as user_settings_manager_module
from src.settings import settings

from tests.bot.doubles import (
    FAKE_SECRET,
    FAKE_TOKEN,
    RecordingBot,
    RecordingRatesManager,
    StubStatistics,
    StubUserSettings,
)


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
        # opened the live databases. Nothing in this package would notice.
        raise RuntimeError(
            "src.bot was already imported before tests/bot/ ran; its "
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


# Imported here, at conftest import time, rather than from inside the fixture: the
# module installs the token-redaction layer as a side effect, and that layer is
# process-wide and never undone (it wraps logging.Logger.addHandler and puts a filter
# on every handler that exists). Doing it while collecting, before any test runs, is
# what keeps every test in the session looking at the same logging stack — importing
# it lazily from the first bot test instead makes the tests that ran earlier behave
# differently from the ones that run later.
#
# The trap that comes with it, for whoever writes the next log assertion ANYWHERE in
# the suite: because _redact_handlers_added_later() wraps logging.Logger.addHandler
# permanently, every handler added after this line gets a _TokenRedactingFilter —
# including the ones capture_logs() and assert_no_logs() create and pytest's own caplog.
# That filter never drops a record (_TokenRedactingFilter.filter() always returns True),
# but it MUTATES record.msg in place. No assertion in the suite is affected today; one
# that expects log text containing `test-token`, `test-api-key`, FAKE_SECRET, or anything
# shaped like `bot\d{4,}:...` would silently see `<BOT_TOKEN>` / `<API_KEY>` instead and
# not match.
_BOT_MODULE = _import_bot_module()


@pytest.fixture(scope="session")
def bot():
    """The src.bot module, imported exactly once for the whole session."""
    return _BOT_MODULE


@pytest.fixture
def pinned_token(bot):
    """Pin both halves of the token the redaction tests search for.

    _redact() reads settings.bot_token on every call, while _TOKEN_SECRET was bound
    once at import. Both are pinned so the assertions do not depend on the ambient
    BOT_TOKEN.
    """
    with mock.patch.object(bot.settings, "bot_token", FAKE_TOKEN), \
         mock.patch.object(bot, "_TOKEN_SECRET", FAKE_SECRET):
        yield


@pytest.fixture
def fake_bot():
    return RecordingBot()


@pytest.fixture
def rates():
    return RecordingRatesManager()


@pytest.fixture
def statistics():
    return StubStatistics()


@pytest.fixture
def user_settings():
    return StubUserSettings()
