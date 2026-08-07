# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Several amounts in one message.

Every pattern is run over the whole text on its own, so one amount can be found by
more than one of them; the overlap filter then sorts the matches by position and
keeps, of any two that overlap, only the one that starts first. What a caller gets
is therefore an ordered, non-overlapping list — the order of the amounts in the
message, which is what these expectations spell out. The same properties are checked
as invariants over a corpus in test_positions.py.
"""

import pytest


SEVERAL_AMOUNTS_CASES = [
    ("1к$ и 2к₽", [(1000.0, "USD", "1к$"), (2000.0, "RUB", "2к₽")]),
    ("перевел 1к$ получил 2к₽", [(1000.0, "USD", "1к$"), (2000.0, "RUB", "2к₽")]),
    ("Перевел 1к$ и 2к₽", [(1000.0, "USD", "1к$"), (2000.0, "RUB", "2к₽")]),
    ("Купил за 100 баксов и 200 рублей",
     [(100.0, "USD", "100 баксов"), (200.0, "RUB", "200 рублей")]),
    ("€100 и 200₽ и $300",
     [(100.0, "EUR", "€100"), (200.0, "RUB", "200₽"), (300.0, "USD", "$300")]),
    ("10 рублей + 20 фунтов", [(10.0, "RUB", "10 рублей"), (20.0, "GBP", "20 фунтов")]),
    ("99 фунтов и 100 долларов",
     [(99.0, "GBP", "99 фунтов"), (100.0, "USD", "100 долларов")]),
    # Twice the same currency is twice a match.
    ("10 рублей + 1 рубль", [(10.0, "RUB", "10 рублей"), (1.0, "RUB", "1 рубль")]),
    ("1 лари 100 рублей 2 доллара",
     [(1.0, "GEL", "1 лари"), (100.0, "RUB", "100 рублей"), (2.0, "USD", "2 доллара")]),
]


@pytest.mark.parametrize("text,expected", SEVERAL_AMOUNTS_CASES)
def test_several_amounts_in_one_text(parser, text, expected):
    assert parser.find_currencies(text) == expected
