# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""The limits of the scan: how long, how deep, and what happens past them.

MAX_TEXT_LENGTH, the bound on the thousands-group repeat, the linear-time guard that
stands in for a fixed denial of service, and the amounts the normaliser has to refuse
rather than turn into a zero. These are the regression guards, not the feature tests —
the comments explain what broke, and they are the reason the numbers are what they are.
"""

import logging
import time

import pytest

from src.currency_parser import MAX_TEXT_LENGTH

from tests.logcapture import capture_logs


BACKTRACKING_CASES = [
    # A fourth decimal digit means the separator was never a thousands separator:
    # "1.2345" is one number, not "1.234" followed by a stray "5".
    ("1.2345 евро", [(1.2345, "EUR", "1.2345 евро")]),
    ("1.234 евро", [(1.234, "EUR", "1.234 евро")]),

    # The "$<amount>" pattern ends in \b, so a letter glued to the digits forces
    # the amount to stop one thousands group earlier.
    ("$1 000 000", [(1000000.0, "USD", "$1 000 000")]),
    ("$1 000 000abc", [(1000.0, "USD", "$1 000")]),

    # The "к" suffix has to be given back when the currency name itself starts
    # with "к" and there is no space in between.
    ("5крон", [(5.0, "CZK", "5крон")]),
    ("5килобаксов", [(5000.0, "USD", "5килобаксов")]),
    ("5к баксов", [(5000.0, "USD", "5к баксов")]),
    ("10 000к рублей", [(10000000.0, "RUB", "10 000к рублей")]),

    # Long amounts stay unbounded: the plain-integer branch has no digit limit.
    ("12345678901234567890 USD", [(1.2345678901234567e+19, "USD", "12345678901234567890 USD")]),
    ("1 000 000 000 000 донгов", [(1000000000000.0, "VND", "1 000 000 000 000 донгов")]),

    # Mixed separators, both orders.
    ("1.234,56 евро", [(1234.56, "EUR", "1.234,56 евро")]),
    ("1,234.56 usd", [(1234.56, "USD", "1,234.56 usd")]),
    ("1 000 000,50 евро", [(1000000.5, "EUR", "1 000 000,50 евро")]),

    # A number right after another number: nothing is glued together.
    ("100 500 долларов", [(100500.0, "USD", "100 500 долларов")]),
    ("1 000 200", []),
    ("10 000₽", [(10000.0, "RUB", "10 000₽")]),
]


PAST_THE_THOUSANDS_GROUP_BOUND_CASES = [
    # Space separator: the amount cannot reach the currency word from the start of
    # the number, so the match slides right and starts on a group of zeroes.
    ("1 000 000 000 000 000 000 000 рублей",
     [(0.0, "RUB", "000 000 000 000 000 000 000 рублей")]),

    # Symbol prefix, space separator: the match simply stops at the sixth group.
    ("€1 000 000 000 000 000 000 000",
     [(1e18, "EUR", "€1 000 000 000 000 000 000")]),

    # Comma separator: not truncated at all. The seventh group is consumed by the
    # decimal tail `(?:[.,]\d+)?`, and the amount normaliser folds it back in.
    ("1,000,000,000,000,000,000,000 USD",
     [(1e21, "USD", "1,000,000,000,000,000,000,000 USD")]),

    # Right at the bound everything still behaves normally, whatever the separator.
    ("1 000 000 000 000 000 000 рублей",
     [(1e18, "RUB", "1 000 000 000 000 000 000 рублей")]),
]


@pytest.mark.parametrize("text,expected", BACKTRACKING_CASES)
def test_amount_shapes_that_need_backtracking(parser, text, expected):
    """Amount shapes that pin down how much the amount regex may consume.

    These are the cases that break if the repeats in the amount pattern are made
    possessive without thinking: each of them only parses because the engine is
    still allowed to hand something back. Kept as an explicit guard so a future
    performance tweak cannot quietly change what the bot recognises.
    """
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", PAST_THE_THOUSANDS_GROUP_BOUND_CASES)
def test_amounts_past_seven_thousands_groups_are_not_specified(parser, text, expected):
    """Pins what actually happens beyond the `{0,6}` bound in the amount regex.

    The repeat over thousands groups is capped at six because the separator class
    contains a space: unbounded, a run of digit groups is re-scanned from every
    start position, which is the quadratic blow-up the test below guards. Six
    groups after the leading one to three digits reach 10^18 — orders of magnitude
    past any amount a chat message can mean, so the cap costs nothing real.

    Past the cap the result depends on the separator, and that is deliberately NOT
    made consistent: capping cheaply is the point, and no reachable input cares.
    These assertions exist so the behaviour is a recorded decision — if a future
    change to the bound moves them, that is fine, but it has to be noticed.
    """
    assert parser.find_currencies(text) == expected


def _time_parse(parser, text):
    started = time.perf_counter()
    parser.find_currencies(text)
    return time.perf_counter() - started


def test_parsing_time_scales_linearly_with_text_length(parser):
    """Regression guard for the catastrophic backtracking in the amount regex.

    The thousands-separator class contains a space, so on a run of digit groups
    ("123 456 789 123 ...") the old unbounded repeat swallowed the whole tail from
    every start position and then handed it back group by group — quadratic in the
    length of the text, times ~170 patterns. Measured before the fix: 0.6 s at 500
    characters, 2.5 s at 1000, 7 s at 1600, ~20-33 s at the 4096-character Telegram
    limit. `re` does not release the GIL, so that froze the whole process — polling,
    both telebot workers and the metrics thread — which made a single chat message a
    remote denial of service, reachable by accident with a pasted CSV column too.

    The assertion is on the SHAPE of the curve, not on a wall-clock threshold: an
    absolute limit tuned on a developer machine says nothing on a loaded shared CI
    runner. Doubling the input doubles the work when the scan is linear (~2.0
    measured) and quadruples it when it is not, so a ratio under 3 separates the two
    regardless of how fast or how busy the machine is. Each length is measured
    several times and the FASTEST run is kept — a scheduling hiccup can only make a
    run slower, so the minimum is the least noisy estimate available.
    """
    def fastest_run(length):
        text = ('123 456 789 ' * 400)[:length]
        assert len(text) == length
        return min(_time_parse(parser, text) for _ in range(5))

    parser.find_currencies('123 456 789 ' * 10)  # warm up the compiled patterns

    half = MAX_TEXT_LENGTH // 2

    # Short circuit on a SINGLE run before measuring the curve. The ratio above is
    # the real assertion, but reaching it costs ten parses, and if the regression is
    # back each of them takes ~10 s: the test would fail after ~3.5 minutes, which on
    # CI looks like a job killed by a timeout rather than like a failed assert. One
    # linear pass over half the Telegram limit is ~0.2 s here, so the budget below
    # leaves an order of magnitude for a loaded shared runner and still trips on the
    # quadratic version, which needs seconds for this very first run.
    probe = _time_parse(parser, ('123 456 789 ' * 400)[:half])
    assert probe < 4.0, (
        f"a single parse of {half} characters took {probe:.2f} s — far past anything a "
        f"linear scan can cost, so the amount regex is backtracking again. Stopping here "
        f"instead of running the full scaling measurement, which would take minutes at "
        f"this speed")

    short = fastest_run(half)
    long = fastest_run(half * 2)
    ratio = long / short

    assert ratio < 3.0, (
        f"parsing time grew {ratio:.1f}x when the text doubled "
        f"({half} chars: {short:.3f} s, {half * 2} chars: {long:.3f} s) — "
        f"linear scanning grows ~2x, quadratic ~4x")

    # Kept as a second, deliberately loose backstop: the quadratic version needed
    # 20-33 s at this length, so this only fires on a genuine regression.
    assert long < 10.0, f"parsing {half * 2} characters took {long:.2f} s"


def test_text_longer_than_the_limit_is_not_parsed(parser):
    # The cap is a backstop for input that should not reach the parser at all
    # (a caption concatenated with something else, say). At the limit the text is
    # still parsed normally; one character over it, nothing is.
    tail = " 100 рублей"
    at_limit = "а" * (MAX_TEXT_LENGTH - len(tail)) + tail
    assert len(at_limit) == MAX_TEXT_LENGTH
    assert parser.find_currencies(at_limit) == [(100.0, "RUB", "100 рублей")]

    over_limit = "а" + at_limit
    with capture_logs("currency_parser", logging.WARNING) as logs:
        assert parser.find_currencies(over_limit) == []
    # The length is logged, the message text is not.
    assert str(len(over_limit)) in logs.output[0]
    assert "рублей" not in logs.output[0]


def test_unparseable_amounts_are_dropped_instead_of_becoming_zero(parser):
    """An amount the normaliser cannot make sense of must disappear, quietly.

    "1.000,000.5" matches the amount regex, and once the thousands dots are
    stripped "1000,0005" is left — not a number. float() raised straight out of
    find_currencies, the handler's blanket except swallowed it, and the WHOLE
    message was lost with it: other amounts included, and an inline query got no
    answer at all. The neighbouring branch of the same normaliser had the mirror
    problem — it answered 0.0, and a zero amount is what the formatter replies to
    with an insult.
    """
    # DEBUG, and nothing at INFO or above: parsing arbitrary chat text and finding
    # something unparseable is routine, not a service fault. At ERROR a single user
    # could fill the log by sending such strings in bulk, and the fragment of their
    # message that goes into the record would be written out at the default level.
    with capture_logs("currency_parser", logging.DEBUG) as captured:
        assert parser.find_currencies("1.000,000.5 евро") == []
    # Asserted on the record itself rather than by capturing at INFO and expecting
    # nothing: that raises the logger to INFO and swallows the very DEBUG record
    # being awaited.
    assert [record.levelname for record in captured.records] == ["DEBUG"]

    # Everything else in the message still gets converted.
    with capture_logs("currency_parser", logging.DEBUG):
        assert parser.find_currencies("1.000,000.5 евро и 100 долларов") == [
            (100.0, "USD", "100 долларов"),
        ]

    # Same shape, separators the other way round.
    with capture_logs("currency_parser", logging.DEBUG):
        assert parser.find_currencies("1.000.000,50 евро") == []

    # A genuine zero is not an unparseable amount and keeps behaving exactly as
    # before — the formatter's reply to it is covered in tests/formatter/test_jokes.py.
    assert parser.find_currencies("0 рублей") == [(0.0, "RUB", "0 рублей")]
    assert parser.find_currencies("0,00 долларов") == [(0.0, "USD", "0,00 долларов")]
    assert parser.find_currencies("0.5 USD") == [(0.5, "USD", "0.5 USD")]
