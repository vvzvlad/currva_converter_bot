# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

import pytest

from src.currencies import CURRENCIES
from src.currency_formatter import CurrencyFormatter


@pytest.fixture(scope="module")
def formatter():
    return CurrencyFormatter()


@pytest.fixture(scope="module")
def unit_rates():
    # Every pair at exactly 1.0, so the expected output depends only on the
    # formatter and never on live rates.
    return {f"{a}_{b}": 1.0 for a in CURRENCIES for b in CURRENCIES if a != b}
