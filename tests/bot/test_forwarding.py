# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""_is_forwarded(): which of the fields Telegram sends actually mark a forward."""

import time

from tests.bot.doubles import LegacyMessage, message


def test_forward_from_a_user_with_an_open_profile(bot):
    forwarded = message(forward_origin={
        "type": "user",
        "date": int(time.time()),
        "sender_user": {"id": 7, "is_bot": False, "first_name": "Author"},
    })
    assert bot._is_forwarded(forwarded)


def test_forward_from_a_hidden_profile(bot):
    forwarded = message(forward_origin={
        "type": "hidden_user",
        "date": int(time.time()),
        "sender_user_name": "Someone",
    })
    # The reason the old forward_from check was not enough: Telegram sends no sender
    # for a hidden profile, so the legacy field stays empty on a forwarded message.
    assert forwarded.forward_from is None
    assert bot._is_forwarded(forwarded)


def test_forward_from_a_channel(bot):
    forwarded = message(forward_origin={
        "type": "channel",
        "date": int(time.time()),
        "chat": {"id": -1009876543210, "type": "channel", "title": "Some channel"},
        "message_id": 17,
    })
    assert forwarded.forward_from is None
    assert bot._is_forwarded(forwarded)


def test_an_ordinary_message_is_not_a_forward(bot):
    assert not bot._is_forwarded(message())


def test_legacy_message_without_forward_origin(bot):
    """Older telebot: the flat forward_* fields are the only thing available."""
    assert bot._is_forwarded(LegacyMessage(forward_sender_name="Someone"))
    assert bot._is_forwarded(LegacyMessage(forward_date=1700000000))
    assert not bot._is_forwarded(LegacyMessage())
