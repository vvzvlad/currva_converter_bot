# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

import unittest

from src.currencies import CURRENCIES
from src.currency_formatter import MAX_LISTED_CONVERSIONS, CurrencyFormatter

from tests.stubs import StubCurrencyParser, StubExchangeRatesManager


class TestCurrencyFormatting(unittest.TestCase):
    def setUp(self):
        self.parser = StubCurrencyParser()
        self.formatter = CurrencyFormatter()
        self.rates_manager = StubExchangeRatesManager()
        self.rates = {}
        for curr in CURRENCIES.keys():
            for target in CURRENCIES.keys():
                if curr != target:
                    self.rates[f"{curr}_{target}"] = self.rates_manager.get_rate(curr, target)

    def test_formatter(self):
        def test(input_text: str, expected_output: str):
            currency_list = self.parser.find_currencies(input_text)
            result = self.formatter.format_multiple_conversions(currency_list, self.rates, mode='chat')
            self.assertEqual(result, expected_output)

        test("100 долларов", "100 долларов (🇺🇸) это 🇷🇺 100 ₽, 🇮🇱 100 ₪, 🇪🇺 100 €, 🇬🇧 £100, 🇯🇵 ¥100, 🇦🇲 100 ֏")
        test("100 фунтов", "100 фунтов (🇬🇧) это 45.4 кг, а также 🇷🇺 100 ₽, 🇺🇸 $100, 🇮🇱 100 ₪, 🇪🇺 100 €, 🇯🇵 ¥100, 🇦🇲 100 ֏")
        test("0 рублей", "Нахуй иди")
        test("0 динаров", "Нахуй иди")
        test("k динаров", None)
        test("k долларов", None)
        test("k евро", None)
        test("k йен", None)
        test("k юаней", None)
        test("k лари", None)
        test("k батов", None)
        test("k тенге", None)
        test(" 5 пять минут пять минут долларов", None)
        test("2000000 долларов", "Откуда у тебя такие деньги, сынок?")
        test("Ноль ноль долларов", None)
        test("Пять минус пять долларов", None)
        test("Восемь восемьсот пять пять пять три пять три пять рублей", None)
        test("Один один доллар", None)
        test("1 bdsm", None)
        test("1 килограмм рублей", None)
        test("1 TON", None)
        test("дюжина рублей", None)
        test("Сво рублей", None)
        test("Да бля а как работает сто сто рублей", None)
        test("6 пять долларов", None)
        test("13\" рублей", None)
        test("Десятнадцать рублей", None)
        test("миллиард долларов", None)
        test("Додекалион рублей", None)
        test("ёёёёё23322ёёёё драм", None)
        test("Один четыре восемь восемь продавать рублей не бросим", None)
        test("ёдесять рублей", None)
        test("тридцатьё лари", None)
        test("Двeсти рyблей", None)
        test("Двести') exit() рублей", None)
        test("Двести рублей') exit() рублей", None)
        test("Две тысячи двести <script>alert()</script> двадцать два рубля", None)
        test("две тысячи ХУËВ ТЕБЕ В ЖОПУ двадцать восемь фунтов", None)
        test("Пять сто пять восемь рублей", None)
        test("Пять сто пять восемь", None)
        test("Две тысячи ПОШЕЛ НА ХУЙ двести двадцать два рубля", None)
        test("Сто блядских рублей", None)
        test("Пять пять рублей", None)
        test("что рублей где", None)
        test("Две тысячи бля двести двадцать два рубля", None)
        test("Сто сто рублей", None)
        test("Две тысячи двести двадцать два рубля", None)
        test("Арубля", None)
        test("1Арубля", None)
        test("10 Арубля", None)
        test("Влад скинь долларов пабрацки", None)
        test("2 бля", None)
        test("Влад скинь длооаров пабрацки", None)
        test("Пица рублей", None)
        test("пицот рублей", None)
        test("``5+5`` долларов", None)
        test("Звоните мне на +79936969420", None)
        test("у меня когда-то в Додо был пин-код 1488, чтобы додорубли списывать", None)
        test("100500 кгам", None)
        test("1488 хуёв", None)
        test("сто тысяч миллионов зимбабвийских долларов", None)
        test("сто фунтов хуев тебе в панамку", None)
        test("два фунта мяса", None)
        test("100 т", None)
        test("я вам расскажу историю про 1488, но писать мне лень, поэтому будет войс мессадж ебать", None)
        test("50 юсд", None)
        test("Пять фунтов долларов", None)
        test("Сука где, фунты есть же", None)
        test("100 камней", None)
        test("Сто фунтов", None)
        test("Я хочу доллар по рублю", None)
        test("Хотя нахер мне доллар)", None)
        test("Могу продать рубль по доллару", None)
        test("Суки скинулись по рублю и разбежались", None)
        test("¾ рублей", None)
        test("Deployed vm nillion-cxs6v0lt in 'dosage' (took 26 min 8 sec, vm 145 out of 301 in batch, left 156 nodes", None)
        test("50 cents", "In Da Club!")
        test("0.5 USD", "In Da Club!")
        test("Привет, как дела?", None)

    def test_inline_formatter(self):
        def test(input_text: str, expected_output: str):
            currency_list = self.parser.find_currencies(input_text)
            result = self.formatter.format_multiple_conversions(currency_list, self.rates, mode='inline')
            self.assertEqual(result, expected_output)

        # Базовые тесты для inline режима
        test("100 долларов", "100 долларов (🇷🇺 100 ₽, 🇮🇱 100 ₪, 🇪🇺 100 €, 🇬🇧 £100, 🇯🇵 ¥100, 🇦🇲 100 ֏)")
        test("100 фунтов", "100 фунтов (45.4 кг) (🇷🇺 100 ₽, 🇺🇸 $100, 🇮🇱 100 ₪, 🇪🇺 100 €, 🇯🇵 ¥100, 🇦🇲 100 ֏)")
        
        # Тесты для специальных случаев
        test("0 долларов", "0 долларов (🇷🇺 0 ₽, 🇮🇱 0 ₪, 🇪🇺 0 €, 🇬🇧 £0, 🇯🇵 ¥0, 🇦🇲 0 ֏)")
        test("0.5 USD", "0.5 USD (🇷🇺 0.5 ₽, 🇮🇱 0.5 ₪, 🇪🇺 0.5 €, 🇬🇧 £0.5, 🇯🇵 ¥0.5, 🇦🇲 0.5 ֏)")
        test("2000000 долларов", "2000000 долларов (🇷🇺 2 000 000 ₽, 🇮🇱 2 000 000 ₪, 🇪🇺 2 000 000 €, 🇬🇧 £2 000 000, 🇯🇵 ¥2 000 000, 🇦🇲 2 000 000 ֏)")
        
        #todo поддержать тест форматтера для проверки итогового сообщения
        #test("я нажрался на 100 долларов в хламину", "я нажрался на 100 долларов (🇪🇺 €100, 🇬🇧 £100, 🇷🇺 100 ₽, 🇮🇱 100 ₪, 🇯🇵 100 ¥, 🇦🇲 100 ֏) в хламину")
        # Тест для множественных валют
        test("100 долларов и 200 евро", 
                "100 долларов (🇷🇺 100 ₽, 🇮🇱 100 ₪, 🇪🇺 100 €, 🇬🇧 £100, 🇯🇵 ¥100, 🇦🇲 100 ֏)\n" + 
                "200 евро (🇷🇺 200 ₽, 🇺🇸 $200, 🇮🇱 200 ₪, 🇬🇧 £200, 🇯🇵 ¥200, 🇦🇲 200 ֏)") 
        
        # Тест для фунтов (с конвертацией в кг)
        test("1 фунт", "1 фунт (0.5 кг) (🇷🇺 1 ₽, 🇺🇸 $1, 🇮🇱 1 ₪, 🇪🇺 1 €, 🇯🇵 ¥1, 🇦🇲 1 ֏)")
        
        # Тест для форматирования больших чисел
        test("30000 долларов", "30000 долларов (🇷🇺 30 000 ₽, 🇮🇱 30 000 ₪, 🇪🇺 30 000 €, 🇬🇧 £30 000, 🇯🇵 ¥30 000, 🇦🇲 30 000 ֏)")
        test("10000 долларов", "10000 долларов (🇷🇺 10000 ₽, 🇮🇱 10000 ₪, 🇪🇺 10000 €, 🇬🇧 £10000, 🇯🇵 ¥10000, 🇦🇲 10000 ֏)")

        # Тест для десятичных чисел
        test("12.34 евро", "12.34 евро (🇷🇺 12.3 ₽, 🇺🇸 $12.3, 🇮🇱 12.3 ₪, 🇬🇧 £12.3, 🇯🇵 ¥12.3, 🇦🇲 12.3 ֏)")
        
        # Тест для отсутствия курсов конвертации
        def test_no_rates(self):
            currency_list = self.parser.find_currencies("100 долларов")
            result = self.formatter.format_multiple_conversions(currency_list, {}, mode='inline')
            self.assertEqual(result, "100 долларов (нет доступных курсов конвертации)")


