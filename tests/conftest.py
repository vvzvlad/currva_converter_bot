# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

import atexit
import os
import shutil
import tempfile

# Provide the required credentials BEFORE any test module imports src.settings
# (Settings() is instantiated at import time and would otherwise fail). In CI the
# same variables are injected via the workflow's `env:` block.
os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("ADMIN_USER_ID", "1")

# Metrics reporting OFF for the whole suite, and assigned rather than setdefault:
# tests build real StatisticsManager instances, whose __init__ runs
# _initialize_influx(), and a developer with INFLUX_* filled in (in the environment
# or in the repo-root .env that Settings reads) would otherwise start a reporting
# thread per instance — one that POSTS first and sleeps afterwards, so `make test`
# would push fake statistics into a live InfluxDB. An empty value is the documented
# "disabled" state: _initialize_influx returns right after the falsy check, before
# any of the error branches.
os.environ["INFLUX_VERSION"] = ""

# Same reasoning for the three state paths, and assigned rather than setdefault for the
# same reason: the defaults in Settings point at data/ RELATIVE to the working
# directory, which under `make test` is the developer's own repository. Most tests pass
# an explicit tempfile path, but anything that builds a manager with default arguments
# (importing src.bot is the obvious one — it constructs all three at import time) would
# otherwise open the live statistics and user-settings databases and overwrite the real
# rates cache. Nothing asserts on that today, so it would fail silently.
_STATE_DIR = tempfile.mkdtemp(prefix="currva-bot-tests-")
# The suite is the only writer, so removing the whole directory at interpreter exit is
# enough — no leftovers in /tmp after `make test`, whether it passed or failed.
atexit.register(shutil.rmtree, _STATE_DIR, ignore_errors=True)
os.environ["EXCHANGE_RATES_CACHE_PATH"] = os.path.join(_STATE_DIR, "exchange_rates_cache.json")
os.environ["STATISTICS_DB_PATH"] = os.path.join(_STATE_DIR, "statistics.db")
os.environ["USER_SETTINGS_DB_PATH"] = os.path.join(_STATE_DIR, "user_settings.db")
