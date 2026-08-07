# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Tests for the sqlite storage layer, the one-shot JSON migration and the two
managers built on top of it.

Every test gets its own tempfile.TemporaryDirectory: no shared state between
tests and nothing ever touches the real data/ directory.
"""

import json
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path

from pydantic import ValidationError

from src.settings import Settings
from src.statistics_manager import StatisticsManager
from src.storage import KeyValueStore, NotASqliteDatabaseError
from src.user_settings_manager import UserSettingsManager


class StubUser:
    """Stand-in for telebot.types.User — log_request only reads these three."""

    def __init__(self, user_id, username=None, first_name=None):
        self.id = user_id
        self.username = username
        self.first_name = first_name


class StorageTestCase(unittest.TestCase):
    """Base: a private temp dir plus bookkeeping so stores get closed."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self._stores = []

    def tearDown(self):
        for store in self._stores:
            try:
                store.close()
            except sqlite3.ProgrammingError:
                pass  # already closed by the test itself
        self._tmp.cleanup()

    def make_store(self, name="state.db", **kwargs):
        store = KeyValueStore(str(self.tmp_path / name), **kwargs)
        self._stores.append(store)
        return store


class TestKeyValueStoreBasics(StorageTestCase):
    def test_set_and_get_roundtrip(self):
        store = self.make_store()
        store.set("user:1:currencies", ["USD", "RUB"])
        self.assertEqual(store.get("user:1:currencies"), ["USD", "RUB"])

    def test_get_missing_key_returns_none(self):
        store = self.make_store()
        self.assertIsNone(store.get("nope"))

    def test_get_missing_key_returns_given_default(self):
        store = self.make_store()
        self.assertEqual(store.get("nope", 0), 0)

    def test_set_overwrites_existing_value(self):
        store = self.make_store()
        store.set("k", 1)
        store.set("k", 2)
        self.assertEqual(store.get("k"), 2)

    def test_stores_nested_structures_and_non_ascii(self):
        store = self.make_store()
        value = {"chats": {"-100": {"title": "Тестовый чат", "requests": 39}}}
        store.set("chats", value)
        self.assertEqual(store.get("chats"), value)

    def test_falsy_values_survive_the_roundtrip(self):
        # These matter: the managers store 0 and {} as legitimate values.
        store = self.make_store()
        for key, value in (("zero", 0), ("empty_dict", {}), ("empty_list", []), ("false", False)):
            store.set(key, value)
            self.assertEqual(store.get(key), value)
            self.assertTrue(store.exists(key))

    def test_exists(self):
        store = self.make_store()
        self.assertFalse(store.exists("k"))
        store.set("k", None)
        self.assertTrue(store.exists("k"))

    def test_rem_deletes_and_reports_whether_key_was_there(self):
        store = self.make_store()
        store.set("k", "v")
        self.assertTrue(store.rem("k"))
        self.assertFalse(store.exists("k"))
        self.assertIsNone(store.get("k"))
        self.assertFalse(store.rem("k"))

    def test_set_many_writes_everything(self):
        store = self.make_store()
        store.set_many({"a": 1, "b": {"x": True}})
        self.assertEqual(store.get("a"), 1)
        self.assertEqual(store.get("b"), {"x": True})

    def test_set_many_with_empty_dict_is_a_noop(self):
        store = self.make_store()
        store.set_many({})  # must not raise, must not open a transaction
        store.set("a", 1)
        self.assertEqual(store.get("a"), 1)

    def test_data_survives_reopening(self):
        path = self.tmp_path / "state.db"
        first = KeyValueStore(str(path))
        first.set("k", ["v"])
        first.close()

        second = self.make_store()
        self.assertEqual(second.get("k"), ["v"])

    def test_creates_missing_parent_directory(self):
        nested = self.tmp_path / "deep" / "nested" / "state.db"
        store = KeyValueStore(str(nested))
        self._stores.append(store)
        store.set("k", "v")
        self.assertTrue(nested.exists())


