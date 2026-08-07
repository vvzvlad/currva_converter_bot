# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Shared fixtures for the storage tests.

Every test gets its own pytest tmp_path: no shared state between tests and nothing
ever touches the real data/ directory.

The doubles live in tests/storage/doubles.py.
"""

import sqlite3

import pytest

from src.storage import KeyValueStore


@pytest.fixture
def closers():
    """Bookkeeping so every store and manager a test opens gets closed."""
    registered = []
    yield registered
    for close in registered:
        try:
            close()
        except sqlite3.ProgrammingError:
            pass  # already closed by the test itself


@pytest.fixture
def make_store(tmp_path, closers):
    """Build a KeyValueStore under the test's private directory."""
    def _make_store(name="state.db", **kwargs):
        store = KeyValueStore(str(tmp_path / name), **kwargs)
        closers.append(store.close)
        return store

    return _make_store


@pytest.fixture
def store(make_store):
    """The default store — tests/storage/test_kv_store.py wants nothing else."""
    return make_store()


@pytest.fixture
def make_manager(tmp_path, closers):
    """Build a manager on a database file under the test's private directory.

    Overridden per module (see test_user_settings.py / test_statistics.py) so the
    call sites only ever pass a file name. The manager's own close() is registered
    rather than the store's: StatisticsManager also has a reporting thread to stop.
    """
    def _make_manager(manager_cls, name):
        manager = manager_cls(db_file=str(tmp_path / name))
        closers.append(manager.close)
        return manager

    return _make_manager
