# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Timestamps the manager cannot take at face value: a clock that stepped backwards,
and a `last_update` that is not the naive local stamp the rest of the class works with.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from src.exchange_rates_manager import CLOCK_SKEW_TOLERANCE, _future_skew
from tests.logcapture import capture_logs
from tests.rates.doubles import LOGGER_NAME


class TestClockGoingBackwards:
    """A cache written under one clock, read under an earlier one: a TZ change in the
    compose file, an NTP step, or a data volume carried over from another host."""

    @staticmethod
    def _write_cache_from_the_future(cache_path, hours=3):
        cache_path.write_text(json.dumps({
            "rates": {"USD": {"EUR": 0.9}, "EUR": {"USD": 1.1}},
            "last_update": (datetime.now() + timedelta(hours=hours)).isoformat(),
        }), encoding="utf-8")

    def test_a_cache_stamped_in_the_future_is_refreshed_at_startup(self, cache_path, make_manager):
        self._write_cache_from_the_future(cache_path)

        with capture_logs(LOGGER_NAME, logging.WARNING) as captured:
            manager = make_manager()

        assert any("in the future" in line for line in captured.output)
        # Without this, "older than two hours" is false forever and the stale snapshot
        # is served across every restart.
        assert manager.calls == 1
        assert manager.get_rate("USD", "EUR") == 0.5

    def test_a_newer_snapshot_on_disk_does_not_block_the_write(self, cache_path, make_manager):
        """The write guard orders the savers of THIS process; a file claiming to be
        from the future used to veto every cache write for as long as the clock stayed
        behind it, while the log cheerfully said "Successfully updated rates"."""
        self._write_cache_from_the_future(cache_path)

        manager = make_manager()

        on_disk = json.loads(cache_path.read_text(encoding="utf-8"))
        assert on_disk["rates"]["USD"]["EUR"] == 0.5
        assert on_disk["rates"]["USD"]["EUR"] == manager.get_rate("USD", "EUR")

    def test_the_reported_age_is_never_negative(self, make_manager):
        manager = make_manager()
        manager._last_update = datetime.now() + timedelta(hours=3)

        with capture_logs(LOGGER_NAME, logging.WARNING) as captured:
            age = manager.rates_age()

        assert age == timedelta(0)
        assert any("in the future" in line for line in captured.output)

    def test_a_small_skew_is_not_worth_a_warning(self, make_manager):
        manager = make_manager()
        manager._last_update = datetime.now() + timedelta(seconds=30)

        with capture_logs(LOGGER_NAME, logging.INFO) as captured:
            manager._log_rates_age()

        assert manager.rates_age() == timedelta(0)
        assert not any(line.startswith("WARNING") for line in captured.output)


class TestBrokenCacheTimestamp:
    """A cache file whose `last_update` is not the naive local timestamp the rest of the
    class works with. The constructor is the dangerous place for this: src.bot builds the
    manager at import time, so an exception here is not a failed update but a bot that
    cannot start — and `restart: always` then loops on it forever, because the offending
    file sits on the data volume and a restart changes nothing about it."""

    def test_a_timestamp_with_an_offset_does_not_kill_the_constructor(self, cache_path, make_manager):
        """The realistic trigger is not a hand-edited file: the day _save_cache starts
        writing datetime.now(timezone.utc), every cache left by the previous release
        becomes one of these."""
        cache_path.write_text(json.dumps({
            "rates": {"USD": {"EUR": 0.9}, "EUR": {"USD": 1.1}},
            "last_update": (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat(),
        }), encoding="utf-8")

        manager = make_manager()

        # Normalised at load, so nothing downstream can hit the mixed subtraction again.
        assert manager._last_update.tzinfo is None
        # Five hours is past the two-hour threshold, and the instant survives the
        # conversion, so the stamp is read as old rather than as broken.
        assert manager.calls == 1
        assert manager.get_rate("USD", "EUR") == 0.5
        assert manager.rates_age() is not None

    def test_an_uncomparable_timestamp_is_reported_as_broken_instead_of_raising(self):
        """_future_skew is the helper whose whole job is to catch a broken timestamp, so
        it must not be the thing that raises on one — even on a path that does not exist
        today."""
        skew = _future_skew(datetime.now(timezone.utc), datetime.now())

        assert skew is not None
        assert skew > CLOCK_SKEW_TOLERANCE

    def test_an_uncomparable_timestamp_does_not_make_rates_age_raise(self, make_manager):
        """_future_skew absorbs the aware/naive TypeError, but rates_age then subtracted
        the very same pair itself. The raise escapes through _log_rates_age into the
        update thread, which has no handler around its loop — one such timestamp ended
        the periodic updates for the rest of the process' life."""
        manager = make_manager()
        manager._last_update = datetime.now(timezone.utc)

        with capture_logs(LOGGER_NAME, logging.WARNING):
            assert manager.rates_age() == timedelta(0)

        with capture_logs(LOGGER_NAME, logging.WARNING):
            manager._log_rates_age()

    def test_an_unparsable_timestamp_leaves_no_half_loaded_state(self, cache_path, make_manager):
        """The cache is rejected AND the update fails, so all three answers have to agree
        on "there are no rates". Serving 0.9 while rates_age() says None means the bot
        converts with numbers the log insists do not exist — and keeps at it until some
        later update happens to succeed."""
        cache_path.write_text(json.dumps({
            "rates": {"USD": {"EUR": 0.9}, "EUR": {"USD": 1.1}},
            "last_update": "not a date at all",
        }), encoding="utf-8")

        manager = make_manager(failures=99)

        assert manager.get_rate("USD", "EUR") is None
        assert manager.rates_age() is None
        assert manager.get_available_currencies() == []
