from typing import List, Tuple, Dict
from decimal import Decimal, ROUND_HALF_UP
import logging

logger = logging.getLogger(__name__)


class CurrencyFormatter:
    def __init__(self):
        # Currency code -> (flag, symbol)
        self.currency_formats = {
            'ILS': ('🇮🇱', '₪'),
            'GBP': ('🇬🇧', '£'),
            'RUB': ('🇷🇺', '₽'),
            'USD': ('🇺🇸', '$'),
            'EUR': ('🇪🇺', '€'),
            'JPY': ('🇯🇵', '¥'),
            'AMD': ('🇦🇲', '֏'),
            'CNY': ('🇨🇳', '¥'),
            'GEL': ('🇬🇪', '₾'),
            'JOD': ('🇯🇴', 'د.ا'),
            'THB': ('🇹🇭', '฿'),
            'KZT': ('🇰🇿', '₸')
        }
        # Все поддерживаемые валюты
        self.target_currencies = list(self.currency_formats.keys())
        # Валюты для показа в сообщении (основные)
        self.display_currencies = ['USD', 'EUR', 'GBP', 'RUB', 'ILS', "JPY", "AMD"]

    def _format_amount(self, amount: Decimal, currency: str) -> str:
        """Format amount with currency symbol and flag"""
        flag, symbol = self.currency_formats[currency]
        
        # Округление: до целых если больше 20, иначе до десятых
        if amount > 20:
            amount_int = int(amount.quantize(Decimal('1.'), rounding=ROUND_HALF_UP))
            # Форматируем числа больше 10000 с пробелами между тысячами
            if amount_int > 10000:
                formatted = f"{amount_int:,}".replace(",", " ")
            else:
                formatted = str(amount_int)
        else:
            formatted = str(amount.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))
        
        # Для USD, EUR и GBP символ валюты ставим перед числом
        if currency in ['USD', 'EUR', 'GBP']:
            return f"{flag} {symbol}{formatted}"
        else:
            return f"{flag} {formatted} {symbol}"

    def format_conversion(self, currency_data: Tuple[float, str, str], rates: Dict[str, float]) -> str:
        """Format currency conversion result into message"""
        amount, currency, original = currency_data
        
        if amount == 0: return "Нахуй пошел"            
        if amount == 0.5 and currency == 'USD': return "In Da Club!"
            
        # Start with original amount
        flag, symbol = self.currency_formats[currency]
        
        # Проверка на большие суммы в долларах (конвертируем в USD если это не USD)
        usd_amount = amount
        if currency != 'USD':
            rate = rates.get(f"{currency}_USD")
            if rate:
                usd_amount = Decimal(str(amount)) * Decimal(str(rate))
        
        if usd_amount > 1_000_000:
            return f"Откуда у тебя такие деньги, сынок?"
            
        message = f"{original} ({flag}) это"
        
        # Специальная обработка для фунтов
        if currency == 'GBP' and ('фунт' in original.lower() or '£' in original):
            kg_amount = Decimal(str(amount)) * Decimal('0.45359237')  # 1 фунт = 0.45359237 кг
            message = f"{original} ({flag}) это {kg_amount:.1f} кг, а также"
        
        # Convert to display currencies only
        conversions = []
        for target_curr in self.display_currencies:
            if target_curr == currency:
                continue
                
            try:
                rate = rates.get(f"{currency}_{target_curr}")
                if rate is None:
                    continue
                    
                converted_amount = Decimal(str(amount)) * Decimal(str(rate))
                conversions.append(self._format_amount(converted_amount, target_curr))
            except Exception as e:
                logger.error(f"Error formatting currency {target_curr}: {e}")
                continue
                
        if conversions:
            message += " " + ", ".join(conversions)
        else:
            message += " (нет доступных курсов конвертации)"
            
        return message
    
    def format_multiple_conversions(self, currency_list: List[Tuple[float, str, str]], rates: Dict[str, float]) -> str:
        """Format multiple currency conversions"""
        if not currency_list:
            return None 
            
        messages = []
        for curr_data in currency_list[:3]:  # Only process first 3 currencies
            messages.append(self.format_conversion(curr_data, rates))
            
        return "\n".join(messages) 