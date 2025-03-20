# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

from typing import List, Tuple, Dict, Optional, Final
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import logging
import os
import string

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(os.path.splitext(os.path.basename(__file__))[0])


# Emoji flags consist of two symbols, from the regional indicator symbols block.
# Those symbols can be combined according to ISO 3166-1 alpha-2 codes to get
# country flags. Since currency codes start with corresponding ISO 3166 country
# code, we can get flag from currency code automatically.
EMOJI_LETTERS: Final = {
    c: chr(ord("🇦") - ord("A") + ord(c))
    for c in string.ascii_uppercase
}


@dataclass
class CurrencyFormat:
    code: str
    symbol: str
    symbol_before_number: bool = False
    flag_override: str | None = None

    @property
    def flag(self):
        return self.flag_override or EMOJI_LETTERS[self.code[0]] + EMOJI_LETTERS[self.code[1]]


class CurrencyFormatter:
    def __init__(self):
        self.currency_formats = {
            'AED': CurrencyFormat('AED', 'dh'),
            'AFN': CurrencyFormat('AFN', 'AFN'),  # there’s a currency symbol but it’s RTL
            'ALL': CurrencyFormat('ALL', 'L'),
            'AMD': CurrencyFormat('AMD', '֏'),
            'ANG': CurrencyFormat('ANG', 'ƒ', flag_override="🇨🇼"),  # https://en.wikipedia.org/wiki/Netherlands_Antillean_guilder
            'AOA': CurrencyFormat('AOA', 'Kz'),
            'ARS': CurrencyFormat('ARS', '$', symbol_before_number=True),
            'AUD': CurrencyFormat('AUD', 'A$', symbol_before_number=True),
            'AWG': CurrencyFormat('AWG', 'ƒ'),
            'AZN': CurrencyFormat('AZN', '₼'),
            'BAM': CurrencyFormat('BAM', 'KM'),
            'BBD': CurrencyFormat('BBD', '$', symbol_before_number=True),
            'BDT': CurrencyFormat('BDT', '৳'),
            'BGN': CurrencyFormat('BGN', 'лв'),
            'BHD': CurrencyFormat('BHD', 'BD'),
            'BIF': CurrencyFormat('BIF', 'FBu'),
            'BMD': CurrencyFormat('BMD', '$', symbol_before_number=True),
            'BND': CurrencyFormat('BND', '$', symbol_before_number=True),
            'BOB': CurrencyFormat('BOB', 'Bs'),
            'BRL': CurrencyFormat('BRL', 'R$', symbol_before_number=True),
            'BSD': CurrencyFormat('BSD', '$', symbol_before_number=True),
            'BTN': CurrencyFormat('BTN', 'Nu'),
            'BWP': CurrencyFormat('BWP', 'P'),
            'BYN': CurrencyFormat('BYN', 'Br'),
            'BZD': CurrencyFormat('BZD', '$', symbol_before_number=True),
            'CAD': CurrencyFormat('CAD', 'C$', symbol_before_number=True),
            'CDF': CurrencyFormat('CDF', 'FC'),
            'CHF': CurrencyFormat('CHF', 'Fr'),
            'CLP': CurrencyFormat('CLP', '$', symbol_before_number=True),
            'CNY': CurrencyFormat('CNY', '¥'),
            'COP': CurrencyFormat('COP', '$', symbol_before_number=True),
            'CRC': CurrencyFormat('CRC', '₡'),
            'CUP': CurrencyFormat('CUP', '$', symbol_before_number=True),
            'CVE': CurrencyFormat('CVE', '$', symbol_before_number=True),
            'CZK': CurrencyFormat('CZK', 'Kč'),
            'DJF': CurrencyFormat('DJF', 'Fdj'),
            'DKK': CurrencyFormat('DKK', 'kr'),
            'DOP': CurrencyFormat('DOP', '$', symbol_before_number=True),
            'DZD': CurrencyFormat('DZD', 'DA'),
            'EGP': CurrencyFormat('EGP', 'LE'),
            'ERN': CurrencyFormat('ERN', 'Nkf'),
            'ETB': CurrencyFormat('ETB', 'Br'),
            'EUR': CurrencyFormat('EUR', '€'),
            'FJD': CurrencyFormat('FJD', '$', symbol_before_number=True),
            'FKP': CurrencyFormat('FKP', '£'),
            'GBP': CurrencyFormat('GBP', '£', symbol_before_number=True),
            'GEL': CurrencyFormat('GEL', '₾'),
            'GHS': CurrencyFormat('GHS', '₵'),
            'GIP': CurrencyFormat('GIP', '£'),
            'GMD': CurrencyFormat('GMD', 'D'),
            'GNF': CurrencyFormat('GNF', 'Fr'),
            'GTQ': CurrencyFormat('GTQ', 'Q'),
            'GYD': CurrencyFormat('GYD', '$', symbol_before_number=True),
            'HKD': CurrencyFormat('HKD', 'H$', symbol_before_number=True),
            'HNL': CurrencyFormat('HNL', 'L'),
            'HTG': CurrencyFormat('HTG', 'G'),
            'HUF': CurrencyFormat('HUF', 'Ft'),
            'IDR': CurrencyFormat('IDR', 'Rp'),
            'ILS': CurrencyFormat('ILS', '₪'),
            'INR': CurrencyFormat('INR', '₹'),
            'IQD': CurrencyFormat('IQD', 'ID'),
            'IRR': CurrencyFormat('IRR', 'Rls'),
            'ISK': CurrencyFormat('ISK', 'kr'),
            'JMD': CurrencyFormat('JMD', '$', symbol_before_number=True),
            'JOD': CurrencyFormat('JOD', 'JD'),
            'JPY': CurrencyFormat('JPY', '¥', symbol_before_number=True),
            'KES': CurrencyFormat('KES', 'Shs'),
            'KGS': CurrencyFormat('KGS', '⃀'),
            'KHR': CurrencyFormat('KHR', '៛'),
            'KMF': CurrencyFormat('KMF', 'FC'),
            'KPW': CurrencyFormat('KPW', '₩'),
            'KRW': CurrencyFormat('KRW', '₩'),
            'KWD': CurrencyFormat('KWD', 'KD'),
            'KYD': CurrencyFormat('KYD', '$', symbol_before_number=True),
            'KZT': CurrencyFormat('KZT', '₸'),
            'LAK': CurrencyFormat('LAK', '₭'),
            'LBP': CurrencyFormat('LBP', 'LL'),
            'LKR': CurrencyFormat('LKR', 'Rs'),
            'LRD': CurrencyFormat('LRD', '$', symbol_before_number=True),
            'LSL': CurrencyFormat('LSL', 'M'),
            'LYD': CurrencyFormat('LYD', 'LD'),
            'MAD': CurrencyFormat('MAD', 'DH'),
            'MDL': CurrencyFormat('MDL', 'lei'),
            'MGA': CurrencyFormat('MGA', 'Ar'),
            'MKD': CurrencyFormat('MKD', 'DEN'),
            'MMK': CurrencyFormat('MMK', 'Ks'),
            'MNT': CurrencyFormat('MNT', '₮'),
            'MOP': CurrencyFormat('MOP', '$', symbol_before_number=True),
            'MRU': CurrencyFormat('MRU', 'UM'),
            'MUR': CurrencyFormat('MUR', 'Rs'),
            'MVR': CurrencyFormat('MVR', 'Rf'),
            'MWK': CurrencyFormat('MWK', 'K'),
            'MXN': CurrencyFormat('MXN', 'MX$', symbol_before_number=True),
            'MYR': CurrencyFormat('MYR', 'RM'),
            'MZN': CurrencyFormat('MZN', 'Mt'),
            'NAD': CurrencyFormat('NAD', '$', symbol_before_number=True),
            'NGN': CurrencyFormat('NGN', '₦'),
            'NIO': CurrencyFormat('NIO', 'C$', symbol_before_number=True),
            'NOK': CurrencyFormat('NOK', 'kr'),
            'NPR': CurrencyFormat('NPR', 'रु'),
            'NZD': CurrencyFormat('NZD', 'NZ$', symbol_before_number=True),
            'OMR': CurrencyFormat('OMR', 'RO'),
            'PAB': CurrencyFormat('PAB', 'B/'),
            'PEN': CurrencyFormat('PEN', 'S/'),
            'PGK': CurrencyFormat('PGK', 'K'),
            'PHP': CurrencyFormat('PHP', '₱', symbol_before_number=True),
            'PKR': CurrencyFormat('PKR', 'Rs'),
            'PLN': CurrencyFormat('PLN', 'zł'),
            'PYG': CurrencyFormat('PYG', '₲'),
            'QAR': CurrencyFormat('QAR', 'QR'),
            'RON': CurrencyFormat('RON', 'lei'),
            'RSD': CurrencyFormat('RSD', 'din'),
            'RUB': CurrencyFormat('RUB', '₽'),
            'RWF': CurrencyFormat('RWF', 'FRw'),
            'SAR': CurrencyFormat('SAR', 'Rls'),
            'SBD': CurrencyFormat('SBD', '$', symbol_before_number=True),
            'SCR': CurrencyFormat('SCR', 'Rs'),
            'SDG': CurrencyFormat('SDG', 'LS'),
            'SEK': CurrencyFormat('SEK', 'kr'),
            'SGD': CurrencyFormat('SGD', '$', symbol_before_number=True),
            'SHP': CurrencyFormat('SHP', '£'),
            'SOS': CurrencyFormat('SOS', 'Shs'),
            'SRD': CurrencyFormat('SRD', '$', symbol_before_number=True),
            'SYP': CurrencyFormat('SYP', 'LS'),
            'SZL': CurrencyFormat('SZL', 'E'),
            'THB': CurrencyFormat('THB', '฿', symbol_before_number=True),
            'TJS': CurrencyFormat('TJS', 'SM'),
            'TMT': CurrencyFormat('TMT', 'm'),
            'TND': CurrencyFormat('TND', 'DT'),
            'TOP': CurrencyFormat('TOP', 'T$', symbol_before_number=True),
            'TRY': CurrencyFormat('TRY', '₺'),
            'TTD': CurrencyFormat('TTD', '$', symbol_before_number=True),
            'TWD': CurrencyFormat('TWD', '$', symbol_before_number=True),
            'TZS': CurrencyFormat('TZS', 'Shs'),
            'UAH': CurrencyFormat('UAH', '₴'),
            'UGX': CurrencyFormat('UGX', 'Shs'),
            'USD': CurrencyFormat('USD', '$', symbol_before_number=True),
            'UYU': CurrencyFormat('UYU', '$', symbol_before_number=True),
            'UZS': CurrencyFormat('UZS', 'Sʻ'),
            'VND': CurrencyFormat('VND', '₫'),
            'VUV': CurrencyFormat('VUV', 'VT'),
            'WST': CurrencyFormat('WST', '$'),
        }

        # Default currencies to display in the message
        self.default_currencies = ['RUB', 'USD', 'ILS', 'EUR', 'GBP', "JPY", "AMD"]
        self.target_currencies = list(self.currency_formats.keys())

    def _format_amount(self, amount: Decimal, currency_code: str) -> str:
        """Format amount with currency symbol and flag"""
        currency = self.currency_formats[currency_code]

        # Rounding: to whole numbers if greater than 20, otherwise to 2 decimal places
        if amount > 20:
            amount_int = int(amount.quantize(Decimal('1.'), rounding=ROUND_HALF_UP))
            # Format numbers greater than 10000 with spaces between thousands
            if amount_int > 10000:
                formatted = f"{amount_int:,}".replace(",", " ")
            else:
                formatted = str(amount_int)
        else:
            # Round to 2 decimal places
            rounded = amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            
            if rounded == 0:
                formatted = "0"
            else:
                # Check if it's a whole number
                if rounded == rounded.quantize(Decimal('1.'), rounding=ROUND_HALF_UP):
                    formatted = str(int(rounded))
                else:
                    # Get decimal part
                    decimal_str = str(rounded).split('.')[1] if '.' in str(rounded) else '00'
                    
                    # If tenths digit is 0, show 2 decimal places
                    if decimal_str[0] == '0':
                        formatted = f"{rounded:.2f}"
                    else:
                        # Otherwise show just 1 decimal place
                        formatted = f"{rounded:.1f}".rstrip('0').rstrip('.')
        
        # For USD, EUR and GBP, place the currency symbol before the number
        if currency.symbol_before_number:
            return f"{currency.flag} {currency.symbol}{formatted}"
        else:
            return f"{currency.flag} {formatted} {currency.symbol}"

    def format_conversion(self, currency_data: Tuple[float, str, str], rates: Dict[str, float], mode: str, user_currencies: Optional[List[str]] = None) -> str:
        """Format currency conversion result into message"""
        amount, currency_code, original = currency_data
        currency = self.currency_formats[currency_code]

        if mode == 'chat':
            if amount == 0: return "Нахуй иди"            
            if amount == 0.5 and currency_code == 'USD': return "In Da Club!"
    
        # Check if user has only the source currency in settings
        target_currencies = user_currencies if user_currencies else self.default_currencies
        if len(target_currencies) == 1 and target_currencies[0] == currency_code:
            return f"{original} ({currency.flag}): других валют для конвертации не установлено. Используйте /currencies"

        if mode == 'chat':
            usd_amount = amount # if currency is USD 
            if currency_code != 'USD':
                rate = rates.get(f"{currency_code}_USD")
                if rate:
                    usd_amount = Decimal(str(amount)) * Decimal(str(rate))
            if usd_amount >= 1_000_000:
                return f"Откуда у тебя такие деньги, сынок?"
        
        # Initialize message based on mode
        if mode == 'chat':
            message = f"{original} ({currency.flag}) это"
        elif mode == 'inline':
            message = f"{original}"
        else:
            raise ValueError(f"Unknown mode: {mode}")
        
        # Special handling for pounds
        if currency_code == 'GBP' and ('фунт' in original.lower() or '£' in original):
            kg_amount = Decimal(str(amount)) * Decimal('0.45359237')  # 1 pound = 0.45359237 kg
            if mode == 'chat':
                message = f"{original} ({currency.flag}) это {kg_amount:.1f} кг, а также"
            elif mode == 'inline':
                message = f"{original} ({kg_amount:.1f} кг)"
            else:
                raise ValueError(f"Unknown mode: {mode}")
        
        conversions = []
        for target_curr in target_currencies:
            if target_curr == currency_code:
                continue
                
            try:
                rate = rates.get(f"{currency_code}_{target_curr}")
                if rate is None:
                    continue
                    
                converted_amount = Decimal(str(amount)) * Decimal(str(rate))
                conversions.append(self._format_amount(converted_amount, target_curr))
            except Exception as e:
                logger.error(f"Error converting {amount} {currency_code} to {target_curr}: {str(e)}")
                continue
                
        if conversions:
            if mode == 'chat':
                message += " " + ", ".join(conversions)
            elif mode == 'inline':
                message += " (" + ", ".join(conversions) + ")"
        else:
            message += " (нет доступных курсов конвертации)"
            
        return message
    
    def format_multiple_conversions(self, currency_list: List[Tuple[float, str, str]], rates: Dict[str, float], mode: str = 'chat', user_currencies: Optional[List[str]] = None) -> str:
        """Format multiple currency conversions"""
        if not currency_list:
            return None 
            
        # Deduplication by amount and currency
        seen = set()
        unique_conversions = []
        for amount, curr, original in currency_list:
            key = (amount, curr)
            if key not in seen:
                seen.add(key)
                unique_conversions.append((amount, curr, original))
                
        # Limit number of conversions to 10
        if len(unique_conversions) > 10:
            unique_conversions = unique_conversions[:10]
            
        conversions = []
        for amount, curr, original in unique_conversions:
            conversion = self.format_conversion((amount, curr, original), rates, mode=mode, user_currencies=user_currencies)
            if conversion:
                conversions.append(conversion)
                
        if len(currency_list) > 10:
            conversions.append("... и остальные (сами считайте)")
                
        return "\n".join(conversions)
