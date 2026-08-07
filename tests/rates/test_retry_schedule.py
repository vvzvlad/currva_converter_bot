# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""The retry schedule after a failed update, and what the cache saves at startup."""

import json
import time
from datetime import datetime, timedelta

from src.exchange_rates_manager import (
    RETRY_INITIAL_INTERVAL,
    RETRY_MAX_INTERVAL,
    UPDATES_INTERVAL,
)


def test_a_failed_first_update_retries_in_minutes_not_in_twelve_hours(make_manager):
    """The whole point of the backoff: an empty cache plus a dead API used to mean
    half a day of "нет доступных курсов конвертации" with no second attempt."""
    manager = make_manager(failures=99)

    assert manager.get_rate("USD", "EUR") is None
    assert manager._consecutive_failures == 1
    assert manager._next_update_delay() == RETRY_INITIAL_INTERVAL
    assert manager._next_update_delay() < UPDATES_INTERVAL / 10


def test_the_retry_delay_doubles_and_is_capped(make_manager):
    manager = make_manager(failures=99)

    delays = []
    for failures in range(1, 13):
        manager._consecutive_failures = failures
        delays.append(manager._next_update_delay())

    assert delays[:4] == [RETRY_INITIAL_INTERVAL * m for m in (1, 2, 4, 8)]
    assert all(delay <= RETRY_MAX_INTERVAL for delay in delays)
    assert delays[-1] == RETRY_MAX_INTERVAL

    # A manager that has been failing for months must not compute 2**100000.
    manager._consecutive_failures = 10 ** 6
    assert manager._next_update_delay() == RETRY_MAX_INTERVAL


def test_a_success_goes_back_to_the_normal_interval(make_manager):
    manager = make_manager(failures=1)
    assert manager._next_update_delay() == RETRY_INITIAL_INTERVAL

    assert manager._update_all_rates()

    assert manager._consecutive_failures == 0
    assert manager._next_update_delay() == UPDATES_INTERVAL
    assert manager._last_successful_update is not None


def test_the_background_thread_actually_retries(make_manager):
    """End to end through the real thread, with the intervals scaled to
    milliseconds — the first attempt fails, the next one lands."""
    manager = make_manager(
        failures=1,
        update_interval=30,
        retry_initial_interval=0.01,
        retry_max_interval=0.01,
        start_update_thread=True,
    )

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and manager.get_rate("USD", "EUR") is None:
        time.sleep(0.01)

    assert manager.get_rate("USD", "EUR") == 0.5
    assert manager.calls >= 2

    manager.close()
    assert not manager._update_thread_handle.is_alive()


def test_a_fresh_cache_costs_no_api_request(cache_path, make_manager):
    cache_path.write_text(json.dumps({
        "rates": {"USD": {"EUR": 0.9}, "EUR": {"USD": 1.1}},
        "last_update": datetime.now().isoformat(),
    }), encoding="utf-8")

    manager = make_manager()

    assert manager.calls == 0
    assert manager.get_rate("USD", "EUR") == 0.9
    assert sorted(manager.get_available_currencies()) == ["EUR", "USD"]


def test_a_stale_cache_is_refreshed_at_startup(cache_path, make_manager):
    cache_path.write_text(json.dumps({
        "rates": {"USD": {"EUR": 0.9}},
        "last_update": (datetime.now() - timedelta(hours=5)).isoformat(),
    }), encoding="utf-8")

    manager = make_manager()

    assert manager.calls == 1
    assert manager.get_rate("USD", "EUR") == 0.5
