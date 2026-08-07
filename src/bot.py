# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name, fixme
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

#TODO Ещё интересный момент: как детектить валюту какой страны имел в виду автор? Я например сейчас под песо подразумеваю филиппинские, а кто-то может в Мексике быть
#TODO дать возможность добавлять произвольные валюты
#TODO https://github.com/FlongyDev/py-rpn калькулятор
#TODO о, можно игнорировать только от того, кто нахуй послал! можно тегать его и тогда он будет включаться

import logging
import os
import signal
import sys
import re
import time
import traceback
import telebot
from telebot import types
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from src.currency_formatter import CurrencyFormatter
from src.currency_parser import CurrencyParser
from src.exchange_rates_manager import ExchangeRatesManager
from src.settings import settings
from src.statistics_manager import StatisticsManager
from src.user_settings_manager import UserSettingsManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(os.path.splitext(os.path.basename(__file__))[0])

OBSERVER = None

# Credentials are validated by pydantic-settings at import time: a missing
# variable already failed the process with a readable message. Never log the
# token or the API key, not even partially.
logger.info("Bot init")
bot = telebot.TeleBot(settings.bot_token)


rates_manager = ExchangeRatesManager()
currency_parser = CurrencyParser()
currency_formatter = CurrencyFormatter()
statistics_manager = StatisticsManager()
user_settings_manager = UserSettingsManager()

bot.set_my_commands([
    types.BotCommand("start", "Запустить бота"),
    types.BotCommand("help", "Показать помощь"),
    types.BotCommand("currencies", "Настроить отображаемые валюты")
])

START_TIME = time.time()
MAX_TIME_DELTA = 10     #time delta in seconds to skip old messages in group chats


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    message_text = (
        "Привет! Это бот для конвертации валют.\n\n"
        "Бывает, заходишь в чат, в котором сидят люди из разных стран, и там пишут: «а я купил за 15000 лари телевизор».\n"
        "Читаешь это и думаешь, «ёпт, а сколько это в евро-то?!»\n\n"
        "Можно добавить этого бота в такой чат: он будет искать сообщения, в которых упоминается сумма (например, «100 шекелей»), "
        "и реплаить: «100 шекелей (🇮🇱) — это 🇺🇸 $28, 🇪🇺 €26, 🇬🇧 £22, 🇷🇺 2932 ₽, 🇯🇵 4124 ¥, 🇦🇲 10 868 ֏». \n"
        "(Если бота в чате нет, перешли ему сообщение и он ответит в личку)\n\n"
        "А ещё бот поддерживает инлайн-режим: можно самому написать \"@currvaconverter_bot я только что продал ноутбук за 15000 йен!\" "
        "в любом чате — бот подставит разные валюты в отправляемое сообщение. В личной переписке тоже сработает.\n\n"
        "С помощью команды /currencies можно настроить, какие валюты будут отображаться.\n\n"
        "А если бот заебал, можно послать его нахуй — он будет игнорировать чат пять минут.\n\n"
    )
    bot.reply_to(message, message_text)



