import re
import requests
import telebot
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import os
import time
import threading
import random
import json
import logging
import signal
import os
import sys
from pathlib import Path
import glob

import requests.exceptions
from urllib3.exceptions import NewConnectionError

import telebot
from telebot import types
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from json.decoder import JSONDecodeError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

bot_token = os.getenv('BOT_TOKEN')
if not bot_token:
    logger.error("BOT_TOKEN environment variable is not set.")
    sys.exit("Error: BOT_TOKEN environment variable is not set.")
logger.info(f"Bot init, token: {bot_token}")
bot = telebot.TeleBot(bot_token)

api_key = os.getenv('API_KEY')
if not api_key:
    logger.error("API_KEY environment variable is not set.")
    sys.exit("Error: API_KEY environment variable is not set.")
logger.info(f"API key: {api_key}")

# Словарь числительных
NUMBER_WORDS = {
    'ноль': 0, 'нуль': 0,
    'один': 1, 'одна': 1, 'полтора': 1.5,
    'два': 2, 'две': 2,
    'три': 3, 'четыре': 4, 'пять': 5,
    'шесть': 6, 'семь': 7, 'восемь': 8,
    'девять': 9, 'десять': 10,
    'одиннадцать': 11, 'двенадцать': 12,
    'тринадцать': 13, 'четырнадцать': 14,
    'пятнадцать': 15, 'шестнадцать': 16,
    'семнадцать': 17, 'восемнадцать': 18,
    'девятнадцать': 19, 'двадцать': 20,
    'тридцать': 30, 'сорок': 40, 'пятьдесят': 50,
    'шестьдесят': 60, 'семьдесят': 70,
    'восемьдесят': 80, 'девяносто': 90,
    'сто': 100, 'двести': 200, 'триста': 300,
    'четыреста': 400, 'пятьсот': 500
}

# Функция для конвертации текстового числа в число
def word_to_number(text: str) -> float:
    words = text.lower().split()
    total = 0
    current = 0
    
    # Проверяем, что хотя бы одно слово является числом
    has_number = False
    for word in words:
        if word in NUMBER_WORDS:
            has_number = True
            break
    
    if not has_number:
        raise ValueError(f"No valid numbers found in: {text}")
    
    for word in words:
        if word in NUMBER_WORDS:
            if NUMBER_WORDS[word] == 100:
                if current == 0:
                    current = 1
                current *= NUMBER_WORDS[word]
            else:
                current += NUMBER_WORDS[word]
        elif word == 'тысяч' or word == 'тысяча' or word == 'тысячи':
            if current == 0:
                current = 1
            total += current * 1000
            current = 0
            
    total += current
    if total == 0:
        raise ValueError(f"Failed to parse number from: {text}")
    return total

# Модифицируем паттерны
CURRENCY_PATTERNS = {
    'AMD': r'(?:(\d+(?:[.,]\d+)?)|(?:([а-яА-Я\s]+)))\s*(к|k|К|K)?\s*(?:драм(?:ов|а|))\b',
    'ILS': r'(?:(\d+(?:[.,]\d+)?)|(?:([а-яА-Я\s]+)))\s*(к|k|К|K)?\s*(?:шекел(?:ей|я|ь)|шек|шах|ils|ILS)\b',
    'GBP': r'(?:£)?(?:(\d+(?:[.,]\d+)?)|(?:([а-яА-Я\s]+)))\s*(к|k|К|K)?\s*(?:фунт(?:ов|а|)|паунд(?:ов|а|)|pound|gbp|GBP|gbr|GBR|£)\b',
    'RUB': r'(?:(\d+(?:[.,]\d+)?)|(?:([а-яА-Я\s]+)))\s*(к|k|К|K)?\s*(?:руб(?:лей|ля|ль)|₽|rub|RUB|(?<=\s)₽)\b',
    'USD': r'(?:\$)?(?:(\d+(?:[.,]\d+)?)|(?:([а-яА-Я\s]+)))\s*(к|k|К|K)?\s*(?:доллар(?:ов|а|)|бакс(?:ов|а|)|usd|USD|\$)\b',
    'EUR': r'(?:(\d+(?:[.,]\d+)?)|(?:([а-яА-Я\s]+)))\s*(к|k|К|K)?\s*(?:евро|eur|EUR|€)\b',
    'JPY': r'(?:(\d+(?:[.,]\d+)?)|(?:([а-яА-Я\s]+)))\s*(к|k|К|K)?\s*(?:йен(?:а|ы|)|¥|jpy|JPY)\b',
    'CNY': r'(?:(\d+(?:[.,]\d+)?)|(?:([а-яА-Я\s]+)))\s*(к|k|К|K)?\s*(?:юан(?:ей|я|ь)|cny|CNY)\b',
    'GEL': r'(?:(\d+(?:[.,]\d+)?)|(?:([а-яА-Я\s]+)))\s*(к|k|К|K)?\s*(?:лари|gel|GEL)\b',
    'JOD': r'(?:(\d+(?:[.,]\d+)?)|(?:([а-яА-Я\s]+)))\s*(к|k|К|K)?\s*(?:динар(?:ов|а|)|jod|JOD)\b',
    'THB': r'(?:(\d+(?:[.,]\d+)?)|(?:([а-яА-Я\s]+)))\s*(к|k|К|K)?\s*(?:бат(?:ов|а|)|thb|THB)\b',
    'KZT': r'(?:(\d+(?:[.,]\d+)?)|(?:([а-яА-Я\s]+)))\s*(к|k|К|K)?\s*(?:тенге|тг|kzt|KZT)\b'
}

