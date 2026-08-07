# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""The temp files a cache write leaves behind, and the startup sweep that removes them."""

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from unittest import mock

import pytest

from tests.logcapture import capture_logs
from tests.rates.doubles import LOGGER_NAME


@pytest.fixture
def stale(tmp_path, cache_path):
    """A leftover old enough for the cleanup to consider it abandoned."""
    def _stale(suffix):
        leftover = tmp_path / f"{cache_path.name}.{suffix}.tmp"
        leftover.write_text('{"rates": {"USD"', encoding="utf-8")
        old = time.time() - 3600
        os.utime(leftover, (old, old))
        return leftover

    return _stale


def _recorded_temp_names(manager):
    """Names of the temp files two consecutive real saves write.

    os.replace is the last thing _save_cache does with the temp file, so watching it
    reports the name that was actually used instead of recomputing it here.
    """
    recorded = []
    real_replace = os.replace

    def record(src, dst):
        recorded.append(Path(src).name)
        return real_replace(src, dst)

    with mock.patch.object(os, "replace", side_effect=record):
        for index in (1, 2):
            manager._save_cache(
                {"USD": {"EUR": float(index)}},
                datetime.now(),
                manager._rates_revision + index,
            )
    return recorded


def test_a_temp_file_left_by_a_killed_process_is_removed_at_startup(stale, make_manager):
    """Every write picks a fresh temp name, so nothing would ever pick up the ~1 MB
    file left behind by a SIGKILL in the middle of a write."""
    leftover = stale("999999")

    make_manager()

    assert not leftover.exists()


def test_a_temp_file_that_is_being_written_right_now_is_left_alone(tmp_path, cache_path, make_manager):
    """Two containers can share the data volume; deleting the temp file of a live
    writer would break its os.replace."""
    in_flight = tmp_path / f"{cache_path.name}.999999.tmp"
    in_flight.write_text("{}", encoding="utf-8")

    make_manager()

    assert in_flight.exists()


def test_one_leftover_that_cannot_be_removed_does_not_stop_the_cleanup(stale, make_manager):
    """A root-owned temp file (entrypoint.sh runs as root and chowns before gosu, so
    anything written before that stays unwritable) used to abort the whole sweep on
    the first PermissionError, and every other megabyte stayed on the volume."""
    blocked = stale("111111")
    others = [stale("222222"), stale("333333")]

    real_unlink = Path.unlink
    real_glob = Path.glob

    def refuse_one(path, *args, **kwargs):
        # The real permissions are left alone: the test has to run as whatever user
        # invoked it, and root can unlink a root-owned file just fine.
        if path.name == blocked.name:
            raise PermissionError(13, "Operation not permitted")
        return real_unlink(path, *args, **kwargs)

    def blocked_first(path, *args, **kwargs):
        # Directory order is whatever the filesystem feels like, and the bug only
        # shows when the unremovable file comes BEFORE the others — pinning the
        # order is what keeps this test from passing by luck.
        found = real_glob(path, *args, **kwargs)
        return iter(sorted(found, key=lambda item: item.name != blocked.name))

    with mock.patch.object(Path, "unlink", refuse_one):
        with mock.patch.object(Path, "glob", blocked_first):
            with capture_logs(LOGGER_NAME, logging.WARNING) as captured:
                make_manager()

    assert blocked.exists()
    for leftover in others:
        assert not leftover.exists(), f"{leftover.name} was left behind"
    assert any(blocked.name in line for line in captured.output)


def test_two_saves_in_a_row_use_different_temp_file_names(make_manager):
    """The name must be unique because it is unique, not because two writers are
    assumed to have different pids — containers have their own PID namespaces, so
    two of them share pid 1 and a pid-only name is the same name."""
    manager = make_manager()
    temp_names = _recorded_temp_names(manager)

    assert len(temp_names) == 2
    assert temp_names[0] != temp_names[1]


def test_the_cleanup_glob_finds_the_name_a_real_save_writes(tmp_path, cache_path, make_manager):
    """The uniqueness fix changed the temp name, and the cleanup only ever sees
    files through its glob: a name the glob misses is a leftover that stays forever."""
    manager = make_manager()
    temp_name = _recorded_temp_names(manager)[0]
    assert temp_name != cache_path.name

    leftover = tmp_path / temp_name
    leftover.write_text('{"rates": {"USD"', encoding="utf-8")
    old = time.time() - 3600
    os.utime(leftover, (old, old))

    make_manager()

    assert not leftover.exists()
