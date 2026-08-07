"""Marks tests/ as a regular package. Do not delete — `from tests.stubs import ...` needs it.

Without this file tests/ is only a PEP 420 namespace portion. The import machinery
records such a portion and keeps scanning sys.path, so a *regular* package named
`tests` found anywhere later — site-packages of a CI runner image, for instance —
wins outright and `tests.stubs` disappears. That is exactly what happened on the
Gitea runner while every local checkout stayed green.
"""
