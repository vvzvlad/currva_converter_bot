# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Test doubles for the rates tests.

A plain module rather than conftest.py, for the same reason tests/stubs.py is one:
importing helpers from a conftest only works under pytest's default `prepend` import
mode and breaks under `--import-mode=importlib`.

Nothing here touches the network — `_fetch_usd_rates` exists as a separate method
precisely so the failure modes can be scripted.
"""

from src.exchange_rates_manager import ExchangeRatesManager

LOGGER_NAME = "exchange_rates_manager"


class ScriptedRatesManager(ExchangeRatesManager):
    """The real manager with the one network call replaced by a script.

    `failures` API calls raise before the quotes start coming back, so "the API is
    down on first start" and "the API recovers on the Nth retry" are both one
    argument away.
    """

    def __init__(self, *args, quotes=None, failures=0, **kwargs):
        # Set before super().__init__: it downloads rates from inside the constructor.
        self.calls = 0
        self.quotes = {"USDEUR": 0.5} if quotes is None else dict(quotes)
        self.failures = failures
        super().__init__(*args, **kwargs)

    def _fetch_usd_rates(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("apilayer is unreachable")
        return dict(self.quotes)
