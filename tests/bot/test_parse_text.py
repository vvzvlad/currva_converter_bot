# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""parse_text is where every message handler ends up, so it is worth driving directly."""

import logging
import time
from unittest import mock

import pytest

from tests.bot.doubles import message
from tests.logcapture import assert_no_logs


@pytest.fixture(autouse=True)
def wired(bot, fake_bot, rates, statistics, user_settings):
    with mock.patch.object(bot, "bot", fake_bot), \
         mock.patch.object(bot, "rates_manager", rates), \
         mock.patch.object(bot, "statistics_manager", statistics), \
         mock.patch.object(bot, "user_settings_manager", user_settings), \
         mock.patch.object(bot, "BOT_USER_ID", 555):
        yield


def _reply_from_a_channel():
    """A replied-to message posted on behalf of a channel: `from` is absent."""
    return {
        "message_id": 2,
        "date": int(time.time()),
        "chat": {"id": -1001234567890, "type": "supergroup", "title": "Test chat"},
        "sender_chat": {"id": -1009876543210, "type": "channel", "title": "Some channel"},
        "text": "исходное сообщение",
    }


def test_reply_to_a_message_without_an_author_is_handled(bot, fake_bot, statistics):
    incoming = message(text="я купил телевизор за 100 долларов",
                       reply_to_message=_reply_from_a_channel())
    assert incoming.reply_to_message.from_user is None

    with assert_no_logs("bot", logging.ERROR):
        bot.parse_text(incoming.text, incoming)

    assert len(fake_bot.replies) == 1
    assert len(statistics.logged) == 1


def test_reply_without_an_author_in_a_private_chat_with_nothing_to_convert(bot, fake_bot):
    payload_chat = {"id": 42, "type": "private"}
    incoming = message(chat=payload_chat, text="просто текст",
                       reply_to_message=_reply_from_a_channel())

    with assert_no_logs("bot", logging.ERROR):
        bot.parse_text(incoming.text, incoming)

    assert len(fake_bot.replies) == 1
    assert "Не нашел ничего" in fake_bot.replies[0][1]


def test_reply_before_get_me_has_answered_is_handled(bot, fake_bot):
    """BOT_USER_ID is None until _start_telegram_session() runs."""
    with mock.patch.object(bot, "BOT_USER_ID", None):
        incoming = message(text="100 долларов", reply_to_message=_reply_from_a_channel())
        with assert_no_logs("bot", logging.ERROR):
            bot.parse_text(incoming.text, incoming)
    assert len(fake_bot.replies) == 1


def test_a_forward_into_a_group_chat_is_ignored(bot, fake_bot):
    incoming = message(text="100 долларов", forward_origin={
        "type": "hidden_user",
        "date": int(time.time()),
        "sender_user_name": "Someone",
    })
    bot.parse_text(incoming.text, incoming)
    assert fake_bot.replies == []
