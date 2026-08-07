"""Durable key-value storage on top of stdlib sqlite3.

Replaces pickleDB, whose `dump()` truncated the target file (`open(..., 'wt')`)
and then serialised the whole database twice — once inline, once from a second
thread — with no temp file, no atomic rename and no fsync. With telebot running
handlers on a thread pool that meant two concurrent writers could interleave
into one file and leave behind invalid JSON, losing every stored setting.

sqlite gives us the three properties we actually need — atomic commits, a
process-wide write lock and crash safety — for free, and drops a dependency.
"""

import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(os.path.splitext(os.path.basename(__file__))[0])


_SCHEMA = "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
_UPSERT = (
    "INSERT INTO kv (key, value) VALUES (?, ?) "
    "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
)

# Suffix appended to a legacy JSON file once its contents are in sqlite. The
# original is never deleted: it is the only rollback path if the import is wrong.
MIGRATED_SUFFIX = ".migrated"

# First 16 bytes of every sqlite database file, header string included.
_SQLITE_MAGIC = b"SQLite format 3\x00"


class NotASqliteDatabaseError(RuntimeError):
    """The configured database path holds a file that is not a sqlite database.

    Raised instead of letting sqlite3 fail with a bare `DatabaseError: file is
    not a database`, which says nothing about which setting is wrong.
    """