@bot.message_handler(commands=['currencies'])
def handle_currencies(message):
    """Handle /currencies command"""
    args = [arg.strip(',') for arg in message.text.split()[1:]]  # Get arguments after command and remove commas
    
    is_chat = message.chat.type in ['group', 'supergroup']
    entity_id = message.chat.id if is_chat else message.from_user.id
    
    if not args:
        # Show current settings and help
        current_currencies = user_settings_manager.get_currencies(entity_id, is_chat)
        available_currencies = currency_formatter.target_currencies
        
        if is_chat:
            response =  f"Укажите набор валют через пробел для чата '{message.chat.title}'. Пример:\n"
        else:
            response = f"Укажите набор валют через пробел для пользователя {message.from_user.username}. Пример:\n"
        response += f"/currencies {' '.join(available_currencies)} (это все доступные валюты)\n"
        
        if current_currencies:
            response += f"\nТекущие {'валюты чата' if is_chat else 'ваши валюты'}: {', '.join(current_currencies)}"
        else:
            response += f"\nСейчас используются валюты по умолчанию: {', '.join(currency_formatter.default_currencies)}"
            
        bot.reply_to(message, response)
        return

    # Check if user is admin
    if is_chat:
        user_member = bot.get_chat_member(message.chat.id, message.from_user.id)
        if user_member.status not in ['creator', 'administrator']:
            bot.reply_to(message, "Только администраторы чата могут менять настройки валют")
            return

    # Convert to uppercase and filter valid currencies, removing duplicates
    new_currencies = list(dict.fromkeys([curr.upper() for curr in args]))
    valid_currencies = [curr for curr in new_currencies if curr in currency_formatter.target_currencies]
    valid_currencies = list(dict.fromkeys(valid_currencies))  # Remove duplicates
    
    if not valid_currencies:
        bot.reply_to(message, "Ошибка: не указано ни одной правильной валюты")
        return
        
    # Save new settings
    user_settings_manager.set_currencies(entity_id, valid_currencies, is_chat)
    
    invalid_currencies = set(new_currencies) - set(valid_currencies)
    response = ""
    if invalid_currencies:
        response += f"\nНекорректные коды валют: {', '.join(invalid_currencies)}, доступные: {', '.join(currency_formatter.target_currencies)}"
    if is_chat:
        response += f"\nУстановлены валюты чата: {', '.join(valid_currencies)}"
    else:
        response += f"\nУстановлены валюты для конвертации: {', '.join(valid_currencies)}"

    bot.reply_to(message, response)

