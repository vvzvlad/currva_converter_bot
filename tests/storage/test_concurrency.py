# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Several threads hammering one store, and one manager."""

import sqlite3
import threading
from contextlib import closing

from src.statistics_manager import StatisticsManager
from tests.storage.doubles import StubUser

THREADS = 8
ITERATIONS = 60


def test_parallel_writers_do_not_lose_data_or_corrupt_the_file(tmp_path, make_store):
    store = make_store()
    errors = []
    start = threading.Barrier(THREADS)

    def worker(thread_id):
        try:
            start.wait(timeout=5)
            for i in range(ITERATIONS):
                key = f"t{thread_id}:{i}"
                store.set(key, {"thread": thread_id, "i": i})
                assert store.get(key) == {"thread": thread_id, "i": i}
            store.set_many({f"batch:{thread_id}:{i}": i for i in range(ITERATIONS)})
        except Exception as exc:  # noqa: BLE001 - reported through `errors`
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert errors == []
    for thread_id in range(THREADS):
        for i in range(ITERATIONS):
            assert store.get(f"t{thread_id}:{i}") == {"thread": thread_id, "i": i}
            assert store.get(f"batch:{thread_id}:{i}") == i

    # Reopen from scratch: proves what is on disk is a valid, complete database.
    store.close()
    reopened = make_store()
    expected = 2 * THREADS * ITERATIONS
    # closing(), not a bare `with`: sqlite3's own context manager commits or
    # rolls back the transaction and leaves the connection (and its file
    # handle) open.
    with closing(sqlite3.connect(str(tmp_path / "state.db"))) as raw:
        assert raw.execute("SELECT COUNT(*) FROM kv").fetchone()[0] == expected
    assert reopened.get("t0:0") == {"thread": 0, "i": 0}


def test_parallel_counter_updates_under_a_manager_lock(tmp_path, make_manager):
    # StatisticsManager keeps its own lock precisely so that read-modify-write
    # sequences do not lose increments. This asserts that they do not.
    manager = make_manager(StatisticsManager, "statistics.db")
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
    assert stats["total_requests"] == 80
    assert stats["top_users"][0]["requests"] == 80
