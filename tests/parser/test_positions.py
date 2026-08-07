# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""find_currency_matches() — the same search, with the offsets kept.

The inline handler splices its conversions into the message by these offsets, so
the property that has to hold is text[start:end] == original_text, for every match
of every text. Checked as a property over a corpus rather than as hand-counted
numbers: hand-counted offsets only prove the parser agrees with whoever counted.
"""

import logging

import pytest

from src.currency_parser import MAX_TEXT_LENGTH, CurrencyMatch

from tests.logcapture import capture_logs


# Deliberately includes the two texts that broke the old str.replace() assembly, a
# symbol-prefixed amount (the match starts before the digits), an amount whose group
# is empty ("килобаксов"), amounts with spaces inside them, and non-BMP characters
# ahead of a match (positions are character offsets, and an emoji is one character
# here but four bytes).
CORPUS_WITH_MATCHES = [
    "дай 100$ и еще 100$",
    "взял 1100$ и 100$",
    "100$",
    "100 долларов в начале",
    "в конце 100 долларов",
    "цена:  100$,  а не 200$!",
    "💰 100$ и 💶 100 евро",
    "£800 и 700£ и €50",
    "5 килобаксов",
    "1 000 000 рублей и 2,5к евро",
    "100500 CAD вышло",
]

# Kept apart from the corpus above: the three invariants below are all statements about
# a match, so a text with no matches runs them over an empty loop and asserts nothing.
# What is worth pinning about these texts is that they produce no match in the first
# place, which is its own test.
TEXTS_WITHOUT_MATCHES = [
    "ничего тут нет",
    "3 top и 5 mad — не валюты",
]

# Both projections of the search have to agree on emptiness too, so that one test runs
# over everything.
CORPUS = CORPUS_WITH_MATCHES + TEXTS_WITHOUT_MATCHES


@pytest.mark.parametrize("text", CORPUS_WITH_MATCHES)
def test_every_match_points_at_its_own_text(parser, text):
    matches = parser.find_currency_matches(text)
    assert matches
    for match in matches:
        assert isinstance(match, CurrencyMatch)
        assert text[match.start:match.end] == match.original_text


@pytest.mark.parametrize("text", CORPUS_WITH_MATCHES)
def test_matches_are_ordered_and_never_overlap(parser, text):
    """What makes a left-to-right rebuild of the text possible at all."""
    previous_end = 0
    for match in parser.find_currency_matches(text):
        assert match.start >= previous_end
        assert match.end > match.start
        previous_end = match.end
    assert previous_end <= len(text)


@pytest.mark.parametrize("text", TEXTS_WITHOUT_MATCHES)
def test_a_text_without_amounts_has_no_matches(parser, text):
    assert parser.find_currency_matches(text) == []


@pytest.mark.parametrize("text", CORPUS_WITH_MATCHES)
def test_the_gaps_and_the_matches_rebuild_the_original_text(parser, text):
    """The matches are a complete cut of the text, not a subset of it.

    This is exactly the assembly the inline handler does, with the conversions
    left out: if it does not reproduce the input, it cannot preserve it either.
    """
    pieces = []
    cursor = 0
    for match in parser.find_currency_matches(text):
        pieces.append(text[cursor:match.start])
        pieces.append(match.original_text)
        cursor = match.end
    pieces.append(text[cursor:])
    assert "".join(pieces) == text


@pytest.mark.parametrize("text", CORPUS)
def test_find_currencies_is_the_same_search_without_the_positions(parser, text):
    matches = parser.find_currency_matches(text)
    assert parser.find_currencies(text) == [match[:3] for match in matches]


def test_two_identical_amounts_are_two_matches_at_different_places(parser):
    """The triples are equal, and that is precisely why the positions are needed."""
    matches = parser.find_currency_matches("дай 100$ и еще 100$")
    assert len(matches) == 2
    first, second = matches
    assert first[:3] == second[:3]
    assert (first.start, first.end) != (second.start, second.end)
    assert (first.start, first.end) == (4, 8)
    assert (second.start, second.end) == (15, 19)


def test_a_shorter_amount_inside_a_longer_one_is_not_a_match_of_its_own(parser):
    """"100$" occurs inside "1100$" as a substring, but not as a match."""
    matches = parser.find_currency_matches("взял 1100$ и 100$")
    assert [match.original_text for match in matches] == ["1100$", "100$"]
    assert [(match.start, match.end) for match in matches] == [(5, 10), (13, 17)]


def test_text_longer_than_the_limit_has_no_matches_either(parser):
    over_limit = "а" * MAX_TEXT_LENGTH + " 100 рублей"
    with capture_logs("currency_parser", logging.WARNING):
        assert parser.find_currency_matches(over_limit) == []
