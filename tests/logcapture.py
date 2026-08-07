# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""pytest-native stand-ins for unittest's assertLogs() / assertNoLogs().

The suite is written with plain functions and fixtures, but a fair number of tests
assert on what a module logs. pytest's own `caplog` would see those records — every
logger in src/ propagates, so everything reaches the root logger caplog attaches to —
but it is a worse tool for this particular job:

  * `caplog.at_level(level)` lowers the threshold on the ROOT logger — process-wide state
    for the duration of the block, so every logger that inherits its level is affected,
    including the ones other threads log through. `caplog.at_level(level, logger=...)`
    narrows that to one logger, the way capture_logs() always does; what it does not
    narrow is where the records are collected. Both put back the level on the way out.
  * caplog collects whatever anybody logged. Naming the logger explicitly is what stops
    a test from silently starting to pass on some other module's records — or on the
    same message emitted from a place the test was never about.
  * assertLogs' own backstop comes with it: the block MUST have logged something, or
    capture_logs() fails. assert_no_logs() is the mirror image, for the blocks that
    must stay silent.
"""

import logging
from contextlib import contextmanager


class _Captured:
    """The records captured inside the block, plus assertLogs' `output` rendering."""

    def __init__(self):
        self.records = []

    @property
    def output(self):
        # "LEVEL:logger.name:message" — the same format assertLogs produces, so the
        # assertions carried over from unittest keep working unchanged.
        return [f"{r.levelname}:{r.name}:{r.getMessage()}" for r in self.records]


@contextmanager
def capture_logs(logger_name: str, level: int = logging.INFO):
    """Capture what `logger_name` logs at `level` or above inside the block.

    The logger's own level is lowered for the duration and restored afterwards, so a
    module that configured itself at import time cannot silence the capture.
    """
    logger = logging.getLogger(logger_name)
    captured = _Captured()

    handler = logging.Handler(level=level)
    handler.emit = captured.records.append

    previous_level = logger.level
    previous_disabled = logger.disabled
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.disabled = False
    try:
        yield captured
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.disabled = previous_disabled

    assert captured.records, (
        f"nothing was logged on {logger_name!r} at {logging.getLevelName(level)} or above"
    )


@contextmanager
def assert_no_logs(logger_name: str, level: int = logging.INFO):
    """The mirror image of capture_logs(): unittest's assertNoLogs.

    Same reasons for existing — the threshold is lowered on the named logger rather than
    globally on root, and the logger under test is named explicitly — and the same
    mechanics: a handler on that named logger for the duration of the block, restored
    afterwards.
    """
    logger = logging.getLogger(logger_name)
    records = []

    handler = logging.Handler(level=level)
    handler.emit = records.append

    previous_level = logger.level
    previous_disabled = logger.disabled
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.disabled = False
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.disabled = previous_disabled

    assert not records, (
        f"{logger_name!r} logged at {logging.getLevelName(level)} or above: "
        f"{[record.getMessage() for record in records]}"
    )
