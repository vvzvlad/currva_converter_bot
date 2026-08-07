# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Integrity of the currency reference book.

src/currencies.py is the single source of truth: the parser derives an ISO-code
pattern from every entry and the formatter renders every amount through one, so a
malformed entry breaks both at once — and nothing else in the suite looks at the book
itself. Adding a currency means adding one line there; these tests are what tells you
that the line is well formed.
"""

import string

import pytest

from src.currencies import CURRENCIES, EMOJI_LETTERS
from src.currency_parser import AMBIGUOUS_CODES


# Regional indicator symbols, U+1F1E6..U+1F1FF: a flag is the two of them that match
# the ISO 3166-1 alpha-2 country code, which is the first two letters of the currency
# code. Derived here from the Unicode block rather than from EMOJI_LETTERS, so this is
# an independent check and not a restatement of the implementation.
REGIONAL_INDICATOR_A = 0x1F1E6

CODES = sorted(CURRENCIES)
ENTRIES = sorted(CURRENCIES.items())


def _regional_indicator(letter: str) -> str:
    return chr(REGIONAL_INDICATOR_A + ord(letter) - ord("A"))


@pytest.mark.parametrize("code, entry", ENTRIES, ids=CODES)
def test_entry_is_well_formed(code, entry):
    """Every invariant of one entry, in one case per currency.

    One test rather than four: the four checks share a single subject and a single
    reason to fail (somebody added or edited a line in the book), and 142 currencies
    times four tests is 568 items that each assert one line about a data file with no
    logic in it. The assertion messages carry which invariant broke.
    """
    # The parser iterates over the values and keys the patterns by entry.code; a
    # mismatch would make a currency unreachable through CURRENCIES[code].
    assert entry.code == code, f"{code}: the key and entry.code disagree ({entry.code!r})"

    assert len(code) == 3, f"{code}: an ISO 4217 code is three characters"
    assert all(c in string.ascii_uppercase for c in code), (
        f"{code}: an ISO 4217 code is uppercase ASCII letters only"
    )

    assert isinstance(entry.symbol, str), f"{code}: the symbol is not a string"
    assert entry.symbol != "", f"{code}: the symbol is empty"
    assert entry.symbol.strip() == entry.symbol, (
        f"{code}: the symbol has surrounding whitespace ({entry.symbol!r})"
    )

    if entry.flag_override is not None:
        # A shape check, not an equality check: CurrencyFormat.flag is defined as
        # `flag_override or <derived>`, so while the override is truthy `flag ==
        # flag_override` cannot fail. What it is actually worth pinning is that an
        # override that IS set is a usable string — an empty one would silently fall
        # through to the derived flag, which is what the override exists to avoid.
        assert isinstance(entry.flag_override, str), f"{code}: the flag override is not a string"
        assert entry.flag_override != "", (
            f"{code}: the flag override is empty, so entry.flag falls back to the derived one"
        )
        assert entry.flag == entry.flag_override, (
            f"{code}: entry.flag does not return the override ({entry.flag!r})"
        )
    else:
        expected = _regional_indicator(code[0]) + _regional_indicator(code[1])
        assert entry.flag == expected, (
            f"{code}: the derived flag is {entry.flag!r}, expected {expected!r}"
        )
        assert len(entry.flag) == 2, f"{code}: a derived flag is exactly two indicators"


def test_the_book_is_not_empty():
    assert len(CURRENCIES) > 100


def test_emoji_letters_covers_the_whole_latin_alphabet():
    assert set(EMOJI_LETTERS) == set(string.ascii_uppercase)
    assert all(EMOJI_LETTERS[c] == _regional_indicator(c) for c in string.ascii_uppercase)


def test_every_ambiguous_code_still_exists():
    # AMBIGUOUS_CODES is a hand-maintained frozenset of ISO codes that are also common
    # words ('ALL', 'MAD', 'PEN', ...) and are therefore excluded from the code-pattern
    # matching. Renaming or dropping a currency would leave a dangling entry there,
    # silently and with no test to catch it.
    assert AMBIGUOUS_CODES <= set(CURRENCIES)
