# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""The three canned replies that replace a conversion — chat mode only.

  * a zero amount            -> "Нахуй иди"
  * exactly 0.5 USD          -> "In Da Club!"
  * >= 1 000 000 US dollars  -> "Откуда у тебя такие деньги, сынок?"
"""

import pytest


CANNED_CHAT_REPLIES = [
    ("0 рублей", "Нахуй иди"),
    ("0 динаров", "Нахуй иди"),
    ("2000000 долларов", "Откуда у тебя такие деньги, сынок?"),
    ("50 cents", "In Da Club!"),
    ("0.5 USD", "In Da Club!"),
]


@pytest.mark.parametrize("text, expected", CANNED_CHAT_REPLIES)
def test_canned_chat_reply(parser, formatter, unit_rates, text, expected):
    currency_list = parser.find_currencies(text)
    assert formatter.format_multiple_conversions(currency_list, unit_rates, mode='chat') == expected


# The "Откуда у тебя такие деньги, сынок?" threshold is in DOLLARS.
#
# Without a `{currency}_USD` rate the dollar amount stayed equal to the amount in
# the source currency, so the threshold was applied to the raw number: 5 000 000
# драм (about 12 000 USD) got the punchline instead of a conversion.


def test_big_amount_without_a_usd_rate_is_converted_normally(formatter):
    rates = {"AMD_RUB": 0.24}
    result = formatter.format_conversion((5_000_000, "AMD", "5 000 000 драм"), rates, mode='chat')
    assert "Откуда" not in result
    assert "₽" in result


def test_big_amount_that_is_small_in_dollars_is_converted_normally(formatter):
    rates = {"AMD_USD": 0.0026, "AMD_RUB": 0.24}
    result = formatter.format_conversion((5_000_000, "AMD", "5 000 000 драм"), rates, mode='chat')
    assert "Откуда" not in result


def test_the_joke_still_fires_when_the_amount_really_is_a_million_dollars(formatter):
    rates = {"AMD_USD": 0.0026, "AMD_RUB": 0.24}
    result = formatter.format_conversion((500_000_000, "AMD", "500 000 000 драм"), rates, mode='chat')
    assert result == "Откуда у тебя такие деньги, сынок?"


def test_dollars_need_no_rate_at_all(formatter):
    # The source currency IS the threshold currency, so an empty rates dict
    # changes nothing here.
    result = formatter.format_conversion((2_000_000, "USD", "2000000 долларов"), {}, mode='chat')
    assert result == "Откуда у тебя такие деньги, сынок?"


def test_inline_mode_never_jokes(formatter):
    result = formatter.format_conversion((2_000_000, "USD", "2000000 долларов"), {"USD_RUB": 1.0}, mode='inline')
    assert "Откуда" not in result


@pytest.mark.parametrize("mode", ["inline", "chat"])
def test_zero_and_half_a_dollar_only_joke_in_chat_mode(formatter, mode):
    # The two cheap jokes sit behind the same `mode == 'chat'` guard as the
    # millionaire one; inline mode converts instead.
    zero = formatter.format_conversion((0.0, "RUB", "0 рублей"), {"RUB_USD": 1.0}, mode=mode)
    half = formatter.format_conversion((0.5, "USD", "0.5 USD"), {"USD_RUB": 1.0}, mode=mode)
    if mode == 'chat':
        assert zero == "Нахуй иди"
        assert half == "In Da Club!"
    else:
        assert zero == "0 рублей (🇺🇸 $0)"
        assert half == "0.5 USD (🇷🇺 0.5 ₽)"
