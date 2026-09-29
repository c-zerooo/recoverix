"""
conftest.py — Global pytest configuration and test isolation for Recoverix.

Guarantees that test executions default to an isolated in-memory SQLite
database unless RECOVERIX_DB_PATH is explicitly set in the environment.
"""

from __future__ import annotations

import os

# Ensure tests default to an isolated in-memory SQLite database.
# Using setdefault preserves explicitly supplied environment configurations.
os.environ.setdefault("RECOVERIX_DB_PATH", ":memory:")
