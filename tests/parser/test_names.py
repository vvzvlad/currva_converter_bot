# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Currency NAMES — the hand-written word patterns, one table per currency.

Both the Russian declensions and the English/latin aliases the parser accepts, and,
right next to them, the rejections that pin down where each pattern stops
("0.2 незлотых", "0.2 кронтаб", "1 лвл"): a near-miss only means something next to
the word it is a near miss of.
"""

import pytest


AMD_CASES = [
    ("100 драм", [(100.0, "AMD", "100 драм")]),
    ("200 драма", [(200.0, "AMD", "200 драма")]),
    ("300 драмов", [(300.0, "AMD", "300 драмов")]),
]


ILS_CASES = [
    ("100 шекелей", [(100.0, "ILS", "100 шекелей")]),
    ("200 шекель", [(200.0, "ILS", "200 шекель")]),
    ("300 шекеля", [(300.0, "ILS", "300 шекеля")]),
    ("400 шек", [(400.0, "ILS", "400 шек")]),
    ("500 шах", [(500.0, "ILS", "500 шах")]),
    ("600 ils", [(600.0, "ILS", "600 ils")]),
    ("3 шекеля", [(3.0, 'ILS', '3 шекеля')]),
    # Neither the subunit nor an invented abbreviation is a name of the currency.
    ("50 нфс", []),
    ("50 агорот", []),
    ("50 огород", []),
]


GBP_CASES = [
    ("100 фунтов", [(100.0, "GBP", "100 фунтов")]),
    ("200 фунт", [(200.0, "GBP", "200 фунт")]),
    ("300 фунтов", [(300.0, "GBP", "300 фунтов")]),
    ("400 паунд", [(400.0, "GBP", "400 паунд")]),
    ("500 квидов", [(500.0, "GBP", "500 квидов")]),
    ("500 pound", [(500.0, "GBP", "500 pound")]),
    ("500 quid", [(500.0, "GBP", "500 quid")]),
    ("600 gbp", [(600.0, "GBP", "600 gbp")]),
    ("1 фунт", [(1.0, "GBP", "1 фунт")]),
    ("1 квид", [(1.0, "GBP", "1 квид")]),
    ("15 фунтов", [(15.0, "GBP", "15 фунтов")]),
    ("1488 фунтов", [(1488.0, "GBP", "1488 фунтов")]),
]


RUB_CASES = [
    ("100 рублей", [(100.0, "RUB", "100 рублей")]),
    ("200 рубль", [(200.0, "RUB", "200 рубль")]),
    ("300 рубля", [(300.0, "RUB", "300 рубля")]),
    ("400 rub", [(400.0, "RUB", "400 rub")]),
    ("1 рубль", [(1.0, "RUB", "1 рубль")]),
    # A letter glued to the end of the word is not the word.
    ("0.2 рубляб", []),
]


USD_CASES = [
    ("200 доллар", [(200.0, "USD", "200 доллар")]),
    # The name patterns are case-insensitive, in any mixture.
    ("200 Доллар", [(200.0, "USD", "200 Доллар")]),
    ("200 ДоллаР", [(200.0, "USD", "200 ДоллаР")]),
    ("200 доЛлаРов", [(200.0, "USD", "200 доЛлаРов")]),
    ("300 доллара", [(300.0, "USD", "300 доллара")]),
    ("400 баксов", [(400.0, "USD", "400 баксов")]),
    ("500 бакс", [(500.0, "USD", "500 бакс")]),
    ("600 usd", [(600.0, "USD", "600 usd")]),
    ("500 баксов", [(500.0, "USD", "500 баксов")]),
    ("600 долларов", [(600.0, "USD", "600 долларов")]),
    ("5 баксов", [(5.0, "USD", "5 баксов")]),
    # The country after the currency name is simply left out of the match.
    ("5 долларов США", [(5.0, 'USD', '5 долларов')]),
]


EUR_CASES = [
    ("100 евро", [(100.0, "EUR", "100 евро")]),
    ("200 eur", [(200.0, "EUR", "200 eur")]),
    ("300 EUR", [(300.0, "EUR", "300 EUR")]),
]


JPY_CASES = [
    ("100 йен", [(100.0, "JPY", "100 йен")]),
    ("200 йена", [(200.0, "JPY", "200 йена")]),
    ("300 йен", [(300.0, "JPY", "300 йен")]),
    ("400 jpy", [(400.0, "JPY", "400 jpy")]),
]


CNY_CASES = [
    ("100 юаней", [(100.0, "CNY", "100 юаней")]),
    ("200 юань", [(200.0, "CNY", "200 юань")]),
    ("300 юаня", [(300.0, "CNY", "300 юаня")]),
    ("400 cny", [(400.0, "CNY", "400 cny")]),
    ("10 юаней", [(10.0, "CNY", "10 юаней")]),
    ("500 юаней", [(500.0, "CNY", "500 юаней")]),
    ("200 cny", [(200.0, "CNY", "200 cny")]),
]


GEL_CASES = [
    ("100 лари", [(100.0, "GEL", "100 лари")]),
    ("200 gel", [(200.0, "GEL", "200 gel")]),
    ("1 лари", [(1.0, "GEL", "1 лари")]),
    ("1337 лари", [(1337.0, "GEL", "1337 лари")]),
]


RSD_CASES = [
    ("100 динаров", [(100.0, "RSD", "100 динаров")]),
    ("200 динар", [(200.0, "RSD", "200 динар")]),
    ("300 динаров", [(300.0, "RSD", "300 динаров")]),
    ("400 rsd", [(400.0, "RSD", "400 rsd")]),
    ("20 динар", [(20.0, 'RSD', "20 динар")]),
]


THB_CASES = [
    ("100 батов", [(100.0, "THB", "100 батов")]),
    ("200 бат", [(200.0, "THB", "200 бат")]),
    ("300 бата", [(300.0, "THB", "300 бата")]),
    ("400 thb", [(400.0, "THB", "400 thb")]),
]


KZT_CASES = [
    ("100 тенге", [(100.0, "KZT", "100 тенге")]),
    ("200 тг", [(200.0, "KZT", "200 тг")]),
    ("300 kzt", [(300.0, "KZT", "300 kzt")]),
]


CAD_CASES = [
    ("127 канадских долларов", [(127.0, "CAD", "127 канадских долларов")]),
    ("127 cad", [(127.0, "CAD", "127 cad")]),
    ("127 CAD", [(127.0, "CAD", "127 CAD")]),
    ("100500 CAD вышло", [(100500.0, 'CAD', '100500 CAD')]),
]


KRW_CASES = [
    ("100 вон", [(100.0, "KRW", "100 вон")]),
    ("200 вона", [(200.0, "KRW", "200 вона")]),
    ("300 воны", [(300.0, "KRW", "300 воны")]),
    ("400 krw", [(400.0, "KRW", "400 krw")]),
]


TRY_CASES = [
    ("0.2 лиры", [(0.2, "TRY", "0.2 лиры")]),
    ("0.2 лир", [(0.2, "TRY", "0.2 лир")]),
    ("0.2 турецкой лиры", [(0.2, "TRY", "0.2 турецкой лиры")]),
]


PLN_CASES = [
    ("0.2 злотых", [(0.2, "PLN", "0.2 злотых")]),
    ("1 злотый", [(1.0, "PLN", "1 злотый")]),
    ("0.2 незлотых", []),
]


CZK_CASES = [
    ("0.2 крон", [(0.2, "CZK", "0.2 крон")]),
    ("0.2 чешских крон", [(0.2, "CZK", "0.2 чешских крон")]),
    ("1 чешская крона", [(1.0, "CZK", "1 чешская крона")]),
    ("0.2 нечешских крон", []),
    ("0.2 кронтаб", []),
]


BYN_CASES = [
    ("0.2 белорусских рублей", [(0.2, "BYN", "0.2 белорусских рублей")]),
    ("1 белорусский рубль", [(1.0, "BYN", "1 белорусский рубль")]),
    ("0.2 небелорусских рублей", []),
]


UAH_CASES = [
    ("0.2 гривны", [(0.2, "UAH", "0.2 гривны")]),
    ("0.2 гривна", [(0.2, "UAH", "0.2 гривна")]),
    ("0.2 негривен", []),
]


VND_CASES = [
    ("0.2 донга", [(0.2, "VND", "0.2 донга")]),
    ("0.2 недонгов", []),
]


AED_CASES = [
    ("100 дирхам", [(100.0, "AED", "100 дирхам")]),
    ("2 дирхама", [(2.0, "AED", "2 дирхама")]),
    ("5 дирхамов", [(5.0, "AED", "5 дирхамов")]),
    ("0.2 недирхамов", []),
]


RON_CASES = [
    ("1 румынский лей", [(1.0, "RON", "1 румынский лей")]),
    ("2 румынских лея", [(2.0, "RON", "2 румынских лея")]),
    ("0.2 нерумынских лей", []),
    ("1 рон", [(1.0, "RON", "1 рон")]),
    ("2 рона", [(2.0, "RON", "2 рона")]),
    ("10 ронов", [(10.0, "RON", "10 ронов")]),
    ("0.2 неронов", []),
]


MDL_CASES = [
    ("1 молдавский лей", [(1.0, "MDL", "1 молдавский лей")]),
    ("2 молдавских лея", [(2.0, "MDL", "2 молдавских лея")]),
    ("5 молдавских леев", [(5.0, "MDL", "5 молдавских леев")]),
    ("0.2 немолдавских леев", []),
    # Without the country word the bare "лей" still belongs to MDL, not to RON.
    ("1 лей", [(1.0, "MDL", "1 лей")]),
    ("2 лея", [(2.0, "MDL", "2 лея")]),
    ("5 леев", [(5.0, "MDL", "5 леев")]),
]


BGN_CASES = [
    ("1 лев", [(1.0, "BGN", "1 лев")]),
    ("2 лева", [(2.0, "BGN", "2 лева")]),
    ("5 левов", [(5.0, "BGN", "5 левов")]),
    ("0.2 нелевов", []),
    ("1 болгарский лев", [(1.0, "BGN", "1 болгарский лев")]),
    ("2 болгарских лева", [(2.0, "BGN", "2 болгарских лева")]),
    ("5 болгарских левов", [(5.0, "BGN", "5 болгарских левов")]),
    ("0.2 неболгарских левов", []),
    ("1 лв", [(1.0, "BGN", "1 лв")]),
    ("1 лвл", []),
]


TJS_CASES = [
    ("100 сомони", [(100.0, "TJS", "100 сомони")]),
    ("200 tjs", [(200.0, "TJS", "200 tjs")]),
    ("300 TJS", [(300.0, "TJS", "300 TJS")]),
]


# Uzbekistani so'm: both spellings, "сум" and "сом", map to UZS.
UZS_CASES = [
    ("100 сум", [(100.0, "UZS", "100 сум")]),
    ("2 сума", [(2.0, "UZS", "2 сума")]),
    ("5 сумов", [(5.0, "UZS", "5 сумов")]),
    ("1 сом", [(1.0, "UZS", "1 сом")]),
    ("2 сома", [(2.0, "UZS", "2 сома")]),
    ("5 сомов", [(5.0, "UZS", "5 сомов")]),
    ("300 uzs", [(300.0, "UZS", "300 uzs")]),
    ("300 UZS", [(300.0, "UZS", "300 UZS")]),
]


MXN_CASES = [
    ("0.2 MXN", [(0.2, "MXN", "0.2 MXN")]),
    ("0.2MXN", [(0.2, "MXN", "0.2MXN")]),
    ("0.2 мексиканского песо", [(0.2, "MXN", "0.2 мексиканского песо")]),
    ("0.2 песо", [(0.2, "MXN", "0.2 песо")]),
    ("100 песо", [(100.0, "MXN", "100 песо")]),
    ("200 мексиканских песо", [(200.0, "MXN", "200 мексиканских песо")]),
    ("300 mxn", [(300.0, "MXN", "300 mxn")]),
    ("1 мексиканское песо", [(1.0, "MXN", "1 мексиканское песо")]),
    ("0.5 песо", [(0.5, "MXN", "0.5 песо")]),
    ("1,000 песо", [(1000.0, "MXN", "1,000 песо")]),
]


PHP_CASES = [
    ("100 филиппинских песо", [(100.0, "PHP", "100 филиппинских песо")]),
    ("200 piso", [(200.0, "PHP", "200 piso")]),
    ("300 php", [(300.0, "PHP", "300 php")]),
    ("1 филиппинское песо", [(1.0, "PHP", "1 филиппинское песо")]),
    ("0.5 piso", [(0.5, "PHP", "0.5 piso")]),
    ("1,000 piso", [(1000.0, "PHP", "1,000 piso")]),
]


ARS_CASES = [
    ("100 аргентинских песо", [(100.0, "ARS", "100 аргентинских песо")]),
    ("1 аргентинское песо", [(1.0, "ARS", "1 аргентинское песо")]),
    ("300 ars", [(300.0, "ARS", "300 ars")]),
    ("300 ARS", [(300.0, "ARS", "300 ARS")]),
    # Negative: without the country word the peso stays MXN.
    ("50 песо", [(50.0, "MXN", "50 песо")]),
]


@pytest.mark.parametrize("text,expected", AMD_CASES)
def test_amd(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", ILS_CASES)
def test_ils(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", GBP_CASES)
def test_gbp(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", RUB_CASES)
def test_rub(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", USD_CASES)
def test_usd(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", EUR_CASES)
def test_eur(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", JPY_CASES)
def test_jpy(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", CNY_CASES)
def test_cny(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", GEL_CASES)
def test_gel(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", RSD_CASES)
def test_rsd(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", THB_CASES)
def test_thb(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", KZT_CASES)
def test_kzt(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", CAD_CASES)
def test_cad(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", KRW_CASES)
def test_krw(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", TRY_CASES)
def test_try(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", PLN_CASES)
def test_pln(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", CZK_CASES)
def test_czk(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", BYN_CASES)
def test_byn(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", UAH_CASES)
def test_uah(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", VND_CASES)
def test_vnd(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", AED_CASES)
def test_aed(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", RON_CASES)
def test_ron(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", MDL_CASES)
def test_mdl(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", BGN_CASES)
def test_bgn(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", TJS_CASES)
def test_tjs(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", UZS_CASES)
def test_uzs(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", MXN_CASES)
def test_mxn(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", PHP_CASES)
def test_php(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", ARS_CASES)
def test_ars(parser, text, expected):
    assert parser.find_currencies(text) == expected
