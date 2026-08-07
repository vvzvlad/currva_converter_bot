# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

# The one test double that is not specific to a single test package: the root
# conftest.py builds the shared `parser` fixture out of it, and tests/parser/ and
# tests/formatter/ both use that fixture. A plain module, not conftest.py: importing
# from conftest only works under pytest's default `prepend` import mode and breaks under
# `--import-mode=importlib`. The per-area doubles follow the same rule and live in
# tests/<area>/doubles.py.
#
# The suite is pytest-only, and `python -m unittest discover -s tests` is not a fallback
# way to run it — it fails differently depending on the environment. With BOT_TOKEN /
# API_KEY / ADMIN_USER_ID already set it collects nothing (`Ran 0 tests`): the tests are
# parametrized plain functions taking fixtures, which unittest cannot collect. Without
# them it does not even get that far — conftest.py is not a test module, so the ENV
# bootstrap at the top of tests/conftest.py never runs, and every test module that
# imports something reading src.settings dies with SystemExit(1) and is reported as a
# unittest.loader._FailedTest (ten of them in a checkout with no .env, from tests/rates/,
# tests/storage/ and tests/config/). Run it with `make test`, or `.venv/bin/pytest`
# directly.
#
# tests/ nevertheless stays a REGULAR package, so that `from tests.stubs import ...` and
# `from tests.logcapture import ...` resolve to this checkout rather than to some other
# `tests` package on sys.path — see tests/__init__.py for the CI-runner failure that
# motivated it.

from src.currency_parser import CurrencyParser


class StubCurrencyParser(CurrencyParser):
    # Named Stub*, not Test*: pytest would try to collect a Test* class as a test
    # case and warn about its __init__.
    def process_currencies(self, currencies):
        return currencies
