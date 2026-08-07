# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""StatisticsManager on top of the store."""

import json
import logging
import sqlite3
import unittest.mock
from contextlib import closing

import pytest

from src.statistics_manager import StatisticsManager
from tests.logcapture import capture_logs
from tests.storage.doubles import StubUser


@pytest.fixture
def make_manager(make_manager):
    """StatisticsManager on a database file under the test's private directory."""
    def _make_manager(name="statistics.db"):
        return make_manager(StatisticsManager, name)

    return _make_manager


def test_empty_database_gets_default_counters(make_manager):
    stats = make_manager().get_statistics(stat_limit=10)
    assert stats["total_requests"] == 0
    assert stats["total_inline_requests"] == 0
    assert stats["unique_users"] == 0
    assert stats["unique_chats"] == 0
    assert stats["top_users"] == []
    assert stats["top_chats"] == []


def test_log_request_counts_messages_and_inline_queries(make_manager):
    manager = make_manager()
    user = StubUser(7, "testuser", "Test User")

    manager.log_request(user, chat_id=-100, chat_title="Test chat")
    manager.log_request(user, chat_id=-100, chat_title="Test chat")
    manager.log_request(user, chat_id=None, chat_title=None, is_inline=True)

    stats = manager.get_statistics(stat_limit=10)
    assert stats["total_requests"] == 2
    assert stats["total_inline_requests"] == 1
    assert stats["unique_users"] == 1
    assert stats["unique_chats"] == 1

    top_user = stats["top_users"][0]
    assert top_user["display_name"] == "Test User"
    assert top_user["username"] == "testuser"
    assert top_user["requests"] == 2
    assert top_user["inline_requests"] == 1
    assert top_user["total_requests"] == 3
    assert "last_active_str" in top_user

    assert stats["top_chats"] == [{"title": "Test chat", "requests": 2}]


def test_private_chat_is_not_counted_as_a_separate_chat(make_manager):
    manager = make_manager()
    user = StubUser(7, "testuser", "Test User")
    manager.log_request(user, chat_id=7, chat_title=None)
    assert manager.get_statistics(stat_limit=10)["unique_chats"] == 0


def test_stat_limit_trims_the_top_list(make_manager):
    manager = make_manager()
    for user_id in range(5):
        for _ in range(user_id + 1):
            manager.log_request(StubUser(user_id + 1, f"u{user_id}", f"U{user_id}"), None, None)

    stats = manager.get_statistics(stat_limit=2)
    assert len(stats["top_users"]) == 2
    assert [u["requests"] for u in stats["top_users"]] == [5, 4]
    assert stats["unique_users"] == 5


def test_statistics_survive_a_restart(make_manager):
    first = make_manager()
    first.log_request(StubUser(7, "testuser", "Test User"), -100, "Test chat")
    first._db.close()

    stats = make_manager().get_statistics(stat_limit=10)
    assert stats["total_requests"] == 1
    assert stats["unique_users"] == 1


def test_migrates_legacy_statistics_json(tmp_path, make_manager):
    # Byte-for-byte the shape produced by the pickleDB implementation.
    legacy = tmp_path / "statistics.json"
    legacy.write_text(json.dumps({
        "total_requests": 52,
        "total_inline_requests": 16,
        "users": {
            "1001": {
                "username": "testuser",
                "first_name": "Test User",
                "requests": 52,
                "inline_requests": 16,
                "first_seen": "2024-01-01T00:00:00.000000",
                "last_active": "2024-01-02T00:00:00.000000",
            }
        },
        "chats": {
            "-1001": {
                "title": "Test chat",
                "requests": 39,
                "first_seen": "2024-01-01T12:00:00.000000",
            }
        },
        "last_update": "2024-01-02T00:00:00.000000",
    }), encoding="utf-8")

    manager = make_manager()
    stats = manager.get_statistics(stat_limit=10)

    assert stats["total_requests"] == 52
    assert stats["total_inline_requests"] == 16
    assert stats["unique_users"] == 1
    assert stats["unique_chats"] == 1
    assert stats["top_users"][0]["total_requests"] == 68
    assert stats["top_chats"][0] == {"title": "Test chat", "requests": 39}
    assert not legacy.exists()
    assert (tmp_path / "statistics.json.migrated").exists()

    # Counting continues from the migrated numbers, not from zero.
    manager.log_request(StubUser(1001, "testuser", "Test User"), None, None)
    assert manager.get_statistics(stat_limit=10)["total_requests"] == 53


