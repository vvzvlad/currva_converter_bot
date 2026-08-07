# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Word boundaries — what may touch a match, and what disqualifies it.

A match is kept only when the character in front of it and the character after it are
not alphanumeric (and the one in front is none of "#@^e%"). That is what keeps the
bot out of URLs, e-mail addresses, hashtags, mentions and ordinary words with digits
in them, while still letting brackets, dashes, punctuation and emoji sit right next to
an amount.
"""

import pytest


# The amount is surrounded by spaces, or sits at the beginning/end of the text
SURROUNDED_BY_SPACES_CASES = [
    ("100 рублей", [(100.0, "RUB", "100 рублей")]),
    ("$100", [(100.0, "USD", "$100")]),
    ("100$", [(100.0, "USD", "100$")]),
    ("текст 100 рублей", [(100.0, "RUB", "100 рублей")]),
    ("100 рублей текст", [(100.0, "RUB", "100 рублей")]),
    ("текст 100$ текст", [(100.0, "USD", "100$")]),
    ("текст $100 текст", [(100.0, "USD", "$100")]),
    ("текст, 100 рублей.", [(100.0, "RUB", "100 рублей")]),
    ("текст! 100$ текст", [(100.0, "USD", "100$")]),
]


# The amount is glued to a word
GLUED_TO_A_WORD_CASES = [
    ("текст100рублей", []),
    ("текст100$текст", []),
    ("текст$100текст", []),
    ("100рублейтекст", []),
    ("$100текст", []),
    ("текст100$", []),
    ("текст$100", []),
    ("цена100рублей", []),
    ("цена100$", []),
]


# The same, with a currency symbol instead of a currency word
SYMBOL_GLUED_TO_A_WORD_CASES = [
    ("текст₽100", []),
    ("текст100₽", []),
    ("текст₽100текст", []),
    ("текст100₽текст", []),
]


# Non-alphanumeric characters are separators, so they do not break a match
SEPARATOR_CASES = [
    ("текст-100$", [(100.0, "USD", "100$")]),
    ("текст_100$", [(100.0, "USD", "100$")]),
    ("текст/100$", [(100.0, "USD", "100$")]),
    ("текст(100$)", [(100.0, "USD", "100$")]),
    ("текст[100$]", [(100.0, "USD", "100$")]),
]


URL_AND_EMAIL_CASES = [
    ("сайт100$.com", []),
    ("email@100$.com", []),
    ("https://100$.com", [(100.0, "USD", "100$")]),
    # From a real message: a track id that happens to contain "6Dh"
    ("https://open.spotify.com/track/3cfgisz6DhZmooQk08P4Eu", []),
]


HASHTAG_AND_MENTION_CASES = [
    ("#100$", []),
    ("@100$", []),
    ("#100 $", []),
]


EMOJI_CASES = [
    ("💰100$", [(100.0, "USD", "100$")]),
    ("100$💰", [(100.0, "USD", "100$")]),
]


# Several currencies with nothing between them: only the ones whose neighbours pass
# the boundary check survive
SEVERAL_CURRENCIES_CASES = [
    ("100$200€", [(200.0, 'EUR', '200€')]),
    ("100$текст200€", []),
    ("текст100$текст200€текст", []),
    ("текст 100$ текст 200€ текст", [(100.0, "USD", "100$"), (200.0, "EUR", "200€")]),
]


# "dh" is a latin abbreviation, so the boundary rules matter more for it than for the
# cyrillic names: a letter on either side makes it part of a word
AED_DH_CASES = [
    ("100dh", [(100.0, "AED", "100dh")]),
    ("текст100dh", []),
    ("текст 100dh", [(100.0, "AED", "100dh")]),
    ("100dhтекст", []),
    ("100dh текст", [(100.0, "AED", "100dh")]),
    ("6Dh", [(6.0, "AED", "6Dh")]),
    ("текст6Dh", []),
    ("текст 6Dh", [(6.0, "AED", "6Dh")]),
    ("6Dhтекст", []),
    ("6Dh текст", [(6.0, "AED", "6Dh")]),
]


@pytest.mark.parametrize("text,expected", SURROUNDED_BY_SPACES_CASES)
def test_surrounded_by_spaces(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", GLUED_TO_A_WORD_CASES)
def test_glued_to_a_word(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", SYMBOL_GLUED_TO_A_WORD_CASES)
def test_symbol_glued_to_a_word(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", SEPARATOR_CASES)
def test_punctuation_is_a_separator(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", URL_AND_EMAIL_CASES)
def test_urls_and_emails(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", HASHTAG_AND_MENTION_CASES)
def test_hashtags_and_mentions(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", EMOJI_CASES)
def test_emoji(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", SEVERAL_CURRENCIES_CASES)
def test_several_currencies_without_spaces(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", AED_DH_CASES)
def test_aed_dh(parser, text, expected):
    assert parser.find_currencies(text) == expected
