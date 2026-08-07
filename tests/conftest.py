# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

import os

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
