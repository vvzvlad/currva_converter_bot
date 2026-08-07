# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

import time
import unittest

from src.currencies import CURRENCIES
from src.currency_parser import AMBIGUOUS_CODES, MAX_TEXT_LENGTH, CurrencyMatch

from tests.stubs import StubCurrencyParser


class TestCurrencyParsing(unittest.TestCase):
    def setUp(self):
        self.parser = StubCurrencyParser()

    def test_all_cases(self):
        def test(text, expected):
            result = self.parser.find_currencies(text)
            print(f'Test "{text}" -> {result} (expected {expected}), {"Pass" if result == expected else "Fail"}')
            self.assertEqual(result, expected)

        test("100 драм", [(100.0, "AMD", "100 драм")])
        test("200 драма", [(200.0, "AMD", "200 драма")])
        test("300 драмов", [(300.0, "AMD", "300 драмов")])
        
        test("100 шекелей", [(100.0, "ILS", "100 шекелей")])
        test("200 шекель", [(200.0, "ILS", "200 шекель")])
        test("300 шекеля", [(300.0, "ILS", "300 шекеля")])
        test("400 шек", [(400.0, "ILS", "400 шек")])
        test("500 шах", [(500.0, "ILS", "500 шах")])
        test("600 ils", [(600.0, "ILS", "600 ils")])
        test("700₪", [(700.0, "ILS", "700₪")])
        test("700 ₪", [(700.0, "ILS", "700 ₪")])
        
        test("100 фунтов", [(100.0, "GBP", "100 фунтов")])
        test("200 фунт", [(200.0, "GBP", "200 фунт")])
        test("300 фунтов", [(300.0, "GBP", "300 фунтов")])
        test("400 паунд", [(400.0, "GBP", "400 паунд")])
        test("500 квидов", [(500.0, "GBP", "500 квидов")])
        test("500 pound", [(500.0, "GBP", "500 pound")])
        test("500 quid", [(500.0, "GBP", "500 quid")])
        test("600 gbp", [(600.0, "GBP", "600 gbp")])
        test("700£", [(700.0, "GBP", "700£")])
        test("£800", [(800.0, "GBP", "£800")])
        test("700 £", [(700.0, "GBP", "700 £")])
        test("£ 800", []) 
        test("1.2.3 доллара", [(2.3, 'USD', '2.3 доллара')]) 
        test("77 тугриков", [])
        test("7666777 kwd", [])
        test("100500 CAD вышло", [(100500.0, 'CAD', '100500 CAD')])
        test("два с половиной бакса", [])
        test("пять баксов", [])
        test("three hundred bucks", [])
        

        test("100 рублей", [(100.0, "RUB", "100 рублей")])
        test("200 рубль", [(200.0, "RUB", "200 рубль")])
        test("300 рубля", [(300.0, "RUB", "300 рубля")])
        test("400 rub", [(400.0, "RUB", "400 rub")])
        test("500₽", [(500.0, "RUB", "500₽")])
        test("500 ₽", [(500.0, "RUB", "500 ₽")])
        test("500\₽", [])
        test(r"\500", [])
        test("500'₽", [])
        test("500,₽", [])
        test("500.₽", [])
        test("500;₽", [])
        test("500:₽", [])
        test("500₽$", [(500.0, "RUB", "500₽")])
        test("500$$", [(500.0, 'USD', '500$')])

        test("200 доллар", [(200.0, "USD", "200 доллар")])
        test("200 Доллар", [(200.0, "USD", "200 Доллар")])
        test("200 ДоллаР", [(200.0, "USD", "200 ДоллаР")])
        test("200 доЛлаРов", [(200.0, "USD", "200 доЛлаРов")])

        test("300 доллара", [(300.0, "USD", "300 доллара")])
        test("400 баксов", [(400.0, "USD", "400 баксов")])
        test("500 бакс", [(500.0, "USD", "500 бакс")])
        test("600 usd", [(600.0, "USD", "600 usd")])
        test("700$", [(700.0, "USD", "700$")])
        test("$800", [(800.0, "USD", "$800")])
        test("100 килобаксов", [(100000.0, 'USD', '100 килобаксов')])
        test("1 килобакс", [(1000.0, "USD", "1 килобакс")])
        test("килобакс", [(1000.0, "USD", "килобакс")])
        
        test("100 евро", [(100.0, "EUR", "100 евро")])
        test("200 eur", [(200.0, "EUR", "200 eur")])
        test("300€", [(300.0, "EUR", "300€")])
        test("€400", [(400.0, "EUR", "€400")])
        test("1 килоевро", [(1000.0, "EUR", "1 килоевро")])
        test("килоевро", [(1000.0, "EUR", "килоевро")])
        
        test("100 йен", [(100.0, "JPY", "100 йен")])
        test("200 йена", [(200.0, "JPY", "200 йена")])
        test("300 йен", [(300.0, "JPY", "300 йен")])
        test("400 jpy", [(400.0, "JPY", "400 jpy")])
        test("500¥", [(500.0, "JPY", "500¥")])
        
        test("100 юаней", [(100.0, "CNY", "100 юаней")])
        test("200 юань", [(200.0, "CNY", "200 юань")])
        test("300 юаня", [(300.0, "CNY", "300 юаня")])
        test("400 cny", [(400.0, "CNY", "400 cny")])
        
        test("100 лари", [(100.0, "GEL", "100 лари")])
        test("200 gel", [(200.0, "GEL", "200 gel")])
        
        test("100 динаров", [(100.0, "RSD", "100 динаров")])
        test("200 динар", [(200.0, "RSD", "200 динар")])
        test("300 динаров", [(300.0, "RSD", "300 динаров")])
        test("400 rsd", [(400.0, "RSD", "400 rsd")])
        
        test("100 батов", [(100.0, "THB", "100 батов")])
        test("200 бат", [(200.0, "THB", "200 бат")])
        test("300 бата", [(300.0, "THB", "300 бата")])
        test("400 thb", [(400.0, "THB", "400 thb")])
        
        test("100 тенге", [(100.0, "KZT", "100 тенге")])
        test("200 тг", [(200.0, "KZT", "200 тг")])
        test("300 kzt", [(300.0, "KZT", "300 kzt")])
        
        test("1.5 рублей", [(1.5, "RUB", "1.5 рублей")])
        test("2,5 евро", [(2.5, "EUR", "2,5 евро")])
        test("$3.14", [(3.14, "USD", "$3.14")])
        test("10.50₽", [(10.50, "RUB", "10.50₽")])
        test("100 рублей", [(100.0, "RUB", "100 рублей")])
        test("1 килорубль", [(1000.0, "RUB", "1 килорубль")])
        test("20 килорублей", [(20000.0, "RUB", "20 килорублей")])
        test("килорубль", [(1000.0, "RUB", "килорубль")])


        test("$200", [(200.0, "USD", "$200")])
        test("300 EUR", [(300.0, "EUR", "300 EUR")])
        test("400₽", [(400.0, "RUB", "400₽")])
        test("500 баксов", [(500.0, "USD", "500 баксов")])
        test("600 долларов", [(600.0, "USD", "600 долларов")])



        test("1к рублей", [(1000.0, "RUB", "1к рублей")])
        test("1к долларов", [(1000.0, "USD", "1к долларов")])
        test("1к евро", [(1000.0, "EUR", "1к евро")])
        test("1к йен", [(1000.0, "JPY", "1к йен")])
        test("1к юаней", [(1000.0, "CNY", "1к юаней")])
        test("1к лари", [(1000.0, "GEL", "1к лари")])
        test("1к динаров", [(1000.0, "RSD", "1к динаров")])
        test("1к батов", [(1000.0, "THB", "1к батов")])
        test("1к тенге", [(1000.0, "KZT", "1к тенге")])
        test("1к тенгег", [])
        test("1к батова", [])


        test("2к баксов", [(2000.0, "USD", "2к баксов")])
        test("1.5к EUR", [(1500.0, "EUR", "1.5к EUR")])
        test("0.5к долларов", [(500.0, "USD", "0.5к долларов")])
        test("1к$", [(1000.0, "USD", "1к$")])
        test("2к₽", [(2000.0, "RUB", "2к₽")])
        test("1.5к€", [(1500.0, "EUR", "1.5к€")])
        test("1к$ и 2к₽", [(1000.0, "USD", "1к$"), (2000.0, "RUB", "2к₽")])
        test("перевел 1к$ получил 2к₽", [(1000.0, "USD", "1к$"), (2000.0, "RUB", "2к₽")])
        test("отдал ему 1.5к€", [(1500.0, "EUR", "1.5к€")])
        test("Купил за 100 баксов и 200 рублей", [(100.0, "USD", "100 баксов"), (200.0, "RUB", "200 рублей")])
        test("Перевел 1к$ и 2к₽", [(1000.0, "USD", "1к$"), (2000.0, "RUB", "2к₽")])
        test("€100 и 200₽ и $300", [(100.0, "EUR", "€100"), (200.0, "RUB", "200₽"), (300.0, "USD", "$300")])
        test("Привет, как дела?", [])
        test("123", [])
        test("просто текст", [])
        test("k рублей", [])
        test("kрублей", [])
        test("k долларов", [])  
        test("k евро", [])
        test("k йен", [])
        test("k юаней", [])
        test("k лари", [])
        test("k динаров", [])
        test("k батов", [])
        test("k тенге", [])
        test("k$", [])
        test("k€", [])
        test("k₽", [])
        test("$k", [])
        test("€k", [])
        test("из долларов он получил 0. рублей тоже не получил", [])
        test("он получил5 рублей, и долларов тоже", []) 
        test("он получил 0.5 рублей, и долларов тоже", [(0.5, 'RUB', "0.5 рублей")])
        test("он получил .5 рублей, и долларов тоже", [(5, 'RUB', "5 рублей")]) #???!!
        test("3 412 928 ₪", [(3412928.0, 'ILS', "3 412 928 ₪")])
        test("3 412  928 ₪", [(928.0, 'ILS', '928 ₪')])
        test("3 412н 928 ₪", [(928.0, 'ILS', '928 ₪')])
        test("3 412 н928 ₪", []) 


        
        test("13675 ₽", [(13675.0, 'RUB', "13675 ₽")])
        test("13675₽", [(13675.0, 'RUB', "13675₽")])

        test("462 ₪", [(462.0, "ILS", "462 ₪")])
        test("462₪", [(462.0, "ILS", "462₪")])

        test("127 $", [(127.0, "USD", "127 $")])
        test("127$", [(127.0, "USD", "127$")])

        test("127 канадских долларов", [(127.0, "CAD", "127 канадских долларов")])
        test("127 cad", [(127.0, "CAD", "127 cad")])
        test("127 CAD", [(127.0, "CAD", "127 CAD")])

        test("120 €", [(120.0, "EUR", "120 €")])
        test("120€", [(120.0, "EUR", "120€")])

        test("888 ₽", [(888.0, "RUB", "888 ₽")])
        test("888₽", [(888.0, "RUB", "888₽")])

        test("8.2 $", [(8.2, "USD", "8.2 $")])
        test("8.2$", [(8.2, "USD", "8.2$")])

        test("6.5 £", [(6.5, "GBP", "6.5 £")])
        test("6.5£", [(6.5, "GBP", "6.5£")])

        test("7.8 €", [(7.8, "EUR", "7.8 €")])
        test("7.8€", [(7.8, "EUR", "7.8€")])

        test("38 $", [(38.0, "USD", "38 $")])
        test("38$", [(38.0, "USD", "38$")])

        test("36 €", [(36.0, "EUR", "36 €")])
        test("36€", [(36.0, "EUR", "36€")])

        test("1.4 ₪", [(1.4, "ILS", "1.4 ₪")])
        test("1.4₪", [(1.4, "ILS", "1.4₪")])

        test("0.4 $", [(0.4, "USD", "0.4 $")])
        test("0.4$", [(0.4, "USD", "0.4$")])

        test("0.3 £", [(0.3, "GBP", "0.3 £")])
        test("0.3£", [(0.3, "GBP", "0.3£")])

        test("0.4 €", [(0.4, "EUR", "0.4 €")])
        test("0.4€", [(0.4, "EUR", "0.4€")])

        test("6838 ₽", [(6838.0, "RUB", "6838 ₽")])
        test("6838₽", [(6838.0, "RUB", "6838₽")])

        test("231 ₪", [(231.0, "ILS", "231 ₪")])
        test("231₪", [(231.0, "ILS", "231₪")])

        test("63 $", [(63.0, "USD", "63 $")])
        test("63$", [(63.0, "USD", "63$")])

        test("60 €", [(60.0, "EUR", "60 €")])
        test("60€", [(60.0, "EUR", "60€")])

        test("26 ₽", [(26.0, "RUB", "26 ₽")])
        test("26₽", [(26.0, "RUB", "26₽")])    

        test("0.9 ₪", [(0.9, "ILS", "0.9 ₪")])
        test("0.9₪", [(0.9, "ILS", "0.9₪")])

        test("0.3 $", [(0.3, "USD", "0.3 $")])
        test("0.3$", [(0.3, "USD", "0.3$")])

        test("0.2 £", [(0.2, "GBP", "0.2 £")])
        test("0.2£", [(0.2, "GBP", "0.2£")])

        test("0.2 €", [(0.2, "EUR", "0.2 €")])
        test("0.2€", [(0.2, "EUR", "0.2€")])

        test("0.2 MXN", [(0.2, "MXN", "0.2 MXN")])
        test("0.2MXN", [(0.2, "MXN", "0.2MXN")])
        test("0.2 мексиканского песо", [(0.2, "MXN", "0.2 мексиканского песо")])
        test("0.2 песо", [(0.2, "MXN", "0.2 песо")])

        test("0.2 ₤", [(0.2, "TRY", "0.2 ₤")])
        test("0.2₤", [(0.2, "TRY", "0.2₤")])
        test("0.2 лиры", [(0.2, "TRY", "0.2 лиры")])
        test("0.2 лир", [(0.2, "TRY", "0.2 лир")])
        test("0.2 турецкой лиры", [(0.2, "TRY", "0.2 турецкой лиры")])


        test("0.2 zł", [(0.2, "PLN", "0.2 zł")])
        test("0.2zł", [(0.2, "PLN", "0.2zł")])
        test("0.2 злотых", [(0.2, "PLN", "0.2 злотых")])
        test("1 злотый", [(1.0, "PLN", "1 злотый")])
        test("0.2 незлотых", [])

        test("0.2 Kč", [(0.2, "CZK", "0.2 Kč")])
        test("0.2Kč", [(0.2, "CZK", "0.2Kč")])
        test("0.2 крон", [(0.2, "CZK", "0.2 крон")])
        test("0.2 чешских крон", [(0.2, "CZK", "0.2 чешских крон")])
        test("1 чешская крона", [(1.0, "CZK", "1 чешская крона")])
        test("0.2 нечешских крон", [])
        test("0.2 кронтаб", [])

        test("0.2 Br", [(0.2, "BYN", "0.2 Br")])
        test("0.2Br", [(0.2, "BYN", "0.2Br")])

        # Тесты для таджикского сомони (TJS)
        test("100 сомони", [(100.0, "TJS", "100 сомони")])
        test("200 tjs", [(200.0, "TJS", "200 tjs")])
        test("300 TJS", [(300.0, "TJS", "300 TJS")])

        # Тесты для узбекского сума/сома (UZS)
        test("100 сум", [(100.0, "UZS", "100 сум")])
        test("2 сума", [(2.0, "UZS", "2 сума")])
        test("5 сумов", [(5.0, "UZS", "5 сумов")])
        test("1 сом", [(1.0, "UZS", "1 сом")])
        test("2 сома", [(2.0, "UZS", "2 сома")])
        test("5 сомов", [(5.0, "UZS", "5 сомов")])
        test("300 uzs", [(300.0, "UZS", "300 uzs")])
        test("300 UZS", [(300.0, "UZS", "300 UZS")])
        test("0.2 белорусских рублей", [(0.2, "BYN", "0.2 белорусских рублей")])
        test("1 белорусский рубль", [(1.0, "BYN", "1 белорусский рубль")])
        test("0.2 небелорусских рублей", [])
        test("0.2 рубляб", [])

        test("0.2 ₴", [(0.2, "UAH", "0.2 ₴")])
        test("0.2₴", [(0.2, "UAH", "0.2₴")])
        test("0.2 гривны", [(0.2, "UAH", "0.2 гривны")])
        test("0.2 гривна", [(0.2, "UAH", "0.2 гривна")])
        test("0.2 негривен", [])

        test("1 румынский лей", [(1.0, "RON", "1 румынский лей")])
        test("2 румынских лея", [(2.0, "RON", "2 румынских лея")])
        test("0.2 нерумынских лей", [])
        test("1 рон", [(1.0, "RON", "1 рон")])
        test("2 рона", [(2.0, "RON", "2 рона")])
        test("10 ронов", [(10.0, "RON", "10 ронов")])
        test("0.2 неронов", [])

        test("1 молдавский лей", [(1.0, "MDL", "1 молдавский лей")])
        test("2 молдавских лея", [(2.0, "MDL", "2 молдавских лея")])
        test("5 молдавских леев", [(5.0, "MDL", "5 молдавских леев")])

        test("0.2 немолдавских леев", [])

        test("1 лей", [(1.0, "MDL", "1 лей")])
        test("2 лея", [(2.0, "MDL", "2 лея")])
        test("5 леев", [(5.0, "MDL", "5 леев")])

        test("1 лев", [(1.0, "BGN", "1 лев")])
        test("2 лева", [(2.0, "BGN", "2 лева")])
        test("5 левов", [(5.0, "BGN", "5 левов")])  
        test("0.2 нелевов", [])
        test("1 болгарский лев", [(1.0, "BGN", "1 болгарский лев")])
        test("2 болгарских лева", [(2.0, "BGN", "2 болгарских лева")])
        test("5 болгарских левов", [(5.0, "BGN", "5 болгарских левов")])
        test("0.2 неболгарских левов", [])
        test("1 лв", [(1.0, "BGN", "1 лв")])
        test("1 лвл", [])

        test("1 dh", [(1.0, "AED", "1 dh")])
        test("2 dh", [(2.0, "AED", "2 dh")])
        test("5 dh", [(5.0, "AED", "5 dh")])
        test("0.2 ndh", [])
        test("100 дирхам", [(100.0, "AED", "100 дирхам")])
        test("2 дирхама", [(2.0, "AED", "2 дирхама")])
        test("5 дирхамов", [(5.0, "AED", "5 дирхамов")])
        test("0.2 недирхамов", [])
        test("1 د.إ", [(1.0, "AED", "1 د.إ")])
        test("2 د.إ", [(2.0, "AED", "2 د.إ")])
        test("5 د.إ", [(5.0, "AED", "5 د.إ")])



        test("0.2 ₫", [(0.2, "VND", "0.2 ₫")])
        test("0.2₫", [(0.2, "VND", "0.2₫")])
        test("0.2 донга", [(0.2, "VND", "0.2 донга")])
        test("0.2 недонгов", [])


        test("-5 рублей", [(5.0, "RUB", "5 рублей")])
        test("10 рублей + 20 фунтов", [(10.0, "RUB", "10 рублей"), (20.0, "GBP", "20 фунтов")])

        test("3^5 фунтов", []) 
        test("3^5 квид", []) 
        test("0x1999 фунтов", []) 
        test("50e10 фунтов", []) 
        test("5+5 долларов", [(5.0, "USD", "5 долларов")]) 
        test("${7*7} долларов", [])
        test("1e10 рублей", [])
        test("4+5 рублей", [(5.0, 'RUB', "5 рублей")])
        test("4-5 рублей", [(5.0, 'RUB', "5 рублей")])
        test("4/5 рублей", [(5.0, 'RUB', "5 рублей")])
        test("4*5 рублей", [(5.0, 'RUB', "5 рублей")])
        test("4^5 рублей", [])
        test("4%5 рублей", [])
        test("4!5 рублей", [(5.0, 'RUB', "5 рублей")])
        test("5! рублей", [])

        test("4.5 в рублей", [])
        test("4.5 рублей", [(4.5, 'RUB', "4.5 рублей")])
        test("100-10 рублей", [(10.0, 'RUB', "10 рублей")])
        test("20 динар", [(20.0, 'RSD', "20 динар")])

        test("-100 баксов", [(100.0, "USD", "100 баксов")])
        test("0 рублей", [(0.0, "RUB", "0 рублей")])
        test("0рублей", [(0.0, "RUB", "0рублей")])

        test("-10 рублей", [(10.0, "RUB", "10 рублей")])
        test("-1 рублей", [(1.0, "RUB", "1 рублей")])
        test("-0 рублей", [(0.0, "RUB", "0 рублей")])
        test("-0 сколько рублей", [])
        test("-0 сколько рублей и долларов", [])
        test("Сто фунтов", [])
        test("Двадцать два рубля", [])
        test("Пять тысяч рублей", [])
        test("пицот рублей", [])
        test("Две тысячи двести двадцать два рубля", [])

        test("10:30 рублей", [(30.0, "RUB", "30 рублей")])
        test("10:30 и дальше рублей", [])
        
        test("1. рубль", [])
        test("0. драм", [])
        test("AMD6521", [])
        test("AMD 6521", [])
        test("1 TON", [])
        test("null долларов", [])
        test("Бля рубля", [])
        test("1 шахерезада", [])
        test("30 пхп", [])
        test("100500 кгам", [])
        test("1337 чего блядь", [])
        test("5500 AMD", [(5500.0, "AMD", "5500 AMD")])
        test("1337 лари", [(1337.0, "GEL", "1337 лари")])
        test("415 amd", [])
        test("300$", [(300.0, "USD", "300$")])
        test("10 юаней", [(10.0, "CNY", "10 юаней")])
        test("1 фунт", [(1.0, "GBP", "1 фунт")])
        test("1 квид", [(1.0, "GBP", "1 квид")])
        test("1488 фунтов", [(1488.0, "GBP", "1488 фунтов")])
        test("5 баксов", [(5.0, "USD", "5 баксов")])
        test("99 фунтов и 100 долларов", [(99.0, "GBP", "99 фунтов"), (100.0, "USD", "100 долларов")])
        test("10 рублей + 1 рубль", [(10.0, "RUB", "10 рублей"), (1.0, "RUB", "1 рубль")])
        test("999999999999999999999999 фунтов", [(999999999999999999999999.0, "GBP", "999999999999999999999999 фунтов")])
        test("500 сигарет", [])
        test("500 хуёв тебе в жопу", [])    
        test("8", [])

        test("Бля ₪", [])
        test("50 нфс", [])
        test("50 агорот", [])
        test("50 огород", [])


        test("1 рубль", [(1.0, "RUB", "1 рубль")])
        test("1 лари 100 рублей 2 доллара", [(1.0, "GEL", "1 лари"), (100.0, "RUB", "100 рублей"), (2.0, "USD", "2 доллара")])
        test("0.0 кг, 0.1 ₽,", [(0.1, 'RUB', '0.1 ₽')])
        test("0.001 фунта", [(0.001, 'GBP', '0.001 фунта')])
        test("1 лари", [(1.0, "GEL", "1 лари")])
        test("0.0015 рублей", [(0.0015, 'RUB', '0.0015 рублей')])

        test("Пять 6 долларов", [(6.0, 'USD', '6 долларов')])
        test("5 6 7 долларов", [(7.0, 'USD', '7 долларов')])
        test("3 шекеля", [(3.0, 'ILS', '3 шекеля')])
        test("10000 рублей", [(10000.0, 'RUB', '10000 рублей')])
        test("двадцать 2 рубля", [(2.0, 'RUB', '2 рубля')])
        test("Один1 рублей", [])

        test("1.0 рублей", [(1.0, 'RUB', '1.0 рублей')])
        test("1. Рублей", [])
        test("2. Долларов", [])
        test("0. драм", [])

        test("-100 фунтов", [(100.0, "GBP", "100 фунтов")])
        test("-100000000000 фунтов", [(100000000000.0, "GBP", "100000000000 фунтов")])
        test("15 фунтов", [(15.0, "GBP", "15 фунтов")])
        test("12345679x9 евро", [])
        test("1блять1 долларов", [])
        test("Ox5 долларов", [])
        test("Блять11 долларов", [])
        test("Вставить 0,05 ₽", [(0.05, 'RUB', '0,05 ₽')])

        # Тесты для центов
        test("50 центов", [(0.5, "USD", "50 центов")])
        test("1 цент", [(0.01, "USD", "1 цент")])
        test("2 цента", [(0.02, "USD", "2 цента")])
        test("5 cents", [(0.05, "USD", "5 cents")])
        test("1 cent", [(0.01, "USD", "1 cent")])
        
        # Тесты для евроцентов
        test("50 евроцентов", [(0.5, "EUR", "50 евроцентов")])
        test("1 евроцент", [(0.01, "EUR", "1 евроцент")])
        test("2 евроцента", [(0.02, "EUR", "2 евроцента")])
        test("5 eurocents", [(0.05, "EUR", "5 eurocents")])
        test("1 eurocent", [(0.01, "EUR", "1 eurocent")])
        
        # Комбинированные тесты
        test("5 долларов 30 центов", [(5.0, "USD", "5 долларов"), (0.3, "USD", "30 центов")])
        test("2 евро 15 евроцентов", [(2.0, "EUR", "2 евро"), (0.15, "EUR", "15 евроцентов")])
        test("1 доллар 1 цент", [(1.0, "USD", "1 доллар"), (0.01, "USD", "1 цент")])
        test("1 евро 1 евроцент", [(1.0, "EUR", "1 евро"), (0.01, "EUR", "1 евроцент")])

        # Негативные тесты
        test("центов", [])
        test("евроцентов", [])
        test("k центов", [])
        test("k евроцентов", [])
        test("0 центов", [(0.0, "USD", "0 центов")])
        test("0 евроцентов", [(0.0, "EUR", "0 евроцентов")])

        test("1,000 долларов", [(1000.0, "USD", "1,000 долларов")])
        test("1 000 долларов", [(1000.0, "USD", "1 000 долларов")])
        test("1 000,50 долларов", [(1000.50, "USD", "1 000,50 долларов")])
        test("2.500,75 евро", [(2500.75, "EUR", "2.500,75 евро")])
        test("3,000,000 йен", [(3000000.0, "JPY", "3,000,000 йен")])

        # Тесты для отрицательных сумм
        test("-5 долларов", [(5.0, "USD", "5 долларов")])
        test("минус 10 евро", [(10.0, "EUR", "10 евро")])

        test("¥1000", [(1000.0, "JPY", "¥1000")])
        test("1000¥", [(1000.0, "JPY", "1000¥")])

        # Тесты для дополнительных валют
        test("500 юаней", [(500.0, "CNY", "500 юаней")])
        test("200 cny", [(200.0, "CNY", "200 cny")])
        test("100 шекелей", [(100.0, "ILS", "100 шекелей")])
        test("200₪", [(200.0, "ILS", "200₪")])

        # Негативные тесты для некорректных форматов
        test("100..50 долларов", [(50.0, 'USD', '50 долларов')])
        test("100, долларов", [])
        test("долларов 100", [])
        test("две тысячи долларов", [])
        test("минус пять евро", [])
        test("5 долларов США", [(5.0, 'USD', '5 долларов')])

        # Тесты для чисел с разделителями тысяч и десятичными
        test("1 000,50 долларов", [(1000.50, "USD", "1 000,50 долларов")])
        test("1.000,50 евро", [(1000.50, "EUR", "1.000,50 евро")])
        test("1,000.50 фунтов", [(1000.50, "GBP", "1,000.50 фунтов")])
        test("3,000,000 йен", [(3000000.0, "JPY", "3,000,000 йен")])
        test("3 412 928 ₪", [(3412928.0, "ILS", "3 412 928 ₪")])
        
        # Дополнительные тесты для проверки граничных случаев
        #test("1.000.000,50 евро", [(1000000.50, "EUR", "1.000.000,50 евро")])
        #test("1,000,000.50 долларов", [(1000000.50, "USD", "1,000,000.50 долларов")])
        test("1 000 000,50 рублей", [(1000000.50, "RUB", "1 000 000,50 рублей")])
        #test("1.234.567,89 евро", [(1234567.89, "EUR", "1.234.567,89 евро")])
        #test("1,234,567.89 фунтов", [(1234567.89, "GBP", "1,234,567.89 фунтов")])

        # Тесты для корейской воны (KRW)
        test("100 вон", [(100.0, "KRW", "100 вон")])
        test("200 вона", [(200.0, "KRW", "200 вона")])
        test("300 воны", [(300.0, "KRW", "300 воны")])
        test("400 krw", [(400.0, "KRW", "400 krw")])
        test("500₩", [(500.0, "KRW", "500₩")])
        test("₩600", [(600.0, "KRW", "₩600")])
        test("700 ₩", [(700.0, "KRW", "700 ₩")])
        
        test("100 юаней", [(100.0, "CNY", "100 юаней")])

        # Тесты для десятичных чисел с запятой
        test("0,015 фунтов", [(0.015, "GBP", "0,015 фунтов")])
        test("0,015 долларов", [(0.015, "USD", "0,015 долларов")])
        test("0,015 евро", [(0.015, "EUR", "0,015 евро")])
        test("0,015 рублей", [(0.015, "RUB", "0,015 рублей")])
        
        # Тесты для десятичных чисел с точкой
        test("0.015 фунтов", [(0.015, "GBP", "0.015 фунтов")])
        test("0.015 долларов", [(0.015, "USD", "0.015 долларов")])
        
        # Тесты для сравнения обработки запятой и точки
        test("1,5 фунтов", [(1.5, "GBP", "1,5 фунтов")])
        test("1.5 фунтов", [(1.5, "GBP", "1.5 фунтов")])
        
        # Тесты для чисел с разделителями тысяч и десятичными
        test("1,000.50 фунтов", [(1000.50, "GBP", "1,000.50 фунтов")])
        test("1.000,50 евро", [(1000.50, "EUR", "1.000,50 евро")])
        
        # Тесты для очень маленьких чисел
        test("0,001 фунтов", [(0.001, "GBP", "0,001 фунтов")])
        test("0,0001 долларов", [(0.0001, "USD", "0,0001 долларов")])
        
        # Тесты для чисел с нулями после запятой
        test("1,00 фунтов", [(1.0, "GBP", "1,00 фунтов")])
        test("10,00 долларов", [(10.0, "USD", "10,00 долларов")])
        
        # Тесты для чисел с нулями перед запятой
        test("0,5 фунтов", [(0.5, "GBP", "0,5 фунтов")])
        test("0,25 долларов", [(0.25, "USD", "0,25 долларов")])

        # Тесты для мексиканского песо (MXN)
        test("100 песо", [(100.0, "MXN", "100 песо")])
        test("200 мексиканских песо", [(200.0, "MXN", "200 мексиканских песо")])
        test("300 mxn", [(300.0, "MXN", "300 mxn")])
        test("1 мексиканское песо", [(1.0, "MXN", "1 мексиканское песо")])
        test("0.5 песо", [(0.5, "MXN", "0.5 песо")])
        test("1,000 песо", [(1000.0, "MXN", "1,000 песо")])

        # Тесты для филиппинского песо (PHP)
        test("100 филиппинских песо", [(100.0, "PHP", "100 филиппинских песо")])
        test("200 piso", [(200.0, "PHP", "200 piso")])
        test("300 php", [(300.0, "PHP", "300 php")])
        test("400₱", [(400.0, "PHP", "400₱")])
        test("₱500", [(500.0, "PHP", "₱500")])
        test("1 филиппинское песо", [(1.0, "PHP", "1 филиппинское песо")])
        test("0.5 piso", [(0.5, "PHP", "0.5 piso")])
        test("1,000 piso", [(1000.0, "PHP", "1,000 piso")])
        # Негативный тест - "песо" не должно матчиться как PHP
        test("100 песо", [(100.0, "MXN", "100 песо")]) 

        # Тесты для аргентинского песо (ARS)
        test("100 аргентинских песо", [(100.0, "ARS", "100 аргентинских песо")])
        test("1 аргентинское песо", [(1.0, "ARS", "1 аргентинское песо")])
        test("300 ars", [(300.0, "ARS", "300 ars")])
        test("300 ARS", [(300.0, "ARS", "300 ARS")])
        # Негативный: без указания страны остаётся MXN
        test("50 песо", [(50.0, "MXN", "50 песо")])
        
        test("0.2 Br", [(0.2, "BYN", "0.2 Br")])
        test("0.2Br", [(0.2, "BYN", "0.2Br")])

        # ISO code fallback: every known currency parses by its uppercase code,
        # except the codes that are ordinary English words (see AMBIGUOUS_CODES)
        for curr in CURRENCIES.values():
            if curr.code in AMBIGUOUS_CODES:
                continue
            test(f"1 {curr.code}", [(1.0, curr.code, f"1 {curr.code}")])

        # ...but a lowercase code is NOT enough for the long tail, otherwise ordinary
        # words would become currency amounts
        test("поставил 3 top", [])
        test("5 mad max", [])
        test("я взял 3 all", [])
        test("8 cup", [])
        test("2 mop", [])
        test("1 bob", [])
        test("50 sos", [])
        test("7666777 KWD", [(7666777.0, "KWD", "7666777 KWD")])
        test("100 CHF", [(100.0, "CHF", "100 CHF")])

        # AMBIGUOUS_CODES are not parsed by code even in uppercase
        test("рецепт: 1 CUP муки", [])
        test("score 3 TOP", [])
        test("5 MAD MAX", [])
        test("I PAID 100 ALL DAY", [])
        test("заказ 5 SOS", [])

        # AMD has no ISO code in its hand-written pattern, so it must keep its fallback
        test("1000 AMD", [(1000.0, "AMD", "1000 AMD")])

    def test_currency_boundary_detection(self):
        def test(text, expected):
            result = self.parser.find_currencies(text)
            print(f'Test "{text}" -> {result} (expected {expected}), {"Pass" if result == expected else "Fail"}')
            self.assertEqual(result, expected)
        
        # Положительные тесты - валюта окружена пробелами или находится в начале/конце строки
        test("100 рублей", [(100.0, "RUB", "100 рублей")])
        test("$100", [(100.0, "USD", "$100")])
        test("100$", [(100.0, "USD", "100$")])
        test("текст 100 рублей", [(100.0, "RUB", "100 рублей")])
        test("100 рублей текст", [(100.0, "RUB", "100 рублей")])
        test("текст 100$ текст", [(100.0, "USD", "100$")])
        test("текст $100 текст", [(100.0, "USD", "$100")])
        test("текст, 100 рублей.", [(100.0, "RUB", "100 рублей")])
        test("текст! 100$ текст", [(100.0, "USD", "100$")])
        
        # Отрицательные тесты - валюта не окружена пробелами
        test("текст100рублей", [])
        test("текст100$текст", [])
        test("текст$100текст", [])
        test("100рублейтекст", [])
        test("$100текст", [])
        test("текст100$", []) 
        test("текст$100", []) 
        
        # Тесты с символами валют
        test("текст₽100", [])
        test("текст100₽", []) 
        test("текст₽100текст", [])
        test("текст100₽текст", [])
        
        # Тесты с разделителями
        test("текст-100$", [(100.0, "USD", "100$")])
        test("текст_100$", [(100.0, "USD", "100$")])
        test("текст/100$", [(100.0, "USD", "100$")])
        test("текст(100$)", [(100.0, "USD", "100$")])
        test("текст[100$]", [(100.0, "USD", "100$")])
        
        # Тесты с URL и email
        test("сайт100$.com", [])
        test("email@100$.com", [])  
        test("https://100$.com", [(100.0, "USD", "100$")]) 
        
        # Тесты с хэштегами и упоминаниями
        test("#100$", [])
        test("@100$", [])
        test("#100 $", [])
        
        # Тесты с эмодзи
        test("💰100$", [(100.0, "USD", "100$")])
        test("100$💰", [(100.0, "USD", "100$")])
        
        # Тесты с кириллицей
        test("цена100рублей", [])
        test("цена100$", []) 
        
        # Тесты с несколькими валютами
        test("100$200€", [(200.0, 'EUR', '200€')]) 
        test("100$текст200€", []) 
        test("текст100$текст200€текст", [])
        test("текст 100$ текст 200€ текст", [(100.0, "USD", "100$"), (200.0, "EUR", "200€")])
        
        # Тесты с dh (дирхамы)
        test("100dh", [(100.0, "AED", "100dh")])
        test("текст100dh", [])
        test("текст 100dh", [(100.0, "AED", "100dh")])
        test("100dhтекст", [])
        test("100dh текст", [(100.0, "AED", "100dh")])
        
        # Тесты с 6Dh из примера
        test("6Dh", [(6.0, "AED", "6Dh")])
        test("текст6Dh", [])
        test("текст 6Dh", [(6.0, "AED", "6Dh")])
        test("6Dhтекст", [])
        test("6Dh текст", [(6.0, "AED", "6Dh")])
        
        # Тест из примера
        test("https://open.spotify.com/track/3cfgisz6DhZmooQk08P4Eu", [])

    def test_amount_shapes_that_need_backtracking(self):
        """Amount shapes that pin down how much the amount regex may consume.

        These are the cases that break if the repeats in the amount pattern are made
        possessive without thinking: each of them only parses because the engine is
        still allowed to hand something back. Kept as an explicit guard so a future
        performance tweak cannot quietly change what the bot recognises.
        """
        def test(text, expected):
            self.assertEqual(self.parser.find_currencies(text), expected, text)

        # A fourth decimal digit means the separator was never a thousands separator:
        # "1.2345" is one number, not "1.234" followed by a stray "5".
        test("1.2345 евро", [(1.2345, "EUR", "1.2345 евро")])
        test("1.234 евро", [(1.234, "EUR", "1.234 евро")])

        # The "$<amount>" pattern ends in \b, so a letter glued to the digits forces
        # the amount to stop one thousands group earlier.
        test("$1 000 000", [(1000000.0, "USD", "$1 000 000")])
        test("$1 000 000abc", [(1000.0, "USD", "$1 000")])

        # The "к" suffix has to be given back when the currency name itself starts
        # with "к" and there is no space in between.
        test("5крон", [(5.0, "CZK", "5крон")])
        test("5килобаксов", [(5000.0, "USD", "5килобаксов")])
        test("5к баксов", [(5000.0, "USD", "5к баксов")])
        test("10 000к рублей", [(10000000.0, "RUB", "10 000к рублей")])

        # Long amounts stay unbounded: the plain-integer branch has no digit limit.
        test("12345678901234567890 USD", [(1.2345678901234567e+19, "USD", "12345678901234567890 USD")])
        test("1 000 000 000 000 донгов", [(1000000000000.0, "VND", "1 000 000 000 000 донгов")])

        # Mixed separators, both orders.
        test("1.234,56 евро", [(1234.56, "EUR", "1.234,56 евро")])
        test("1,234.56 usd", [(1234.56, "USD", "1,234.56 usd")])
        test("1 000 000,50 евро", [(1000000.5, "EUR", "1 000 000,50 евро")])

        # A number right after another number: nothing is glued together.
        test("100 500 долларов", [(100500.0, "USD", "100 500 долларов")])
        test("1 000 200", [])
        test("10 000₽", [(10000.0, "RUB", "10 000₽")])

    def test_amounts_past_seven_thousands_groups_are_not_specified(self):
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
        def parsed(text):
            return self.parser.find_currencies(text)

        # Space separator: the amount cannot reach the currency word from the start of
        # the number, so the match slides right and starts on a group of zeroes.
        self.assertEqual(
            parsed("1 000 000 000 000 000 000 000 рублей"),
            [(0.0, "RUB", "000 000 000 000 000 000 000 рублей")])

        # Symbol prefix, space separator: the match simply stops at the sixth group.
        self.assertEqual(
            parsed("€1 000 000 000 000 000 000 000"),
            [(1e18, "EUR", "€1 000 000 000 000 000 000")])

        # Comma separator: not truncated at all. The seventh group is consumed by the
        # decimal tail `(?:[.,]\d+)?`, and the amount normaliser folds it back in.
        self.assertEqual(
            parsed("1,000,000,000,000,000,000,000 USD"),
            [(1e21, "USD", "1,000,000,000,000,000,000,000 USD")])

        # Right at the bound everything still behaves normally, whatever the separator.
        self.assertEqual(
            parsed("1 000 000 000 000 000 000 рублей"),
            [(1e18, "RUB", "1 000 000 000 000 000 000 рублей")])

    def test_parsing_time_scales_linearly_with_text_length(self):
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
            self.assertEqual(len(text), length)
            return min(self._time_parse(text) for _ in range(5))

        self.parser.find_currencies('123 456 789 ' * 10)  # warm up the compiled patterns

        half = MAX_TEXT_LENGTH // 2

        # Short circuit on a SINGLE run before measuring the curve. The ratio above is
        # the real assertion, but reaching it costs ten parses, and if the regression is
        # back each of them takes ~10 s: the test would fail after ~3.5 minutes, which on
        # CI looks like a job killed by a timeout rather than like a failed assert. One
        # linear pass over half the Telegram limit is ~0.2 s here, so the budget below
        # leaves an order of magnitude for a loaded shared runner and still trips on the
        # quadratic version, which needs seconds for this very first run.
        probe = self._time_parse(('123 456 789 ' * 400)[:half])
        self.assertLess(
            probe, 4.0,
            f"a single parse of {half} characters took {probe:.2f} s — far past anything a "
            f"linear scan can cost, so the amount regex is backtracking again. Stopping here "
            f"instead of running the full scaling measurement, which would take minutes at "
            f"this speed")

        short = fastest_run(half)
        long = fastest_run(half * 2)
        ratio = long / short

        self.assertLess(
            ratio, 3.0,
            f"parsing time grew {ratio:.1f}x when the text doubled "
            f"({half} chars: {short:.3f} s, {half * 2} chars: {long:.3f} s) — "
            f"linear scanning grows ~2x, quadratic ~4x")

        # Kept as a second, deliberately loose backstop: the quadratic version needed
        # 20-33 s at this length, so this only fires on a genuine regression.
        self.assertLess(long, 10.0, f"parsing {half * 2} characters took {long:.2f} s")

    def _time_parse(self, text):
        started = time.perf_counter()
        self.parser.find_currencies(text)
        return time.perf_counter() - started

    def test_text_longer_than_the_limit_is_not_parsed(self):
        # The cap is a backstop for input that should not reach the parser at all
        # (a caption concatenated with something else, say). At the limit the text is
        # still parsed normally; one character over it, nothing is.
        tail = " 100 рублей"
        at_limit = "а" * (MAX_TEXT_LENGTH - len(tail)) + tail
        self.assertEqual(len(at_limit), MAX_TEXT_LENGTH)
        self.assertEqual(self.parser.find_currencies(at_limit), [(100.0, "RUB", "100 рублей")])

        over_limit = "а" + at_limit
        with self.assertLogs("currency_parser", level="WARNING") as captured:
            self.assertEqual(self.parser.find_currencies(over_limit), [])
        # The length is logged, the message text is not.
        self.assertIn(str(len(over_limit)), captured.output[0])
        self.assertNotIn("рублей", captured.output[0])

    def test_unparseable_amounts_are_dropped_instead_of_becoming_zero(self):
        """An amount the normaliser cannot make sense of must disappear, quietly.

        "1.000,000.5" matches the amount regex, and once the thousands dots are
        stripped "1000,0005" is left — not a number. float() raised straight out of
        find_currencies, the handler's blanket except swallowed it, and the WHOLE
        message was lost with it: other amounts included, and an inline query got no
        answer at all. The neighbouring branch of the same normaliser had the mirror
        problem — it answered 0.0, and a zero amount is what the formatter replies to
        with an insult.
        """
        with self.assertLogs("currency_parser", level="ERROR"):
            self.assertEqual(self.parser.find_currencies("1.000,000.5 евро"), [])

        # Everything else in the message still gets converted.
        with self.assertLogs("currency_parser", level="ERROR"):
            self.assertEqual(
                self.parser.find_currencies("1.000,000.5 евро и 100 долларов"),
                [(100.0, "USD", "100 долларов")],
            )

        # Same shape, separators the other way round.
        with self.assertLogs("currency_parser", level="ERROR"):
            self.assertEqual(self.parser.find_currencies("1.000.000,50 евро"), [])

        # A genuine zero is not an unparseable amount and keeps behaving exactly as
        # before — the formatter's reply to it is covered in test_formatter.
        self.assertEqual(self.parser.find_currencies("0 рублей"), [(0.0, "RUB", "0 рублей")])
        self.assertEqual(self.parser.find_currencies("0,00 долларов"), [(0.0, "USD", "0,00 долларов")])
        self.assertEqual(self.parser.find_currencies("0.5 USD"), [(0.5, "USD", "0.5 USD")])