class TestLegacyMigration(StorageTestCase):
    LEGACY = {
        "chat:-1001:currencies": ["USD", "RUB"],
        "user:1001:currencies": ["RUB", "USD", "ILS", "GBP", "EUR"],
    }

    def write_legacy(self, text, name="state.json"):
        path = self.tmp_path / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_valid_legacy_json_is_imported_and_archived(self):
        legacy = self.write_legacy(json.dumps(self.LEGACY))
        store = self.make_store()

        self.assertEqual(store.get("chat:-1001:currencies"), ["USD", "RUB"])
        self.assertEqual(store.get("user:1001:currencies"), ["RUB", "USD", "ILS", "GBP", "EUR"])
        self.assertFalse(legacy.exists())
        archived = self.tmp_path / "state.json.migrated"
        self.assertTrue(archived.exists())
        self.assertEqual(json.loads(archived.read_text(encoding="utf-8")), self.LEGACY)

    def test_broken_json_does_not_raise_and_keeps_the_original(self):
        # A dump killed mid-write: truncated object, exactly the pickleDB failure.
        legacy = self.write_legacy('{"user:1:currencies": ["USD", "RU')

        with self.assertLogs("storage", level="ERROR"):
            store = self.make_store()

        self.assertIsNone(store.get("user:1:currencies"))
        self.assertTrue(legacy.exists(), "a broken legacy file must stay under its own name")
        self.assertFalse((self.tmp_path / "state.json.migrated").exists())
        # And the empty database is fully usable.
        store.set("k", "v")
        self.assertEqual(store.get("k"), "v")

    def test_empty_legacy_file_is_left_alone(self):
        legacy = self.write_legacy("")

        with self.assertLogs("storage", level="WARNING"):
            store = self.make_store()

        self.assertTrue(legacy.exists())
        self.assertFalse((self.tmp_path / "state.json.migrated").exists())
        store.set("k", "v")
        self.assertEqual(store.get("k"), "v")

    def test_legacy_json_that_is_not_an_object_is_rejected(self):
        legacy = self.write_legacy('["not", "a", "mapping"]')

        with self.assertLogs("storage", level="ERROR"):
            store = self.make_store()

        self.assertTrue(legacy.exists())
        self.assertFalse(store.exists("0"))

    def test_no_legacy_file_at_all(self):
        store = self.make_store()
        self.assertIsNone(store.get("anything"))
        self.assertFalse((self.tmp_path / "state.json").exists())

    def test_migration_does_not_run_twice(self):
        self.write_legacy(json.dumps(self.LEGACY))

        first = KeyValueStore(str(self.tmp_path / "state.db"))
        first.set("chat:-1001:currencies", ["EUR"])  # a change made after the import
        first.close()

        # Someone restores the old JSON next to the database; the second start
        # must ignore it, because the table already holds rows.
        restored = self.write_legacy(json.dumps(self.LEGACY))
        second = self.make_store()

        self.assertEqual(second.get("chat:-1001:currencies"), ["EUR"])
        self.assertTrue(restored.exists(), "an already-migrated store must not touch the file again")

    def test_existing_archive_is_not_overwritten(self):
        previous = self.tmp_path / "state.json.migrated"
        previous.write_text('{"older": "copy"}', encoding="utf-8")
        self.write_legacy(json.dumps(self.LEGACY))

        self.make_store()

        self.assertEqual(json.loads(previous.read_text(encoding="utf-8")), {"older": "copy"})
        extra = [p for p in self.tmp_path.iterdir() if p.name.startswith("state.json.migrated.")]
        self.assertEqual(len(extra), 1)
        self.assertEqual(json.loads(extra[0].read_text(encoding="utf-8")), self.LEGACY)

    def test_json_db_path_does_not_migrate_into_itself(self):
        # src.settings rejects a *.json database path outright, so this is only a
        # backstop for a direct KeyValueStore caller: the derived legacy path would
        # be the database itself, and migrating a file into itself must be a no-op.
        store = self.make_store(name="state.json")
        store.set("k", "v")
        self.assertEqual(store.get("k"), "v")

    def test_broken_json_is_imported_after_it_is_repaired(self):
        """The whole point of keying the import on content instead of on the file.

        First start finds a truncated dump, logs it and starts empty. The operator
        repairs the JSON and restarts — and the settings must arrive. Keying on
        `not self._path.exists()` broke exactly here: connect() had already created
        the database, so the import was disabled forever after one bad start.
        """
        legacy = self.write_legacy('{"user:1001:currencies": ["USD", "RU')

        with self.assertLogs("storage", level="ERROR"):
            first = KeyValueStore(str(self.tmp_path / "state.db"))
        self.assertIsNone(first.get("user:1001:currencies"))
        first.close()

        legacy.write_text(json.dumps(self.LEGACY), encoding="utf-8")
        second = self.make_store()

        self.assertEqual(second.get("user:1001:currencies"), ["RUB", "USD", "ILS", "GBP", "EUR"])
        self.assertFalse(legacy.exists())
        self.assertTrue((self.tmp_path / "state.json.migrated").exists())

    def test_import_is_not_repeated_when_the_rename_failed(self):
        """Rows present, legacy file still under its own name -> no second import.

        Simulates the archive step failing (read-only directory, EPERM): the data
        is already in sqlite, so a re-import would be a silent overwrite of every
        change made since.
        """
        self.write_legacy(json.dumps(self.LEGACY))
        first = KeyValueStore(str(self.tmp_path / "state.db"))
        first.close()

        # Put the source back, exactly as a failed rename would have left it.
        restored = self.write_legacy(json.dumps(self.LEGACY))
        second = KeyValueStore(str(self.tmp_path / "state.db"))
        second.set("user:1001:currencies", ["EUR"])
        second.close()

        third = self.make_store()
        self.assertEqual(third.get("user:1001:currencies"), ["EUR"])
        self.assertTrue(restored.exists())

    def test_an_emptied_store_does_not_reimport_the_archive(self):
        # A user legitimately cleared every setting. The table is empty again, but
        # the only JSON around is the *.migrated archive, and that name is never
        # looked at — so their deletion is not undone on the next restart.
        self.write_legacy(json.dumps(self.LEGACY))
        first = KeyValueStore(str(self.tmp_path / "state.db"))
        for key in self.LEGACY:
            first.rem(key)
        first.close()

        second = self.make_store()
        self.assertIsNone(second.get("user:1001:currencies"))
        self.assertTrue((self.tmp_path / "state.json.migrated").exists())

    def test_two_stores_importing_at_once_produce_the_same_rows(self):
        # Two containers starting on one fresh volume. Both see an empty table and
        # both import; the UPSERT makes the second import a no-op rather than a
        # duplicate-key error.
        self.write_legacy(json.dumps(self.LEGACY))
        first = KeyValueStore(str(self.tmp_path / "state.db"))
        self._stores.append(first)
        first.set_many(self.LEGACY)  # what a racing second importer would write

        with closing(sqlite3.connect(str(self.tmp_path / "state.db"))) as raw:
            self.assertEqual(raw.execute("SELECT COUNT(*) FROM kv").fetchone()[0], len(self.LEGACY))
        self.assertEqual(first.get("user:1001:currencies"), ["RUB", "USD", "ILS", "GBP", "EUR"])

    def test_the_searched_legacy_path_is_logged(self):
        # A custom database name derives a legacy name that may not be the real
        # one (settings.sqlite3 -> settings.json, never user_settings.json). The
        # INFO line is the only way to notice that from the log.
        self.write_legacy(json.dumps(self.LEGACY), name="user_settings.json")

        with self.assertLogs("storage", level="INFO") as captured:
            store = self.make_store(name="settings.sqlite3")

        self.assertIsNone(store.get("user:1001:currencies"))
        self.assertTrue(any(str(self.tmp_path / "settings.json") in line for line in captured.output))


