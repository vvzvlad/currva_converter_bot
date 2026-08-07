# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""The one-shot import of the pickleDB-era JSON store."""

import json
import logging
import sqlite3
from contextlib import closing

import pytest

from src.storage import KeyValueStore
from tests.logcapture import capture_logs

LEGACY = {
    "chat:-1001:currencies": ["USD", "RUB"],
    "user:1001:currencies": ["RUB", "USD", "ILS", "GBP", "EUR"],
}


@pytest.fixture
def write_legacy(tmp_path):
    def _write_legacy(text, name="state.json"):
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return path

    return _write_legacy


def test_valid_legacy_json_is_imported_and_archived(tmp_path, make_store, write_legacy):
    legacy = write_legacy(json.dumps(LEGACY))
    store = make_store()

    assert store.get("chat:-1001:currencies") == ["USD", "RUB"]
    assert store.get("user:1001:currencies") == ["RUB", "USD", "ILS", "GBP", "EUR"]
    assert not legacy.exists()
    archived = tmp_path / "state.json.migrated"
    assert archived.exists()
    assert json.loads(archived.read_text(encoding="utf-8")) == LEGACY


def test_broken_json_does_not_raise_and_keeps_the_original(tmp_path, make_store, write_legacy):
    # A dump killed mid-write: truncated object, exactly the pickleDB failure.
    legacy = write_legacy('{"user:1:currencies": ["USD", "RU')

    with capture_logs("storage", logging.ERROR):
        store = make_store()

    assert store.get("user:1:currencies") is None
    assert legacy.exists(), "a broken legacy file must stay under its own name"
    assert not (tmp_path / "state.json.migrated").exists()
    # And the empty database is fully usable.
    store.set("k", "v")
    assert store.get("k") == "v"


def test_empty_legacy_file_is_left_alone(tmp_path, make_store, write_legacy):
    legacy = write_legacy("")

    with capture_logs("storage", logging.WARNING):
        store = make_store()

    assert legacy.exists()
    assert not (tmp_path / "state.json.migrated").exists()
    store.set("k", "v")
    assert store.get("k") == "v"


def test_legacy_json_that_is_not_an_object_is_rejected(make_store, write_legacy):
    legacy = write_legacy('["not", "a", "mapping"]')

    with capture_logs("storage", logging.ERROR):
        store = make_store()

    assert legacy.exists()
    assert not store.exists("0")


def test_no_legacy_file_at_all(tmp_path, make_store):
    store = make_store()
    assert store.get("anything") is None
    assert not (tmp_path / "state.json").exists()


def test_migration_does_not_run_twice(tmp_path, make_store, write_legacy):
    write_legacy(json.dumps(LEGACY))

    first = KeyValueStore(str(tmp_path / "state.db"))
    first.set("chat:-1001:currencies", ["EUR"])  # a change made after the import
    first.close()

    # Someone restores the old JSON next to the database; the second start
    # must ignore it, because the table already holds rows.
    restored = write_legacy(json.dumps(LEGACY))
    second = make_store()

    assert second.get("chat:-1001:currencies") == ["EUR"]
    assert restored.exists(), "an already-migrated store must not touch the file again"


def test_existing_archive_is_not_overwritten(tmp_path, make_store, write_legacy):
    previous = tmp_path / "state.json.migrated"
    previous.write_text('{"older": "copy"}', encoding="utf-8")
    write_legacy(json.dumps(LEGACY))

    make_store()

    assert json.loads(previous.read_text(encoding="utf-8")) == {"older": "copy"}
    extra = [p for p in tmp_path.iterdir() if p.name.startswith("state.json.migrated.")]
    assert len(extra) == 1
    assert json.loads(extra[0].read_text(encoding="utf-8")) == LEGACY


