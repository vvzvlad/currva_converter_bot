# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

# Test doubles shared by the test modules. A plain module, not conftest.py:
# importing from conftest only works under pytest's default `prepend` import mode
# and breaks under `--import-mode=importlib`.
# `from tests.stubs import ...` also works outside pytest even without an __init__.py,
# because tests/ is picked up as a PEP 420 namespace package: both
# `python -m unittest tests.test_parser` and `python -m unittest discover -s tests`
# pass. Only a bare `python -m unittest discover` from the repo root collects nothing
# (Ran 0 tests, exit 5): its start directory is `.` and discovery does not descend into
# a namespace package, so tests/ is never looked at. Use `-s tests` or pytest.

from src.currency_parser import CurrencyParser


class StubCurrencyParser(CurrencyParser):
    # Named Stub*, not Test*: pytest would try to collect a Test* class as a test
    # case and warn about its __init__.
    def process_currencies(self, currencies):
        return currencies


class StubExchangeRatesManager:
    def get_rate(self, from_currency, to_currency):
        # A fixed rate of 1 keeps the expected formatter output independent of live rates.
        return 1.0