class TestNonSqliteDatabaseFile(StorageTestCase):
    def test_a_json_file_under_the_db_path_is_rejected_with_a_readable_message(self):
        # What a prod .env pinned to the old default produces. Without the check
        # sqlite3 raises "file is not a database", which names nothing.
        path = self.tmp_path / "user_settings.db"
        path.write_text('{"user:1001:currencies": ["USD"]}', encoding="utf-8")

        with self.assertRaises(NotASqliteDatabaseError) as caught:
            KeyValueStore(str(path))

        message = str(caught.exception)
        self.assertIn(str(path), message)
        self.assertIn("not a sqlite database", message)

    def test_an_empty_file_is_treated_as_a_fresh_database(self):
        path = self.tmp_path / "state.db"
        path.touch()
        store = KeyValueStore(str(path))
        self._stores.append(store)
        store.set("k", "v")
        self.assertEqual(store.get("k"), "v")


class TestSettingsDbPathValidation(unittest.TestCase):
    """The first line of defence: a *.json database path fails at startup."""

    def build(self, **overrides):
        return Settings(bot_token="t", api_key="k", admin_user_id=1, **overrides)

    def test_json_statistics_path_is_rejected(self):
        with self.assertRaises(ValidationError) as caught:
            self.build(statistics_db_path="data/statistics.json")
        message = str(caught.exception)
        self.assertIn("statistics_db_path", message)
        self.assertIn(".db", message)

    def test_json_user_settings_path_is_rejected(self):
        with self.assertRaises(ValidationError) as caught:
            self.build(user_settings_db_path="data/user_settings.json")
        self.assertIn("user_settings_db_path", str(caught.exception))

    def test_db_paths_are_accepted(self):
        settings = self.build(
            statistics_db_path="data/statistics.db",
            user_settings_db_path="data/user_settings.sqlite3",
        )
        self.assertEqual(settings.statistics_db_path, "data/statistics.db")
        self.assertEqual(settings.user_settings_db_path, "data/user_settings.sqlite3")

    def test_the_rates_cache_may_still_be_json(self):
        # Only the two sqlite paths are constrained; the rates cache really is JSON.
        self.assertEqual(
            self.build(exchange_rates_cache_path="data/exchange_rates_cache.json").exchange_rates_cache_path,
            "data/exchange_rates_cache.json",
        )