class TestMillionaireJoke(unittest.TestCase):
    """The "Откуда у тебя такие деньги, сынок?" threshold is in DOLLARS.

    Without a `{currency}_USD` rate the dollar amount stayed equal to the amount in
    the source currency, so the threshold was applied to the raw number: 5 000 000
    драм (about 12 000 USD) got the punchline instead of a conversion.
    """

    def setUp(self):
        self.formatter = CurrencyFormatter()

    def test_big_amount_without_a_usd_rate_is_converted_normally(self):
        rates = {"AMD_RUB": 0.24}
        result = self.formatter.format_conversion((5_000_000, "AMD", "5 000 000 драм"), rates, mode='chat')
        self.assertNotIn("Откуда", result)
        self.assertIn("₽", result)

    def test_big_amount_that_is_small_in_dollars_is_converted_normally(self):
        rates = {"AMD_USD": 0.0026, "AMD_RUB": 0.24}
        result = self.formatter.format_conversion((5_000_000, "AMD", "5 000 000 драм"), rates, mode='chat')
        self.assertNotIn("Откуда", result)

    def test_the_joke_still_fires_when_the_amount_really_is_a_million_dollars(self):
        rates = {"AMD_USD": 0.0026, "AMD_RUB": 0.24}
        result = self.formatter.format_conversion((500_000_000, "AMD", "500 000 000 драм"), rates, mode='chat')
        self.assertEqual(result, "Откуда у тебя такие деньги, сынок?")

    def test_dollars_need_no_rate_at_all(self):
        # The source currency IS the threshold currency, so an empty rates dict
        # changes nothing here.
        result = self.formatter.format_conversion((2_000_000, "USD", "2000000 долларов"), {}, mode='chat')
        self.assertEqual(result, "Откуда у тебя такие деньги, сынок?")

    def test_inline_mode_never_jokes(self):
        result = self.formatter.format_conversion((2_000_000, "USD", "2000000 долларов"), {"USD_RUB": 1.0}, mode='inline')
        self.assertNotIn("Откуда", result)


