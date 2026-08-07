# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

from typing import Dict, List, Optional
from datetime import datetime, timedelta
import json
import logging
import math
import threading
import os
import time
import uuid
from pathlib import Path

import requests

from src.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(os.path.splitext(os.path.basename(__file__))[0])


# Cadence between two SUCCESSFUL updates. apilayer bills per request and currency
# rates move slowly enough that a chat bot does not need them fresher than half a
# day, so the steady state costs two paid requests per day.
UPDATES_INTERVAL = 12 * 60 * 60  # 12 hours

# Retry schedule used INSTEAD of UPDATES_INTERVAL while updates keep failing. The
# first retry comes a minute later (a network blip or an apilayer 5xx is normally
# over by then) and the delay doubles up to an hour. Before this, the update thread
# slept the full 12 hours BEFORE its first run, so a first start with an empty cache
# and an unreachable API left the bot answering "нет доступных курсов конвертации"
# for half a day without ever retrying. The hour cap keeps a long outage under ~24
# extra requests a day.
RETRY_INITIAL_INTERVAL = 60      # 1 minute
RETRY_MAX_INTERVAL = 60 * 60     # 1 hour

# Cap on the backoff exponent, so a manager that has been failing for months does not
# compute 2**10000 on every loop iteration. 2**32 minutes is already far past the
# RETRY_MAX_INTERVAL cap, so the value is invisible in behaviour.
RETRY_MAX_EXPONENT = 32

# Rates older than this are still served — stale rates are far more useful than no
# rates at all — but every update cycle logs a warning naming the age. Two whole
# update intervals without a single success means the API side is broken rather than
# merely slow, and users are silently getting yesterday's numbers.
STALE_RATES_MAX_AGE = 2 * UPDATES_INTERVAL  # 24 hours

# How long close() waits for the update thread. Only relevant when the thread is in
# the middle of an HTTP request (itself capped at API_REQUEST_TIMEOUT); otherwise it
# is parked on the stop event and returns immediately.
#
# Deliberately short. close() runs from bot.shutdown_managers(), i.e. from inside the
# SIGTERM handler, and docker's stop_grace_period is the budget for the WHOLE shutdown:
# waiting out a stalled HTTP request here eats the time the sqlite stores need to close
# cleanly, and SIGKILL then lands exactly where it hurts. The thread is a daemon, so
# giving up on it costs nothing — it dies with the process.
UPDATE_THREAD_STOP_TIMEOUT = 2

API_REQUEST_TIMEOUT = 10

# How far a cached timestamp may sit in the future before it is treated as broken
# rather than as ordinary jitter. Container clocks and hosts drift by seconds, and an
# NTP correction lands between the write and the read easily enough, so five minutes
# leaves that noise alone; anything beyond it is a timezone change or a clock that
# stepped backwards, not drift.
CLOCK_SKEW_TOLERANCE = timedelta(minutes=5)

# Temp files left by a write that never finished are removed at startup if they are at
# least this old. Age (mtime) is the ONLY filter the cleanup applies — it does not try
# to tell "our" leftovers from anybody else's, because a temp name is unique per write
# and says nothing about whether its writer is still alive. The age check is what keeps
# the cleanup from deleting the temp file of ANOTHER process that is writing right now
# (two containers can share the data volume); a real write takes milliseconds.
STALE_TEMP_FILE_AGE = 60


# What _future_skew reports when the two timestamps cannot be compared at all. The
# exact value carries no meaning — the callers only ask "is this in the future?" — it
# merely has to exceed CLOCK_SKEW_TOLERANCE so an uncomparable stamp is handled as
# broken. The real reason is logged separately, by _future_skew itself.
UNCOMPARABLE_SKEW = CLOCK_SKEW_TOLERANCE + timedelta(seconds=1)


