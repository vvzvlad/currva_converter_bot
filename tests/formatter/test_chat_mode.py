# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""mode='chat': the reply the bot posts into a group chat.

Every case here is a real message that went through the bot at some point. The
canned replies ("Нахуй иди", "In Da Club!", "Откуда у тебя такие деньги, сынок?")
live in test_jokes.py; this module keeps the conversions and the much longer list
of texts that must produce no reply at all.
"""

import pytest


# (input text, expected chat reply). All rates are 1.0 — see the `unit_rates`
# fixture — so the numbers are carried through unchanged and only the rendering is
# under test.
CHAT_CONVERSIONS = [
    (
        "100 долларов",
        "100 долларов (🇺🇸) это 🇷🇺 100 ₽, 🇮🇱 100 ₪, 🇪🇺 100 €, 🇬🇧 £100, 🇯🇵 ¥100, 🇦🇲 100 ֏",
    ),
    (
        "100 фунтов",
        "100 фунтов (🇬🇧) это 45.4 кг, а также 🇷🇺 100 ₽, 🇺🇸 $100, 🇮🇱 100 ₪, 🇪🇺 100 €, 🇯🇵 ¥100, 🇦🇲 100 ֏",
    ),
]


# Texts the parser rejects, so the formatter is handed an empty list. The expected
# value is None — NOT an empty string: bot.py treats a falsy result as "nothing to
# reply with", and returning "" would be indistinguishable from a real reply that
# happened to be empty only by accident.
#
# These are regression cases collected from production chats, obscenities included;
# each one is a text that used to (or could) make the bot answer when it should stay
# silent. Do not "fix" an entry that looks wrong — the expectation IS the contract.
TEXTS_WITH_NOTHING_TO_CONVERT = [
    "k динаров",
    "k долларов",
    "k евро",
    "k йен",
    "k юаней",
    "k лари",
    "k батов",
    "k тенге",
    " 5 пять минут пять минут долларов",
    "Ноль ноль долларов",
    "Пять минус пять долларов",
    "Восемь восемьсот пять пять пять три пять три пять рублей",
    "Один один доллар",
    "1 bdsm",
    "1 килограмм рублей",
    "1 TON",
    "дюжина рублей",
    "Сво рублей",
    "Да бля а как работает сто сто рублей",
    "6 пять долларов",
    "13\" рублей",
    "Десятнадцать рублей",
    "миллиард долларов",
    "Додекалион рублей",
    "ёёёёё23322ёёёё драм",
    "Один четыре восемь восемь продавать рублей не бросим",
    "ёдесять рублей",
    "тридцатьё лари",
    "Двeсти рyблей",
    "Двести') exit() рублей",
    "Двести рублей') exit() рублей",
    "Две тысячи двести <script>alert()</script> двадцать два рубля",
    "две тысячи ХУËВ ТЕБЕ В ЖОПУ двадцать восемь фунтов",
    "Пять сто пять восемь рублей",
    "Пять сто пять восемь",
    "Две тысячи ПОШЕЛ НА ХУЙ двести двадцать два рубля",
    "Сто блядских рублей",
    "Пять пять рублей",
    "что рублей где",
    "Две тысячи бля двести двадцать два рубля",
    "Сто сто рублей",
    "Две тысячи двести двадцать два рубля",
    "Арубля",
    "1Арубля",
    "10 Арубля",
    "Влад скинь долларов пабрацки",
    "2 бля",
    "Влад скинь длооаров пабрацки",
    "Пица рублей",
    "пицот рублей",
    "``5+5`` долларов",
    "Звоните мне на +79936969420",
    "у меня когда-то в Додо был пин-код 1488, чтобы додорубли списывать",
    "100500 кгам",
    "1488 хуёв",
    "сто тысяч миллионов зимбабвийских долларов",
    "сто фунтов хуев тебе в панамку",
    "два фунта мяса",
    "100 т",
    "я вам расскажу историю про 1488, но писать мне лень, поэтому будет войс мессадж ебать",
    "50 юсд",
    "Пять фунтов долларов",
    "Сука где, фунты есть же",
    "100 камней",
    "Сто фунтов",
    "Я хочу доллар по рублю",
    "Хотя нахер мне доллар)",
    "Могу продать рубль по доллару",
    "Суки скинулись по рублю и разбежались",
    "¾ рублей",
    "Deployed vm nillion-cxs6v0lt in 'dosage' (took 26 min 8 sec, vm 145 out of 301 in batch, left 156 nodes",
    "Привет, как дела?",
]


@pytest.mark.parametrize("text, expected", CHAT_CONVERSIONS)
def test_chat_reply(parser, formatter, unit_rates, text, expected):
    currency_list = parser.find_currencies(text)
    assert formatter.format_multiple_conversions(currency_list, unit_rates, mode='chat') == expected


@pytest.mark.parametrize("text", TEXTS_WITH_NOTHING_TO_CONVERT)
def test_nothing_to_convert(parser, formatter, unit_rates, text):
    currency_list = parser.find_currencies(text)
    assert formatter.format_multiple_conversions(currency_list, unit_rates, mode='chat') is None