def test_broken_legacy_statistics_json_still_starts(tmp_path, make_manager):
    legacy = tmp_path / "statistics.json"
    legacy.write_text('{"total_requests": 52, "users": {"100', encoding="utf-8")

    with capture_logs("storage", logging.ERROR):
        manager = make_manager()

    assert manager.get_statistics(stat_limit=10)["total_requests"] == 0
    assert legacy.exists()


def test_repaired_legacy_statistics_json_is_imported_on_the_next_start(tmp_path, make_manager):
    """The end-to-end version of the retry, through the real manager.

    This is why StatisticsManager no longer seeds its counters at startup: five
    default rows written on the first (failed) start would leave the table
    non-empty, and the retry would never happen.
    """
    legacy = tmp_path / "statistics.json"
    legacy.write_text('{"total_requests": 52, "users": {"100', encoding="utf-8")

    with capture_logs("storage", logging.ERROR):
        first = make_manager()
    first._db.close()

    legacy.write_text(json.dumps({"total_requests": 52, "total_inline_requests": 16}), encoding="utf-8")
    second = make_manager()

    assert second.get_statistics(stat_limit=10)["total_requests"] == 52
    assert second.get_statistics(stat_limit=10)["total_inline_requests"] == 16
    assert (tmp_path / "statistics.json.migrated").exists()


def test_a_fresh_statistics_store_writes_nothing_at_startup(tmp_path, make_manager):
    # Guards the property the migration criterion depends on: constructing the
    # manager must not put rows into an empty database.
    manager = make_manager()
    manager._db.close()
    with closing(sqlite3.connect(str(tmp_path / "statistics.db"))) as raw:
        assert raw.execute("SELECT COUNT(*) FROM kv").fetchone()[0] == 0


def test_an_unreadable_timestamp_does_not_take_down_the_statistics(make_manager):
    """One bad string in the stored blob used to raise out of get_statistics —
    killing /stats and every iteration of the InfluxDB reporting loop with it,
    for as long as the row stayed in the database."""
    manager = make_manager()
    manager.log_request(StubUser(7, "testuser", "Test User"), -100, "Test chat")

    users = manager._db.get("users")
    users["7"]["last_active"] = "2024-13-45T99:"  # truncated / hand-edited
    users["7"]["first_seen"] = None
    manager._db.set("users", users)

    with capture_logs("statistics_manager", logging.WARNING) as captured:
        stats = manager.get_statistics(stat_limit=10)

    assert any("last_active" in line for line in captured.output)
    assert stats["unique_users"] == 1
    assert stats["top_users"][0]["total_requests"] == 1
    assert "last_active_str" in stats["top_users"][0]
    # The value itself is not echoed into the log.
    assert not any("2024-13-45" in line for line in captured.output)


def test_a_non_positive_stat_limit_returns_every_chat(make_manager):
    """The metrics thread calls get_statistics(stat_limit=-1); [: -1] quietly
    dropped the last chat, while the user list already handled the same case."""
    manager = make_manager()
    user = StubUser(7, "testuser", "Test User")
    for chat_id, title in ((-1, "First"), (-2, "Second"), (-3, "Third")):
        manager.log_request(user, chat_id, title)

    for limit in (-1, 0):
        stats = manager.get_statistics(stat_limit=limit)
        assert len(stats["top_chats"]) == 3, f"stat_limit={limit}"
        assert len(stats["top_users"]) == 1, f"stat_limit={limit}"

    assert len(manager.get_statistics(stat_limit=2)["top_chats"]) == 2


def test_close_stops_the_reporting_thread(make_manager):
    """Shutdown goes through close(), not through __del__ — which may never run,
    and runs against a half-torn-down interpreter when it does."""
    assert not hasattr(StatisticsManager, "__del__")

    manager = make_manager()
    manager._influx_topic = "test_topic"
    manager._reporting_period = 0.05

    response = unittest.mock.Mock()
    response.status_code = 204
    with unittest.mock.patch("src.statistics_manager.requests.post", return_value=response):
        manager.configure_metrics_v2("http://influx.invalid", "token", "org", "bucket")
        thread = manager._reporting_thread
        assert thread.is_alive()

        manager.close()

    thread.join(timeout=5)
    assert not thread.is_alive()
    assert manager._stop_reporting.is_set()
