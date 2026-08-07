# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Number SHAPES — everything the amount half of a match may look like.

The currency word only says which currency it is; what is recognised as the amount
in front of it is the amount regex plus the normaliser that folds separators back
into a float. These tables cover both: thousands separators (space, comma, dot),
the decimal comma and the decimal dot, the "к" and "кило…" multipliers, cents and
eurocents, minus signs, and the arithmetic-looking input where only part of the
expression ends up in the match.
"""

import pytest


DECIMAL_SEPARATOR_CASES = [
    ("1.5 рублей", [(1.5, "RUB", "1.5 рублей")]),
    ("2,5 евро", [(2.5, "EUR", "2,5 евро")]),
    ("$3.14", [(3.14, "USD", "$3.14")]),
    ("10.50₽", [(10.50, "RUB", "10.50₽")]),
    ("4.5 рублей", [(4.5, 'RUB', "4.5 рублей")]),
    ("1.0 рублей", [(1.0, 'RUB', '1.0 рублей')]),
    ("0.001 фунта", [(0.001, 'GBP', '0.001 фунта')]),
    ("0.0015 рублей", [(0.0015, 'RUB', '0.0015 рублей')]),
    ("Вставить 0,05 ₽", [(0.05, 'RUB', '0,05 ₽')]),
    # A decimal comma
    ("0,015 фунтов", [(0.015, "GBP", "0,015 фунтов")]),
    ("0,015 долларов", [(0.015, "USD", "0,015 долларов")]),
    ("0,015 евро", [(0.015, "EUR", "0,015 евро")]),
    ("0,015 рублей", [(0.015, "RUB", "0,015 рублей")]),
    # ...and the same numbers with a decimal dot
    ("0.015 фунтов", [(0.015, "GBP", "0.015 фунтов")]),
    ("0.015 долларов", [(0.015, "USD", "0.015 долларов")]),
    # Comma and dot side by side
    ("1,5 фунтов", [(1.5, "GBP", "1,5 фунтов")]),
    ("1.5 фунтов", [(1.5, "GBP", "1.5 фунтов")]),
    # Very small numbers
    ("0,001 фунтов", [(0.001, "GBP", "0,001 фунтов")]),
    ("0,0001 долларов", [(0.0001, "USD", "0,0001 долларов")]),
    # Zeroes after the comma
    ("1,00 фунтов", [(1.0, "GBP", "1,00 фунтов")]),
    ("10,00 долларов", [(10.0, "USD", "10,00 долларов")]),
    # Zeroes before the comma
    ("0,5 фунтов", [(0.5, "GBP", "0,5 фунтов")]),
    ("0,25 долларов", [(0.25, "USD", "0,25 долларов")]),
]


THOUSANDS_SEPARATOR_CASES = [
    ("1,000 долларов", [(1000.0, "USD", "1,000 долларов")]),
    ("1 000 долларов", [(1000.0, "USD", "1 000 долларов")]),
    ("1 000,50 долларов", [(1000.50, "USD", "1 000,50 долларов")]),
    ("2.500,75 евро", [(2500.75, "EUR", "2.500,75 евро")]),
    ("3,000,000 йен", [(3000000.0, "JPY", "3,000,000 йен")]),
    ("1.000,50 евро", [(1000.50, "EUR", "1.000,50 евро")]),
    ("1,000.50 фунтов", [(1000.50, "GBP", "1,000.50 фунтов")]),
    ("1 000 000,50 рублей", [(1000000.50, "RUB", "1 000 000,50 рублей")]),
    ("3 412 928 ₪", [(3412928.0, 'ILS', "3 412 928 ₪")]),
    # A separator that is not a single space ends the number early.
    ("3 412  928 ₪", [(928.0, 'ILS', '928 ₪')]),
    ("3 412н 928 ₪", [(928.0, 'ILS', '928 ₪')]),
    ("3 412 н928 ₪", []),
    ("10000 рублей", [(10000.0, 'RUB', '10000 рублей')]),
    ("999999999999999999999999 фунтов",
     [(999999999999999999999999.0, "GBP", "999999999999999999999999 фунтов")]),
]


K_SUFFIX_CASES = [
    ("1к рублей", [(1000.0, "RUB", "1к рублей")]),
    ("1к долларов", [(1000.0, "USD", "1к долларов")]),
    ("1к евро", [(1000.0, "EUR", "1к евро")]),
    ("1к йен", [(1000.0, "JPY", "1к йен")]),
    ("1к юаней", [(1000.0, "CNY", "1к юаней")]),
    ("1к лари", [(1000.0, "GEL", "1к лари")]),
    ("1к динаров", [(1000.0, "RSD", "1к динаров")]),
    ("1к батов", [(1000.0, "THB", "1к батов")]),
    ("1к тенге", [(1000.0, "KZT", "1к тенге")]),
    ("1к тенгег", []),
    ("1к батова", []),
    ("2к баксов", [(2000.0, "USD", "2к баксов")]),
    ("1.5к EUR", [(1500.0, "EUR", "1.5к EUR")]),
    ("0.5к долларов", [(500.0, "USD", "0.5к долларов")]),
    ("1к$", [(1000.0, "USD", "1к$")]),
    ("2к₽", [(2000.0, "RUB", "2к₽")]),
    ("1.5к€", [(1500.0, "EUR", "1.5к€")]),
    ("отдал ему 1.5к€", [(1500.0, "EUR", "1.5к€")]),
]


# The latin "k" is not the cyrillic "к" suffix, and neither is an amount on its own.
LATIN_K_CASES = [
    ("k рублей", []),
    ("kрублей", []),
    ("k долларов", []),
    ("k евро", []),
    ("k йен", []),
    ("k юаней", []),
    ("k лари", []),
    ("k динаров", []),
    ("k батов", []),
    ("k тенге", []),
    ("k$", []),
    ("k€", []),
    ("k₽", []),
    ("$k", []),
    ("€k", []),
]


# "кило…" is part of the currency word, and it carries its own amount: without a
# number in front of it the amount is one thousand.
KILO_PREFIX_CASES = [
    ("100 килобаксов", [(100000.0, 'USD', '100 килобаксов')]),
    ("1 килобакс", [(1000.0, "USD", "1 килобакс")]),
    ("килобакс", [(1000.0, "USD", "килобакс")]),
    ("1 килоевро", [(1000.0, "EUR", "1 килоевро")]),
    ("килоевро", [(1000.0, "EUR", "килоевро")]),
    ("1 килорубль", [(1000.0, "RUB", "1 килорубль")]),
    ("20 килорублей", [(20000.0, "RUB", "20 килорублей")]),
    ("килорубль", [(1000.0, "RUB", "килорубль")]),
]


CENT_CASES = [
    ("50 центов", [(0.5, "USD", "50 центов")]),
    ("1 цент", [(0.01, "USD", "1 цент")]),
    ("2 цента", [(0.02, "USD", "2 цента")]),
    ("5 cents", [(0.05, "USD", "5 cents")]),
    ("1 cent", [(0.01, "USD", "1 cent")]),
    # Eurocents
    ("50 евроцентов", [(0.5, "EUR", "50 евроцентов")]),
    ("1 евроцент", [(0.01, "EUR", "1 евроцент")]),
    ("2 евроцента", [(0.02, "EUR", "2 евроцента")]),
    ("5 eurocents", [(0.05, "EUR", "5 eurocents")]),
    ("1 eurocent", [(0.01, "EUR", "1 eurocent")]),
    # The unit and its subunit in one message
    ("5 долларов 30 центов", [(5.0, "USD", "5 долларов"), (0.3, "USD", "30 центов")]),
    ("2 евро 15 евроцентов", [(2.0, "EUR", "2 евро"), (0.15, "EUR", "15 евроцентов")]),
    ("1 доллар 1 цент", [(1.0, "USD", "1 доллар"), (0.01, "USD", "1 цент")]),
    ("1 евро 1 евроцент", [(1.0, "EUR", "1 евро"), (0.01, "EUR", "1 евроцент")]),
    # Negative cases: unlike "килобакс", a bare subunit carries no implicit amount
    ("центов", []),
    ("евроцентов", []),
    ("k центов", []),
    ("k евроцентов", []),
    ("0 центов", [(0.0, "USD", "0 центов")]),
    ("0 евроцентов", [(0.0, "EUR", "0 евроцентов")]),
]


# The minus sign is not part of the amount: the bot converts the magnitude.
SIGN_AND_ZERO_CASES = [
    ("-5 рублей", [(5.0, "RUB", "5 рублей")]),
    ("-100 баксов", [(100.0, "USD", "100 баксов")]),
    ("0 рублей", [(0.0, "RUB", "0 рублей")]),
    ("0рублей", [(0.0, "RUB", "0рублей")]),
    ("-10 рублей", [(10.0, "RUB", "10 рублей")]),
    ("-1 рублей", [(1.0, "RUB", "1 рублей")]),
    ("-0 рублей", [(0.0, "RUB", "0 рублей")]),
    ("-0 сколько рублей", []),
    ("-0 сколько рублей и долларов", []),
    ("-100 фунтов", [(100.0, "GBP", "100 фунтов")]),
    ("-100000000000 фунтов", [(100000000000.0, "GBP", "100000000000 фунтов")]),
    ("-5 долларов", [(5.0, "USD", "5 долларов")]),
    ("минус 10 евро", [(10.0, "EUR", "10 евро")]),
]


# Arithmetic is not evaluated: what is recognised is the number that sits directly in
# front of the currency word, and nothing about the operator in front of it.
ARITHMETIC_CASES = [
    ("1.2.3 доллара", [(2.3, 'USD', '2.3 доллара')]),
    ("3^5 фунтов", []),
    ("3^5 квид", []),
    ("0x1999 фунтов", []),
    ("50e10 фунтов", []),
    ("5+5 долларов", [(5.0, "USD", "5 долларов")]),
    ("${7*7} долларов", []),
    ("1e10 рублей", []),
    ("4+5 рублей", [(5.0, 'RUB', "5 рублей")]),
    ("4-5 рублей", [(5.0, 'RUB', "5 рублей")]),
    ("4/5 рублей", [(5.0, 'RUB', "5 рублей")]),
    ("4*5 рублей", [(5.0, 'RUB', "5 рублей")]),
    ("4^5 рублей", []),
    ("4%5 рублей", []),
    ("4!5 рублей", [(5.0, 'RUB', "5 рублей")]),
    ("5! рублей", []),
    ("100-10 рублей", [(10.0, 'RUB', "10 рублей")]),
    ("100..50 долларов", [(50.0, 'USD', '50 долларов')]),
]


# A partial number in front of the currency word: what survives is the part of it the
# amount regex accepts, which is not always the part a human would read.
PARTIAL_NUMBER_CASES = [
    ("из долларов он получил 0. рублей тоже не получил", []),
    ("он получил 0.5 рублей, и долларов тоже", [(0.5, 'RUB', "0.5 рублей")]),
    ("он получил .5 рублей, и долларов тоже", [(5, 'RUB', "5 рублей")]),  # ???!!
    ("1. рубль", []),
    ("0. драм", []),
    ("1. Рублей", []),
    ("2. Долларов", []),
    ("100, долларов", []),
    ("4.5 в рублей", []),
    ("10:30 рублей", [(30.0, "RUB", "30 рублей")]),
    ("10:30 и дальше рублей", []),
    ("0.0 кг, 0.1 ₽,", [(0.1, 'RUB', '0.1 ₽')]),
]


# Only the number closest to the currency word is the amount.
NUMBER_BEFORE_THE_AMOUNT_CASES = [
    ("Пять 6 долларов", [(6.0, 'USD', '6 долларов')]),
    ("5 6 7 долларов", [(7.0, 'USD', '7 долларов')]),
    ("двадцать 2 рубля", [(2.0, 'RUB', '2 рубля')]),
]


# Letters glued to the digits: the amount has to start on a word boundary.
LETTERS_GLUED_TO_THE_AMOUNT_CASES = [
    ("он получил5 рублей, и долларов тоже", []),
    ("Один1 рублей", []),
    ("12345679x9 евро", []),
    ("1блять1 долларов", []),
    ("Ox5 долларов", []),
    ("Блять11 долларов", []),
]


@pytest.mark.parametrize("text,expected", DECIMAL_SEPARATOR_CASES)
def test_decimal_separators(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", THOUSANDS_SEPARATOR_CASES)
def test_thousands_separators(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", K_SUFFIX_CASES)
def test_k_suffix(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", LATIN_K_CASES)
def test_latin_k_is_not_an_amount(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", KILO_PREFIX_CASES)
def test_kilo_prefix(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", CENT_CASES)
def test_cents_and_eurocents(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", SIGN_AND_ZERO_CASES)
def test_negatives_and_zero(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", ARITHMETIC_CASES)
def test_arithmetic_looking_input(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", PARTIAL_NUMBER_CASES)
def test_partial_numbers(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", NUMBER_BEFORE_THE_AMOUNT_CASES)
def test_only_the_nearest_number_is_the_amount(parser, text, expected):
    assert parser.find_currencies(text) == expected


@pytest.mark.parametrize("text,expected", LETTERS_GLUED_TO_THE_AMOUNT_CASES)
def test_letters_glued_to_the_amount(parser, text, expected):
    assert parser.find_currencies(text) == expected
