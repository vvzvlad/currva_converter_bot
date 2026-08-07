# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Writing the on-disk cache: atomicity, the lock it must not hold, and ordering."""

import json
import logging
import threading
from datetime import datetime, timedelta
from unittest import mock

from tests.logcapture import capture_logs
from tests.rates.doubles import LOGGER_NAME


def test_a_successful_update_leaves_a_valid_cache_and_no_temp_file(tmp_path, cache_path, make_manager):
    manager = make_manager()

    data = json.loads(cache_path.read_text(encoding="utf-8"))
    assert data["rates"]["USD"]["EUR"] == 0.5
    assert list(tmp_path.glob("*.tmp")) == []
    assert manager._cache_written_revision == manager._rates_revision


def test_a_write_that_dies_halfway_leaves_the_previous_cache_intact(tmp_path, cache_path, make_manager):
    """The reason for the temp file plus os.replace: writing in place truncates
    the real cache first, so a kill in the middle left a file that no longer
    parses — and the next start had no rates at all."""
    manager = make_manager()
    before = cache_path.read_text(encoding="utf-8")

    def die_halfway(_data, handle, **_kwargs):
        handle.write('{"rates": {"USD"')
        raise OSError("no space left on device")

    with mock.patch.object(json, "dump", side_effect=die_halfway):
        with capture_logs(LOGGER_NAME, logging.ERROR):
            manager._save_cache({"USD": {"EUR": 9.0}}, datetime.now(), manager._rates_revision + 1)

    assert cache_path.read_text(encoding="utf-8") == before
    assert json.loads(before)["rates"]["USD"]["EUR"] == 0.5
    assert list(tmp_path.glob("*.tmp")) == []


def test_writing_the_cache_does_not_block_readers(make_manager):
    """The cache write used to happen while holding the lock get_rate needs, so a
    megabyte of json.dump stalled every message handler."""
    manager = make_manager()
    real_dump = json.dump
    observed = {}

    def dump_and_probe(data, handle, **kwargs):
        # A non-reentrant lock: if the write still ran under it, this acquire
        # would block for the whole timeout and come back False.
        observed["lock_was_free"] = manager._lock.acquire(timeout=1)
        if observed["lock_was_free"]:
            manager._lock.release()
        return real_dump(data, handle, **kwargs)

    with mock.patch.object(json, "dump", side_effect=dump_and_probe):
        assert manager._update_all_rates()

    assert observed["lock_was_free"]


def test_concurrent_saves_end_with_the_newest_snapshot_and_valid_json(tmp_path, cache_path, make_manager):
    manager = make_manager()
    base = datetime.now() + timedelta(seconds=1)
    # The snapshots are ordered by revision, not by their timestamps: the clock can
    # step backwards, an in-process counter cannot.
    first_revision = manager._rates_revision

    def save(index):
        manager._save_cache(
            {"USD": {"EUR": float(index)}},
            base + timedelta(seconds=index),
            first_revision + index,
        )

    threads = [threading.Thread(target=save, args=(index,)) for index in range(1, 11)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    data = json.loads(cache_path.read_text(encoding="utf-8"))
    # Whatever the interleaving, an older snapshot never overwrites a newer one.
    assert data["rates"]["USD"]["EUR"] == 10.0
    assert data["last_update"] == (base + timedelta(seconds=10)).isoformat()
    assert list(tmp_path.glob("*.tmp")) == []
