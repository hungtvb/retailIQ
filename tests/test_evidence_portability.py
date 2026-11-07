"""Evidence-gate portability and CI-gating regressions (deep-review Task 3).

Offline only: no provider calls, no 209 MB Fiction release, no live/smoke run.
Two properties are pinned here:

* A documented live gate must fail on business facts, not on Windows temp-file
  cleanup: ``events.jsonl`` stays open when ``TemporaryDirectory.__exit__``
  runs, which raises ``PermissionError`` (WinError 32) and turns PASS into
  exit 1 while the post-run no-write hash assertion never executes.
* The only gates that exercise the real published Fiction release must not be
  selectable by PR-title wording (deep review C4), or the strongest
  data-integrity check can silently not run while CI stays green.
"""
from __future__ import annotations

import pathlib
import shutil

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
FICTION_JOBS = ("fiction-t04-release", "fiction-t02-oracle")


def _workflow(name: str) -> dict:
    workflow = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf8"))
    assert isinstance(workflow, dict), f"{name} has no workflow mapping"
    return workflow


def _triggers(workflow: dict) -> dict:
    # PyYAML resolves the unquoted YAML 1.1 key ``on`` to the boolean True.
    triggers = workflow["on"] if "on" in workflow else workflow[True]
    assert isinstance(triggers, dict), "workflow has no trigger mapping"
    return triggers


def test_safe_tempdir_survives_open_file():
    from scripts._evidence_io import safe_tempdir

    handle = None
    folder = None
    with safe_tempdir(prefix="retailiq-evidence-portability-") as temp:
        folder = pathlib.Path(temp)
        # Deliberately left open across context exit: the deferred close is what
        # makes cleanup raise WinError 32 on Windows.
        handle = (folder / "events.jsonl").open("a", encoding="utf-8")
        handle.write('{"event": "gate.started"}\n')
        handle.flush()
    # Reaching this point means __exit__ raised nothing on Windows or POSIX.
    assert handle is not None and not handle.closed
    handle.close()
    shutil.rmtree(folder, ignore_errors=True)


def test_both_workflows_parse_without_pr_title_gating():
    names = {"ci.yml", "fiction-integrity.yml"}
    workflows = [path for path in WORKFLOWS.glob("*.yml") if path.name in names]
    assert {path.name for path in workflows} == names
    for path in workflows:
        workflow = _workflow(path.name)
        offenders = [name for name, job in workflow["jobs"].items()
                     if "github.event.pull_request.title" in str(job.get("if", ""))]
        assert offenders == [], f"{path.name} jobs keyed on PR title: {offenders}"


def test_fiction_workflow_has_path_scoped_pr_and_recurring_triggers():
    triggers = _triggers(_workflow("fiction-integrity.yml"))
    assert "workflow_dispatch" in triggers, "manual dispatch gate was removed"
    crons = [entry.get("cron") for entry in triggers.get("schedule") or ()
             if isinstance(entry, dict)]
    assert crons == ["0 3 1 * *"], "Fiction integrity needs its quota-safe monthly schedule"
    paths = triggers["pull_request"].get("paths")
    assert isinstance(paths, list) and paths, "Fiction PR runs must be path scoped"
    assert {"data/fiction/**", "retailiq/domain/fiction.py",
            "retailiq/domain/backorder.py", "retailiq/domain/uc01_review.py",
            "retailiq/orchestration/fiction_handlers.py",
            "retailiq/orchestration/fiction_requests.py",
            "retailiq/api/http.py", "scripts/_evidence_io.py"} <= set(paths)


def test_ci_keeps_python_tests_unfiltered_without_fiction_jobs():
    workflow = _workflow("ci.yml")
    assert not set(FICTION_JOBS).intersection(workflow["jobs"])
    assert "python-tests" in workflow["jobs"]
    triggers = _triggers(workflow)
    assert "pull_request" in triggers
    assert not (triggers["pull_request"] or {}).get("paths")
    assert not (triggers["pull_request"] or {}).get("paths-ignore")


def test_fiction_jobs_keep_event_guards_and_read_only_time_limits():
    """Path-scoped release gates also run monthly and on manual dispatch."""
    workflow = _workflow("fiction-integrity.yml")
    for name in FICTION_JOBS:
        job = workflow["jobs"][name]
        condition = str(job.get("if", ""))
        assert "github.event.pull_request.title" not in condition, (name, condition)
        for event in ("pull_request", "schedule", "workflow_dispatch"):
            assert event in condition, f"{name} no longer runs on {event}: {condition!r}"
        assert job.get("timeout-minutes") == 15, f"{name} lost its bounded runtime"
        assert job.get("permissions", {}).get("contents") == "read", \
            f"{name} must stay read-only"
        for step in job["steps"]:
            assert "github.event.pull_request.title" not in str(step.get("if", ""))


def test_verify_scripts_use_safe_tempdir():
    for name in ("verify_uc01_live_release.py", "verify_uc01_policy_live.py",
                 "smoke_mcp_stdio.py"):
        source = (ROOT / "scripts" / name).read_text(encoding="utf8")
        assert "safe_tempdir(" in source, \
            f"{name} still creates a cleanup-fragile TemporaryDirectory"
        assert "tempfile.TemporaryDirectory(" not in source, \
            f"{name} bypasses the portable temp-dir helper"