# Конфигурация валют
CURRENCIES = {
    'RUB': {'symbol': '₽', 'target': True, 'flag': '🇷🇺'},
    'ILS': {'symbol': '₪', 'target': True, 'flag': '🇮🇱'},
    'USD': {'symbol': '$', 'target': True, 'flag': '🇺🇸'},
    'GBP': {'symbol': '£', 'target': True, 'flag': '🇬🇧'},
    'EUR': {'symbol': '€', 'target': True, 'flag': '🇪🇺'},
    'JPY': {'symbol': '¥', 'target': True, 'flag': '🇯🇵'},
    'CNY': {'symbol': '¥', 'target': False, 'flag': '🇨🇳'},
    'GEL': {'symbol': '₾', 'target': False, 'flag': '🇬🇪'},
    'JOD': {'symbol': 'د.ا', 'target': False, 'flag': '🇯🇴'},
    'THB': {'symbol': '฿', 'target': False, 'flag': '🇹🇭'},
    'AMD': {'symbol': '֏', 'target': True, 'flag': '🇦🇲'},
    'KZT': {'symbol': '₸', 'target': False, 'flag': '🇰🇿'}
}

# Генерируем списки из конфигурации
ALL_CURRENCIES = list(CURRENCIES.keys())
TARGET_CURRENCIES = [code for code, info in CURRENCIES.items() if info['target']]