def test_json_db_path_does_not_migrate_into_itself(make_store):
    # src.settings rejects a *.json database path outright, so this is only a
    # backstop for a direct KeyValueStore caller: the derived legacy path would
    # be the database itself, and migrating a file into itself must be a no-op.
    store = make_store(name="state.json")
    store.set("k", "v")
    assert store.get("k") == "v"


def test_broken_json_is_imported_after_it_is_repaired(tmp_path, make_store, write_legacy):
    """The whole point of keying the import on content instead of on the file.

    First start finds a truncated dump, logs it and starts empty. The operator
    repairs the JSON and restarts — and the settings must arrive. Keying on
    `not self._path.exists()` broke exactly here: connect() had already created
    the database, so the import was disabled forever after one bad start.
    """
    legacy = write_legacy('{"user:1001:currencies": ["USD", "RU')

    with capture_logs("storage", logging.ERROR):
        first = KeyValueStore(str(tmp_path / "state.db"))
    assert first.get("user:1001:currencies") is None
    first.close()

    legacy.write_text(json.dumps(LEGACY), encoding="utf-8")
    second = make_store()

    assert second.get("user:1001:currencies") == ["RUB", "USD", "ILS", "GBP", "EUR"]
    assert not legacy.exists()
    assert (tmp_path / "state.json.migrated").exists()


def test_import_is_not_repeated_when_the_rename_failed(tmp_path, make_store, write_legacy):
    """Rows present, legacy file still under its own name -> no second import.

    Simulates the archive step failing (read-only directory, EPERM): the data
    is already in sqlite, so a re-import would be a silent overwrite of every
    change made since.
    """
    write_legacy(json.dumps(LEGACY))
    first = KeyValueStore(str(tmp_path / "state.db"))
    first.close()

    # Put the source back, exactly as a failed rename would have left it.
    restored = write_legacy(json.dumps(LEGACY))
    second = KeyValueStore(str(tmp_path / "state.db"))
    second.set("user:1001:currencies", ["EUR"])
    second.close()

    third = make_store()
    assert third.get("user:1001:currencies") == ["EUR"]
    assert restored.exists()


def test_an_emptied_store_does_not_reimport_the_archive(tmp_path, make_store, write_legacy):
    # A user legitimately cleared every setting. The table is empty again, but
    # the only JSON around is the *.migrated archive, and that name is never
    # looked at — so their deletion is not undone on the next restart.
    write_legacy(json.dumps(LEGACY))
    first = KeyValueStore(str(tmp_path / "state.db"))
    for key in LEGACY:
        first.rem(key)
    first.close()

    second = make_store()
    assert second.get("user:1001:currencies") is None
    assert (tmp_path / "state.json.migrated").exists()


def test_two_stores_importing_at_once_produce_the_same_rows(tmp_path, closers, write_legacy):
    # Two containers starting on one fresh volume. Both see an empty table and
    # both import; the UPSERT makes the second import a no-op rather than a
    # duplicate-key error.
    write_legacy(json.dumps(LEGACY))
    first = KeyValueStore(str(tmp_path / "state.db"))
    closers.append(first.close)
    first.set_many(LEGACY)  # what a racing second importer would write

    with closing(sqlite3.connect(str(tmp_path / "state.db"))) as raw:
        assert raw.execute("SELECT COUNT(*) FROM kv").fetchone()[0] == len(LEGACY)
    assert first.get("user:1001:currencies") == ["RUB", "USD", "ILS", "GBP", "EUR"]


def test_the_searched_legacy_path_is_logged(tmp_path, make_store, write_legacy):
    # A custom database name derives a legacy name that may not be the real
    # one (settings.sqlite3 -> settings.json, never user_settings.json). The
    # INFO line is the only way to notice that from the log.
    write_legacy(json.dumps(LEGACY), name="user_settings.json")

    with capture_logs("storage", logging.INFO) as captured:
        store = make_store(name="settings.sqlite3")

    assert store.get("user:1001:currencies") is None
    assert any(str(tmp_path / "settings.json") in line for line in captured.output)
