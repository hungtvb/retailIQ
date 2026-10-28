"""Read-only SQLite adapter for reviewed retail queries.

No arbitrary SQL generation from the LLM is passed here. Every connection is
closed on success or failure; row count and SQLite execution time are bounded.
"""
from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
import re
import sqlite3
import time


DB = Path(__file__).resolve().parents[2] / 'data' / 'retailiq.sqlite3'
MAX_QUERY_ROWS = 10_000
SQLITE_BUSY_SECONDS = 3.0
SQLITE_QUERY_SECONDS = 4.0


def query(sql: str, args: tuple = ()) -> list[dict]:
    """Execute an internal reviewed SELECT, returning bounded materialized rows.

    This is a safety boundary, not a general-purpose SQL interpreter.
    Parameter binding is required for caller-provided values.
    """
    if not isinstance(sql, str) or re.match(r'^\s*SELECT\b', sql, re.I) is None:
        raise ValueError('Only reviewed SELECT queries permitted')
    if not isinstance(args, (tuple, list)):
        raise TypeError('SQL parameters must be a sequence')

    # mode=ro prevents write access even if a future caller passes bad SQL.
    # closing(), unlike "with connection", actually closes the DB handle.
    db_path = Path(os.environ.get('RETAILIQ_DATA_DB') or DB)
    uri = db_path.resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True, timeout=SQLITE_BUSY_SECONDS)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only = ON')
        deadline = time.monotonic() + SQLITE_QUERY_SECONDS

        def stop_expensive_query() -> int:
            return int(time.monotonic() >= deadline)

        connection.set_progress_handler(stop_expensive_query, 1_000)
        try:
            rows = connection.execute(sql, args).fetchmany(MAX_QUERY_ROWS + 1)
        finally:
            connection.set_progress_handler(None, 0)
        if len(rows) > MAX_QUERY_ROWS:
            raise ValueError('SQL result exceeds the configured row limit')
        return [dict(row) for row in rows]
