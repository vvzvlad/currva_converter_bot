# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""UserSettingsManager on top of the store."""

import json
import time

import pytest

from src.user_settings_manager import UserSettingsManager


@pytest.fixture
def make_manager(make_manager):
    """UserSettingsManager on a database file under the test's private directory."""
    def _make_manager(name="user_settings.db"):
        return make_manager(UserSettingsManager, name)

    return _make_manager


def test_currencies_roundtrip_for_user_and_chat(make_manager):
    manager = make_manager()
    assert manager.get_currencies(42) is None

    manager.set_currencies(42, ["USD", "EUR"])
    assert manager.get_currencies(42) == ["USD", "EUR"]

    # A chat with the same numeric id is a separate entity.
    assert manager.get_currencies(42, is_chat=True) is None
    manager.set_currencies(42, ["RUB"], is_chat=True)
    assert manager.get_currencies(42, is_chat=True) == ["RUB"]
    assert manager.get_currencies(42) == ["USD", "EUR"]


def test_empty_currency_list_reads_back_as_none(make_manager):
    # Preserved from the pickleDB implementation: an empty list means
    # "no preference", so the bot falls back to the default currencies.
    manager = make_manager()
    manager.set_currencies(42, [])
    assert manager.get_currencies(42) is None


def test_settings_survive_a_restart(make_manager):
    first = make_manager()
    first.set_currencies(-100200, ["GEL", "USD"], is_chat=True)
    first._db.close()

    second = make_manager()
    assert second.get_currencies(-100200, is_chat=True) == ["GEL", "USD"]


def test_chat_disable_and_expiry(make_manager):
    manager = make_manager()
    chat_id = -100500
    assert not manager.is_chat_disabled(chat_id)

    manager.set_chat_disabled(chat_id, 3600)
    assert manager.is_chat_disabled(chat_id)

    # Expired: reported as enabled again and the key is cleaned up.
    manager._db.set(f"chat:{chat_id}:disabled_until", time.time() - 1)
    assert not manager.is_chat_disabled(chat_id)
    assert not manager._db.exists(f"chat:{chat_id}:disabled_until")


def test_disabled_state_is_per_chat(make_manager):
    manager = make_manager()
    manager.set_chat_disabled(-1, 3600)
    assert manager.is_chat_disabled(-1)
    assert not manager.is_chat_disabled(-2)


def test_migrates_legacy_user_settings_json(tmp_path, make_manager):
    legacy = tmp_path / "user_settings.json"
    legacy.write_text(json.dumps({
        "chat:-1001:currencies": ["USD", "RUB"],
        "user:1001:currencies": ["RUB", "USD", "ILS", "GBP", "EUR"],
        "chat:-100777:disabled_until": time.time() + 3600,
    }), encoding="utf-8")

    manager = make_manager()

    assert manager.get_currencies(-1001, is_chat=True) == ["USD", "RUB"]
    assert manager.get_currencies(1001) == ["RUB", "USD", "ILS", "GBP", "EUR"]
    assert manager.is_chat_disabled(-100777)
    assert (tmp_path / "user_settings.json.migrated").exists()
    assert not legacy.exists()