class TestConversionListTruncation(unittest.TestCase):
    def setUp(self):
        self.formatter = CurrencyFormatter()
        self.rates = {f"{a}_{b}": 1.0 for a in CURRENCIES for b in CURRENCIES if a != b}

    def test_the_rest_note_counts_unique_amounts_not_raw_matches(self):
        # Twelve matches, five distinct amounts: all five fit, so promising "the rest"
        # would simply be a lie.
        currency_list = [(float(i % 5) + 1, "USD", f"{i % 5 + 1} долларов") for i in range(12)]
        result = self.formatter.format_multiple_conversions(currency_list, self.rates, mode='chat')
        self.assertNotIn("и остальные", result)
        self.assertEqual(len(result.split("\n")), 5)

    def test_more_unique_amounts_than_the_limit_are_truncated_with_the_note(self):
        currency_list = [(float(i), "USD", f"{i} долларов") for i in range(1, 15)]
        result = self.formatter.format_multiple_conversions(currency_list, self.rates, mode='chat')
        lines = result.split("\n")
        self.assertEqual(len(lines), MAX_LISTED_CONVERSIONS + 1)
        self.assertEqual(lines[-1], "... и остальные (сами считайте)")

    def test_empty_list_still_returns_none(self):
        # Behaviour deliberately unchanged; only the annotation was corrected.
        self.assertIsNone(self.formatter.format_multiple_conversions([], self.rates, mode='chat'))
