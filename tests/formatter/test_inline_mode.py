# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""mode='inline': the answer offered in Telegram's inline mode.

Same conversions as the chat mode, different wrapping — and none of the canned
jokes, which only fire on mode='chat'.
"""

import pytest


# (input text, expected inline answer). All rates are 1.0 — see the `unit_rates`
# fixture.
INLINE_CONVERSIONS = [
    # Baseline
    (
        "100 долларов",
        "100 долларов (🇷🇺 100 ₽, 🇮🇱 100 ₪, 🇪🇺 100 €, 🇬🇧 £100, 🇯🇵 ¥100, 🇦🇲 100 ֏)",
    ),
    (
        "100 фунтов",
        "100 фунтов (45.4 кг) (🇷🇺 100 ₽, 🇺🇸 $100, 🇮🇱 100 ₪, 🇪🇺 100 €, 🇯🇵 ¥100, 🇦🇲 100 ֏)",
    ),
    # Special cases: the amounts that get a canned reply in chat mode are plain
    # conversions here.
    (
        "0 долларов",
        "0 долларов (🇷🇺 0 ₽, 🇮🇱 0 ₪, 🇪🇺 0 €, 🇬🇧 £0, 🇯🇵 ¥0, 🇦🇲 0 ֏)",
    ),
    (
        "0.5 USD",
        "0.5 USD (🇷🇺 0.5 ₽, 🇮🇱 0.5 ₪, 🇪🇺 0.5 €, 🇬🇧 £0.5, 🇯🇵 ¥0.5, 🇦🇲 0.5 ֏)",
    ),
    (
        "2000000 долларов",
        "2000000 долларов (🇷🇺 2 000 000 ₽, 🇮🇱 2 000 000 ₪, 🇪🇺 2 000 000 €, 🇬🇧 £2 000 000, 🇯🇵 ¥2 000 000, 🇦🇲 2 000 000 ֏)",
    ),
    # todo: support a formatter test that checks the final rewritten message
    # ("я нажрался на 100 долларов в хламину",
    #  "я нажрался на 100 долларов (🇪🇺 €100, 🇬🇧 £100, 🇷🇺 100 ₽, 🇮🇱 100 ₪, 🇯🇵 100 ¥, 🇦🇲 100 ֏) в хламину"),
    # Several currencies in one text — one line per amount.
    # An explicit id, because the expected value spans two lines: this file's ids go
    # into the node id verbatim (pytest.ini turns id escaping off so the Russian text
    # stays readable), and a node id with a newline in it cannot be passed to -k or to
    # a shell, and --junitxml would fold the newline into a space so the reported name
    # would no longer match the real one.
    pytest.param(
        "100 долларов и 200 евро",
        "100 долларов (🇷🇺 100 ₽, 🇮🇱 100 ₪, 🇪🇺 100 €, 🇬🇧 £100, 🇯🇵 ¥100, 🇦🇲 100 ֏)\n"
        "200 евро (🇷🇺 200 ₽, 🇺🇸 $200, 🇮🇱 200 ₪, 🇬🇧 £200, 🇯🇵 ¥200, 🇦🇲 200 ֏)",
        id="two-amounts-two-lines",
    ),
    # Pounds, with the conversion to kilograms.
    (
        "1 фунт",
        "1 фунт (0.5 кг) (🇷🇺 1 ₽, 🇺🇸 $1, 🇮🇱 1 ₪, 🇪🇺 1 €, 🇯🇵 ¥1, 🇦🇲 1 ֏)",
    ),
    # Large numbers: thousands are space-separated only ABOVE 10000.
    (
        "30000 долларов",
        "30000 долларов (🇷🇺 30 000 ₽, 🇮🇱 30 000 ₪, 🇪🇺 30 000 €, 🇬🇧 £30 000, 🇯🇵 ¥30 000, 🇦🇲 30 000 ֏)",
    ),
    (
        "10000 долларов",
        "10000 долларов (🇷🇺 10000 ₽, 🇮🇱 10000 ₪, 🇪🇺 10000 €, 🇬🇧 £10000, 🇯🇵 ¥10000, 🇦🇲 10000 ֏)",
    ),
    # Decimals.
    (
        "12.34 евро",
        "12.34 евро (🇷🇺 12.3 ₽, 🇺🇸 $12.3, 🇮🇱 12.3 ₪, 🇬🇧 £12.3, 🇯🇵 ¥12.3, 🇦🇲 12.3 ֏)",
    ),
]


@pytest.mark.parametrize("text, expected", INLINE_CONVERSIONS)
def test_inline_answer(parser, formatter, unit_rates, text, expected):
    currency_list = parser.find_currencies(text)
    assert formatter.format_multiple_conversions(currency_list, unit_rates, mode='inline') == expected
