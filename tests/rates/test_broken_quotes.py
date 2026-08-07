# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""A quote payload that is only partly usable."""

import logging

import pytest

from tests.logcapture import capture_logs
from tests.rates.doubles import LOGGER_NAME


def test_a_zero_rate_skips_one_currency_instead_of_the_whole_update(make_manager):
    with capture_logs(LOGGER_NAME, logging.WARNING) as captured:
        manager = make_manager(quotes={"USDEUR": 0.5, "USDZWL": 0.0, "USDGBP": 0.25})

    assert any("ZWL" in line for line in captured.output)
    assert manager.get_rate("USD", "EUR") == 0.5
    assert manager.get_rate("USD", "ZWL") is None
    assert "ZWL" not in manager.get_available_currencies()
    # The healthy cross-rates are computed as if the dead currency never came.
    assert manager.get_rate("EUR", "GBP") == pytest.approx(0.5)


def test_negative_and_non_numeric_rates_are_skipped_too(make_manager):
    with capture_logs(LOGGER_NAME, logging.WARNING):
        manager = make_manager(quotes={
            "USDEUR": 0.5,
            "USDAAA": -1.0,
            "USDBBB": "not a number",
            "USDCCC": None,
        })

    assert sorted(manager.get_available_currencies()) == ["EUR", "USD"]
    assert manager.get_rate("USD", "EUR") == 0.5


def test_a_payload_with_nothing_usable_is_a_failure_and_keeps_the_old_rates(make_manager):
    manager = make_manager()
    assert manager.get_rate("USD", "EUR") == 0.5

    manager.quotes = {"USDZWL": 0.0}
    with capture_logs(LOGGER_NAME, logging.ERROR):
        assert not manager._update_all_rates()

    assert manager.get_rate("USD", "EUR") == 0.5
    assert manager._consecutive_failures == 1
