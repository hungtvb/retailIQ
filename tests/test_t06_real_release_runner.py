"""T06 real-release verifier refuses missing LFS or corrupted release.

These tests run NO provider and cannot substitute for the published G1 CI gate.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _run(tmp_path, *args):
    out = tmp_path / "t06-report.json"
    completed = subprocess.run(
        [sys.executable, "-m", "scripts.verify_t06_real_release",
         "--db", str(tmp_path / "fiction.sqlite"),
         "--manifest", str(tmp_path / "manifest.json"),
         "--knowledge-root", str(tmp_path / "knowledge"),
         "--retailiq-manifest", str(tmp_path / "pinned.json"),
         "--out", str(out), *args],
        cwd=ROOT, capture_output=True, text=True, timeout=20,
    )
    assert out.exists(), completed.stderr
    return completed, json.loads(out.read_text(encoding="utf-8"))


def test_missing_published_lfs_reports_not_run_not_pass(tmp_path):
    result, report = _run(tmp_path)
    assert result.returncode == 2, result.stderr
    assert report["status"] == "NOT_RUN"
    assert report["reason_code"] == "MISSING_RELEASE_OR_LFS"
    assert "PASS" not in result.stdout


def test_corrupt_or_unpublished_release_is_fail_not_a_fixture_pass(tmp_path):
    (tmp_path / "fiction.sqlite").write_bytes(b"not a published sqlite release")
    (tmp_path / "manifest.json").write_text("{}", encoding="utf8")
    (tmp_path / "pinned.json").write_text("{}", encoding="utf8")
    (tmp_path / "knowledge").mkdir()
    result, report = _run(tmp_path)
    assert result.returncode == 1, result.stderr
    assert report["status"] == "FAIL"
    assert report["reason_code"] == "VERIFICATION_FAILED"
    assert report["mode"].endswith("NO_LLM")
    assert "error_type" in report
