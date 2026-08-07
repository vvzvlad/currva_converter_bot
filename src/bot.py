# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name, fixme
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

#TODO Ещё интересный момент: как детектить валюту какой страны имел в виду автор? Я например сейчас под песо подразумеваю филиппинские, а кто-то может в Мексике быть
#TODO дать возможность добавлять произвольные валюты
#TODO https://github.com/FlongyDev/py-rpn калькулятор
#TODO о, можно игнорировать только от того, кто нахуй послал! можно тегать его и тогда он будет включаться

import functools
import logging
import os
import signal
import sys
import re
import threading
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

# Cached result of the single get_me() call made at startup. Every incoming message
# needs the bot's own id to tell a reply-to-the-bot apart from any other reply, and
# calling get_me() per message would mean one extra HTTPS round-trip to Telegram for
# every message in every chat (latency + rate-limit budget).
BOT_USER_ID = None

# --- Credential redaction ----------------------------------------------------
# Every Telegram API call is an HTTPS request to /bot<TOKEN>/<method>, and `requests`
# puts the full URL into the text of its exceptions. So the token can escape into the
# container log through paths that have nothing to do with our own logging calls:
# an uncaught exception printed to stderr by the interpreter (at ANY log level,
# including CRITICAL), an exception in a telebot worker thread, or any third-party
# library logging `str(exc)` / `exc_info=True`.
#
# Redacting the two known call sites would only close today's holes, so the secrets are
# scrubbed centrally instead, at the three places where text leaves the process:
# the logging handlers, sys.excepthook and threading.excepthook. Any new API call
# added later is covered automatically.
TOKEN_PLACEHOLDER = "<BOT_TOKEN>"

# The apilayer key and the InfluxDB token travel in request HEADERS rather than in the
# URL, so they have never leaked the way the bot token did. They are covered anyway:
# _fetch_usd_rates puts the whole API response body into the text of the exception it
# raises, and an API that ever echoes the key back would put it straight into the log.
API_KEY_PLACEHOLDER = "<API_KEY>"
INFLUX_TOKEN_PLACEHOLDER = "<INFLUX_TOKEN>"

# `bot<id>:<secret>` as it appears inside API URLs — the safety net for a token that
# reached the text in some other shape (telebot masks only the part after the colon).
_TOKEN_URL_RE = re.compile(r"bot\d{4,}:[A-Za-z0-9_\-*]{10,}")

# The secret half is matched separately: something may log it without the numeric id.
_TOKEN_SECRET = settings.bot_token.split(":", 1)[-1] if settings.bot_token else ""

# Searching for a very short secret would turn ordinary log lines into noise (a
# one-character API_KEY would match half the alphabet), so anything shorter than this
# is left alone. Real credentials are far longer.
_MIN_SECRET_LENGTH = 8


def _extra_secrets():
    """The non-Telegram credentials, each with the placeholder that replaces it.

    Read on every call rather than captured once at import: `settings` is a live
    object, and both values are optional — INFLUX_TOKEN is unset in every deployment
    that does not report metrics.
    """
    return (
        (settings.api_key, API_KEY_PLACEHOLDER),
        (settings.influx_token, INFLUX_TOKEN_PLACEHOLDER),
    )


def _redact_text(text):
    """Mask every known credential inside an already-rendered string."""
    if settings.bot_token and settings.bot_token in text:
        text = text.replace(settings.bot_token, TOKEN_PLACEHOLDER)
    if len(_TOKEN_SECRET) >= _MIN_SECRET_LENGTH and _TOKEN_SECRET in text:
        text = text.replace(_TOKEN_SECRET, TOKEN_PLACEHOLDER)
    for secret, placeholder in _extra_secrets():
        if secret and len(secret) >= _MIN_SECRET_LENGTH and secret in text:
            text = text.replace(secret, placeholder)
    return _TOKEN_URL_RE.sub(f"bot{TOKEN_PLACEHOLDER}", text)


