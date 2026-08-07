# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""The generated "<amount> <ISO CODE>" fallback.

Every currency in the reference book gets one, so the long tail (KWD, CHF, NOK, ...)
parses without a hand-written regex. Two rules make that safe, and both are pinned
here: the codes that are ordinary English words are skipped altogether
(AMBIGUOUS_CODES), and the generated pattern is deliberately case-SENSITIVE, so a
lowercase "3 top" or "5 mad max" stays plain text while "7666777 KWD" is an amount.
A hand-written pattern that itself matches "1 <CODE>" replaces the generated
fallback for that code entirely (_already_matched), and such codes then match
case-INsensitively — true for most hand-written currencies, whose patterns
embed their own code (USD, RUB, KRW, ...; see e.g. BRL_CASES in test_names.py).
"""

import pytest

from src.currencies import CURRENCIES
from src.currency_parser import AMBIGUOUS_CODES


# ...but a lowercase code is NOT enough for the long tail, otherwise ordinary
# words would become currency amounts
LOWERCASE_LONG_TAIL_CASES = [
    ("7666777 kwd", []),
    ("поставил 3 top", []),
    ("5 mad max", []),
    ("я взял 3 all", []),
    ("8 cup", []),
    ("2 mop", []),
    ("1 bob", []),
    ("50 sos", []),
    ("7666777 KWD", [(7666777.0, "KWD", "7666777 KWD")]),
    ("100 CHF", [(100.0, "CHF", "100 CHF")]),
]


# AMBIGUOUS_CODES are not parsed by code even in uppercase
AMBIGUOUS_CODE_CASES = [
    ("рецепт: 1 CUP муки", []),
    ("score 3 TOP", []),
    ("5 MAD MAX", []),
    ("I PAID 100 ALL DAY", []),
    ("заказ 5 SOS", []),
]


# AMD has no ISO code in its hand-written pattern, so it must keep its fallback
AMD_FALLBACK_CASES = [
    ("1000 AMD", [(1000.0, "AMD", "1000 AMD")]),
    ("5500 AMD", [(5500.0, "AMD", "5500 AMD")]),
    # Lowercase is not enough here either, and the code has to follow the amount.
    ("415 amd", []),
    ("AMD6521", []),
    ("AMD 6521", []),
]


# An uppercase word that is not a currency code stays plain text.
UNKNOWN_CODE_CASES = [
    ("1 TON", []),
]


@pytest.mark.parametrize(
    "currency",
    [currency for currency in CURRENCIES.values() if currency.code not in AMBIGUOUS_CODES],
    ids=lambda currency: currency.code,
)
def test_every_known_code_parses_in_uppercase(parser, currency):
    """ISO code fallback: every known currency parses by its uppercase code,
    except the codes that are ordinary English words (see AMBIGUOUS_CODES)"""
    text = f"1 {currency.code}"
    assert parser.find_currencies(text) == [(1.0, currency.code, text)]


@pytest.mark.parametrize("text,expected", LOWERCASE_LONG_TAIL_CASES)
def test_the_fallback_is_case_sensitive(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", AMBIGUOUS_CODE_CASES)
def test_ambiguous_codes_are_never_parsed(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", AMD_FALLBACK_CASES)
def test_amd_keeps_its_generated_fallback(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", UNKNOWN_CODE_CASES)
def test_unknown_uppercase_words_are_not_codes(parser, text, expected):
    assert parser.find_currencies(text) == expected
