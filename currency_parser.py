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
            ('ILS', fr'{self.number}\s*(?:шекел(?:ей|я|ь)|шек|шах|ils|ILS|₪)\b'),
            ('ILS', fr'{self.number}\s*₪'),

            ('GBP', fr'(?:£){self.number}\b'),
            ('GBP', fr'{self.number}\s*(?:фунт(?:ов|а|)|паунд(?:ов|а|)|pound|gbp|GBP|gbr|GBR|£)\b'),
            ('GBP', fr'{self.number}\s*£'),

            ('RUB', fr'{self.number}\s*(?:руб(?:лей|ля|ль)|₽|rub|RUB)\b'),
            ('RUB', fr'{self.number}\s*₽'),

            ('USD', fr'\${self.number}\b'),
            ('USD', fr'{self.number}\s*(?:доллар(?:ов|а|)|бакс(?:ов|а|)|usd|USD|\$)\b'),
            ('USD', fr'{self.number}\s*\$'),

            ('EUR', fr'€{self.number}\b'),
            ('EUR', fr'{self.number}\s*(?:евро|eur|EUR|€)\b'),
            ('EUR', fr'{self.number}\s*€'),

            ('JPY', fr'¥{self.number}\b'),
            ('JPY', fr'{self.number}\s*(?:йен(?:а|ы|)|¥|jpy|JPY)\b'),
            ('JPY', fr'{self.number}\s*¥'),
            
            ('AMD', fr'{self.number}\s*(?:драм(?:ов|а|))\b'),
            ('CNY', fr'{self.number}\s*(?:юан(?:ей|я|ь)|cny|CNY)\b'),
            ('GEL', fr'{self.number}\s*(?:лари|gel|GEL)\b'),
            ('RSD', fr'{self.number}\s*(?:динар(?:ов|а|)|rsd|RSD)\b'),
            ('THB', fr'{self.number}\s*(?:бат(?:ов|а|)|thb|THB)\b'),
            ('KZT', fr'{self.number}\s*(?:тенге|тг|kzt|KZT)\b'),
            ('CAD', fr'{self.number}\s*(?:канадск(?:их|ого|ий) доллар(?:ов|а|)|cad|CAD)\b'),

            ('USD', fr'{self.number}\s*(?:цент(?:ов|а|)|cent|cents)\b'),
            ('EUR', fr'{self.number}\s*(?:евроцент(?:ов|а|)|eurocent|eurocents)\b'),
        ]
        
        self.compiled_patterns = [
            (curr, re.compile(pattern, re.IGNORECASE)) 
            for curr, pattern in self.patterns
        ]

    def _convert_amount(self, amount_str: str) -> float:
        if amount_str.lower().endswith('к'):
            multiplier = 1000
            clean_amount = amount_str.lower().rstrip('к')
        else:
            multiplier = 1
            clean_amount = amount_str
        
        # Remove spaces first
        clean_amount = clean_amount.replace(' ', '')
        
        # Handle different number formats:
        # 1,000.50 or 1.000,50 or 1000,50 or 1000.50
        if clean_amount.count('.') > 1 or clean_amount.count(',') > 1:
            # Handle formats like 1,000,000 or 1.000.000
            clean_amount = clean_amount.replace(',', '').replace('.', '')
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
                if len(parts[1]) <= 2:  # Assume decimal if 2 or fewer digits after comma
                    clean_amount = clean_amount.replace(',', '.')
                else:
                    clean_amount = clean_amount.replace(',', '')
            
            amount = float(clean_amount)
        
        if any(cent in self.current_match.lower() for cent in ['цент', 'cent']):
            amount = amount / 100
            
        return amount * multiplier

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
                matches.append((
                    match.start(),
                    match.end(),
                    self._convert_amount(match.group('amount')),
                    currency,
                    self.current_match
                ))
        
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
