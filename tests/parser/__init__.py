"""Marks tests/parser/ as a regular package. Do not delete.

tests/ itself is a regular package (tests/__init__.py explains why that file has to
stay), and a subdirectory of a regular package has to be one too — otherwise
tests.parser is only a PEP 420 namespace portion and any regular package of the same
name found later on sys.path wins over it.
"""
