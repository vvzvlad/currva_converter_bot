# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylance: disable=reportMissingImports, reportMissingModuleSource, reportGeneralTypeIssues
# type: ignore

"""Test doubles for the storage tests.

A plain module rather than conftest.py, for the same reason tests/stubs.py is one:
importing helpers from a conftest only works under pytest's default `prepend` import
mode and breaks under `--import-mode=importlib`.
"""


class StubUser:
    """Stand-in for telebot.types.User — log_request only reads these three."""

    def __init__(self, user_id, username=None, first_name=None):
        self.id = user_id
        self.username = username
        self.first_name = first_name
