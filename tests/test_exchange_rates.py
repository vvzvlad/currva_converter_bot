# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Tests for the rates manager: the retry schedule, the tolerance for broken quotes
and the atomicity of the on-disk cache.

Nothing here touches the network — `_fetch_usd_rates` exists as a separate method
precisely so the failure modes can be scripted. Nothing sleeps for a real interval
either: the intervals are constructor arguments, so the one test that does run the
background thread runs it in milliseconds.
"""

import json
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from src.exchange_rates_manager import (
    CLOCK_SKEW_TOLERANCE,
    RETRY_INITIAL_INTERVAL,
    RETRY_MAX_INTERVAL,
    STALE_RATES_MAX_AGE,
    UPDATES_INTERVAL,
    ExchangeRatesManager,
    _future_skew,
)

LOGGER_NAME = "exchange_rates_manager"


class ScriptedRatesManager(ExchangeRatesManager):
    """The real manager with the one network call replaced by a script.

    `failures` API calls raise before the quotes start coming back, so "the API is
    down on first start" and "the API recovers on the Nth retry" are both one
    argument away.
    """

    def __init__(self, *args, quotes=None, failures=0, **kwargs):
        # Set before super().__init__: it downloads rates from inside the constructor.
        self.calls = 0
        self.quotes = {"USDEUR": 0.5} if quotes is None else dict(quotes)
        self.failures = failures
        super().__init__(*args, **kwargs)

    def _fetch_usd_rates(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("apilayer is unreachable")
        return dict(self.quotes)


class RatesTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.cache_path = self.tmp_path / "exchange_rates_cache.json"
        self._managers = []

    def tearDown(self):
        for manager in self._managers:
            manager.close()
        self._tmp.cleanup()

    def make_manager(self, **kwargs):
        kwargs.setdefault("cache_file", str(self.cache_path))
        # The background thread is off unless a test explicitly asks for it, so the
        # rest of the suite stays deterministic.
        kwargs.setdefault("start_update_thread", False)
        manager = ScriptedRatesManager(**kwargs)
        self._managers.append(manager)
        return manager


class TestRetrySchedule(RatesTestCase):
    def test_a_failed_first_update_retries_in_minutes_not_in_twelve_hours(self):
        """The whole point of the backoff: an empty cache plus a dead API used to mean
        half a day of "нет доступных курсов конвертации" with no second attempt."""
        manager = self.make_manager(failures=99)

        self.assertIsNone(manager.get_rate("USD", "EUR"))
        self.assertEqual(manager._consecutive_failures, 1)
        self.assertEqual(manager._next_update_delay(), RETRY_INITIAL_INTERVAL)
        self.assertLess(manager._next_update_delay(), UPDATES_INTERVAL / 10)

    def test_the_retry_delay_doubles_and_is_capped(self):
        manager = self.make_manager(failures=99)

        delays = []
        for failures in range(1, 13):
            manager._consecutive_failures = failures
            delays.append(manager._next_update_delay())

        self.assertEqual(delays[:4], [RETRY_INITIAL_INTERVAL * m for m in (1, 2, 4, 8)])
        self.assertTrue(all(delay <= RETRY_MAX_INTERVAL for delay in delays))
        self.assertEqual(delays[-1], RETRY_MAX_INTERVAL)

        # A manager that has been failing for months must not compute 2**100000.
        manager._consecutive_failures = 10 ** 6
        self.assertEqual(manager._next_update_delay(), RETRY_MAX_INTERVAL)

    def test_a_success_goes_back_to_the_normal_interval(self):
        manager = self.make_manager(failures=1)
        self.assertEqual(manager._next_update_delay(), RETRY_INITIAL_INTERVAL)

        self.assertTrue(manager._update_all_rates())

        self.assertEqual(manager._consecutive_failures, 0)
        self.assertEqual(manager._next_update_delay(), UPDATES_INTERVAL)
        self.assertIsNotNone(manager._last_successful_update)

    def test_the_background_thread_actually_retries(self):
        """End to end through the real thread, with the intervals scaled to
        milliseconds — the first attempt fails, the next one lands."""
        manager = self.make_manager(
            failures=1,
            update_interval=30,
            retry_initial_interval=0.01,
            retry_max_interval=0.01,
            start_update_thread=True,
        )

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and manager.get_rate("USD", "EUR") is None:
            time.sleep(0.01)

        self.assertEqual(manager.get_rate("USD", "EUR"), 0.5)
        self.assertGreaterEqual(manager.calls, 2)

        manager.close()
        self.assertFalse(manager._update_thread_handle.is_alive())

    def test_a_fresh_cache_costs_no_api_request(self):
        self.cache_path.write_text(json.dumps({
            "rates": {"USD": {"EUR": 0.9}, "EUR": {"USD": 1.1}},
            "last_update": datetime.now().isoformat(),
        }), encoding="utf-8")

        manager = self.make_manager()

        self.assertEqual(manager.calls, 0)
        self.assertEqual(manager.get_rate("USD", "EUR"), 0.9)
        self.assertEqual(sorted(manager.get_available_currencies()), ["EUR", "USD"])

    def test_a_stale_cache_is_refreshed_at_startup(self):
        self.cache_path.write_text(json.dumps({
            "rates": {"USD": {"EUR": 0.9}},
            "last_update": (datetime.now() - timedelta(hours=5)).isoformat(),
        }), encoding="utf-8")

        manager = self.make_manager()

        self.assertEqual(manager.calls, 1)
        self.assertEqual(manager.get_rate("USD", "EUR"), 0.5)


class TestRatesAgeReporting(RatesTestCase):
    def test_rates_older_than_the_threshold_are_warned_about(self):
        manager = self.make_manager()
        manager._last_update = datetime.now() - timedelta(seconds=STALE_RATES_MAX_AGE + 60)

        with self.assertLogs(LOGGER_NAME, level="WARNING") as captured:
            manager._log_rates_age()

        self.assertTrue(any("Serving exchange rates that are" in line for line in captured.output))

    def test_fresh_rates_are_not_warned_about(self):
        manager = self.make_manager()

        with self.assertLogs(LOGGER_NAME, level="INFO") as captured:
            manager._log_rates_age()

        self.assertFalse(any(line.startswith("WARNING") for line in captured.output))

    def test_having_no_rates_at_all_is_an_error(self):
        manager = self.make_manager(failures=99)

        self.assertIsNone(manager.rates_age())
        with self.assertLogs(LOGGER_NAME, level="ERROR") as captured:
            manager._log_rates_age()

        self.assertTrue(any("No exchange rates available" in line for line in captured.output))


class TestBrokenQuotes(RatesTestCase):
    def test_a_zero_rate_skips_one_currency_instead_of_the_whole_update(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as captured:
            manager = self.make_manager(quotes={"USDEUR": 0.5, "USDZWL": 0.0, "USDGBP": 0.25})

        self.assertTrue(any("ZWL" in line for line in captured.output))
        self.assertEqual(manager.get_rate("USD", "EUR"), 0.5)
        self.assertIsNone(manager.get_rate("USD", "ZWL"))
        self.assertNotIn("ZWL", manager.get_available_currencies())
        # The healthy cross-rates are computed as if the dead currency never came.
        self.assertAlmostEqual(manager.get_rate("EUR", "GBP"), 0.5)

    def test_negative_and_non_numeric_rates_are_skipped_too(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING"):
            manager = self.make_manager(quotes={
                "USDEUR": 0.5,
                "USDAAA": -1.0,
                "USDBBB": "not a number",
                "USDCCC": None,
            })

        self.assertEqual(sorted(manager.get_available_currencies()), ["EUR", "USD"])
        self.assertEqual(manager.get_rate("USD", "EUR"), 0.5)

    def test_a_payload_with_nothing_usable_is_a_failure_and_keeps_the_old_rates(self):
        manager = self.make_manager()
        self.assertEqual(manager.get_rate("USD", "EUR"), 0.5)

        manager.quotes = {"USDZWL": 0.0}
        with self.assertLogs(LOGGER_NAME, level="ERROR"):
            self.assertFalse(manager._update_all_rates())

        self.assertEqual(manager.get_rate("USD", "EUR"), 0.5)
        self.assertEqual(manager._consecutive_failures, 1)


class TestCacheWriting(RatesTestCase):
    def test_a_successful_update_leaves_a_valid_cache_and_no_temp_file(self):
        manager = self.make_manager()

        data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self.assertEqual(data["rates"]["USD"]["EUR"], 0.5)
        self.assertEqual(list(self.tmp_path.glob("*.tmp")), [])
        self.assertEqual(manager._cache_written_revision, manager._rates_revision)

    def test_a_write_that_dies_halfway_leaves_the_previous_cache_intact(self):
        """The reason for the temp file plus os.replace: writing in place truncates
        the real cache first, so a kill in the middle left a file that no longer
        parses — and the next start had no rates at all."""
        manager = self.make_manager()
        before = self.cache_path.read_text(encoding="utf-8")

        def die_halfway(_data, handle, **_kwargs):
            handle.write('{"rates": {"USD"')
            raise OSError("no space left on device")

        with mock.patch.object(json, "dump", side_effect=die_halfway):
            with self.assertLogs(LOGGER_NAME, level="ERROR"):
                manager._save_cache({"USD": {"EUR": 9.0}}, datetime.now(), manager._rates_revision + 1)

        self.assertEqual(self.cache_path.read_text(encoding="utf-8"), before)
        self.assertEqual(json.loads(before)["rates"]["USD"]["EUR"], 0.5)
        self.assertEqual(list(self.tmp_path.glob("*.tmp")), [])

    def test_writing_the_cache_does_not_block_readers(self):
        """The cache write used to happen while holding the lock get_rate needs, so a
        megabyte of json.dump stalled every message handler."""
        manager = self.make_manager()
        real_dump = json.dump
        observed = {}

        def dump_and_probe(data, handle, **kwargs):
            # A non-reentrant lock: if the write still ran under it, this acquire
            # would block for the whole timeout and come back False.
            observed["lock_was_free"] = manager._lock.acquire(timeout=1)
            if observed["lock_was_free"]:
                manager._lock.release()
            return real_dump(data, handle, **kwargs)

        with mock.patch.object(json, "dump", side_effect=dump_and_probe):
            self.assertTrue(manager._update_all_rates())

        self.assertTrue(observed["lock_was_free"])

    def test_concurrent_saves_end_with_the_newest_snapshot_and_valid_json(self):
        manager = self.make_manager()
        base = datetime.now() + timedelta(seconds=1)
        # The snapshots are ordered by revision, not by their timestamps: the clock can
        # step backwards, an in-process counter cannot.
        first_revision = manager._rates_revision

        def save(index):
            manager._save_cache(
                {"USD": {"EUR": float(index)}},
                base + timedelta(seconds=index),
                first_revision + index,
            )

        threads = [threading.Thread(target=save, args=(index,)) for index in range(1, 11)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        # Whatever the interleaving, an older snapshot never overwrites a newer one.
        self.assertEqual(data["rates"]["USD"]["EUR"], 10.0)
        self.assertEqual(data["last_update"], (base + timedelta(seconds=10)).isoformat())
        self.assertEqual(list(self.tmp_path.glob("*.tmp")), [])


class TestClockGoingBackwards(RatesTestCase):
    """A cache written under one clock, read under an earlier one: a TZ change in the
    compose file, an NTP step, or a data volume carried over from another host."""

    def _write_cache_from_the_future(self, hours=3):
        self.cache_path.write_text(json.dumps({
            "rates": {"USD": {"EUR": 0.9}, "EUR": {"USD": 1.1}},
            "last_update": (datetime.now() + timedelta(hours=hours)).isoformat(),
        }), encoding="utf-8")

    def test_a_cache_stamped_in_the_future_is_refreshed_at_startup(self):
        self._write_cache_from_the_future()

        with self.assertLogs(LOGGER_NAME, level="WARNING") as captured:
            manager = self.make_manager()

        self.assertTrue(any("in the future" in line for line in captured.output))
        # Without this, "older than two hours" is false forever and the stale snapshot
        # is served across every restart.
        self.assertEqual(manager.calls, 1)
        self.assertEqual(manager.get_rate("USD", "EUR"), 0.5)

    def test_a_newer_snapshot_on_disk_does_not_block_the_write(self):
        """The write guard orders the savers of THIS process; a file claiming to be
        from the future used to veto every cache write for as long as the clock stayed
        behind it, while the log cheerfully said "Successfully updated rates"."""
        self._write_cache_from_the_future()

        manager = self.make_manager()

        on_disk = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["rates"]["USD"]["EUR"], 0.5)
        self.assertEqual(on_disk["rates"]["USD"]["EUR"], manager.get_rate("USD", "EUR"))

    def test_the_reported_age_is_never_negative(self):
        manager = self.make_manager()
        manager._last_update = datetime.now() + timedelta(hours=3)

        with self.assertLogs(LOGGER_NAME, level="WARNING") as captured:
            age = manager.rates_age()

        self.assertEqual(age, timedelta(0))
        self.assertTrue(any("in the future" in line for line in captured.output))

    def test_a_small_skew_is_not_worth_a_warning(self):
        manager = self.make_manager()
        manager._last_update = datetime.now() + timedelta(seconds=30)

        with self.assertLogs(LOGGER_NAME, level="INFO") as captured:
            manager._log_rates_age()

        self.assertEqual(manager.rates_age(), timedelta(0))
        self.assertFalse(any(line.startswith("WARNING") for line in captured.output))


class TestBrokenCacheTimestamp(RatesTestCase):
    """A cache file whose `last_update` is not the naive local timestamp the rest of the
    class works with. The constructor is the dangerous place for this: src.bot builds the
    manager at import time, so an exception here is not a failed update but a bot that
    cannot start — and `restart: always` then loops on it forever, because the offending
    file sits on the data volume and a restart changes nothing about it."""

    def test_a_timestamp_with_an_offset_does_not_kill_the_constructor(self):
        """The realistic trigger is not a hand-edited file: the day _save_cache starts
        writing datetime.now(timezone.utc), every cache left by the previous release
        becomes one of these."""
        self.cache_path.write_text(json.dumps({
            "rates": {"USD": {"EUR": 0.9}, "EUR": {"USD": 1.1}},
            "last_update": (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat(),
        }), encoding="utf-8")

        manager = self.make_manager()

        # Normalised at load, so nothing downstream can hit the mixed subtraction again.
        self.assertIsNone(manager._last_update.tzinfo)
        # Five hours is past the two-hour threshold, and the instant survives the
        # conversion, so the stamp is read as old rather than as broken.
        self.assertEqual(manager.calls, 1)
        self.assertEqual(manager.get_rate("USD", "EUR"), 0.5)
        self.assertIsNotNone(manager.rates_age())

    def test_an_uncomparable_timestamp_is_reported_as_broken_instead_of_raising(self):
        """_future_skew is the helper whose whole job is to catch a broken timestamp, so
        it must not be the thing that raises on one — even on a path that does not exist
        today."""
        skew = _future_skew(datetime.now(timezone.utc), datetime.now())

        self.assertIsNotNone(skew)
        self.assertGreater(skew, CLOCK_SKEW_TOLERANCE)

    def test_an_unparsable_timestamp_leaves_no_half_loaded_state(self):
        """The cache is rejected AND the update fails, so all three answers have to agree
        on "there are no rates". Serving 0.9 while rates_age() says None means the bot
        converts with numbers the log insists do not exist — and keeps at it until some
        later update happens to succeed."""
        self.cache_path.write_text(json.dumps({
            "rates": {"USD": {"EUR": 0.9}, "EUR": {"USD": 1.1}},
            "last_update": "not a date at all",
        }), encoding="utf-8")

        manager = self.make_manager(failures=99)

        self.assertIsNone(manager.get_rate("USD", "EUR"))
        self.assertIsNone(manager.rates_age())
        self.assertEqual(manager.get_available_currencies(), [])


class TestTempFileCleanup(RatesTestCase):
    def test_a_temp_file_left_by_a_killed_process_is_removed_at_startup(self):
        """The temp name carries the writer's pid, so nothing would ever pick up the
        ~1 MB file left behind by a SIGKILL in the middle of a write."""
        leftover = self.tmp_path / f"{self.cache_path.name}.999999.tmp"
        leftover.write_text('{"rates": {"USD"', encoding="utf-8")
        old = time.time() - 3600
        os.utime(leftover, (old, old))

        self.make_manager()

        self.assertFalse(leftover.exists())

    def test_a_temp_file_that_is_being_written_right_now_is_left_alone(self):
        """Two containers can share the data volume; deleting the temp file of a live
        writer would break its os.replace."""
        in_flight = self.tmp_path / f"{self.cache_path.name}.999999.tmp"
        in_flight.write_text("{}", encoding="utf-8")

        self.make_manager()

        self.assertTrue(in_flight.exists())


if __name__ == "__main__":
    unittest.main()