class ExchangeRateCache:
    def __init__(self, update_interval: int = 7200):
        logger.info("Initializing ExchangeRateCache")
        self._rates: Dict[str, Dict[str, float]] = {}
        self._update_interval = timedelta(seconds=update_interval)
        self._lock = threading.Lock()
        self._cache_file = "exchange_rates_cache.json"
        self._should_update = False
        
        self._load_cache()
        
        now = datetime.now()
        logger.info(f"Current time: {now.isoformat()}")
        logger.info(f"Last update: {self._last_update.isoformat()}")
        logger.info(f"Update interval: {update_interval} seconds")
        
        self._should_update = now - self._last_update > self._update_interval
        logger.info(f"Should update on start: {self._should_update}")
        if not self._should_update:
            logger.info("Cache is fresh, skipping initial update")
        
        logger.info("Starting update thread")
        self._update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self._update_thread.start()
    
    def _load_cache(self) -> None:
        """Load exchange rates from cache file"""
        try:
            if os.path.exists(self._cache_file):
                with open(self._cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    if cache_data.get('rates'): 
                        self._rates = cache_data['rates']
                        self._last_update = datetime.fromisoformat(cache_data['last_update'])
                        return

            self._last_update = datetime.now() - timedelta(hours=3)
        except Exception as e:
            logger.error(f"Failed to load cache file: {e}")
            self._last_update = datetime.now() - timedelta(hours=3)
    


    def _save_cache(self) -> None:
        """Save current exchange rates to cache file"""
        try:
            cache_data = {
                'rates': self._rates,
                'last_update': self._last_update.isoformat()
            }
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)
            logger.info("Saved rates to cache file")
        except Exception as e:
            logger.error(f"Failed to save cache file: {e}")
    
    def get_rate(self, from_currency: str, to_currency: str) -> Optional[float]:
        """Get exchange rate from cache"""
        with self._lock:
            if from_currency in self._rates and to_currency in self._rates[from_currency]:
                return self._rates[from_currency][to_currency]
            return None
    
    def _update_loop(self):
        """Background thread that updates all rates periodically"""
        logger.info("Update loop started")
        while True:
            now = datetime.now()
            logger.info(f"Update loop iteration at {now.isoformat()}")
            logger.info(f"Last update was at {self._last_update.isoformat()}")
            logger.info(f"Should update: {self._should_update}")
            
            if self._should_update:
                logger.info("Starting update")
                self._update_all_rates()
                self._last_update = datetime.now()
                logger.info(f"Update completed at {self._last_update.isoformat()}")
                self._should_update = False
            
            old_should_update = self._should_update
            self._should_update = now - self._last_update > self._update_interval
            if self._should_update != old_should_update:
                logger.info(f"Should update changed to: {self._should_update}")
                logger.info(f"Current time: {now.isoformat()}")
                logger.info(f"Last update: {self._last_update.isoformat()}")
            
            time.sleep(300)
    
    def _update_all_rates(self) -> None:
        """Update rates for all currencies"""
        logger.info("Starting full rates update")
        new_rates = {}
        
        try:
            url = "https://api.apilayer.com/currency_data/live"
            headers = {"apikey": api_key}
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if not result.get('success'):
                logger.error(f"API request failed. Response: {result}")
                return
            
            usd_rates = {}
            for key, value in result['quotes'].items():
                currency = key[3:]  # Убираем 'USD' из начала ключа
                usd_rates[currency] = value
            
            # Вычисляем кросс-курсы для ВСЕХ валют
            for base in ALL_CURRENCIES: 
                base_in_usd = 1.0 / usd_rates[base] if base != 'USD' else 1.0
                rates = {}
                
                for target in ALL_CURRENCIES: 
                    if target != base:
                        target_rate = usd_rates[target] if target != 'USD' else 1.0
                        rates[target] = target_rate * base_in_usd
                
                new_rates[base] = rates
            
            with self._lock:
                self._rates = new_rates
                self._save_cache()
                logger.info("Successfully updated all rates")
                
        except Exception as e:
            logger.error(f"Failed to update rates: {str(e)}")

rate_cache = ExchangeRateCache()

def extract_amount_and_currency(text: str) -> List[Tuple[float, str]]:
    found_currencies = []
    
    for currency, pattern in CURRENCY_PATTERNS.items():
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                if match.group(1):  # Если нашли цифровое значение
                    amount_str = match.group(1).replace(',', '.')
                    amount = float(amount_str)
                #elif match.group(2):  # Если нашли текстовое значение
                #    amount = word_to_number(match.group(2))
                else:
                    continue
                
                # Проверяем на ноль ДО умножения на 1000
                if abs(amount) < 0.000001:
                    logger.info("Found zero amount")
                    return [(-1, currency)]
                
                if amount < 0:
                    logger.info(f"Found negative amount: {amount}")
                    continue
                    
                if match.group(3):  # Проверка 'к' теперь в группе 3
                    amount *= 1000
                
                # Проверяем на слишком большую сумму
                if currency == 'USD' and amount > 1000000:
                    logger.info(f"Found too large amount: {amount} USD")
                    return [(-2, currency)]
                elif currency != 'USD':
                    usd_rate = rate_cache.get_rate(currency, 'USD')
                    if usd_rate and amount * usd_rate > 1000000:
                        logger.info(f"Found too large amount: {amount} {currency} = {amount * usd_rate} USD")
                        return [(-2, currency)]
                
                found_currencies.append((amount, currency))
            except ValueError:
                logger.info(f"Failed to parse amount from: {match.group(0)}")
                continue
    
    return found_currencies

def convert_currency(amount: float, from_currency: str, to_currency: str) -> float:
    """Convert amount from one currency to another using cached exchange rates"""
    if from_currency == to_currency:
        return amount
        
    rate = rate_cache.get_rate(from_currency, to_currency)
    if rate is None:
        logger.error(f"Failed to get rate for {from_currency} to {to_currency}")
        return 0
        
    converted_amount = amount * rate
    logger.info(f"Converted {amount} {from_currency} to {converted_amount} {to_currency} (rate: {rate})")
    return converted_amount