def _future_skew(timestamp: datetime, now: datetime) -> Optional[timedelta]:
    """How far `timestamp` lies in the future, or None when it does not.

    Anything within CLOCK_SKEW_TOLERANCE counts as "not in the future": the point is
    to catch a clock that moved backwards, not to complain about jitter.
    """
    try:
        skew = timestamp - now
    except TypeError:
        # One side is timezone-aware and the other is not, so the two simply cannot be
        # compared. This helper exists to catch a broken timestamp, so it must not be
        # the thing that kills the process over one: its first caller runs inside
        # ExchangeRatesManager.__init__, which src.bot builds at import time, and an
        # exception there is a bot that cannot start at all rather than a failed update.
        # Reported as "in the future" — the conservative answer, since it sends the
        # caller down the refresh path instead of letting it subtract these two values
        # itself and raise the very TypeError caught here.
        logger.warning(
            f"Rates timestamp {timestamp!r} cannot be compared with {now!r} "
            "(timezone-aware vs naive); treating it as broken"
        )
        return UNCOMPARABLE_SKEW
    return skew if skew > CLOCK_SKEW_TOLERANCE else None


class ExchangeRatesManager:
    def __init__(
        self,
        cache_file: str = settings.exchange_rates_cache_path,
        update_interval: float = UPDATES_INTERVAL,
        retry_initial_interval: float = RETRY_INITIAL_INTERVAL,
        retry_max_interval: float = RETRY_MAX_INTERVAL,
        start_update_thread: bool = True,
    ):
        # The intervals are constructor arguments purely so tests can drive the whole
        # retry cycle in milliseconds instead of hours; production uses the defaults.
        self._cache_file = Path(cache_file)
        # This manager is constructed first of the three, so on a clean volume
        # nobody has created data/ yet and the first _save_cache() would die with
        # FileNotFoundError — silently, since it only logs. The cache would never
        # be written and every restart would burn another paid API request.
        self._cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._rates: Dict = {}
        # Age of the rates we are serving. Survives a restart through the cache file,
        # so right after a start it usually predates this process.
        self._last_update: Optional[datetime] = None
        # When an update last succeeded IN THIS PROCESS — None while every attempt so
        # far has failed, even when _last_update is set from the cache. Kept apart
        # from _last_update so "we are serving old rates" and "we cannot reach the
        # API" are two distinguishable states in the log.
        self._last_successful_update: Optional[datetime] = None
        self._consecutive_failures = 0
        self._lock = threading.Lock()
        # Deliberately NOT self._lock: the cache write must never block get_rate.
        # This one only keeps two savers from writing at the same time (see _save_cache).
        self._save_lock = threading.Lock()
        # Ordering key for cache writes: a counter bumped once per successful update,
        # NOT a wall-clock timestamp. Two savers can be in flight at once (a slow update
        # overtaken by the next one) and the older one must not overwrite the newer
        # snapshot — but wall time cannot answer that question, because the clock can
        # step backwards (a TZ change, an NTP correction, a data volume moved between
        # hosts). It is also deliberately NOT seeded from the cache file: the guard is
        # about two savers inside THIS process, and seeding it from disk meant that a
        # file claiming to be from the future silently blocked every write for as long
        # as the clock stayed behind it.
        self._rates_revision = 0
        self._cache_written_revision = 0
        self._currencies: List[str] = []

        self._update_interval = update_interval
        self._retry_initial_interval = retry_initial_interval
        self._retry_max_interval = retry_max_interval
        self._stop_updates = threading.Event()
        self._update_thread_handle: Optional[threading.Thread] = None

        self._cleanup_stale_temp_files()
        self._initialize_rates()
        if start_update_thread:
            self._start_update_thread()

    def _cleanup_stale_temp_files(self) -> None:
        """Delete leftovers of a cache write that never finished.

        _save_cache writes to `<cache>.<pid>.<random>.tmp` and only unlinks it on the
        error path, so a process killed mid-write (SIGKILL, the OOM killer, power loss)
        leaves roughly a megabyte behind — and every write picks a fresh name, so
        nothing would ever reuse that file.

        Files younger than STALE_TEMP_FILE_AGE are left alone: they may belong to
        another process writing right now (two containers can share the data volume),
        and deleting one from under it would fail its os.replace.
        """
        try:
            cutoff = time.time() - STALE_TEMP_FILE_AGE
            leftovers = list(self._cache_file.parent.glob(f"{self._cache_file.name}.*.tmp"))
        except OSError as e:
            # Housekeeping must never keep the bot from starting.
            logger.warning(f"Failed to list stale rates cache temp files: {str(e)}")
            return

        for leftover in leftovers:
            try:
                if leftover.stat().st_mtime > cutoff:
                    continue
                leftover.unlink()
            except FileNotFoundError:
                continue
            except OSError as e:
                # One file we may not touch must not cost us the whole sweep: this used
                # to abort the loop, leaving every other megabyte-sized leftover on the
                # volume forever. A root-owned temp file is not hypothetical —
                # entrypoint.sh starts as root and chowns the volume before dropping to
                # the service user with gosu, so anything written before that (or put
                # there by hand) stays unwritable for the process that finds it.
                logger.warning(
                    f"Failed to remove the stale rates cache temp file {leftover.name}: {str(e)}"
                )
                continue
            logger.info(f"Removed a stale rates cache temp file: {leftover.name}")

    def _initialize_rates(self) -> None:
        """Initialize rates from cache file or download new ones"""
        if self._load_cache():
            now = datetime.now()
            skew = _future_skew(self._last_update, now)
            if skew is not None:
                # The snapshot claims to be newer than "now", so its real age is
                # unknown. Trusting it would freeze the rates for good: the "older
                # than two hours" test below can never be true for a timestamp in the
                # future, so the bot would keep serving that snapshot across every
                # restart without ever refreshing it.
                logger.warning(
                    f"Cached rates are stamped {skew} in the future (last update "
                    f"{self._last_update.isoformat()}); the clock moved backwards, refreshing"
                )
                self._update_all_rates()
            elif now - self._last_update > timedelta(hours=2):
                logger.info("Cached rates are too old, updating...")
                self._update_all_rates()
        else:
            logger.info("No valid cache found, downloading rates...")
            self._update_all_rates()

        # Say right at startup what the bot is going to serve — including the case
        # where the answer is "nothing at all".
        self._log_rates_age()

    def _load_cache(self) -> bool:
        """Load rates from cache file"""
        try:
            if not self._cache_file.exists():
                return False
            with open(self._cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            rates = data['rates']
            last_update = datetime.fromisoformat(data['last_update'])
            if last_update.tzinfo is not None:
                # Everything else here works in naive local time (datetime.now()), and
                # mixing the two raises TypeError on the first subtraction — which
                # happens in _initialize_rates, i.e. inside __init__, i.e. at import of
                # src.bot. fromisoformat accepts an offset happily, so the cache only
                # has to come from a build whose _save_cache used an aware `now` for
                # the bot to die on import with `restart: always` looping it forever.
                # astimezone() keeps the instant and only drops the representation.
                last_update = last_update.astimezone().replace(tzinfo=None)

            # Nothing is published into the fields until the WHOLE file has been
            # understood. Assigning the rates before parsing the date meant that an
            # unparsable date returned False with the rates already in memory: the bot
            # converted, while the log and rates_age() said there were no rates at all,
            # and kept saying it until an update finally succeeded.
            self._rates = rates
            self._last_update = last_update
            self._currencies = list(rates.keys())
            # _cache_written_revision is deliberately NOT touched here: it orders the
            # writes made by THIS process, and a timestamp read from the file used to
            # veto every one of them whenever it happened to be in the future.
            logger.info(f"Loaded rates from cache, last update: {self._last_update}")
            return True

        except Exception as e:
            logger.error(f"Failed to load rates cache: {str(e)}")
            return False

    def _save_cache(self, rates: Dict, last_update: datetime, revision: int) -> None:
        """Write the rates cache atomically, without holding self._lock.

        `revision` is the ordering key — see _rates_revision. It is passed in rather
        than read here because it identifies the snapshot being written, which was
        taken before this call.

        Two separate problems this shape solves:
          - the file is around a megabyte, and json.dump on it is slow enough that
            doing it under self._lock stalled get_rate for every message handler;
          - open(path, 'w') truncates the real cache first, so a kill in the middle
            left a half-written file that _load_cache then rejects — the next start
            began with no rates and burned a paid API request.
        _save_lock serialises two concurrent savers, so that the revision check, the
        write and the os.replace happen as one step and the older snapshot cannot land
        last; it is never held while rates are read, so it cannot put a handler to sleep.
        """
        # The random suffix is what makes the name unique, so that two writers sharing
        # the data volume cannot end up in the same temp file and publish the mix.
        # A pid does NOT give that: every container has its own PID namespace, so two of
        # them routinely run the same pid — it is kept in the name only as a hint about
        # who wrote the file. A file left behind by a process that died mid-write is
        # removed by _cleanup_stale_temp_files at startup, by age.
        tmp_path = self._cache_file.with_name(
            f"{self._cache_file.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
        )
        try:
            with self._save_lock:
                # A slow save that started earlier must not overwrite the newer
                # snapshot another saver in this process already wrote.
                if revision <= self._cache_written_revision:
                    logger.info("Skipping rates cache write: a newer snapshot has already been written")
                    return
                data = {'rates': rates, 'last_update': last_update.isoformat()}
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self._cache_file)
                self._cache_written_revision = revision
            logger.info("Rates cache saved successfully")

        except Exception as e:
            logger.error(f"Failed to save rates cache: {str(e)}")
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _next_update_delay(self) -> float:
        """Seconds to wait before the next update attempt.

        The normal interval while updates succeed, exponential backoff between
        RETRY_INITIAL_INTERVAL and RETRY_MAX_INTERVAL while they fail.
        """
        if self._consecutive_failures <= 0:
            return self._update_interval
        exponent = min(self._consecutive_failures - 1, RETRY_MAX_EXPONENT)
        return min(self._retry_initial_interval * (2 ** exponent), self._retry_max_interval)

    def _update_thread(self) -> None:
        """Background thread for periodic rates updates.

        Waits on the stop event rather than sleeping, so close() does not have to wait
        out a twelve-hour nap.
        """
        while not self._stop_updates.is_set():
            if self._stop_updates.wait(self._next_update_delay()):
                return
            self._update_all_rates()
            self._log_rates_age()

    def _start_update_thread(self) -> None:
        """Start background update thread"""
        thread = threading.Thread(target=self._update_thread, daemon=True)
        self._update_thread_handle = thread
        thread.start()
        logger.info("Started rates update thread")

    def close(self) -> None:
        """Stop the background update thread. Safe to call more than once.

        Public on purpose — see bot.shutdown_managers, which calls it on the way out.
        """
        self._stop_updates.set()
        thread = self._update_thread_handle
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=UPDATE_THREAD_STOP_TIMEOUT)

    def rates_age(self) -> Optional[timedelta]:
        """How old the rates currently being served are, or None if there are none.

        Never negative. A snapshot stamped in the future (the clock stepped back, the
        timezone changed, the data volume came from another host) is reported as zero
        age and the skew itself is logged — a negative age silently switched off the
        staleness warning in _log_rates_age, because nothing negative can ever exceed
        STALE_RATES_MAX_AGE.
        """
        with self._lock:
            if not self._rates or self._last_update is None:
                return None
            last_update = self._last_update

        # Outside the lock: nothing below touches shared state, and logging under a
        # lock every message handler needs is not worth it.
        now = datetime.now()
        skew = _future_skew(last_update, now)
        if skew is not None:
            logger.warning(
                f"Rates timestamp {last_update.isoformat()} is {skew} in the future; "
                "reporting the age as zero (the clock moved backwards)"
            )
            # Returned here rather than falling through to the subtraction below. For a
            # comparable stamp the two are the same answer (a future stamp gives a
            # negative difference, which max() floors at zero anyway); for one that is
            # NOT comparable — the aware/naive case _future_skew reports as broken — the
            # subtraction is exactly the TypeError that helper exists to absorb, and it
            # would escape through _log_rates_age into the update thread, ending the
            # update loop for the rest of the process' life.
            return timedelta(0)
        return max(now - last_update, timedelta(0))

    def _log_rates_age(self) -> None:
        """Report how stale the served rates are — the only signal that a long outage
        is silently handing users last week's numbers."""
        age = self.rates_age()
        if age is None:
            logger.error(
                f"No exchange rates available "
                f"({self._consecutive_failures} consecutive failed updates), the bot cannot convert anything"
            )
        elif age.total_seconds() > STALE_RATES_MAX_AGE:
            logger.warning(
                f"Serving exchange rates that are {age} old "
                f"(threshold {timedelta(seconds=STALE_RATES_MAX_AGE)}, "
                f"{self._consecutive_failures} consecutive failed updates)"
            )
        else:
            logger.info(f"Exchange rates age: {age}")

    def get_rate(self, from_currency: str, to_currency: str) -> Optional[float]:
        """Get exchange rate for currency pair"""
        with self._lock:
            try:
                return self._rates[from_currency][to_currency]
            except KeyError:
                logger.error(f"Rate not found for {from_currency}->{to_currency}")
                return None

    def _fetch_usd_rates(self) -> Dict:
        """Fetch the raw USD-based quotes from the API. Raises on any failure.

        Split out of _update_all_rates so the whole retry/backoff/caching machinery
        can be exercised in tests without touching the network.
        """
        url = "https://api.apilayer.com/currency_data/live"
        headers = {"apikey": settings.api_key}

        response = requests.get(url, headers=headers, timeout=API_REQUEST_TIMEOUT)
        response.raise_for_status()
        result = response.json()

        if not result.get('success'):
            raise RuntimeError(f"API request failed. Response: {result}")

        return result['quotes']

    def _update_all_rates(self) -> bool:
        """Update rates for all currencies. Returns True when the rates were replaced.

        The return value drives the retry schedule in _update_thread: a failure here
        must shorten the next wait, not leave the bot with nothing for half a day.
        """
        logger.info("Starting full rates update")

        try:
            quotes = self._fetch_usd_rates()

            # Get all currencies from API response
            usd_rates = {'USD': 1.0}  # Add base USD currency
            skipped: List[str] = []
            for key, value in quotes.items():
                currency = key[3:]  # Remove 'USD' prefix from key
                # apilayer returns 0 for some dead currencies, and 1.0 / 0 used to
                # raise ZeroDivisionError in the cross-rate loop below — throwing away
                # the whole update, every healthy currency included, until the next
                # scheduled attempt.
                try:
                    rate = float(value)
                except (TypeError, ValueError):
                    skipped.append(currency)
                    continue
                if not math.isfinite(rate) or rate <= 0:
                    skipped.append(currency)
                    continue
                usd_rates[currency] = rate

            if skipped:
                logger.warning(
                    f"Skipped {len(skipped)} currencies with an unusable (non-positive or non-numeric) "
                    f"rate: {', '.join(sorted(skipped))}"
                )

            # An empty (or entirely unusable) quotes payload would otherwise "succeed"
            # and replace working rates with nothing at all.
            if len(usd_rates) < 2:
                raise RuntimeError(f"API returned no usable quotes ({len(quotes)} received, all skipped)")

            currencies = list(usd_rates.keys())

            # Calculate cross-rates for ALL currencies
            new_rates = {}
            for base in currencies:
                base_in_usd = 1.0 / usd_rates[base]
                rates = {}

                for target in currencies:
                    if target != base:
                        target_rate = usd_rates[target]
                        rates[target] = target_rate * base_in_usd

                new_rates[base] = rates

            now = datetime.now()
            with self._lock:
                self._rates = new_rates
                # Assigned here, not while parsing the response: a failure halfway
                # through used to leave the currency list describing rates we never
                # actually stored.
                self._currencies = currencies
                self._last_update = now
                self._last_successful_update = now
                self._consecutive_failures = 0
                # Under the same lock as the rates themselves, so two updates finishing
                # at once get two different revisions in the order they published.
                self._rates_revision += 1
                revision = self._rates_revision

            # Outside the lock on purpose: new_rates is never mutated after being
            # published (every update builds a fresh dict), so the writer cannot race
            # with a reader — see _save_cache.
            self._save_cache(new_rates, now, revision)
            logger.info(f"Successfully updated rates for {len(currencies)} currencies")
            return True

        except Exception as e:
            self._consecutive_failures += 1
            logger.error(
                f"Failed to update rates (failure {self._consecutive_failures} in a row, "
                f"next attempt in {self._next_update_delay():.0f}s): {str(e)}"
            )
            return False

    def get_available_currencies(self) -> List[str]:
        """Get list of all available currencies"""
        with self._lock:
            return self._currencies.copy()
