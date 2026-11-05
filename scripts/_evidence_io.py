"""Portable I/O helpers shared by the evidence gates in ``scripts/``.

Windows keeps the last handle of a still-open file (for example the
``events.jsonl`` written by ``retailiq.observability``) until the process
closes it, so ``TemporaryDirectory.__exit__`` raises ``PermissionError``
(WinError 32). In the live gates that turned a completed business PASS into
``status: FAIL``/exit 1 before the post-run no-write hash assertion could run.
Evidence gates must fail on business facts, never on temp-dir cleanup.
"""
from __future__ import annotations

import tempfile


def safe_tempdir(**kwargs) -> tempfile.TemporaryDirectory:
    """``tempfile.TemporaryDirectory`` whose cleanup cannot raise.

    Cleanup errors are ignored instead of aborting the gate; the temporary
    folder may survive until the OS/runner reclaims it, which is strictly
    better than reporting a false negative after real business verification.
    """
    return tempfile.TemporaryDirectory(ignore_cleanup_errors=True, **kwargs)