class TestFailedCommitLeavesTheConnectionUsable(StorageTestCase):
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

    def make_flaky_store(self):
        store = self.make_store()
        store._conn.close()
        store._conn = sqlite3.connect(
            str(self.tmp_path / "state.db"),
            check_same_thread=False,
            isolation_level=None,
            factory=self.FlakyCommitConnection,
        )
        store._conn.execute("PRAGMA busy_timeout=5000")
        return store

    def test_write_after_a_failed_commit_still_works(self):
        store = self.make_flaky_store()
        store._conn.fail_commit = True

        with self.assertRaises(sqlite3.OperationalError):
            store.set_many({"a": 1, "b": 2})

        self.assertFalse(store._conn.in_transaction, "the failed transaction must be rolled back")

        # And the connection is genuinely reusable, not merely flagged as clean.
        store._conn.fail_commit = False
        store.set_many({"c": 3})
        store.set("d", 4)
        self.assertEqual(store.get("c"), 3)
        self.assertEqual(store.get("d"), 4)
        self.assertIsNone(store.get("a"), "the failed batch must not be partially visible")

    def test_a_failed_batch_is_not_visible_to_another_connection(self):
        store = self.make_flaky_store()
        store._conn.fail_commit = True
        with self.assertRaises(sqlite3.OperationalError):
            store.set_many({"a": 1})
        store._conn.fail_commit = False

        with closing(sqlite3.connect(str(self.tmp_path / "state.db"))) as raw:
            self.assertEqual(raw.execute("SELECT key FROM kv").fetchall(), [])


