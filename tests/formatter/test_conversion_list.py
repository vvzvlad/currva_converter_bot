# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""format_multiple_conversions(): deduplication, truncation and the empty list."""

from src.currency_formatter import MAX_LISTED_CONVERSIONS


def test_the_rest_note_counts_unique_amounts_not_raw_matches(formatter, unit_rates):
    # Twelve matches, five distinct amounts: all five fit, so promising "the rest"
    # would simply be a lie.
    currency_list = [(float(i % 5) + 1, "USD", f"{i % 5 + 1} долларов") for i in range(12)]
    result = formatter.format_multiple_conversions(currency_list, unit_rates, mode='chat')
    assert "и остальные" not in result
    assert len(result.split("\n")) == 5


def test_more_unique_amounts_than_the_limit_are_truncated_with_the_note(formatter, unit_rates):
    currency_list = [(float(i), "USD", f"{i} долларов") for i in range(1, 15)]
    result = formatter.format_multiple_conversions(currency_list, unit_rates, mode='chat')
    lines = result.split("\n")
    assert len(lines) == MAX_LISTED_CONVERSIONS + 1
    assert lines[-1] == "... и остальные (сами считайте)"


def test_empty_list_still_returns_none(formatter, unit_rates):
    # Behaviour deliberately unchanged; only the annotation was corrected.
    assert formatter.format_multiple_conversions([], unit_rates, mode='chat') is None