class KeyValueStore:
    """A tiny key -> JSON-value store. Only what the managers actually use.

    Threading model: ONE connection opened with `check_same_thread=False`, and a
    single `threading.Lock` around every statement.

    Why not a connection per thread via `threading.local`: telebot creates and
    retires worker threads, so per-thread connections accumulate file handles for
    threads that are already gone and each new thread has to re-run the PRAGMAs.
    The write volume here is a handful of tiny rows per message, so serialising
    on one lock costs nothing measurable — while a shared connection without a
    lock is genuinely unsafe (a `Connection` may only be used by one thread at a
    time, and `check_same_thread=False` disables the check, not the requirement).

    The lock is only ever held inside a single method, and the only method that
    calls another one (`set_many` -> `_rollback_quietly`) calls a private helper
    that never takes the lock, so it cannot deadlock and never nests.
    """

    def __init__(self, db_path: str, legacy_json_path: Optional[str] = None) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # The legacy file is derived from the new path (data/statistics.db ->
        # data/statistics.json) rather than configured separately, so there is
        # exactly one path setting per store. If the caller still points the
        # store at a *.json path, `legacy` would equal `_path` — guard against
        # trying to migrate a file into itself.
        legacy = Path(legacy_json_path) if legacy_json_path else self._path.with_suffix(".json")
        self._legacy_path: Optional[Path] = None if legacy == self._path else legacy

        # Before connect(), because connect() would happily treat any existing
        # file as a database and fail later with an unhelpful message.
        self._reject_non_sqlite_file()

        self._lock = threading.Lock()
        # isolation_level=None -> no implicit transactions: single statements
        # commit on their own and multi-statement writes are wrapped in an
        # explicit BEGIN/COMMIT (see set_many). Nothing is ever left uncommitted.
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False, isolation_level=None)

        # WAL: a reader never blocks the writer and a half-written transaction is
        # rolled back on the next open instead of leaving a truncated file — the
        # exact failure mode pickleDB had.
        # synchronous=NORMAL: in WAL mode this is crash-safe for a process kill
        # (the WAL is replayed); only a host power loss can drop the last few
        # commits. Worth it — FULL means an fsync per commit, and these are chat
        # settings and request counters, not payments.
        # busy_timeout: wait instead of raising if another process (a leftover
        # container, a manual sqlite3 session) holds the write lock.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute(_SCHEMA)

        # The trigger for the one-shot import is the CONTENT of the store, not the
        # existence of its file: connect() above already created the file, so "the
        # file is new" would also be false after any failed first start (broken
        # JSON, no disk space, a kill between connect() and the import) and the
        # import would never be retried — a silent, permanent loss of every stored
        # setting. "No rows yet" is self-healing instead; see _migrate_legacy for
        # the case-by-case reasoning.
        if not self._has_rows():
            # A broken import must never take the bot down with it: worst case we
            # start empty and the untouched JSON is still there to retry from.
            try:
                self._migrate_legacy()
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("Legacy migration into %s failed unexpectedly: %s", self._path, exc)
        elif self._legacy_path is not None and self._legacy_path.exists():
            # Rows present AND the legacy file still under its original name. Either
            # it was imported and the rename failed, or an earlier start failed to
            # import it and the table has since been filled by ordinary traffic — a
            # single message is enough, log_request writes counters on every one.
            # The two cases are indistinguishable from here, so say what is certain
            # and name the way out: without this line the skipped file is completely
            # invisible in the log, and the operator keeps restarting for nothing.
            logger.warning(
                "Legacy store %s is still present, but %s already holds data — not importing. "
                "If it was never imported, stop the bot, move %s aside and start again.",
                self._legacy_path, self._path, self._path,
            )

    def _reject_non_sqlite_file(self) -> None:
        """Fail early, and readably, if the database path points at something else.

        The realistic case is a deployment that still pins the pre-migration
        defaults (`STATISTICS_DB_PATH=data/statistics.json`): sqlite would open the
        JSON file, raise `DatabaseError: file is not a database` on the first
        statement, and the container would crash-loop with no hint at the cause.
        `src.settings` already rejects a *.json path outright; this covers every
        other way a non-database file can end up under the configured name.
        """
        if not self._path.exists() or self._path.stat().st_size == 0:
            return  # missing or freshly created -> sqlite will initialise it
        try:
            with open(self._path, "rb") as handle:
                header = handle.read(len(_SQLITE_MAGIC))
        except OSError as exc:
            # Anything that is not a readable regular file lands here, and both
            # realistic cases come from the container: docker creates a DIRECTORY at
            # the mount point when `volumes:` names a file that does not exist yet
            # (IsADirectoryError), and a volume owned by another uid gives
            # PermissionError when entrypoint.sh did not manage to fix it. Left
            # unwrapped, the function whose entire job is a pointed message would
            # instead produce a bare traceback from an `open()` call.
            raise NotASqliteDatabaseError(
                f"{self._path} cannot be read as a sqlite database file ({exc}). Make sure the "
                f"*_DB_PATH setting points at a file (not a directory) that this process may read "
                f"and write — a bind mount of a path that does not exist yet becomes a directory."
            ) from exc
        if header != _SQLITE_MAGIC:
            raise NotASqliteDatabaseError(
                f"{self._path} exists but is not a sqlite database. Point the *_DB_PATH "
                f"setting at a .db file; if this is the old pickleDB JSON store, leave it "
                f"where it is and use a .db path — it is imported automatically on first start."
            )

    def _has_rows(self) -> bool:
        """True if the table already holds data. Cheap: stops at the first row."""
        return self._conn.execute("SELECT 1 FROM kv LIMIT 1").fetchone() is not None

    # --- key-value API -------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        # Decoding outside the lock: it is pure CPU work on a private string.
        return default if row is None else json.loads(row[0])

    def set(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        with self._lock:
            self._conn.execute(_UPSERT, (key, payload))

    def set_many(self, items: Dict[str, Any]) -> None:
        """Write several keys in ONE transaction — all of them or none.

        This is what replaces pickleDB's auto_dump: logging a single request used
        to rewrite the whole file up to five times (twice each, from two threads),
        with the cost growing with the number of users. Here it is one commit.
        """
        if not items:
            return
        payload = [(key, json.dumps(value, ensure_ascii=False)) for key, value in items.items()]
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                self._conn.executemany(_UPSERT, payload)
                # COMMIT is INSIDE the try on purpose: it has its own failure modes
                # (disk full, SQLITE_BUSY past busy_timeout) and a failed COMMIT
                # leaves the transaction open. On the single shared connection that
                # is unrecoverable — every later write raises "cannot start a
                # transaction within a transaction", and StatisticsManager.log_request
                # swallows those, so the bot would keep answering "currencies set"
                # while nothing reached the disk until a restart.
                #
                # `with self._conn:` would also recover on the Pythons we support
                # (Connection.__exit__ rolls back after a failed commit since 3.11 —
                # 3.9 leaks the transaction), but it would not save the explicit
                # BEGIN: with isolation_level=None nothing starts a transaction on
                # its own, so the block would read as if it were transactional while
                # relying on a version-dependent detail for the failure path. Doing
                # both ends here keeps the boundary visible and the behaviour fixed.
                self._conn.execute("COMMIT")
            except Exception:
                self._rollback_quietly()
                raise

    def _rollback_quietly(self) -> None:
        """Return the connection to a usable state, never replacing the real error.

        Called with the lock already held, and it never takes the lock itself. The
        caller re-raises the original exception either way — this only decides what
        gets logged, and the two outcomes are worlds apart:

        - sqlite already rolled back on its own, so ROLLBACK raises "no transaction
          is active". That IS the state we wanted; DEBUG and move on;
        - ROLLBACK genuinely failed and the transaction is still open. On the single
          shared connection that is the unrecoverable state set_many exists to
          prevent — every later write dies on BEGIN with "cannot start a transaction
          within a transaction", and log_request swallows those. It has to be ERROR,
          and it has to be visible at the default LOG_LEVEL=INFO.

        The two are told apart by `in_transaction`, i.e. by the state the connection
        is actually in, not by matching the message text of the exception.
        """
        try:
            self._conn.execute("ROLLBACK")
        except sqlite3.Error as exc:
            if self._conn.in_transaction:
                logger.error("ROLLBACK failed and the transaction is still open on %s: %s", self._path, exc)
            else:
                logger.debug("Rollback found no open transaction: %s", exc)

    def rem(self, key: str) -> bool:
        """Delete a key. Returns True if it was there."""
        with self._lock:
            cursor = self._conn.execute("DELETE FROM kv WHERE key = ?", (key,))
            return cursor.rowcount > 0

    def exists(self, key: str) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT 1 FROM kv WHERE key = ? LIMIT 1", (key,)).fetchone()
        return row is not None

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- one-shot import from the pickleDB-era JSON --------------------------

    def _migrate_legacy(self) -> None:
        """Import `<name>.json` into a database that has no rows of its own.

        pickleDB stored a flat `{key: json_value}` object, which maps 1:1 onto
        this table. The caller runs this only while the table is empty, and the
        combination "table empty AND the legacy file is still under its original
        name" is what keeps it both retryable and non-repeating:

        - import failed for any reason (unreadable file, invalid JSON, not an
          object, sqlite error, no disk space) -> nothing was written and nothing
          was renamed, so the next start tries again. Fix the JSON, restart, done;
        - import succeeded but the rename failed -> the table has rows, so the
          next start skips the import and no key is imported twice;
        - import succeeded completely -> the file is gone from its original name,
          so there is nothing to import even if the table is emptied later;
        - everything legitimately deleted, with a `*.json.migrated` next to it ->
          the original name does not exist, so the archive is never re-imported;
        - two instances starting at once on a fresh volume -> both import the same
          rows, and the UPSERT makes that idempotent.
        """
        legacy = self._legacy_path
        if legacy is None:
            return

        # Logged unconditionally: the legacy name is DERIVED from the database
        # path, so a custom path (data/settings.sqlite3) looks for
        # data/settings.json and will not find data/user_settings.json. Without
        # this line that mismatch is invisible — the bot just starts empty.
        logger.info("Store %s is empty, looking for a legacy JSON store at %s", self._path, legacy)
        if not legacy.exists():
            logger.info("No legacy store at %s, starting with an empty database.", legacy)
            return

        try:
            raw = legacy.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.error("Cannot read legacy store %s: %s. Starting with an empty database.", legacy, exc)
            return

        if not raw.strip():
            # Empty file — most likely a pickleDB dump killed right after it
            # truncated the target. There is nothing to import and nothing to
            # archive, so leave it alone rather than hide it behind .migrated.
            logger.warning("Legacy store %s is empty, nothing to migrate.", legacy)
            return

        try:
            data = json.loads(raw)
        except ValueError as exc:
            # Truncated or interleaved JSON. Do NOT rename: the file is the only
            # copy of whatever is still recoverable, and keeping the name intact is
            # what makes the retry work — nothing was written, so the next start
            # sees an empty table plus this file and imports it.
            logger.error(
                "Legacy store %s is not valid JSON (%s). Starting with an empty database; the file "
                "is left untouched. Fix it and restart to import it — but only while %s is still "
                "empty: the first write closes that window (one incoming message is enough), and "
                "from then on the import is skipped.", legacy, exc, self._path)
            return

        if not isinstance(data, dict):
            logger.error(
                "Legacy store %s holds %s, expected a JSON object. Starting with an empty database; "
                "the file is left untouched.", legacy, type(data).__name__)
            return

        try:
            self.set_many(data)
        except (sqlite3.Error, TypeError, ValueError) as exc:
            logger.error("Failed to import %s into %s: %s. Starting with an empty database.", legacy, self._path, exc)
            return

        logger.info("Migrated %d key(s) from %s into %s", len(data), legacy, self._path)
        self._archive_legacy(legacy)

    def _archive_legacy(self, legacy: Path) -> None:
        """Rename the imported JSON aside so it stays available for a rollback."""
        target = legacy.with_name(legacy.name + MIGRATED_SUFFIX)
        if target.exists():
            # Never clobber an earlier archive — it may be the older, better copy.
            target = legacy.with_name(f"{legacy.name}{MIGRATED_SUFFIX}.{int(time.time())}")
        try:
            legacy.rename(target)
            logger.info("Legacy store archived as %s", target)
        except OSError as exc:
            # Not fatal, and not a source of duplicates either: the rows are in the
            # table now, so the next start sees a non-empty store and skips the
            # import regardless of what this file is called.
            logger.error("Imported %s but could not rename it to %s: %s", legacy, target, exc)
