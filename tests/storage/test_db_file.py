# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""What the store does with the file behind the database path: a file that is not a
sqlite database at all, and a connection whose COMMIT fails."""

import sqlite3
from contextlib import closing

import pytest

from src.storage import KeyValueStore, NotASqliteDatabaseError


def test_a_json_file_under_the_db_path_is_rejected_with_a_readable_message(tmp_path):
    # What a prod .env pinned to the old default produces. Without the check
    # sqlite3 raises "file is not a database", which names nothing.
    path = tmp_path / "user_settings.db"
    path.write_text('{"user:1001:currencies": ["USD"]}', encoding="utf-8")

    with pytest.raises(NotASqliteDatabaseError) as caught:
        KeyValueStore(str(path))

    message = str(caught.value)
    assert str(path) in message
    assert "not a sqlite database" in message


def test_an_empty_file_is_treated_as_a_fresh_database(tmp_path, closers):
    path = tmp_path / "state.db"
    path.touch()
    store = KeyValueStore(str(path))
    closers.append(store.close)
    store.set("k", "v")
    assert store.get("k") == "v"


class TestFailedCommitLeavesTheConnectionUsable:
    """Blocker: a COMMIT that raises used to leave the transaction open forever.

    On the single shared connection that poisoned every later write with
    "cannot start a transaction within a transaction", and
    StatisticsManager.log_request swallows those — so the bot kept confirming
    settings that never reached the disk until someone restarted it.

    The failure is injected rather than provoked: the real triggers are a full
    disk and a lock held past busy_timeout, neither of which a unit test should
    arrange. What matters is the recovery path, and that is the same either way.
    """

    class FlakyCommitConnection(sqlite3.Connection):
        fail_commit = False

        def execute(self, sql, *args, **kwargs):
            if self.fail_commit and sql.strip().upper() == "COMMIT":
                raise sqlite3.OperationalError("simulated: database or disk is full")
            return super().execute(sql, *args, **kwargs)

    def make_flaky_store(self, make_store, tmp_path):
        store = make_store()
        store._conn.close()
        store._conn = sqlite3.connect(
            str(tmp_path / "state.db"),
            check_same_thread=False,
            isolation_level=None,
            factory=self.FlakyCommitConnection,
        )
        store._conn.execute("PRAGMA busy_timeout=5000")
        return store

    def test_write_after_a_failed_commit_still_works(self, make_store, tmp_path):
        store = self.make_flaky_store(make_store, tmp_path)
        store._conn.fail_commit = True

        with pytest.raises(sqlite3.OperationalError):
            store.set_many({"a": 1, "b": 2})

        assert not store._conn.in_transaction, "the failed transaction must be rolled back"

        # And the connection is genuinely reusable, not merely flagged as clean.
        store._conn.fail_commit = False
        store.set_many({"c": 3})
        store.set("d", 4)
        assert store.get("c") == 3
        assert store.get("d") == 4
        assert store.get("a") is None, "the failed batch must not be partially visible"

    def test_a_failed_batch_is_not_visible_to_another_connection(self, make_store, tmp_path):
        store = self.make_flaky_store(make_store, tmp_path)
        store._conn.fail_commit = True
        with pytest.raises(sqlite3.OperationalError):
            store.set_many({"a": 1})
        store._conn.fail_commit = False

        with closing(sqlite3.connect(str(tmp_path / "state.db"))) as raw:
            assert raw.execute("SELECT key FROM kv").fetchall() == []
