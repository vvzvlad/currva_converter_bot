import re
import requests
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
from abc import ABC, abstractmethod
from decimal import Decimal

import requests.exceptions
from urllib3.exceptions import NewConnectionError

import telebot
from telebot import types
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from json.decoder import JSONDecodeError

from exchange_rates_manager import ExchangeRatesManager
from currency_parser import CurrencyParser
from currency_formatter import CurrencyFormatter

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

rates_manager = ExchangeRatesManager()
currency_parser = CurrencyParser()
currency_formatter = CurrencyFormatter()

bot.set_my_commands([
    types.BotCommand("start", "Запустить бота"),
    types.BotCommand("help", "Показать помощь")
])

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Я конвертирую валюты. Просто напиши сумму и валюту, например: 100 долларов, £5, 1000₽\n"
                        "Также можешь использовать инлайн-режим, набрав @currvaconverter_bot и сумму с валютой")

@bot.message_handler(commands=['help'])
def send_help(message):
    bot.reply_to(message, "Примеры использования:\n"
                        "• 100 долларов\n"
                        "• £50\n"
                        "• 1000₽\n"
                        "• 10 шекелей\n"
                        "Поддерживаемые валюты: " + ", ".join(currency_formatter.display_currencies))

@bot.inline_handler(lambda query: len(query.query) > 0)
def handle_inline_query(query):
    try:
        found_currencies = currency_parser.find_currencies(query.query)
        if not found_currencies:
            return

        rates = {}
        for amount, curr, _ in found_currencies:
            for target in currency_formatter.target_currencies:
                if target != curr:
                    rate = rates_manager.get_rate(curr, target)
                    if rate:
                        rates[f"{curr}_{target}"] = rate

        response = currency_formatter.format_multiple_conversions(found_currencies, rates)
        if not response:
            return

        r = types.InlineQueryResultArticle(
            id='1',
            title=f'Конвертировать',
            description=response,
            input_message_content=types.InputTextMessageContent(
                message_text=response
            )
        )
        bot.answer_inline_query(query.id, [r])

    except Exception as e:
        logger.error(f"Error processing inline query '{query.query}': {str(e)}")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    # Игнорируем форварды и инлайн сообщения
    if message.forward_from or message.via_bot:
        return
        
    try:
        found_currencies = currency_parser.find_currencies(message.text)
        if not found_currencies:
            return  
        rates = {}
        for amount, curr, _ in found_currencies:
            for target in currency_formatter.target_currencies:
                if target != curr:
                    rate = rates_manager.get_rate(curr, target)
                    if rate:
                        rates[f"{curr}_{target}"] = rate
        
        response = currency_formatter.format_multiple_conversions(found_currencies, rates)
        if response: bot.reply_to(message, response)
        
    except Exception as e:
        logger.error(f"Error processing message '{message.text}': {str(e)}")
        #bot.reply_to(message, "Произошла ошибка при обработке вашего запроса")

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

# Global observer instance for file watching
observer = None

def signal_handler(signum, frame):
    """Handle Ctrl+C signal"""
    global observer
    logger.info("Received shutdown signal, stopping...")
    if observer:
        observer.stop()
        observer.join()
    sys.exit(0)

if __name__ == '__main__':
    logger.info("\n\n\nStarting currency converter bot...")
    signal.signal(signal.SIGINT, signal_handler)
    event_handler = CodeChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, path='.', recursive=False)
    observer.schedule(event_handler, path='questions', recursive=False)
    observer.start()
    
    try:
        logger.info("Starting bot polling...")
        bot.infinity_polling()
    except Exception as e:
        logger.error(f"Bot crashed with unexpected error: {e}", exc_info=True)
    finally:
        observer.stop()
        observer.join()
        logger.info("Bot stopped")
