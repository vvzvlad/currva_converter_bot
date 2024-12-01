# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name, fixme
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

#TODO а приникь на "нахуй пошел" он будет игнорить чат какое-то время
#TODO Ещё интересный момент: как детектить валюту какой страны имел в виду автор? Я например сейчас под песо подразумеваю филиппинские, а кто-то может в Мексике быть
#TODO дать возможность добавлять произвольные валюты
#TODO https://github.com/FlongyDev/py-rpn калькулятор

import logging
import os
import signal
import sys
import time
import traceback
import telebot
from telebot import types
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from currency_formatter import CurrencyFormatter
from currency_parser import CurrencyParser
from exchange_rates_manager import ExchangeRatesManager
from statistics_manager import StatisticsManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
OBSERVER = None

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

admin_user_id = os.getenv('ADMIN_USER_ID')
if not admin_user_id:
    logger.error("ADMIN_USER_ID environment variable is not set.")
    sys.exit("Error: ADMIN_USER_ID environment variable is not set.")
logger.info(f"Admin user ID: {admin_user_id}")


rates_manager = ExchangeRatesManager()
currency_parser = CurrencyParser()
currency_formatter = CurrencyFormatter()
statistics_manager = StatisticsManager()

bot.set_my_commands([
    types.BotCommand("start", "Запустить бота"),
    types.BotCommand("help", "Показать помощь"),
    types.BotCommand("stats", "Показать статистику (только для админа)")
])

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Бот конвертирует валюты. Он написан специально для чатов, в которых много людей из разных стран, которые постоянно говорят 'а я купил за 100 фунтов телевизор'.\n "
                        "А ты читаешь это и думаешь, 'епт, а сколько это в евро-то??' Этого бота можно добавить в любой чат, он будет искать сообщения, "
                        "в которых есть паттерн '(сумма) (валюта)', например '100 шекелей' и реплаить на них сообщением \n"
                        "с конвертацией этой суммы в другие валюты: '100 шекелей (🇮🇱) это 🇺🇸 $28, 🇪🇺 €26, 🇬🇧 £22, 🇷🇺 2932 ₽, 🇯🇵 4124 ¥, 🇦🇲 10 868 ֏' \n\n"
                        "Тоже самое можно просто писать ему в личку (он ответит там) или написать '@currvaconverter_bot 100 шекелей' в любом чате(в диалогах тоже), чтобы использовать инлайн режим\n")


@bot.message_handler(commands=['stats'])
def send_statistics(message):
    if message.from_user.id != int(admin_user_id):
        bot.reply_to(message, "У вас нет доступа к этой команде")
        return
        
    stats = statistics_manager.get_statistics()

    response = (
        f"📊 Статистика бота:\n\n"
        f"Всего обычных запросов: {stats['total_requests']}\n"
        f"Всего инлайн-запросов: {stats['total_inline_requests']}\n"
        f"Уникальных пользователей: {stats['unique_users']}\n"
        f"Уникальных чатов: {stats['unique_chats']}\n\n"
        f"Топ-10 пользователей:\n"
        + "\n".join(f"{('@' + user['username']) if user.get('username') else user['display_name']}: "
                    f"{user['total_requests']} (обычных: {user['requests']}, инлайн: {user['inline_requests']}) "
                    f"[активность: {user['last_active_str']}]" 
                    for user in stats['top_users'])
        + "\n\nТоп-10 чатов:\n"
        + "\n".join(f"{chat['title']}: {chat['requests']}" 
                    for chat in stats['top_chats'])
    )
    
    bot.reply_to(message, response)


