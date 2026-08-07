# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""The "Дополняй" result: the user's own text with a conversion after every amount.

It used to be built with str.replace(original, conversion) once per match, which
rewrites EVERY equal substring rather than the match it was called for. Two amounts
of the same size therefore got two conversions each, and a shorter amount replaced
itself inside the conversion a longer one had already inserted. The text the user
then sent into the chat was mangled, so these tests assert on the exact string.

Every expectation is written as a template — literal gap, conversion, literal gap —
so the text between the matches is part of what is checked.
"""

import logging
from unittest import mock

import pytest

from tests.bot.doubles import inline_query
from tests.logcapture import assert_no_logs


@pytest.fixture(autouse=True)
def wired(bot, fake_bot, rates, statistics, user_settings):
    with mock.patch.object(bot, "bot", fake_bot), \
         mock.patch.object(bot, "rates_manager", rates), \
         mock.patch.object(bot, "statistics_manager", statistics), \
         mock.patch.object(bot, "user_settings_manager", user_settings):
        yield


@pytest.fixture
def complete(bot, fake_bot):
    """Run the handler and return the message text of the "Дополняй" result."""
    def _complete(text):
        with assert_no_logs("bot", logging.ERROR):
            bot.handle_inline_query(inline_query(text))
        assert len(fake_bot.answered) == 1
        results = fake_bot.answered[0][1]
        assert [result.id for result in results] == ["1", "2"]
        return results[1].input_message_content.message_text

    return _complete


@pytest.fixture
def conversion(bot):
    """What the formatter alone produces for a text holding exactly one amount.

    Built through the formatter rather than spelled out, because the wording of a
    conversion is the formatter's business and is covered by its own tests. What is
    being tested here is only WHERE those strings end up.
    """
    def _conversion(amount_text):
        found = bot.currency_parser.find_currencies(amount_text)
        assert len(found) == 1, amount_text
        rates = bot._collect_rates(found, None)
        return bot.currency_formatter.format_conversion(found[0], rates, mode="inline", user_currencies=None)

    return _conversion


def test_two_identical_amounts_are_each_replaced_by_one_conversion(complete, conversion):
    converted = conversion("100$")
    completed = complete("дай 100$ и еще 100$")

    assert completed == f"дай {converted} и еще {converted}"
    # The symptom the user saw: "100$ (…) (…)". Counting the blocks catches it even
    # if the wording of a conversion ever changes.
    assert completed.count("(") == 2 * converted.count("(")
    assert ") (" not in completed


def test_a_shorter_amount_is_not_replaced_inside_the_conversion_of_a_longer_one(complete, conversion):
    """"100$" is a substring of "1100$" — and of the conversion inserted for it."""
    completed = complete("взял 1100$ и 100$")

    assert completed == f"взял {conversion('1100$')} и {conversion('100$')}"


def test_an_amount_at_the_start_of_the_text(complete, conversion):
    assert complete("100$ и всё") == f"{conversion('100$')} и всё"


def test_an_amount_at_the_end_of_the_text(complete, conversion):
    assert complete("итого 100$") == f"итого {conversion('100$')}"


def test_the_whole_text_is_one_amount(complete, conversion):
    assert complete("100$") == conversion("100$")


def test_a_single_amount_in_the_middle_behaves_as_before(complete, conversion):
    completed = complete("я купил телевизор за 100 долларов и доволен")
    assert completed == f"я купил телевизор за {conversion('100 долларов')} и доволен"


def test_text_without_amounts_is_passed_through_untouched(bot, fake_bot):
    text = "просто текст без денег"
    with assert_no_logs("bot", logging.ERROR):
        bot.handle_inline_query(inline_query(text))

    results = fake_bot.answered[0][1]
    assert [result.input_message_content.message_text for result in results] == [text, text]


def test_everything_outside_the_matches_survives_verbatim(complete, conversion):
    """Punctuation, doubled spaces and non-BMP characters, character for character.

    The emoji matter for more than decoration: they are one character each in
    Python but four bytes, so an offset computed anywhere other than on the string
    itself would slice the text apart in the wrong place.
    """
    text = "💰 цена:  100$,  а не 200 евро!  💶"
    completed = complete(text)

    assert completed == f"💰 цена:  {conversion('100$')},  а не {conversion('200 евро')}!  💶"

    # Same claim from the other side, without a template: putting the originals back
    # in place of the conversions must return the input unchanged.
    restored = completed
    for original in ("100$", "200 евро"):
        restored = restored.replace(conversion(original), original, 1)
    assert restored == text


def test_the_conversion_belongs_to_the_amount_it_follows(complete, conversion):
    """Different amounts, so a mixed-up assembly cannot pass by accident."""
    completed = complete("сначала 100$, потом 200$, снова 100$")

    assert completed == (
        f"сначала {conversion('100$')}, потом {conversion('200$')}, "
        f"снова {conversion('100$')}"
    )
