# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""_collect_rates(): which pairs a message actually costs a lookup."""

from unittest import mock

import pytest

from tests.bot.doubles import RecordingRatesManager


@pytest.fixture(autouse=True)
def wired_rates(bot, rates):
    with mock.patch.object(bot, "rates_manager", rates):
        yield


@pytest.fixture
def defaults(bot):
    return set(bot.currency_formatter.default_currencies)


def test_no_user_settings_fetches_only_the_default_currencies(bot, rates, defaults):
    found = [(100.0, "GEL", "100 лари")]
    for user_currencies in (None, []):
        rates.requested.clear()
        result = bot._collect_rates(found, user_currencies)
        assert rates.requested_targets == defaults, f"user_currencies={user_currencies}"
        # The whole reference book is ~142 entries; the point of the fallback is
        # that a message costs a handful of lookups, not all of them.
        assert len(rates.requested) < len(bot.currency_formatter.target_currencies) // 2, \
            f"user_currencies={user_currencies}"
        assert set(result) == {f"GEL_{target}" for target in defaults}, \
            f"user_currencies={user_currencies}"


def test_usd_is_requested_even_when_the_user_left_it_out(bot, rates):
    result = bot._collect_rates([(100.0, "GEL", "100 лари")], ["EUR", "GBP"])
    assert rates.requested_targets == {"EUR", "GBP", "USD"}
    assert "GEL_USD" in result


def test_usd_is_not_requested_twice_when_the_user_asked_for_it(bot, rates):
    bot._collect_rates([(100.0, "GEL", "100 лари")], ["USD", "EUR"])
    assert rates.requested == [("GEL", "USD"), ("GEL", "EUR")]


def test_the_source_currency_is_not_converted_into_itself(bot, rates):
    bot._collect_rates([(100.0, "EUR", "100 евро")], ["EUR", "GBP"])
    assert ("EUR", "EUR") not in rates.requested
    assert rates.requested_targets == {"GBP", "USD"}


def test_repeated_amounts_in_the_same_currency_are_fetched_once(bot, rates):
    """Twelve sums in roubles used to mean 7 x 12 lookups, each taking the
    manager's lock, all writing the same twelve keys."""
    found = [(float(index), "RUB", f"{index} рублей") for index in range(1, 13)]
    result = bot._collect_rates(found, ["EUR", "USD"])

    assert rates.requested == [("RUB", "EUR"), ("RUB", "USD")]
    assert set(result) == {"RUB_EUR", "RUB_USD"}


def test_several_source_currencies_are_all_fetched(bot, rates):
    found = [(1.0, "RUB", "1 рубль"), (2.0, "GEL", "2 лари"), (3.0, "RUB", "3 рубля")]
    bot._collect_rates(found, ["EUR"])

    assert rates.requested == [("RUB", "EUR"), ("RUB", "USD"), ("GEL", "EUR"), ("GEL", "USD")]


def test_a_missing_rate_is_left_out_of_the_result(bot):
    rates = RecordingRatesManager(missing=[("GEL", "GBP")])
    with mock.patch.object(bot, "rates_manager", rates):
        result = bot._collect_rates([(100.0, "GEL", "100 лари")], ["GBP", "EUR"])
    assert "GEL_GBP" not in result
    assert "GEL_EUR" in result
