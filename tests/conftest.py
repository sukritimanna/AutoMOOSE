"""Shared pytest configuration.

Puts the repository root on sys.path so the offline test suite can
``import automoose`` without first installing the package. The tests below
exercise only the pure-Python modules (plugin registry, plugins, recovery,
Skeptic invariants) and the declared MCP tool list; none of them launch the
MOOSE solver or contact a language-model backend, so the whole suite runs
offline and without an API key.
"""
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
