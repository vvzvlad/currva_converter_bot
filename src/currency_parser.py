# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

import re
from typing import List, Tuple
import logging
import os

from src.currencies import CURRENCIES

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(os.path.splitext(os.path.basename(__file__))[0])

# ISO codes that are also ordinary English words. Parsing them by code would make
# the bot barge into messages that have nothing to do with money ("1 CUP of flour",
# "3 TOP", "5 MAD MAX"), so the generated fallback skips them. None of them has a
# hand-written pattern either, so amounts in these currencies are not recognised in
# text at all — a deliberate trade-off: a false match on plain English is worse than
# missing an exotic currency. They remain available as *target* currencies via
# /currencies.
AMBIGUOUS_CODES = frozenset({'ALL', 'BOB', 'CUP', 'MAD', 'MOP', 'PEN', 'SOS', 'TOP'})

# Hard cap on the text we are willing to scan. Telegram allows 4096 characters per
# message and the parser runs on every message in every group chat, so an oversized
# input must degrade to "no currencies found" instead of burning CPU in the handler.
MAX_TEXT_LENGTH = 4096

class CurrencyParser:
    def __init__(self):
        # Amount pattern. Four details here are load-bearing for *performance*, not
        # only for correctness: this regex is embedded in ~170 patterns, each of which
        # is run over every incoming message, and `re` does not release the GIL — a slow
        # scan freezes the whole bot process, not just the calling thread.
        #
        #   \d{1,3}+   The leading group of an amount. Possessive: if it gave a digit
        #       back, the next character would be a digit again, and no continuation of
        #       the pattern can start with one — so a shorter first group can never turn
        #       a failed match into a successful one, it only triples the work.
        #   {0,6} instead of *   The thousands-separator class contains a SPACE, so on a
        #       run of digit groups ("123 456 789 123 456 ...") an unbounded repeat eats
        #       the whole tail from every start position and then gives it back group by
        #       group — quadratic. A 4096-character message (the Telegram limit) cost
        #       ~20 s of CPU. Six groups reach 10^18, far past anything a chat message
        #       means, and make the per-position work constant.
        #   (?!\d)   A thousands group followed by another digit can never be part of a
        #       successful match: nothing that may follow the amount starts with a digit.
        #       Refusing it up front loses no match and removes the ambiguity with the
        #       decimal part below, so "1.2345" stays a decimal instead of "1.234" + "5".
        #   (?<!\d)\d++   Plain-integer branch. Possessive because giving digits back can
        #       never help (again: nothing after the amount starts with a digit), and the
        #       lookbehind stops a long unseparated digit run from being rescanned from
        #       every offset inside it. It drops no match either: a run start always
        #       yields the same match end as any offset inside the run, and finditer
        #       prefers the leftmost one.
        #
        # The decimal tail and the "к" suffix stay ordinary greedy on purpose — "5крон"
        # only parses if the engine may give the "к" back so that "крон" can match.
        self.number = r'(?P<amount>(?:\d{1,3}+(?:[., ]\d{3}(?!\d)){0,6}|(?<!\d)\d++)(?:[.,]\d+)?(?:к)?)'
        self.current_match = ''

        handwritten = [
            ('ILS',     fr'{self.number}\s*(?:шекел(?:ей|я|ь)|шек|шах|ils|ILS|₪)\b'),
            ('ILS',     fr'{self.number}\s*₪'),
    
            ('GBP',     fr'(?:£){self.number}\b'),
            ('GBP',     fr'{self.number}\s*(?:фунт(?:ов|а|)|паунд(?:ов|а|)|квид(?:ов|а|)|pound|quid|gbp|GBP|gbr|GBR|£)\b'),
            ('GBP',     fr'{self.number}\s*£'),
    
            ('RUB',     fr'{self.number}\s*(?:руб(?:лей|ля|ль)|₽|rub|RUB)\b'),
            ('RUB',     fr'{self.number}\s*₽'),
            ('RUBK',     fr'{self.number}\s*(?:килоруб(?:лей|ля|ль))\b'),
            ('RUBK',     r'(?P<amount>)килоруб(?:лей|ля|ль)\b'),
                
            ('USD',     fr'\${self.number}\b'),
            ('USD',     fr'{self.number}\s*(?:доллар(?:ов|а|)|бакс(?:ов|а|)|usd|USD|\$)\b'),
            ('USD',     fr'{self.number}\s*\$'),
            ('USDCENT', fr'{self.number}\s*(?:цент(?:ов|а|)|cent|cents)\b'),
            ('USDK',     fr'{self.number}\s*(?:килобакс(?:ов|а|))\b'),
            ('USDK',     r'(?P<amount>)килобакс(?:ов|а|)\b'),

            ('EUR',     fr'€{self.number}\b'),
            ('EUR',     fr'{self.number}\s*(?:евро|eur|EUR|€)\b'),
            ('EUR',     fr'{self.number}\s*€'),
            ('EURCENT', fr'{self.number}\s*(?:евроцент(?:ов|а|)|eurocent|eurocents)\b'),
            ('EURK',     fr'{self.number}\s*(?:килоевро|eurk|EURK)\b'),
            ('EURK',     r'(?P<amount>)килоевро(?:ов|а|)\b'),

            ('JPY',     fr'¥{self.number}\b'),
            ('JPY',     fr'{self.number}\s*(?:йен(?:а|ы|)|¥|jpy|JPY)\b'),
            ('JPY',     fr'{self.number}\s*¥'),

            ('KRW',     fr'{self.number}\s*(?:вон(?:а|ы|)|krw|KRW|₩)\b'),
            ('KRW',     fr'{self.number}\s*₩'),
            ('KRW',     fr'₩{self.number}\b'),

            ('PLN',     fr'{self.number}\s*(?:злот(?:ый|ых|ого|ые)|pln|PLN|zł)\b'),
            ('PLN',     fr'{self.number}\s*zł'),

            ('TRY',     fr'{self.number}\s*(?:лир(?:а|ы|)|турецк(?:ая|ой|их|ую) лир(?:а|ы|)|try|TRY|₺|₤)\b'),
            ('TRY',     fr'{self.number}\s*₺'),
            ('TRY',     fr'{self.number}\s*₤'),
            ('TRY',     fr'₤{self.number}\b'),
            ('TRY',     fr'₺{self.number}\b'),

            ('CZK',     fr'{self.number}\s*(?:крон(?:а|ы|)|чешск(?:ая|ой|их|ую) крон(?:а|ы|)|czk|CZK|Kč|Kč)\b'),
            ('CZK',     fr'{self.number}\s*Kč'),

            ('UAH',     fr'{self.number}\s*(?:гривн(?:а|ы|)|гривен|грн|uah|UAH|₴)\b'),
            ('UAH',     fr'{self.number}\s*₴'),

            ('BYN',     fr'{self.number}\s*(?:белорусск(?:их|ого|ий|ие) руб(?:лей|ля|ль)|беларуск(?:их|ого|ий|ие) руб(?:лей|ля|ль)|byn|BYN|Br)\b'),
            ('BYN',     fr'{self.number}\s*Br'),
            ('AMD',     fr'{self.number}\s*(?:драм(?:ов|а|))\b'),
            ('CNY',     fr'{self.number}\s*(?:юан(?:ей|я|ь)|cny|CNY)\b'),
            ('GEL',     fr'{self.number}\s*(?:лари|gel|GEL)\b'),
            ('RSD',     fr'{self.number}\s*(?:динар(?:ов|а|)|rsd|RSD)\b'),
            ('THB',     fr'{self.number}\s*(?:бат(?:ов|а|)|thb|THB)\b'),
            ('KZT',     fr'{self.number}\s*(?:тенге|тг|kzt|KZT)\b'),
            ('CAD',     fr'{self.number}\s*(?:канадск(?:их|ого|ий) доллар(?:ов|а|)|cad|CAD)\b'),
            ('MXN',     fr'{self.number}\s*(?:песо|мексиканск(?:их|ого|ий|ое) песо|mxn|MXN)\b'),

            ('ARS',     fr'{self.number}\s*(?:аргентинск(?:их|ого|ий|ое) песо|ars|ARS)\b'),

            ('MDL',     fr'{self.number}\s*(?:ле(?:й|я|и)|mdl|MDL)\b'),
            ('MDL',     fr'{self.number}\s*(?:молдавск(?:их|ого|ий) ле(?:й|я|ев)|ле(?:й|я|ев)|mdl|MDL)\b'),

            ('RON',     fr'{self.number}\s*(?:румынск(?:их|ого|ий) ле(?:й|я|ев)|ле(?:й|я|ев)|leu|RON)\b'),
            ('RON',     fr'{self.number}\s*(?:рон(?:ов|а|))\b'),
            
            ('VND',     fr'{self.number}\s*(?:донг(?:ов|а|)|vnd|VND|₫|dd)\b'),
            ('VND',     fr'{self.number}\s*₫'),

            ('BGN',     fr'{self.number}\s*(?:лев(?:ов|а|)|болгарск(?:их|ого|ий) лев(?:ов|а|)|bgn|BGN|(?<!\w)лв(?!\w))\b'),
            ('BGN',     fr'{self.number}\s*(?<!\w)лв(?!\w)'),

            ('AED',     fr'{self.number}\s*(?:дирхам(?:ов|а|)|aed|AED|د.إ|dh)\b'),
            ('AED',     fr'{self.number}\s*د.إ'),
            ('AED',     fr'{self.number}\s*dh'),

            ('PHP',     fr'{self.number}\s*(?:филиппинск(?:их|ого|ий|ое) песо|piso|php|PHP|₱)\b'),
            ('PHP',     fr'{self.number}\s*₱'),
            ('PHP',     fr'₱{self.number}\b'),

            # Tajikistani somoni
            ('TJS',     fr'{self.number}\s*(?:сомони|tjs|TJS)\b'),

            # Uzbekistani so'm (sum) and som (user requested mapping to UZS)
            ('UZS',     fr'{self.number}\s*(?:сум(?:ов|а|)|сом(?:ов|а|)|uzs|UZS)\b')
        ]

        # Codes whose hand-written pattern already matches the bare "<amount> <CODE>"
        # form. Generating a fallback for them would only add a duplicate pass over
        # the text and a duplicate match that the overlap filter throws away anyway.
        # Detected by probing rather than hardcoded, so the two lists cannot drift apart.
        handwritten_res = [re.compile(p, re.IGNORECASE) for _, p in handwritten]

        def _already_matched(code: str) -> bool:
            probe = f"1 {code}"
            for compiled in handwritten_res:
                found = compiled.search(probe)
                if found and found.group(0) == probe:
                    return True
            return False

        # Fallback: "<amount> <ISO CODE>" for every known currency that no hand-written
        # pattern covers yet, so the long tail (KWD, CHF, NOK, ...) parses without a
        # hand-written regex.
        # (?-i:...) switches IGNORECASE off for the code itself: matching codes
        # case-insensitively would turn ordinary words into currency amounts
        # ("3 top", "5 mad", "2 all", "8 cup").
        self.patterns = handwritten + [
            (currency.code, rf'{self.number}\s*(?-i:{currency.code})\b')
            for currency in CURRENCIES.values()
            if currency.code not in AMBIGUOUS_CODES and not _already_matched(currency.code)
        ]

        self.compiled_patterns = [
            (curr, re.compile(pattern, re.IGNORECASE)) 
            for curr, pattern in self.patterns
        ]
    def _convert_amount(self, amount_str: str, currency: str) -> Tuple[float, str]:
        multiplier = 1
        clean_amount = amount_str
        base_currency = currency

        # mapping special currencies to base currencies
        currency_mapping = {
            'USDK': 'USD',
            'EURK': 'EUR',
            'RUBK': 'RUB',
            'USDCENT': 'USD',
            'EURCENT': 'EUR',
        }

        # multipliers for special currencies
        currency_multipliers = {
            'USDK': 1000,
            'EURK': 1000,
            'RUBK': 1000,
            'USDCENT': 0.01,
            'EURCENT': 0.01,
        }

        # if special currency, apply corresponding multiplier and get base currency
        if currency in currency_multipliers:
            multiplier = currency_multipliers[currency]
            base_currency = currency_mapping[currency]
            if not amount_str:
                if currency in ['USDK', 'EURK', 'RUBK']: #for 'кило...' without amount
                    return 1000.0, base_currency
                
        elif amount_str.lower().endswith('к'):
            multiplier = 1000
            clean_amount = amount_str.lower().rstrip('к')

        # Remove spaces first
        clean_amount = clean_amount.replace(' ', '')
        
        # Handle different number formats:
        # 1,000.50 or 1.000,50 or 1000,50 or 1000.50
        if clean_amount.count('.') > 1 or clean_amount.count(',') > 1:
            # Handle formats like 1,000,000 or 1.000.000
            if ',' in clean_amount and clean_amount.count(',') > 1:
                # For formats like 1,000,000
                clean_amount = clean_amount.replace(',', '')
            elif '.' in clean_amount and clean_amount.count('.') > 1:
                # For formats like 1.000.000
                clean_amount = clean_amount.replace('.', '')
            amount = float(clean_amount)
        else:
            if ',' in clean_amount and '.' in clean_amount: 
                # If both separators present, last one is decimal
                if clean_amount.rindex(',') > clean_amount.rindex('.'):
                    clean_amount = clean_amount.replace('.', '').replace(',', '.')
                else:
                    clean_amount = clean_amount.replace(',', '')
            elif ',' in clean_amount: 
                # Check if comma is decimal separator
                parts = clean_amount.split(',')
                if len(parts) == 2:
                    # Проверяем, является ли запятая десятичным разделителем
                    # Если число начинается с 0, и после запятой идут цифры, это десятичная дробь
                    if clean_amount.startswith('0,') or len(parts[1]) <= 2:
                        clean_amount = clean_amount.replace(',', '.')
                    else:
                        # Assume thousands separator
                        clean_amount = clean_amount.replace(',', '')
                else:
                    # Assume thousands separator
                    clean_amount = clean_amount.replace(',', '')
            
            try:
                amount = float(clean_amount)
            except ValueError:
                logger.error(f"Failed to convert '{clean_amount}' to float from original '{amount_str}'")
                amount = 0.0
            
        return amount * multiplier, base_currency

    def find_currencies(self, text: str) -> List[Tuple[float, str, str]]:
        """Find currencies in text
        Returns list of tuples: (amount: float, currency_code: str, original_text: str)
        """
        result = []
        matches = []

        # Only the length is logged: message texts never go into the logs.
        if len(text) > MAX_TEXT_LENGTH:
            logger.warning(f"Text of {len(text)} characters exceeds the {MAX_TEXT_LENGTH} character limit, skipping currency parsing")
            return result

        # Find all matches first
        for currency, pattern in self.compiled_patterns:
            for match in pattern.finditer(text):
                # Check that currency is surrounded by spaces or is at the beginning/end of text
                start_pos = match.start()
                end_pos = match.end()
                
                # Start validation: either it's the beginning of text or preceded by space or non-alphanumeric
                valid_start = start_pos == 0 or text[start_pos-1].isspace() or not text[start_pos-1].isalnum()
                
                # End validation: either it's the end of text or followed by space or non-alphanumeric
                valid_end = end_pos == len(text) or text[end_pos].isspace() or not text[end_pos].isalnum()
                
                # Additional check for special characters that should not be considered as separators
                special_chars = "#@^e%"
                if start_pos > 0 and text[start_pos-1] in special_chars:
                    valid_start = False
                
                if valid_start and valid_end:
                    self.current_match = match.group(0)
                    amount, base_currency = self._convert_amount(match.group('amount'), currency)
                    matches.append(( start_pos, end_pos, amount, base_currency, self.current_match ))
        
        # Sort matches by start position
        matches.sort(key=lambda x: x[0])
        
        # Filter overlapping matches
        if matches:
            current = matches[0]
            filtered = [current]
            
            for match in matches[1:]:
                if match[0] >= current[1]:  # If current match starts after previous ends
                    filtered.append(match)
                    current = match
            
            # Convert to required format
            result = [(m[2], m[3], m[4]) for m in filtered]
        
        return result

    def process_currencies(self, text: str) -> List[Tuple[float, str, str]]:
        return self.find_currencies(text)
