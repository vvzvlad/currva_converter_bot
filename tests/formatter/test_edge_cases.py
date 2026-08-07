# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""The branches of CurrencyFormatter that the message-level tests never reach:
no rates at all, an unknown mode, a user currency list that leaves nothing to
convert, a rate that blows up mid-conversion, and the rounding rules of
_format_amount().
"""

from decimal import Decimal
import logging

import pytest

from tests.logcapture import capture_logs


# --- no rates available ------------------------------------------------------
# With no rates at all there is nothing to convert, and the reply says so instead of
# ending after the amount. The wording is pinned per mode: inline mode appends the
# notice in parentheses right after the amount, chat mode keeps its "это" and puts the
# notice where the conversions would have been.

def test_inline_answer_without_any_rates(parser, formatter):
    currency_list = parser.find_currencies("100 долларов")
    result = formatter.format_multiple_conversions(currency_list, {}, mode='inline')
    assert result == "100 долларов (нет доступных курсов конвертации)"


def test_chat_reply_without_any_rates(parser, formatter):
    currency_list = parser.find_currencies("100 долларов")
    result = formatter.format_multiple_conversions(currency_list, {}, mode='chat')
    assert result == "100 долларов (🇺🇸) это (нет доступных курсов конвертации)"


# --- unknown mode ------------------------------------------------------------

@pytest.mark.parametrize(
    "currency_data",
    [
        (100.0, "USD", "100 долларов"),
        # The GBP path has a second `raise ValueError(f"Unknown mode: {mode}")` of its
        # own (currency_formatter.py:118), guarded by the same 'фунт' / '£' condition
        # as the kilogram joke. It is dead code: the mode dispatch a few lines above
        # (:107-108) already raises for anything that is neither 'chat' nor 'inline',
        # so control never reaches it. This case therefore raises from the FIRST site,
        # exactly like the USD one — it is here to pin the observable behaviour.
        (100.0, "GBP", "100 фунтов"),
    ],
    ids=["plain", "gbp-kilogram-path"],
)
def test_an_unknown_mode_is_rejected(formatter, unit_rates, currency_data):
    with pytest.raises(ValueError, match="Unknown mode: telepathy"):
        formatter.format_conversion(currency_data, unit_rates, mode='telepathy')


def test_an_unknown_mode_propagates_through_format_multiple_conversions(formatter, unit_rates):
    with pytest.raises(ValueError, match="Unknown mode"):
        formatter.format_multiple_conversions([(100.0, "USD", "100 долларов")], unit_rates, mode='telepathy')


# --- user currency lists -----------------------------------------------------

def test_only_the_source_currency_configured(formatter, unit_rates):
    # Converting USD to USD is not a conversion, so the user is pointed at the
    # command that fixes their settings instead of getting an empty list.
    result = formatter.format_conversion(
        (100.0, "USD", "100 долларов"), unit_rates, mode='chat', user_currencies=['USD'],
    )
    assert result == "100 долларов (🇺🇸): других валют для конвертации не установлено. Используйте /currencies"


def test_user_currencies_replace_the_defaults(formatter, unit_rates):
    # ILS and GBP are in the defaults but not in this list, so they must not show up;
    # USD is the source currency and is skipped even though it is listed.
    result = formatter.format_conversion(
        (100.0, "USD", "100 долларов"), unit_rates, mode='chat', user_currencies=['EUR', 'JPY', 'USD'],
    )
    assert result == "100 долларов (🇺🇸) это 🇪🇺 100 €, 🇯🇵 ¥100"


# --- a conversion that raises ------------------------------------------------

def test_a_broken_rate_is_logged_and_skipped(formatter):
    # A rate that cannot become a Decimal kills only its own conversion: the reply
    # still carries every other currency instead of disappearing entirely.
    rates = {"USD_RUB": "not-a-number", "USD_EUR": 1.0}
    with capture_logs("currency_formatter", logging.ERROR) as captured:
        result = formatter.format_conversion(
            (100.0, "USD", "100 долларов"), rates, mode='chat', user_currencies=['RUB', 'EUR'],
        )
    assert result == "100 долларов (🇺🇸) это 🇪🇺 100 €"
    assert "₽" not in result
    assert any("Error converting" in record.getMessage() for record in captured.records)


# --- _format_amount rounding rules -------------------------------------------

FORMAT_AMOUNT_CASES = [
    # Above 20: whole numbers only.
    (Decimal("100.6"), "USD", "🇺🇸 $101"),
    (Decimal("21"), "RUB", "🇷🇺 21 ₽"),
    # Above 10000 (strictly): thousands separated by spaces.
    (Decimal("10000"), "USD", "🇺🇸 $10000"),
    (Decimal("10001"), "USD", "🇺🇸 $10 001"),
    (Decimal("2000000"), "RUB", "🇷🇺 2 000 000 ₽"),
    # At or below 20: rounded to two decimals first...
    (Decimal("20"), "USD", "🇺🇸 $20"),
    (Decimal("1"), "ILS", "🇮🇱 1 ₪"),
    # ...then a non-zero tenths digit is shown with ONE decimal place...
    (Decimal("12.34"), "RUB", "🇷🇺 12.3 ₽"),
    # ...unless rounding to one decimal makes it whole again.
    (Decimal("1.96"), "USD", "🇺🇸 $2"),
    # A tenths digit of 0 keeps both decimals, otherwise "0.05" would print as "0".
    (Decimal("0.05"), "USD", "🇺🇸 $0.05"),
    (Decimal("3.04"), "GBP", "🇬🇧 £3.04"),
    # Anything that rounds to zero is a plain "0", never "0.00".
    (Decimal("0"), "ILS", "🇮🇱 0 ₪"),
    (Decimal("0.004"), "USD", "🇺🇸 $0"),
]


@pytest.mark.parametrize("amount, code, expected", FORMAT_AMOUNT_CASES)
def test_format_amount(formatter, amount, code, expected):
    assert formatter._format_amount(amount, code) == expected


@pytest.mark.parametrize(
    "code, expected",
    [
        # symbol_before_number=True
        ("USD", "🇺🇸 $7"),
        ("GBP", "🇬🇧 £7"),
        # symbol_before_number=False
        ("RUB", "🇷🇺 7 ₽"),
        ("ILS", "🇮🇱 7 ₪"),
    ],
)
def test_symbol_placement_follows_the_reference_book(formatter, code, expected):
    assert formatter._format_amount(Decimal("7"), code) == expected


# --- the pounds-to-kilograms joke --------------------------------------------
# GBP written as "фунт" (or with a £ sign) is deliberately read as pounds of WEIGHT
# as well: 1 lb = 0.45359237 kg.

@pytest.mark.parametrize(
    "amount, original, mode, expected_prefix",
    [
        (1.0, "1 фунт", 'inline', "1 фунт (0.5 кг) ("),
        (1.0, "1 фунт", 'chat', "1 фунт (🇬🇧) это 0.5 кг, а также "),
        (100.0, "100 фунтов", 'inline', "100 фунтов (45.4 кг) ("),
        (100.0, "100 фунтов", 'chat', "100 фунтов (🇬🇧) это 45.4 кг, а также "),
        (100.0, "£100", 'inline', "£100 (45.4 кг) ("),
        (100.0, "£100", 'chat', "£100 (🇬🇧) это 45.4 кг, а также "),
    ],
)
def test_pounds_are_also_weighed(formatter, unit_rates, amount, original, mode, expected_prefix):
    result = formatter.format_conversion((amount, "GBP", original), unit_rates, mode=mode)
    assert result.startswith(expected_prefix)


@pytest.mark.parametrize("mode", ['chat', 'inline'])
def test_an_iso_coded_gbp_amount_is_not_weighed(formatter, unit_rates, mode):
    # The condition looks at the ORIGINAL text, not at the currency code, so "100 GBP"
    # is money and nothing else.
    result = formatter.format_conversion((100.0, "GBP", "100 GBP"), unit_rates, mode=mode)
    assert "кг" not in result
