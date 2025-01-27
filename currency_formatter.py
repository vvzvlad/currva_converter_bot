# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

from typing import List, Tuple, Dict, Optional
from decimal import Decimal, ROUND_HALF_UP
import logging
import os
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(os.path.splitext(os.path.basename(__file__))[0])



class CurrencyFormatter:
    def __init__(self):
        # Currency code -> (flag, symbol)
        self.currency_formats = {
            'RUB': ('🇷🇺', '₽'),
            'USD': ('🇺🇸', '$'),
            'ILS': ('🇮🇱', '₪'),
            'GBP': ('🇬🇧', '£'),
            'EUR': ('🇪🇺', '€'),
            'JPY': ('🇯🇵', '¥'),
            'AMD': ('🇦🇲', '֏'),
            'CNY': ('🇨🇳', '¥'),
            'GEL': ('🇬🇪', '₾'),
            'RSD': ('🇷🇸', 'din'),
            'THB': ('🇹🇭', '฿'),
            'KZT': ('🇰🇿', '₸'),
            'CAD': ('🇨🇦', 'C$'),
            'MXN': ('🇲🇽', 'MX$'),
            'TRY': ('🇹🇷', '₺'),
            'PLN': ('🇵🇱', 'zł'),
            'CZK': ('🇨🇿', 'Kč'),
            'UAH': ('🇺🇦', '₴'),
            'BYN': ('🇧🇾', 'Br'),
            'RON': ('🇷🇴', 'lei'),
            'MDL': ('🇲🇩', 'lei'),
            'VND': ('🇻🇳', '₫'),
            'BGN': ('🇧🇬', 'лв'),
            'AED': ('🇦🇪', 'dh'),
        }
        self.target_currencies = list(self.currency_formats.keys())
        # Currencies to display in the message
        self.default_currencies = ['RUB', 'USD', 'ILS', 'EUR', 'GBP', "JPY", "AMD"]
        self.symbol_before_number = ['USD', 'JPY', 'GBP', 'CAD', 'THB']

    def _format_amount(self, amount: Decimal, currency: str) -> str:
        """Format amount with currency symbol and flag"""
        flag, symbol = self.currency_formats[currency]
        
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
        if currency in self.symbol_before_number:
            return f"{flag} {symbol}{formatted}"
        else:
            return f"{flag} {formatted} {symbol}"

    def format_conversion(self, currency_data: Tuple[float, str, str], rates: Dict[str, float], mode: str, user_currencies: Optional[List[str]] = None) -> str:
        """Format currency conversion result into message"""
        amount, currency, original = currency_data
        
        if mode == 'chat':
            if amount == 0: return "Нахуй иди"            
            if amount == 0.5 and currency == 'USD': return "In Da Club!"
    
        # Check if user has only the source currency in settings
        target_currencies = user_currencies if user_currencies else self.default_currencies
        if len(target_currencies) == 1 and target_currencies[0] == currency:
            return f"{original} (🇷🇺): других валют для конвертации не установлено. Используйте /currencies"
        
        if mode == 'chat':
            usd_amount = amount # if currency is USD 
            if currency != 'USD':
                rate = rates.get(f"{currency}_USD")
                if rate:
                    usd_amount = Decimal(str(amount)) * Decimal(str(rate))
            if usd_amount >= 1_000_000:
                return f"Откуда у тебя такие деньги, сынок?"
        
        # Initialize message based on mode
        if mode == 'chat':
            flag, _symbol = self.currency_formats[currency]
            message = f"{original} ({flag}) это"
        elif mode == 'inline':
            message = f"{original}"
        else:
            raise ValueError(f"Unknown mode: {mode}")
        
        # Special handling for pounds
        if currency == 'GBP' and ('фунт' in original.lower() or '£' in original):
            kg_amount = Decimal(str(amount)) * Decimal('0.45359237')  # 1 pound = 0.45359237 kg
            if mode == 'chat':
                message = f"{original} ({flag}) это {kg_amount:.1f} кг, а также"
            elif mode == 'inline':
                message = f"{original} ({kg_amount:.1f} кг)"
            else:
                raise ValueError(f"Unknown mode: {mode}")
        
        conversions = []
        for target_curr in target_currencies:
            if target_curr == currency:
                continue
                
            try:
                rate = rates.get(f"{currency}_{target_curr}")
                if rate is None:
                    continue
                    
                converted_amount = Decimal(str(amount)) * Decimal(str(rate))
                conversions.append(self._format_amount(converted_amount, target_curr))
            except Exception as e:
                logger.error(f"Error converting {amount} {currency} to {target_curr}: {str(e)}")
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