@bot.inline_handler(lambda query: len(query.query) > 0)
def handle_inline_query(query):
    try:
        
        found_currencies = currency_parser.find_currencies(query.query)
        if not found_currencies:
            results = [
                types.InlineQueryResultArticle(
                    id='1',
                    title='Конвертировай',
                    description=r'Не найдено ничего, что можно конвертировать в другую валюту ¯\_(ツ)_/¯',
                    thumbnail_url='https://raw.githubusercontent.com/vvzvlad/currva_converter_bot/master/assets/convert_small.jpeg',
                    input_message_content=types.InputTextMessageContent(
                        message_text=query.query
                    )
                ),
                types.InlineQueryResultArticle(
                    id='2', 
                    title='Дополняй',
                    description=fr"{query.query} (валюты не найдены ¯\_(ツ)_/¯)",
                    thumbnail_url='https://raw.githubusercontent.com/vvzvlad/currva_converter_bot/master/assets/insert_small.jpeg', 
                    input_message_content=types.InputTextMessageContent(
                        message_text=query.query
                    )
                )
            ]
            bot.answer_inline_query(query.id, results)
            return

        rates = {}
        for amount, curr, _ in found_currencies:
            for target in currency_formatter.target_currencies:
                if target != curr:
                    rate = rates_manager.get_rate(curr, target)
                    if rate:
                        rates[f"{curr}_{target}"] = rate

        # Original response with just conversions
        converted_text = currency_formatter.format_multiple_conversions(found_currencies, rates, mode='chat')
        if not converted_text:
            return

        # Create modified message with replacements
        modified_text_inline = query.query
        for amount, curr, original in reversed(found_currencies):
            conversion = currency_formatter.format_conversion((amount, curr, original), rates, mode='inline')
            modified_text_inline = modified_text_inline.replace(original, conversion)


        results = [
            types.InlineQueryResultArticle(
                id='1',
                title='Конвертировай',
                description=converted_text,
                thumbnail_url='https://raw.githubusercontent.com/vvzvlad/currva_converter_bot/master/assets/convert_small.jpeg',
                input_message_content=types.InputTextMessageContent(
                    message_text=converted_text
                )
            ),
            types.InlineQueryResultArticle(
                id='2', 
                title='Дополняй',
                description=modified_text_inline,
                thumbnail_url='https://raw.githubusercontent.com/vvzvlad/currva_converter_bot/master/assets/insert_small.jpeg',
                input_message_content=types.InputTextMessageContent(
                    message_text=modified_text_inline
                )
            )
        ]
        bot.answer_inline_query(query.id, results)
        statistics_manager.log_request(user=query.from_user, chat_id=None, chat_title=None, is_inline=True)

    except Exception as e:
        logger.error(f"Error processing inline query '{query.query}': {str(e)}")
        traceback.print_exc()

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if message.forward_from or message.via_bot: return
        
    try:
        found_currencies = currency_parser.find_currencies(message.text)
        if not found_currencies:
            return  
        rates = {}
        for _amount, curr, _ in found_currencies:
            for target in currency_formatter.target_currencies:
                if target != curr:
                    rate = rates_manager.get_rate(curr, target)
                    if rate:
                        rates[f"{curr}_{target}"] = rate
        
        response = currency_formatter.format_multiple_conversions(found_currencies, rates)
        if response: 
            bot.reply_to(message, response)
            statistics_manager.log_request(user=message.from_user, chat_id=message.chat.id, chat_title=message.chat.title)

    except Exception as e:
        logger.error(f"Error processing message '{message.text}': {str(e)}")
        #bot.reply_to(message, "Произошла ошибка при обработке вашего запроса")


class CodeChangeHandler(FileSystemEventHandler):
    def __init__(self):
        self.last_modified = time.time()
        
    def on_modified(self, event):
        # Check if the modified file is either the bot code or a question file
        is_bot_code = event.src_path.endswith('.py')
        
        if is_bot_code:
            current_time = time.time()
            if current_time - self.last_modified > 1:  # Prevent multiple reloads
                self.last_modified = current_time
                logger.info(f"Change detected in {event.src_path}. Restarting bot...")
                try:
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                except Exception as e:
                    logger.error(f"Failed to restart bot: {e}")


def signal_handler(_signum, _frame):
    """Handle Ctrl+C signal"""
    logger.info("Received shutdown signal, stopping...")
    if OBSERVER:
        OBSERVER.stop()
        OBSERVER.join()
    sys.exit(0)

if __name__ == '__main__':
    logger.info(f"Bot name: @{bot.get_me().username}")
    logger.info(f"Starting currency converter bot...\n\n\n")
    signal.signal(signal.SIGINT, signal_handler)
    event_handler = CodeChangeHandler()
    OBSERVER = Observer()
    OBSERVER.schedule(event_handler, path='.', recursive=False)
    OBSERVER.start()
    
    try:
        logger.info("Starting bot polling...")
        bot.infinity_polling()
    except Exception as e:
        logger.error(f"Bot crashed with unexpected error: {e}", exc_info=True)
    finally:
        OBSERVER.stop()
        OBSERVER.join()
        logger.info("Bot stopped")
