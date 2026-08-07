# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""How old the served rates are, and how loudly that is said."""

import logging
from datetime import datetime, timedelta

from src.exchange_rates_manager import STALE_RATES_MAX_AGE
from tests.logcapture import capture_logs
from tests.rates.doubles import LOGGER_NAME


def test_rates_older_than_the_threshold_are_warned_about(make_manager):
    manager = make_manager()
    manager._last_update = datetime.now() - timedelta(seconds=STALE_RATES_MAX_AGE + 60)

    with capture_logs(LOGGER_NAME, logging.WARNING) as captured:
        manager._log_rates_age()

    assert any("Serving exchange rates that are" in line for line in captured.output)


def test_fresh_rates_are_not_warned_about(make_manager):
    manager = make_manager()

    with capture_logs(LOGGER_NAME, logging.INFO) as captured:
        manager._log_rates_age()

    assert not any(line.startswith("WARNING") for line in captured.output)


def test_having_no_rates_at_all_is_an_error(make_manager):
    manager = make_manager(failures=99)

    assert manager.rates_age() is None
    with capture_logs(LOGGER_NAME, logging.ERROR) as captured:
        manager._log_rates_age()

    assert any("No exchange rates available" in line for line in captured.output)