def _redact(value):
    """Return `value` with every recognisable credential masked.

    Non-strings are rendered with str() before the search instead of being passed
    through: `logger.error(exc)` and `logger.exception(exc)` put the exception OBJECT
    into record.msg, and LogRecord.getMessage() renders it with `str(self.msg) %
    self.args` only later — so skipping non-strings here printed the full token for
    the single most common way of logging an exception.

    A value whose rendering holds no secret is returned exactly as it came, type
    included: record.args feed %-formatting, and turning an int into a str would
    break "%d".
    """
    if isinstance(value, str):
        return _redact_text(value)
    try:
        text = str(value)
    except Exception:
        # An object whose __str__ raises is about to blow up in getMessage() anyway,
        # and there is nothing to scrub in a value that cannot be rendered.
        return value
    redacted = _redact_text(text)
    return redacted if redacted != text else value


class _TokenRedactingFilter(logging.Filter):
    """Scrub credentials out of every record reaching a handler, whoever emitted it.

    Installed on HANDLERS rather than on loggers: a filter attached to a logger only
    sees records logged through that logger, while a handler filter sees everything
    that reaches that handler — our modules, telebot, urllib3, requests.
    """

    def filter(self, record):
        record.msg = _redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {key: _redact(val) for key, val in record.args.items()}
            else:
                record.args = tuple(_redact(arg) for arg in record.args)
        if record.exc_info:
            # Formatter.format() reuses a non-empty exc_text instead of rendering
            # exc_info again, so filling it in here is the only hook that lets the
            # traceback text be scrubbed once for every handler. Idempotent: the
            # second handler sees the already-redacted text.
            if not record.exc_text:
                # rstrip like Formatter.formatException() does: the rendered traceback
                # ends with a newline, the formatter appends its own separator before
                # it, and the result was a blank line after every traceback.
                record.exc_text = "".join(traceback.format_exception(*record.exc_info)).rstrip("\n")
            record.exc_text = _redact(record.exc_text)
        if record.stack_info:
            record.stack_info = _redact(record.stack_info)
        return True


def _write_redacted_traceback(exc_type, exc_value, exc_tb, header=""):
    """Print a traceback to stderr with the credentials removed."""
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    sys.stderr.write(header + _redact(text))
    sys.stderr.flush()


def _iter_known_handlers():
    """Every handler currently attached to any logger, the root one included.

    Logger.callHandlers walks from the emitting logger UP to the root, so a handler
    sitting on a non-root logger sees the record BEFORE the root handlers do — filtering
    only the root handlers leaves that first hop unredacted. pyTelegramBotAPI is exactly
    such a case: importing telebot puts a StreamHandler(sys.stderr) on the `TeleBot`
    logger, and it emits before anything of ours can clean the record.
    """
    yield from logging.getLogger().handlers
    # list(): another thread creating a logger mid-iteration would otherwise raise
    # "dictionary changed size during iteration".
    for existing in list(logging.Logger.manager.loggerDict.values()):
        # loggerDict also holds PlaceHolder objects, standing in for the intermediate
        # names of a dotted hierarchy ("urllib3" while only "urllib3.connectionpool"
        # exists). They have no handlers.
        if isinstance(existing, logging.Logger):
            yield from existing.handlers


def _attach_redactor(handler):
    """Give `handler` a redacting filter unless it already has one.

    A fresh filter instance per handler rather than one shared object: it is
    stateless, and this way an accidental double install stays visible as a single
    filter per handler instead of silently doubling the work on every record.

    Anything that is not a logging.Handler is left alone: a handler is a duck type as
    far as Logger.callHandlers is concerned (it only ever touches `.level` and
    `.handle()`), so a dependency — or its dictConfig — may legitimately install an
    object that has no `.filters` at all. Reading it here would raise AttributeError
    inside somebody else's addHandler() call.
    """
    if not isinstance(handler, logging.Handler):
        return
    if not any(isinstance(existing, _TokenRedactingFilter) for existing in handler.filters):
        handler.addFilter(_TokenRedactingFilter())


