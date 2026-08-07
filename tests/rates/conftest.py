# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Shared fixtures for the rates tests.

Nothing here touches the network — `_fetch_usd_rates` exists as a separate method
precisely so the failure modes can be scripted. Nothing sleeps for a real interval
either: the intervals are constructor arguments, so the one test that does run the
background thread runs it in milliseconds.

The doubles live in tests/rates/doubles.py.
"""

import pytest

from tests.rates.doubles import ScriptedRatesManager


@pytest.fixture
def cache_path(tmp_path):
    """The cache file every manager in a test writes to, inside its private directory."""
    return tmp_path / "exchange_rates_cache.json"


@pytest.fixture
def make_manager(cache_path):
    """Build a ScriptedRatesManager and close it when the test is done.

    Closing matters: ExchangeRatesManager.__init__ starts a background thread unless
    told not to, and the manager also has to be pointed away from the settings path.
    """
    managers = []

    def _make_manager(**kwargs):
        kwargs.setdefault("cache_file", str(cache_path))
        # The background thread is off unless a test explicitly asks for it, so the
        # rest of the suite stays deterministic.
        kwargs.setdefault("start_update_thread", False)
        manager = ScriptedRatesManager(**kwargs)
        managers.append(manager)
        return manager

    yield _make_manager

    for manager in managers:
        manager.close()
