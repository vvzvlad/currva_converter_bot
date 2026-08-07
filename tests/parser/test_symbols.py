# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Currency SYMBOLS — one table per symbol family.

Both positions are covered where the parser supports them: the symbol glued to the
digits, separated from them by a space, and — for $, €, £, ¥, ₩, ₱ — in front of the
amount. A prefix symbol has to touch the digits ("£ 800" is not a match), which is
the asymmetry these tables exist to pin down.
"""

import pytest


ILS_SYMBOL_CASES = [
    ("700₪", [(700.0, "ILS", "700₪")]),
    ("700 ₪", [(700.0, "ILS", "700 ₪")]),
    ("462 ₪", [(462.0, "ILS", "462 ₪")]),
    ("462₪", [(462.0, "ILS", "462₪")]),
    ("1.4 ₪", [(1.4, "ILS", "1.4 ₪")]),
    ("1.4₪", [(1.4, "ILS", "1.4₪")]),
    ("231 ₪", [(231.0, "ILS", "231 ₪")]),
    ("231₪", [(231.0, "ILS", "231₪")]),
    ("0.9 ₪", [(0.9, "ILS", "0.9 ₪")]),
    ("0.9₪", [(0.9, "ILS", "0.9₪")]),
    ("200₪", [(200.0, "ILS", "200₪")]),
    # The symbol on its own, with no amount in front of it, is not a match.
    ("Бля ₪", []),
]


USD_SYMBOL_CASES = [
    ("700$", [(700.0, "USD", "700$")]),
    ("$800", [(800.0, "USD", "$800")]),
    ("$200", [(200.0, "USD", "$200")]),
    ("300$", [(300.0, "USD", "300$")]),
    ("127 $", [(127.0, "USD", "127 $")]),
    ("127$", [(127.0, "USD", "127$")]),
    ("8.2 $", [(8.2, "USD", "8.2 $")]),
    ("8.2$", [(8.2, "USD", "8.2$")]),
    ("38 $", [(38.0, "USD", "38 $")]),
    ("38$", [(38.0, "USD", "38$")]),
    ("63 $", [(63.0, "USD", "63 $")]),
    ("63$", [(63.0, "USD", "63$")]),
    ("0.4 $", [(0.4, "USD", "0.4 $")]),
    ("0.4$", [(0.4, "USD", "0.4$")]),
    ("0.3 $", [(0.3, "USD", "0.3 $")]),
    ("0.3$", [(0.3, "USD", "0.3$")]),
    # A second symbol is not part of the match.
    ("500$$", [(500.0, 'USD', '500$')]),
]


RUB_SYMBOL_CASES = [
    ("500₽", [(500.0, "RUB", "500₽")]),
    ("500 ₽", [(500.0, "RUB", "500 ₽")]),
    ("400₽", [(400.0, "RUB", "400₽")]),
    ("13675 ₽", [(13675.0, 'RUB', "13675 ₽")]),
    ("13675₽", [(13675.0, 'RUB', "13675₽")]),
    ("888 ₽", [(888.0, "RUB", "888 ₽")]),
    ("888₽", [(888.0, "RUB", "888₽")]),
    ("6838 ₽", [(6838.0, "RUB", "6838 ₽")]),
    ("6838₽", [(6838.0, "RUB", "6838₽")]),
    ("26 ₽", [(26.0, "RUB", "26 ₽")]),
    ("26₽", [(26.0, "RUB", "26₽")]),
    # Only a space (or nothing) may sit between the amount and the symbol.
    (r"500\₽", []),
    (r"\500", []),
    ("500'₽", []),
    ("500,₽", []),
    ("500.₽", []),
    ("500;₽", []),
    ("500:₽", []),
    # A foreign symbol right after the matched one is not part of the match.
    ("500₽$", [(500.0, "RUB", "500₽")]),
]


EUR_SYMBOL_CASES = [
    ("300€", [(300.0, "EUR", "300€")]),
    ("€400", [(400.0, "EUR", "€400")]),
    ("120 €", [(120.0, "EUR", "120 €")]),
    ("120€", [(120.0, "EUR", "120€")]),
    ("7.8 €", [(7.8, "EUR", "7.8 €")]),
    ("7.8€", [(7.8, "EUR", "7.8€")]),
    ("36 €", [(36.0, "EUR", "36 €")]),
    ("36€", [(36.0, "EUR", "36€")]),
    ("60 €", [(60.0, "EUR", "60 €")]),
    ("60€", [(60.0, "EUR", "60€")]),
    ("0.4 €", [(0.4, "EUR", "0.4 €")]),
    ("0.4€", [(0.4, "EUR", "0.4€")]),
    ("0.2 €", [(0.2, "EUR", "0.2 €")]),
    ("0.2€", [(0.2, "EUR", "0.2€")]),
]


GBP_SYMBOL_CASES = [
    ("700£", [(700.0, "GBP", "700£")]),
    ("£800", [(800.0, "GBP", "£800")]),
    ("700 £", [(700.0, "GBP", "700 £")]),
    # A space after the prefix symbol is not a match.
    ("£ 800", []),
    ("6.5 £", [(6.5, "GBP", "6.5 £")]),
    ("6.5£", [(6.5, "GBP", "6.5£")]),
    ("0.3 £", [(0.3, "GBP", "0.3 £")]),
    ("0.3£", [(0.3, "GBP", "0.3£")]),
    ("0.2 £", [(0.2, "GBP", "0.2 £")]),
    ("0.2£", [(0.2, "GBP", "0.2£")]),
]


JPY_SYMBOL_CASES = [
    ("500¥", [(500.0, "JPY", "500¥")]),
    ("¥1000", [(1000.0, "JPY", "¥1000")]),
    ("1000¥", [(1000.0, "JPY", "1000¥")]),
]


KRW_SYMBOL_CASES = [
    ("500₩", [(500.0, "KRW", "500₩")]),
    ("₩600", [(600.0, "KRW", "₩600")]),
    ("700 ₩", [(700.0, "KRW", "700 ₩")]),
]


TRY_SYMBOL_CASES = [
    ("0.2 ₤", [(0.2, "TRY", "0.2 ₤")]),
    ("0.2₤", [(0.2, "TRY", "0.2₤")]),
]


PLN_SYMBOL_CASES = [
    ("0.2 zł", [(0.2, "PLN", "0.2 zł")]),
    ("0.2zł", [(0.2, "PLN", "0.2zł")]),
]


CZK_SYMBOL_CASES = [
    ("0.2 Kč", [(0.2, "CZK", "0.2 Kč")]),
    ("0.2Kč", [(0.2, "CZK", "0.2Kč")]),
]


BYN_SYMBOL_CASES = [
    ("0.2 Br", [(0.2, "BYN", "0.2 Br")]),
    ("0.2Br", [(0.2, "BYN", "0.2Br")]),
]


UAH_SYMBOL_CASES = [
    ("0.2 ₴", [(0.2, "UAH", "0.2 ₴")]),
    ("0.2₴", [(0.2, "UAH", "0.2₴")]),
]


VND_SYMBOL_CASES = [
    ("0.2 ₫", [(0.2, "VND", "0.2 ₫")]),
    ("0.2₫", [(0.2, "VND", "0.2₫")]),
]


PHP_SYMBOL_CASES = [
    ("400₱", [(400.0, "PHP", "400₱")]),
    ("₱500", [(500.0, "PHP", "₱500")]),
]


AED_SYMBOL_CASES = [
    ("1 dh", [(1.0, "AED", "1 dh")]),
    ("2 dh", [(2.0, "AED", "2 dh")]),
    ("5 dh", [(5.0, "AED", "5 dh")]),
    # A letter glued to "dh" is not the symbol.
    ("0.2 ndh", []),
    ("1 د.إ", [(1.0, "AED", "1 د.إ")]),
    ("2 د.إ", [(2.0, "AED", "2 د.إ")]),
    ("5 د.إ", [(5.0, "AED", "5 د.إ")]),
]


@pytest.mark.parametrize("text,expected", ILS_SYMBOL_CASES)
def test_ils_symbol(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", USD_SYMBOL_CASES)
def test_usd_symbol(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", RUB_SYMBOL_CASES)
def test_rub_symbol(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", EUR_SYMBOL_CASES)
def test_eur_symbol(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", GBP_SYMBOL_CASES)
def test_gbp_symbol(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", JPY_SYMBOL_CASES)
def test_jpy_symbol(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", KRW_SYMBOL_CASES)
def test_krw_symbol(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", TRY_SYMBOL_CASES)
def test_try_symbol(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", PLN_SYMBOL_CASES)
def test_pln_symbol(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", CZK_SYMBOL_CASES)
def test_czk_symbol(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", BYN_SYMBOL_CASES)
def test_byn_symbol(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", UAH_SYMBOL_CASES)
def test_uah_symbol(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", VND_SYMBOL_CASES)
def test_vnd_symbol(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", PHP_SYMBOL_CASES)
def test_php_symbol(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", AED_SYMBOL_CASES)
def test_aed_symbol(parser, text, expected):
    assert parser.find_currencies(text) == expected