def _redact_handlers_added_later():
    """Cover handlers that get attached AFTER the layer is installed.

    Sweeping the loggers that exist right now is not enough on its own: a dependency
    imported later (or one that builds its logger lazily, on first use) brings its own
    handler with it, and so does any later logging.basicConfig(). Wrapping
    Logger.addHandler is the only hook the logging module offers for that — it is the
    single funnel every handler goes through, root included.

    Idempotent: installing twice must not stack two wrappers.
    """
    if getattr(logging.Logger.addHandler, "_redacts_secrets", False):
        return

    original_add_handler = logging.Logger.addHandler

    # wraps() so the patched method keeps the stdlib name, docstring and signature:
    # the parameter is called `hdlr` there, and anything calling addHandler(hdlr=...)
    # by keyword — or reading __name__ / inspect.signature() while working out where a
    # log line went — would otherwise be broken by our wrapper, in the one place where
    # good diagnostics matter most.
    @functools.wraps(original_add_handler)
    def add_handler(self, hdlr):
        original_add_handler(self, hdlr)
        try:
            _attach_redactor(hdlr)
        except Exception:
            # This patches a stdlib method for the WHOLE process, so it must have no
            # path on which it breaks logging setup that used to work: the handler is
            # attached already, and an unredacted handler is a far smaller problem
            # than an exception escaping into a dependency's import.
            pass

    add_handler._redacts_secrets = True
    # Kept reachable so a test (or anything else that has to undo this) can restore
    # the stdlib method instead of leaving a wrapper behind for the whole process.
    add_handler._original_add_handler = original_add_handler
    logging.Logger.addHandler = add_handler


def _install_token_redaction():
    """Wire the redaction into logging and into both uncaught-exception hooks."""
    root = logging.getLogger()
    if not root.handlers:
        # Direct import of this module without main.py: make sure there is a handler
        # to attach the filter to, otherwise the first later-added one is unfiltered.
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    for handler in _iter_known_handlers():
        _attach_redactor(handler)
    _redact_handlers_added_later()

    # telebot's own StreamHandler is now filtered like every other one, so this is not
    # about the token any more: the `TeleBot` logger propagates as well, so every
    # telebot ERROR was printed twice, once in telebot's format and once in ours.
    # Dropping the handler leaves a single line, formatted like the rest of the log.
    telebot.logger.handlers.clear()

    def excepthook(exc_type, exc_value, exc_tb):
        _write_redacted_traceback(exc_type, exc_value, exc_tb)

    def thread_excepthook(args):
        if args.exc_type is SystemExit:
            return
        thread_name = args.thread.name if args.thread is not None else "unknown"
        _write_redacted_traceback(
            args.exc_type, args.exc_value, args.exc_traceback,
            header=f"Exception in thread {thread_name}:\n",
        )

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook


_install_token_redaction()

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

START_TIME = time.time()
MAX_TIME_DELTA = 10     #time delta in seconds to skip old messages in group chats

# /stats builds one line per user and per chat, so an unbounded argument produces a
# reply far over Telegram's 4096-character limit (and a pointless full scan of the
# statistics store). The reply is split into chunks as well, see _reply_in_chunks.
MAX_STAT_LIMIT = 50


def _reply_in_chunks(message, text):
    """Reply with `text`, split into pieces Telegram will accept.

    Telegram rejects anything over 4096 characters with a 400, which in a command
    handler means the user gets nothing at all. smart_split() cuts on newlines first,
    so the per-user / per-chat lines of /stats stay intact.
    """
    parts = telebot.util.smart_split(text, telebot.util.MAX_MESSAGE_LENGTH)
    bot.reply_to(message, parts[0])
    for part in parts[1:]:
        bot.send_message(message.chat.id, part)


def _collect_rates(found_currencies, user_currencies):
    """Fetch exactly the rates the formatter is going to use.

    The fallback is `default_currencies`, the same list format_conversion() falls back
    to when no user settings exist — using `target_currencies` (the whole reference
    book, ~140 entries) meant fetching twenty times more pairs than the reply can show,
    for every amount found, on every keystroke in inline mode.

    USD is always included: format_conversion()'s "more than a million dollars" guard
    looks up `<source>_USD` in this dict, and it must not silently misfire just because
    the user configured a currency list without the dollar in it.
    """
    targets = list(user_currencies) if user_currencies else list(currency_formatter.default_currencies)
    if 'USD' not in targets:
        targets.append('USD')

    # Over the set of source CURRENCIES, not over the amounts: a message with twelve
    # sums in roubles asked the manager for the same twelve rates twelve times (each
    # call takes the manager's lock) and wrote the same key into `rates` twelve times.
    # dict.fromkeys instead of set(): it keeps the order the currencies were found in,
    # which keeps the number of get_rate calls predictable in tests and in the log.
    sources = dict.fromkeys(curr for _amount, curr, _original in found_currencies)

    rates = {}
    for curr in sources:
        for target in targets:
            if target == curr:
                continue
            rate = rates_manager.get_rate(curr, target)
            if rate:
                rates[f"{curr}_{target}"] = rate
    return rates


