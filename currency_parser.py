# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

import re
from typing import List, Tuple

class CurrencyParser:
    def __init__(self):
        self.number = r'(?P<amount>(?:\d{1,3}(?:[., ]\d{3})*|\d+)(?:[.,]\d+)?(?:к)?)'
        self.current_match = ''

        self.patterns = [
            ('ILS',     fr'{self.number}\s*(?:шекел(?:ей|я|ь)|шек|шах|ils|ILS|₪)\b'),
            ('ILS',     fr'{self.number}\s*₪'),
    
            ('GBP',     fr'(?:£){self.number}\b'),
            ('GBP',     fr'{self.number}\s*(?:фунт(?:ов|а|)|паунд(?:ов|а|)|pound|gbp|GBP|gbr|GBR|£)\b'),
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

            ('BYN',     fr'{self.number}\s*(?:белорусск(?:их|ого|ий) руб(?:лей|ля|ль)|byn|BYN|Br)\b'),
            ('BYN',     fr'{self.number}\s*Br'),

            ('AMD',     fr'{self.number}\s*(?:драм(?:ов|а|))\b'),
            ('CNY',     fr'{self.number}\s*(?:юан(?:ей|я|ь)|cny|CNY)\b'),
            ('GEL',     fr'{self.number}\s*(?:лари|gel|GEL)\b'),
            ('RSD',     fr'{self.number}\s*(?:динар(?:ов|а|)|rsd|RSD)\b'),
            ('THB',     fr'{self.number}\s*(?:бат(?:ов|а|)|thb|THB)\b'),
            ('KZT',     fr'{self.number}\s*(?:тенге|тг|kzt|KZT)\b'),
            ('CAD',     fr'{self.number}\s*(?:канадск(?:их|ого|ий) доллар(?:ов|а|)|cad|CAD)\b'),
            ('MXN',     fr'{self.number}\s*(?:песо|мексиканск(?:их|ого|ий) песо|mxn|MXN)\b'),
            ('RON',     fr'{self.number}\s*(?:лей|лея|lei|ron|RON)\b'),
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
            clean_amount = clean_amount.replace(',', '').replace('.', '')
            amount = float(clean_amount)
        else:
            if ',' in clean_amount and '.' in clean_amount: # If both separators present, last one is decimal
                if clean_amount.rindex(',') > clean_amount.rindex('.'):
                    clean_amount = clean_amount.replace('.', '').replace(',', '.')
                else:
                    clean_amount = clean_amount.replace(',', '')
            elif ',' in clean_amount: # Check if comma is decimal separator
                parts = clean_amount.split(',')
                if len(parts[1]) <= 2:  # Assume decimal if 2 or fewer digits after comma
                    clean_amount = clean_amount.replace(',', '.')
                else:
                    clean_amount = clean_amount.replace(',', '')
            
            amount = float(clean_amount)
            
        return amount * multiplier, base_currency

    def find_currencies(self, text: str) -> List[Tuple[float, str, str]]:
        """Find currencies in text
        Returns list of tuples: (amount: float, currency_code: str, original_text: str)
        """
        result = []
        matches = []
        
        # Find all matches first
        for currency, pattern in self.compiled_patterns:
            for match in pattern.finditer(text):
                self.current_match = match.group(0)
                amount, base_currency = self._convert_amount(match.group('amount'), currency)
                matches.append(( match.start(), match.end(), amount, base_currency, self.current_match ))
        
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