class TestMatchPositions(unittest.TestCase):
    """find_currency_matches() — the same search, with the offsets kept.

    The inline handler splices its conversions into the message by these offsets, so
    the property that has to hold is text[start:end] == original_text, for every match
    of every text. Checked as a property over a corpus rather than as hand-counted
    numbers: hand-counted offsets only prove the parser agrees with whoever counted.
    """

    # Deliberately includes the two texts that broke the old str.replace() assembly, a
    # symbol-prefixed amount (the match starts before the digits), an amount whose group
    # is empty ("килобаксов"), amounts with spaces inside them, non-BMP characters ahead
    # of a match (positions are character offsets, and an emoji is one character here but
    # four bytes), and texts with no amounts at all.
    CORPUS = [
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
        "ничего тут нет",
        "3 top и 5 mad — не валюты",
        "100500 CAD вышло",
    ]

    def setUp(self):
        self.parser = StubCurrencyParser()

    def test_every_match_points_at_its_own_text(self):
        for text in self.CORPUS:
            for match in self.parser.find_currency_matches(text):
                with self.subTest(text=text, match=match):
                    self.assertIsInstance(match, CurrencyMatch)
                    self.assertEqual(text[match.start:match.end], match.original_text)

    def test_matches_are_ordered_and_never_overlap(self):
        """What makes a left-to-right rebuild of the text possible at all."""
        for text in self.CORPUS:
            with self.subTest(text=text):
                previous_end = 0
                for match in self.parser.find_currency_matches(text):
                    self.assertGreaterEqual(match.start, previous_end)
                    self.assertGreater(match.end, match.start)
                    previous_end = match.end
                self.assertLessEqual(previous_end, len(text))

    def test_the_gaps_and_the_matches_rebuild_the_original_text(self):
        """The matches are a complete cut of the text, not a subset of it.

        This is exactly the assembly the inline handler does, with the conversions
        left out: if it does not reproduce the input, it cannot preserve it either.
        """
        for text in self.CORPUS:
            with self.subTest(text=text):
                pieces = []
                cursor = 0
                for match in self.parser.find_currency_matches(text):
                    pieces.append(text[cursor:match.start])
                    pieces.append(match.original_text)
                    cursor = match.end
                pieces.append(text[cursor:])
                self.assertEqual("".join(pieces), text)

    def test_find_currencies_is_the_same_search_without_the_positions(self):
        for text in self.CORPUS:
            with self.subTest(text=text):
                matches = self.parser.find_currency_matches(text)
                self.assertEqual(self.parser.find_currencies(text), [match[:3] for match in matches])

    def test_two_identical_amounts_are_two_matches_at_different_places(self):
        """The triples are equal, and that is precisely why the positions are needed."""
        matches = self.parser.find_currency_matches("дай 100$ и еще 100$")
        self.assertEqual(len(matches), 2)
        first, second = matches
        self.assertEqual(first[:3], second[:3])
        self.assertNotEqual((first.start, first.end), (second.start, second.end))
        self.assertEqual((first.start, first.end), (4, 8))
        self.assertEqual((second.start, second.end), (15, 19))

    def test_a_shorter_amount_inside_a_longer_one_is_not_a_match_of_its_own(self):
        """"100$" occurs inside "1100$" as a substring, but not as a match."""
        matches = self.parser.find_currency_matches("взял 1100$ и 100$")
        self.assertEqual([match.original_text for match in matches], ["1100$", "100$"])
        self.assertEqual([(match.start, match.end) for match in matches], [(5, 10), (13, 17)])

    def test_text_longer_than_the_limit_has_no_matches_either(self):
        over_limit = "а" * MAX_TEXT_LENGTH + " 100 рублей"
        with self.assertLogs("currency_parser", level="WARNING"):
            self.assertEqual(self.parser.find_currency_matches(over_limit), [])