def _is_forwarded(message):
    """True for any forwarded message, whatever the origin.

    `forward_from` alone is not enough: Bot API 7.0 replaced the flat forward_* fields
    with a single forward_origin object, and pyTelegramBotAPI now derives the old names
    from it — forward_from stays None for a forward from a hidden profile, a channel or
    a group, so those slipped through the group-chat filter. forward_origin covers all
    four origin kinds at once; the legacy names are only consulted on an older telebot
    that has no forward_origin attribute (reading them there costs a deprecation
    warning on a modern one).
    """
    if hasattr(message, 'forward_origin'):
        return message.forward_origin is not None
    legacy_fields = ('forward_from', 'forward_from_chat', 'forward_sender_name', 'forward_date')
    return any(getattr(message, field, None) is not None for field in legacy_fields)


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Handle /start and /help.

    Wrapped like every other handler: with threaded=True an exception escaping a
    handler unwinds into the polling loop, which tears polling down and restarts it —
    a single failed reply_to() in one chat becomes a short outage for every chat.
    There is no logic here to fail, but reply_to() is a network call and the bot may
    well have been blocked or kicked between the /start and the answer.
    """
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
    try:
        bot.reply_to(message, message_text)
    except telebot.apihelper.ApiTelegramException as e:
        logger.error(f"Telegram API error in /start or /help for chat {message.chat.id}: {e.error_code}", exc_info=True)
    except Exception:
        logger.error(f"Error processing /start or /help in chat {message.chat.id}", exc_info=True)



@bot.message_handler(commands=['currencies'])
def handle_currencies(message):
    """Handle /currencies command.

    Everything is inside a try: with threaded=True an exception escaping a handler
    unwinds into the polling loop, which then tears polling down and restarts it —
    one bad command in one chat becomes a short outage for every chat. Realistic
    triggers here are get_chat_member() (fails for an anonymous admin or a channel
    post) and any network hiccup inside reply_to().
    """
    try:
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

            _reply_in_chunks(message, response)
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

        _reply_in_chunks(message, response)

    except telebot.apihelper.ApiTelegramException as e:
        logger.error(f"Telegram API error in /currencies for chat {message.chat.id}: {e.error_code}", exc_info=True)
    except Exception:
        logger.error(f"Error processing /currencies in chat {message.chat.id}", exc_info=True)

@bot.message_handler(commands=['stats'])
def send_statistics(message):
    """Handle /stats [limit]. Admin only, never allowed to break the polling loop."""
    try:
        if message.from_user.id != settings.admin_user_id:
            bot.reply_to(message, "У вас нет доступа к этой команде")
            return

        try:
            stat_limit = int(message.text.split()[1]) if len(message.text.split()) > 1 else 10
        except ValueError:
            stat_limit = 10
        # Clamp: a negative limit would slice the top lists from the wrong end and a
        # huge one only produces a reply nobody can read (see MAX_STAT_LIMIT).
        stat_limit = max(1, min(stat_limit, MAX_STAT_LIMIT))

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

        _reply_in_chunks(message, response)

    except telebot.apihelper.ApiTelegramException as e:
        logger.error(f"Telegram API error in /stats for chat {message.chat.id}: {e.error_code}", exc_info=True)
    except Exception:
        logger.error(f"Error processing /stats in chat {message.chat.id}", exc_info=True)


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

        rates = _collect_rates(found_currencies, user_currencies)

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
            
        # Query text is never logged: an inline query is a user's message in progress.
        # Only its length and the author's id go into the log, same rule as the
        # length guard in currency_parser.
        logger.info(f"Processed inline query from user {query.from_user.id} ({len(query.query)} chars)")
        statistics_manager.log_request(user=query.from_user, chat_id=None, chat_title=None, is_inline=True)

    except telebot.apihelper.ApiTelegramException as e:
        # Same split as the command handlers: an API refusal (an expired inline query
        # id is the common one) is a one-line known failure, everything else is a bug.
        logger.error(
            f"Telegram API error in inline query from user {query.from_user.id}: {e.error_code}",
            exc_info=True,
        )
    except Exception:
        # exc_info instead of traceback.print_exc(): the latter writes straight to
        # stderr, bypassing both the log format and the token-redacting filter.
        logger.error(
            f"Error processing inline query from user {query.from_user.id} ({len(query.query)} chars)",
            exc_info=True,
        )


@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    # No try here on purpose: both this handler and handle_message below are one-line
    # adapters over parse_text, and parse_text catches everything itself (same
    # ApiTelegramException / Exception split as the command handlers), so nothing can
    # escape into the polling loop from either of them.
    if message.caption:
        return parse_text(message.caption, message)
    else:
        return None

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    # content_types defaults to ['text'], so photos never reach this handler —
    # they go to handle_photo above.
    return parse_text(message.text, message)

def parse_text(text, message):
    try:
        is_group_chat = message.chat.type in ['group', 'supergroup']
        # `from_user` is None when the replied-to message was posted on behalf of a
        # channel; reading .id on it raised an AttributeError that the except below
        # swallowed, so such messages were silently dropped. BOT_USER_ID is the
        # cached get_me() id — no API call per message.
        reply = message.reply_to_message
        is_reply_message = bool(
            reply is not None
            and reply.from_user is not None
            and BOT_USER_ID is not None
            and reply.from_user.id == BOT_USER_ID
        )
        is_chat_disabled = user_settings_manager.is_chat_disabled(message.chat.id)

        # skip messages from bots
        if message.via_bot:
            return

        # skip forwarded messages only in group chats
        if is_group_chat and _is_forwarded(message):
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
            # `text`, not message.text: for a photo reply the text lives in
            # message.caption and message.text is None.
            if any(phrase in (text or "").lower() for phrase in ignore_phrases):
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

        rates = _collect_rates(found_currencies, user_currencies)

        response = currency_formatter.format_multiple_conversions(
            found_currencies,
            rates,
            mode='chat',
            user_currencies=user_currencies
        )
        if response:
            # Message texts stay out of the log — only the length and the chat id.
            logger.info(f"Processed message ({len(text or '')} chars) in chat {message.chat.id}")
            statistics_manager.log_request(user=message.from_user, chat_id=message.chat.id, chat_title=message.chat.title)
            try:
                bot.reply_to(message, response)
            except telebot.apihelper.ApiTelegramException as e:
                if e.error_code == 431:  # Request Header Fields Too Large
                    bot.reply_to(message, "Слишком большое сообщение")
                else:
                    raise

    except telebot.apihelper.ApiTelegramException as e:
        logger.error(f"Telegram API error handling message in chat {message.chat.id}: {e.error_code}", exc_info=True)
    except Exception:
        # exc_info: without the stack every failure in production looked like one
        # line with no indication of where it came from.
        logger.error(f"Error processing message in chat {message.chat.id}", exc_info=True)


class CodeChangeHandler(FileSystemEventHandler):
    """Restart the process when a source file changes. Development only.

    Only instantiated when settings.watch_code_changes is on: os.execv() below replaces
    the running process from the observer thread, so main()'s finally never runs and the
    sqlite stores are never closed.
    """

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


def shutdown_managers():
    """Stop every module-level manager on the way out.

    Named after the managers rather than after storage because it does both halves of
    a shutdown: it closes the two sqlite connections AND stops the background threads
    (ExchangeRatesManager's rates updater, StatisticsManager's InfluxDB reporter).

    Nothing is lost without the sqlite half — WAL plus committed transactions already
    survive a kill — but an unclosed database leaves its `-wal` file uncheckpointed, so
    it keeps growing across every restart until something opens the file again. The
    threads are daemons and would die with the process anyway; stopping them explicitly
    means the shutdown does not depend on that.

    Deliberately forgiving: the managers are module-level and may be missing or
    half-built if an import failed, and a failure to close must never be the reason
    the process refuses to exit. Safe to call twice — closing an already closed
    connection is what happens on the signal path, where SystemExit also unwinds
    through main()'s finally.

    Goes through each manager's public close(), which also stops whatever background
    work it owns (StatisticsManager sets its reporting-thread stop flag before the
    connection disappears). Reaching into a private `_db` would be a silent no-op the
    day that attribute is renamed, and the `-wal` growth this exists to prevent would
    come back unnoticed.

    Latent hazard, harmless today: KeyValueStore.close() takes a non-reentrant lock,
    and this runs from a signal handler, i.e. on the MAIN thread. TeleBot is created
    with threaded=True (the default), so handlers — and therefore set_many — only ever
    run on worker threads and the main thread is never already holding that lock.
    Switch the bot to threaded=False and a Ctrl+C landing mid-write deadlocks the
    shutdown forever.
    """
    # Rates first: it is the only one that may be in the middle of an outbound HTTP
    # request, and close() waits for that thread with a timeout.
    for name in ("rates_manager", "statistics_manager", "user_settings_manager"):
        manager = globals().get(name)
        if manager is None:
            continue
        try:
            manager.close()
        except Exception as e:
            logger.warning(f"Failed to close {name}: {e}")


def signal_handler(_signum, _frame):
    """Handle Ctrl+C signal"""
    logger.info("Received shutdown signal, stopping...")
    if OBSERVER:
        OBSERVER.stop()
        OBSERVER.join()
    shutdown_managers()
    sys.exit(0)


def _start_telegram_session():
    """Make the first calls to Telegram and cache what the handlers need.

    Kept in one place and deliberately silent about the exception text: the failure
    modes here are network ones, and a requests exception carries the request URL with
    the token in it. The redaction hooks would catch it anyway, but not re-raising is
    the cheaper guarantee — one readable line, exit code 1, and the container restart
    policy tries again when the network comes back.
    """
    global BOT_USER_ID

    try:
        me = bot.get_me()
    except Exception:
        logger.critical("Telegram API is unreachable (getMe failed) — exiting, will retry on restart")
        raise SystemExit(1) from None

    BOT_USER_ID = me.id
    logger.info(f"Bot name: @{me.username} (id {me.id})")

    try:
        bot.set_my_commands([
            types.BotCommand("start", "Запустить бота"),
            types.BotCommand("help", "Показать помощь"),
            types.BotCommand("currencies", "Настроить отображаемые валюты")
        ])
    except Exception:
        # Cosmetic: the command menu is not worth refusing to start over.
        logger.warning("Failed to publish the command list, continuing without it")


def main():
    # `global` is required: without it the assignment below makes OBSERVER local
    # and signal_handler would still see the module-level None.
    global OBSERVER

    logger.info("Starting currency converter bot...")

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        _start_telegram_session()

        if settings.watch_code_changes:
            logger.warning("WATCH_CODE_CHANGES is enabled: the process restarts itself on any .py change (development only)")
            event_handler = CodeChangeHandler()
            OBSERVER = Observer()
            # Watch the package directory only (non-recursive): edits to main.py in the
            # repo root are NOT picked up and do not trigger a restart.
            OBSERVER.schedule(event_handler, path=os.path.dirname(os.path.abspath(__file__)), recursive=False)
            OBSERVER.start()

        logger.info("Starting bot polling...")
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception:
        # No str(e) in the message: a network exception carries the API URL, i.e. the
        # token. exc_info goes through the redacting filter, an f-string would not
        # (it would be redacted too, but there is no reason to duplicate the text).
        logger.error("Bot crashed with unexpected error", exc_info=True)
    finally:
        if OBSERVER:
            OBSERVER.stop()
            OBSERVER.join()
        shutdown_managers()
        logger.info("Bot stopped")


if __name__ == "__main__":
    main()