def format_currency(amount: float, currency: str) -> str:
    """Format currency amount with proper symbols"""
    # Округляем до целого если больше 10, иначе до одного знака после запятой
    formatted_amount = int(round(amount)) if amount >= 10 else round(amount, 1)
    
    # Форматируем с разделением тысяч если число больше 10000
    if formatted_amount >= 10000:
        formatted_amount = f"{formatted_amount:,}".replace(',', ' ')
    
    return f"{CURRENCIES[currency]['flag']} {formatted_amount} {CURRENCIES[currency]['symbol']}"

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Handle incoming messages and convert currencies if found"""
    try:
        if re.search(r'\d+[^\d\s,\.кkКK]+\d+', message.text):
            bot.reply_to(message, "Некорректный формат числа")
            return
            
        found_currencies = extract_amount_and_currency(message.text)
        
        if not found_currencies:
            return
            
        logger.info(f"Processing message: {message.text}")
        logger.info(f"Found currencies: {found_currencies}")
        
        amount, base_currency = found_currencies[0]
        if amount == -1:
            bot.reply_to(message, "нахуй пошел")
            return
        elif amount == -2:
            bot.reply_to(message, "откуда у тебя такие деньги, сынок")
            return
        
        conversion_results = []
        
        pattern = CURRENCY_PATTERNS[base_currency]
        match = re.search(pattern, message.text, re.IGNORECASE)
        original_text = message.text[match.start():match.end()]
        
        # Добавляем конвертацию в килограммы для фунтов
        if base_currency == 'GBP' and 'фунт' in original_text.lower():
            kg_amount = amount * 0.45359237  # 1 фунт = 0.45359237 кг
            if kg_amount >= 10:
                kg_text = f"{int(round(kg_amount))} кг"
            else:
                kg_text = f"{round(kg_amount, 1)} кг"
            conversion_results.append(kg_text)
        
        for target_currency in TARGET_CURRENCIES:
            if target_currency != base_currency:
                converted_amount = convert_currency(amount, base_currency, target_currency)
                if converted_amount > 0:
                    conversion_results.append(format_currency(converted_amount, target_currency))
        
        if conversion_results:
            response_text = f'{original_text} это {", ".join(conversion_results)}'
            bot.reply_to(message, response_text)
        else:
            error_msg = "Не удалось получить курсы валют"
            bot.reply_to(message, error_msg)
                
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}", exc_info=True)
        bot.reply_to(message, "Ошибка при обработке сообщения")


class CodeChangeHandler(FileSystemEventHandler):
    def __init__(self):
        self.last_modified = time.time()
        
    def on_modified(self, event):
        # Check if the modified file is either the bot code or a question file
        is_bot_code = event.src_path.endswith('bot.py')
        is_question_file = event.src_path.endswith('.json') and 'questions' in event.src_path
        
        if is_bot_code or is_question_file:
            current_time = time.time()
            if current_time - self.last_modified > 1:  # Prevent multiple reloads
                self.last_modified = current_time
                logger.info(f"Change detected in {event.src_path}. Restarting bot...")
                try:
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                except Exception as e:
                    logger.error(f"Failed to restart bot: {e}")

if __name__ == '__main__':
    logger.info("\n\n\nStarting currency converter bot...")

        
    # Set up file watcher
    event_handler = CodeChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, path='.', recursive=False)
    observer.schedule(event_handler, path='questions', recursive=False)
    observer.start()
    
    while True:
        try:
            logger.info("Starting bot polling...")
            bot.infinity_polling()
        except (requests.exceptions.ConnectionError, 
                requests.exceptions.ReadTimeout,
                NewConnectionError) as e:
            logger.error(f"Network error occurred: {e}")
            logger.info("Waiting 2 seconds before retry...")
            time.sleep(2)
            continue
        except Exception as e:
            # Log any other unexpected errors
            logger.error(f"Bot crashed with unexpected error: {e}", exc_info=True)
            break
        finally:
            observer.stop()
            observer.join()
            logger.info("Bot stopped") 