@bot.message_handler(commands=['stats'])
def send_statistics(message):
    if message.from_user.id != settings.admin_user_id:
        bot.reply_to(message, "У вас нет доступа к этой команде")
        return
    
    try:
        stat_limit = int(message.text.split()[1]) if len(message.text.split()) > 1 else 10
    except ValueError:
        stat_limit = 10
        
    stats = statistics_manager.get_statistics(stat_limit)

    response = (
        f"📊 Статистика бота:\n\n"
        f"Всего обычных запросов: {stats['total_requests']}\n"
        f"Всего инлайн-запросов: {stats['total_inline_requests']}\n"
        f"Уникальных пользователей: {stats['unique_users']}\n"
        f"Уникальных чатов: {stats['unique_chats']}\n\n"
        f"Топ-{stat_limit} пользователей:\n"
        + "\n".join(f"{('@' + user['username']) if user.get('username') else user['display_name']}: "
                    f"{user['total_requests']} (обычных: {user['requests']}, инлайн: {user['inline_requests']}) "
                    f"[активность: {user['last_active_str']}]" 
                    for user in stats['top_users'])
        + f"\n\nТоп-{stat_limit} чатов:\n"
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

        # Get user settings for the user who sent the inline query
        user_currencies = user_settings_manager.get_currencies(query.from_user.id, is_chat=False)

        rates = {}
        for amount, curr, _ in found_currencies:
            target_currencies = user_currencies if user_currencies else currency_formatter.target_currencies
            for target in target_currencies:
                if target != curr:
                    rate = rates_manager.get_rate(curr, target)
                    if rate:
                        rates[f"{curr}_{target}"] = rate

        # Original response with just conversions
        converted_text = currency_formatter.format_multiple_conversions(
            found_currencies, 
            rates, 
            mode='chat',
            user_currencies=user_currencies
        )
        if not converted_text:
            return

        # Create modified message with replacements
        modified_text_inline = query.query
        for amount, curr, original in reversed(found_currencies):
            conversion = currency_formatter.format_conversion(
                (amount, curr, original), 
                rates, 
                mode='inline',
                user_currencies=user_currencies
            )
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
        try:
            bot.answer_inline_query(query.id, results)
        except (telebot.apihelper.ApiTelegramException, telebot.apihelper.ApiHTTPException) as e:
            error_code = getattr(e, 'error_code', None)
            if isinstance(e, telebot.apihelper.ApiHTTPException):
                match = re.search(r'HTTP (\d+)', str(e)) # Extract error code from HTTP error message using regex
                error_code = int(match.group(1)) if match else None
                
            if error_code in [400, 431, 414]:  # Message too long errors
                error_results = [
                    types.InlineQueryResultArticle(
                        id='1',
                        title='Ошибка',
                        description='Слишком большое сообщение',
                        input_message_content=types.InputTextMessageContent( message_text='Слишком большое сообщение' )
                    )
                ]
                bot.answer_inline_query(query.id, error_results)
            else:
                raise
            
        logger.info(f"Processed inline query '{query.query}'")
        statistics_manager.log_request(user=query.from_user, chat_id=None, chat_title=None, is_inline=True)

    except Exception as e:
        logger.error(f"Error processing inline query '{query.query}': {str(e)}")
        traceback.print_exc()


@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    if message.caption:
        return parse_text(message.caption, message)
    else:
        return None

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if message.photo:
        return parse_text(message.caption, message)
    else:
        return parse_text(message.text, message)

def parse_text(text, message):
    try:
        is_group_chat = message.chat.type in ['group', 'supergroup']
        is_reply_message = message.reply_to_message and message.reply_to_message.from_user.id == bot.get_me().id
        is_chat_disabled = user_settings_manager.is_chat_disabled(message.chat.id)

        # skip messages from bots 
        if message.via_bot:
            return
            
        # skip forwarded messages only in group chats
        if message.forward_from and is_group_chat:
            return
            
        if message.date < START_TIME - MAX_TIME_DELTA:
            logger.debug(f"Skipping old message from {message.date}, bot start time: {START_TIME}")
            return

        # Check if chat is disabled
        if is_group_chat and is_chat_disabled and not is_reply_message:
            return
        
        # Check for ignore trigger phrases in group chats
        ignore_phrases = ["нахуй", "заткнись", "отключись"]
        ignore_duration = 5 * 60  # 5 minutes 
        if is_group_chat and is_reply_message:
            if any(phrase in message.text.lower() for phrase in ignore_phrases):
                user_settings_manager.set_chat_disabled(message.chat.id, ignore_duration)
                bot.reply_to(message, "Ну и конвертируйте сами теперь!!")
                return
            
        found_currencies = currency_parser.find_currencies(text)
        
        if not found_currencies:
            if not is_group_chat:
                bot.reply_to(message, "Не нашел ничего, что можно конвертировать в другую валюту ¯\\_(ツ)_/¯")
            return  

        entity_id = message.chat.id if is_group_chat else message.from_user.id
        user_currencies = user_settings_manager.get_currencies(entity_id, is_group_chat)
        
        rates = {}
        for _amount, curr, _ in found_currencies:
            target_currencies = user_currencies if user_currencies else currency_formatter.target_currencies
            for target in target_currencies:
                if target != curr:
                    rate = rates_manager.get_rate(curr, target)
                    if rate:
                        rates[f"{curr}_{target}"] = rate
        
        response = currency_formatter.format_multiple_conversions(
            found_currencies, 
            rates, 
            mode='chat',
            user_currencies=user_currencies
        )
        if response:
            logger.info(f"Processed message '{message.text}' in chat '{message.chat.title}'")
            statistics_manager.log_request(user=message.from_user, chat_id=message.chat.id, chat_title=message.chat.title)
            try:
                bot.reply_to(message, response)
            except telebot.apihelper.ApiTelegramException as e:
                if e.error_code == 431:  # Request Header Fields Too Large
                    bot.reply_to(message, "Слишком большое сообщение")
                else:
                    raise

    except Exception as e:
        logger.error(f"Error processing message '{message.text}': {str(e)}")


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


def main():
    # `global` is required: without it the assignment below makes OBSERVER local
    # and signal_handler would still see the module-level None.
    global OBSERVER

    logger.info(f"Bot name: @{bot.get_me().username}")
    logger.info(f"Starting currency converter bot...\n\n\n")

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    event_handler = CodeChangeHandler()
    OBSERVER = Observer()
    # Watch the package directory only (non-recursive): edits to main.py in the
    # repo root are NOT picked up and do not trigger a restart.
    OBSERVER.schedule(event_handler, path=os.path.dirname(os.path.abspath(__file__)), recursive=False)
    OBSERVER.start()

    try:
        logger.info("Starting bot polling...")
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        logger.error(f"Bot crashed with unexpected error: {e}", exc_info=True)
    finally:
        OBSERVER.stop()
        OBSERVER.join()
        logger.info("Bot stopped")


if __name__ == "__main__":
    main()
