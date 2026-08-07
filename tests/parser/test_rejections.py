# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Text that must produce no match at all.

Only the generic junk lives here — ordinary chat messages, spelled-out numbers,
swearing, a currency word with nothing that looks like an amount. A rejection that
exists to pin down ONE currency's pattern ("0.2 незлотых", "1 лвл") stays next to
that currency instead, in test_names.py or test_symbols.py.
"""

import pytest


# A number and a Russian numeral spelled out in words: the parser reads digits only.
SPELLED_OUT_NUMBER_CASES = [
    ("два с половиной бакса", []),
    ("пять баксов", []),
    ("three hundred bucks", []),
    ("Сто фунтов", []),
    ("Двадцать два рубля", []),
    ("Пять тысяч рублей", []),
    ("пицот рублей", []),
    ("Две тысячи двести двадцать два рубля", []),
    ("две тысячи долларов", []),
    ("минус пять евро", []),
]


# Ordinary text, with or without a number in it.
PROSE_CASES = [
    ("Привет, как дела?", []),
    ("123", []),
    ("просто текст", []),
    ("8", []),
    # The currency word has to follow the amount, not precede it.
    ("долларов 100", []),
    ("null долларов", []),
    ("Бля рубля", []),
    ("77 тугриков", []),
    ("1 шахерезада", []),
    ("30 пхп", []),
    ("100500 кгам", []),
    ("1337 чего блядь", []),
    ("500 сигарет", []),
]


# Whatever the message is, a word that is not a currency is not a currency.
ABUSE_CASES = [
    ("500 хуёв тебе в жопу", []),
]


@pytest.mark.parametrize("text,expected", SPELLED_OUT_NUMBER_CASES)
def test_spelled_out_numbers(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", PROSE_CASES)
def test_prose(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", ABUSE_CASES)
def test_abuse(parser, text, expected):
    assert parser.find_currencies(text) == expected