class TestConcurrency(StorageTestCase):
    THREADS = 8
    ITERATIONS = 60

    def test_parallel_writers_do_not_lose_data_or_corrupt_the_file(self):
        store = self.make_store()
        errors = []
        start = threading.Barrier(self.THREADS)

        def worker(thread_id):
            try:
                start.wait(timeout=5)
                for i in range(self.ITERATIONS):
                    key = f"t{thread_id}:{i}"
                    store.set(key, {"thread": thread_id, "i": i})
                    self.assertEqual(store.get(key), {"thread": thread_id, "i": i})
                store.set_many({f"batch:{thread_id}:{i}": i for i in range(self.ITERATIONS)})
            except Exception as exc:  # noqa: BLE001 - reported through `errors`
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(self.THREADS)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        self.assertEqual(errors, [])
        for thread_id in range(self.THREADS):
            for i in range(self.ITERATIONS):
                self.assertEqual(store.get(f"t{thread_id}:{i}"), {"thread": thread_id, "i": i})
                self.assertEqual(store.get(f"batch:{thread_id}:{i}"), i)

        # Reopen from scratch: proves what is on disk is a valid, complete database.
        store.close()
        reopened = self.make_store()
        expected = 2 * self.THREADS * self.ITERATIONS
        # closing(), not a bare `with`: sqlite3's own context manager commits or
        # rolls back the transaction and leaves the connection (and its file
        # handle) open.
        with closing(sqlite3.connect(str(self.tmp_path / "state.db"))) as raw:
            self.assertEqual(raw.execute("SELECT COUNT(*) FROM kv").fetchone()[0], expected)
        self.assertEqual(reopened.get("t0:0"), {"thread": 0, "i": 0})

    def test_parallel_counter_updates_under_a_manager_lock(self):
        # StatisticsManager keeps its own lock precisely so that read-modify-write
        # sequences do not lose increments. This asserts that they do not.
        manager = StatisticsManager(db_file=str(self.tmp_path / "statistics.db"))
        user = StubUser(1, "user", "User")
        threads = [
            threading.Thread(target=lambda: [manager.log_request(user, None, None) for _ in range(20)])
            for _ in range(4)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        stats = manager.get_statistics(stat_limit=10)
        self.assertEqual(stats["total_requests"], 80)
        self.assertEqual(stats["top_users"][0]["requests"], 80)


class TestUserSettingsManager(StorageTestCase):
    def make_manager(self, name="user_settings.db"):
        return UserSettingsManager(db_file=str(self.tmp_path / name))

    def test_currencies_roundtrip_for_user_and_chat(self):
        manager = self.make_manager()
        self.assertIsNone(manager.get_currencies(42))

        manager.set_currencies(42, ["USD", "EUR"])
        self.assertEqual(manager.get_currencies(42), ["USD", "EUR"])

        # A chat with the same numeric id is a separate entity.
        self.assertIsNone(manager.get_currencies(42, is_chat=True))
        manager.set_currencies(42, ["RUB"], is_chat=True)
        self.assertEqual(manager.get_currencies(42, is_chat=True), ["RUB"])
        self.assertEqual(manager.get_currencies(42), ["USD", "EUR"])

    def test_empty_currency_list_reads_back_as_none(self):
        # Preserved from the pickleDB implementation: an empty list means
        # "no preference", so the bot falls back to the default currencies.
        manager = self.make_manager()
        manager.set_currencies(42, [])
        self.assertIsNone(manager.get_currencies(42))

    def test_settings_survive_a_restart(self):
        first = self.make_manager()
        first.set_currencies(-100200, ["GEL", "USD"], is_chat=True)
        first._db.close()

        second = self.make_manager()
        self.assertEqual(second.get_currencies(-100200, is_chat=True), ["GEL", "USD"])

    def test_chat_disable_and_expiry(self):
        manager = self.make_manager()
        chat_id = -100500
        self.assertFalse(manager.is_chat_disabled(chat_id))

        manager.set_chat_disabled(chat_id, 3600)
        self.assertTrue(manager.is_chat_disabled(chat_id))

        # Expired: reported as enabled again and the key is cleaned up.
        manager._db.set(f"chat:{chat_id}:disabled_until", time.time() - 1)
        self.assertFalse(manager.is_chat_disabled(chat_id))
        self.assertFalse(manager._db.exists(f"chat:{chat_id}:disabled_until"))

    def test_disabled_state_is_per_chat(self):
        manager = self.make_manager()
        manager.set_chat_disabled(-1, 3600)
        self.assertTrue(manager.is_chat_disabled(-1))
        self.assertFalse(manager.is_chat_disabled(-2))

    def test_migrates_legacy_user_settings_json(self):
        legacy = self.tmp_path / "user_settings.json"
        legacy.write_text(json.dumps({
            "chat:-1001:currencies": ["USD", "RUB"],
            "user:1001:currencies": ["RUB", "USD", "ILS", "GBP", "EUR"],
            "chat:-100777:disabled_until": time.time() + 3600,
        }), encoding="utf-8")

        manager = self.make_manager()

        self.assertEqual(manager.get_currencies(-1001, is_chat=True), ["USD", "RUB"])
        self.assertEqual(manager.get_currencies(1001), ["RUB", "USD", "ILS", "GBP", "EUR"])
        self.assertTrue(manager.is_chat_disabled(-100777))
        self.assertTrue((self.tmp_path / "user_settings.json.migrated").exists())
        self.assertFalse(legacy.exists())


class TestStatisticsManager(StorageTestCase):
    def make_manager(self, name="statistics.db"):
        return StatisticsManager(db_file=str(self.tmp_path / name))

    def test_empty_database_gets_default_counters(self):
        stats = self.make_manager().get_statistics(stat_limit=10)
        self.assertEqual(stats["total_requests"], 0)
        self.assertEqual(stats["total_inline_requests"], 0)
        self.assertEqual(stats["unique_users"], 0)
        self.assertEqual(stats["unique_chats"], 0)
        self.assertEqual(stats["top_users"], [])
        self.assertEqual(stats["top_chats"], [])

    def test_log_request_counts_messages_and_inline_queries(self):
        manager = self.make_manager()
        user = StubUser(7, "testuser", "Test User")

        manager.log_request(user, chat_id=-100, chat_title="Test chat")
        manager.log_request(user, chat_id=-100, chat_title="Test chat")
        manager.log_request(user, chat_id=None, chat_title=None, is_inline=True)

        stats = manager.get_statistics(stat_limit=10)
        self.assertEqual(stats["total_requests"], 2)
        self.assertEqual(stats["total_inline_requests"], 1)
        self.assertEqual(stats["unique_users"], 1)
        self.assertEqual(stats["unique_chats"], 1)

        top_user = stats["top_users"][0]
        self.assertEqual(top_user["display_name"], "Test User")
        self.assertEqual(top_user["username"], "testuser")
        self.assertEqual(top_user["requests"], 2)
        self.assertEqual(top_user["inline_requests"], 1)
        self.assertEqual(top_user["total_requests"], 3)
        self.assertIn("last_active_str", top_user)

        self.assertEqual(stats["top_chats"], [{"title": "Test chat", "requests": 2}])

    def test_private_chat_is_not_counted_as_a_separate_chat(self):
        manager = self.make_manager()
        user = StubUser(7, "testuser", "Test User")
        manager.log_request(user, chat_id=7, chat_title=None)
        self.assertEqual(manager.get_statistics(stat_limit=10)["unique_chats"], 0)

    def test_stat_limit_trims_the_top_list(self):
        manager = self.make_manager()
        for user_id in range(5):
            for _ in range(user_id + 1):
                manager.log_request(StubUser(user_id + 1, f"u{user_id}", f"U{user_id}"), None, None)

        stats = manager.get_statistics(stat_limit=2)
        self.assertEqual(len(stats["top_users"]), 2)
        self.assertEqual([u["requests"] for u in stats["top_users"]], [5, 4])
        self.assertEqual(stats["unique_users"], 5)

    def test_statistics_survive_a_restart(self):
        first = self.make_manager()
        first.log_request(StubUser(7, "testuser", "Test User"), -100, "Test chat")
        first._db.close()

        stats = self.make_manager().get_statistics(stat_limit=10)
        self.assertEqual(stats["total_requests"], 1)
        self.assertEqual(stats["unique_users"], 1)

    def test_migrates_legacy_statistics_json(self):
        # Byte-for-byte the shape produced by the pickleDB implementation.
        legacy = self.tmp_path / "statistics.json"
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

        manager = self.make_manager()
        stats = manager.get_statistics(stat_limit=10)

        self.assertEqual(stats["total_requests"], 52)
        self.assertEqual(stats["total_inline_requests"], 16)
        self.assertEqual(stats["unique_users"], 1)
        self.assertEqual(stats["unique_chats"], 1)
        self.assertEqual(stats["top_users"][0]["total_requests"], 68)
        self.assertEqual(stats["top_chats"][0], {"title": "Test chat", "requests": 39})
        self.assertFalse(legacy.exists())
        self.assertTrue((self.tmp_path / "statistics.json.migrated").exists())

        # Counting continues from the migrated numbers, not from zero.
        manager.log_request(StubUser(1001, "testuser", "Test User"), None, None)
        self.assertEqual(manager.get_statistics(stat_limit=10)["total_requests"], 53)

    def test_broken_legacy_statistics_json_still_starts(self):
        legacy = self.tmp_path / "statistics.json"
        legacy.write_text('{"total_requests": 52, "users": {"100', encoding="utf-8")

        with self.assertLogs("storage", level="ERROR"):
            manager = self.make_manager()

        self.assertEqual(manager.get_statistics(stat_limit=10)["total_requests"], 0)
        self.assertTrue(legacy.exists())

    def test_repaired_legacy_statistics_json_is_imported_on_the_next_start(self):
        """The end-to-end version of the retry, through the real manager.

        This is why StatisticsManager no longer seeds its counters at startup: five
        default rows written on the first (failed) start would leave the table
        non-empty, and the retry would never happen.
        """
        legacy = self.tmp_path / "statistics.json"
        legacy.write_text('{"total_requests": 52, "users": {"100', encoding="utf-8")

        with self.assertLogs("storage", level="ERROR"):
            first = self.make_manager()
        first._db.close()

        legacy.write_text(json.dumps({"total_requests": 52, "total_inline_requests": 16}), encoding="utf-8")
        second = self.make_manager()

        self.assertEqual(second.get_statistics(stat_limit=10)["total_requests"], 52)
        self.assertEqual(second.get_statistics(stat_limit=10)["total_inline_requests"], 16)
        self.assertTrue((self.tmp_path / "statistics.json.migrated").exists())

    def test_a_fresh_statistics_store_writes_nothing_at_startup(self):
        # Guards the property the migration criterion depends on: constructing the
        # manager must not put rows into an empty database.
        manager = self.make_manager()
        manager._db.close()
        with closing(sqlite3.connect(str(self.tmp_path / "statistics.db"))) as raw:
            self.assertEqual(raw.execute("SELECT COUNT(*) FROM kv").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
