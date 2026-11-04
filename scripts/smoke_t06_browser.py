"""Real Chromium T06 G1 local HITL workspace journey (no paid LLM).

Test-only setup provisions a source-verified, committed UC-01 conversation
directly in an isolated app SQLite. Browser/API, Analyst submit, Manager CAS,
logout and reload are REAL; prior chat tool execution is NOT replayed here.
Fiction published release and historical SQL/policy evidence are real and read-only.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from secrets import token_urlsafe
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

from retailiq.domain.backorder import investigate_backorder
from retailiq.domain.fiction import FictionStore
from scripts.verify_uc01_live_release import (
    independent_oracle, CASE, CUTOFF, SNAPSHOT, WAREHOUSE, RELEASE_SHA,
)


def digest(path: Path) -> str:
    stream_hash = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            stream_hash.update(chunk)
    return stream_hash.hexdigest()


def sign_in(page, base: str, username: str, password: str, role: str) -> None:
    page.goto(base + "/workspace", wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
    page.locator("#auth-username").fill(username)
    page.locator("#auth-password").fill(password)
    page.get_by_role("button", name="Sign in", exact=True).click()
    expect(page.locator(".header-account")).to_contain_text(role, timeout=30000)
    expect(page.locator(".network-pane")).to_be_visible()
    expect(page.locator(".auth-logout")).to_be_visible()


def journey(page, base: str, analyst: tuple[str, str],
            manager: tuple[str, str], case_id: str) -> None:
    sign_in(page, base, *analyst, "analyst")
    page.get_by_role("button", name="G1 verified historical review").click()
    expect(page.locator(".message-assistant")).to_have_count(1)
    expect(page.locator(".review-eligible")).to_be_visible(timeout=30000)
    expect(page.locator(".review-eligible")).to_contain_text(SNAPSHOT)
    page.get_by_role("button", name="Submit for Manager review").click()
    expect(page.locator(".review-item")).to_have_count(1, timeout=30000)
    expect(page.locator(".review-item")).to_contain_text("PENDING")
    expect(page.locator(".review-item")).to_contain_text(case_id)
    expect(page.locator(".review-boundary")).to_contain_text("No warehouse transfer")
    page.reload(wait_until="domcontentloaded")
    expect(page.locator(".review-item")).to_contain_text("PENDING", timeout=30000)
    page.get_by_role("button", name="Sign out").click()
    expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
    assert page.locator(".message-assistant").count() == 0

    sign_in(page, base, *manager, "manager")
    expect(page.locator(".session-row")).to_have_count(0)
    expect(page.locator(".message-assistant")).to_have_count(0)
    expect(page.locator(".review-item")).to_have_count(1, timeout=30000)
    expect(page.locator(".review-item")).to_contain_text(SNAPSHOT)
    page.get_by_role("button", name="Approve locally").click()
    expect(page.locator(".review-notice")).to_contain_text(
        "APPROVED_LOCAL", timeout=30000)
    expect(page.locator(".review-notice")).to_contain_text("no transfer executed")
    expect(page.locator(".review-item")).to_have_count(0)
    page.get_by_role("button", name="Sign out").click()
    expect(page.get_by_role("heading", name="Sign in")).to_be_visible()

    sign_in(page, base, *analyst, "analyst")
    expect(page.locator(".review-item")).to_contain_text(
        "APPROVED LOCAL", timeout=30000)
    expect(page.locator(".session-row")).to_have_count(1)
    expect(page.locator(".review-boundary")).to_contain_text("No warehouse transfer")
    page.get_by_role("button", name="Sign out").click()
    page.reload(wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="Sign in")).to_be_visible()


def main() -> None:
    p = argparse.ArgumentParser(description="Chromium on published Fiction G1, no paid model")
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--knowledge-root", type=Path, required=True)
    p.add_argument("--retailiq-manifest", type=Path,
                   default=Path("data/fiction/manifest.json"))
    args = p.parse_args()
    if not Path("frontend/dist/index.html").is_file():
        raise RuntimeError("Build frontend before G1 Chromium journey")
    chrome = next((shutil.which(v) for v in
                   ("google-chrome", "google-chrome-stable", "chromium")
                   if shutil.which(v)), None)
    if not chrome:
        raise RuntimeError("Chromium unavailable: T06 browser is NOT VERIFIED")
    oracle = independent_oracle(
        args.db, args.manifest, args.knowledge_root, args.retailiq_manifest)
    source_hash = digest(args.db)
    with tempfile.TemporaryDirectory(prefix="ri-t06-browser-") as temp:
        root = Path(temp)
        env = dict(os.environ, RETAILIQ_MODE="offline",
                   RETAILIQ_FICTION_DB=str(args.db.resolve()),
                   RETAILIQ_FICTION_MANIFEST=str(args.manifest.resolve()),
                   RETAILIQ_FICTION_KNOWLEDGE_ROOT=str(args.knowledge_root.resolve()),
                   RETAILIQ_CHAT_DB=str(root / "app.sqlite"),
                   RETAILIQ_CHECKPOINT_DB=str(root / "checkpoints.sqlite"),
                   RETAILIQ_LOG_FILE=str(root / "events.jsonl"),
                   LANGSMITH_TRACING="false")
        store = FictionStore.open(args.db, args.manifest)
        result = investigate_backorder(
            store, oracle["case_id"], knowledge_root=args.knowledge_root)
        assert result["disposition"] == "NEEDS_REVIEW"
        assert result["data"]["cutoff"] == CUTOFF
        assert result["data"]["evidence_candidates"][0]["snapshot_id"] == SNAPSHOT

        from retailiq.infrastructure import auth, sessions
        with patch.dict(os.environ, env):
            analyst = ("g1analyst_" + uuid4().hex[:16], token_urlsafe(32))
            manager = ("g1manager_" + uuid4().hex[:16], token_urlsafe(32))
            owner = auth.create_local_user(analyst[0], "analyst", analyst[1])
            auth.create_local_user(manager[0], "manager", manager[1])
            token, _csrf = auth.issue_auth_session(owner)
            principal = auth.principal_from_token(token)
            assert principal is not None
            sid = sessions.create_session("G1 verified historical review",
                                          owner_user_id=owner)["id"]
            response = {
                "answer": "Verified historical warehouse candidate; needs human review.",
                "intent": "backorder",
                "active_agent": "backorder_agent",
                "disposition": result["disposition"],
                "approval_status": result["approval_status"],
                "source": result["source"],
                "temporal": result["temporal"],
                "evidence_refs": result["record_refs"],
                "capability_plan": {
                    "case_id": CASE,
                    "capabilities": ["fiction.backorder.investigate"],
                },
                "request_id": "g1browser" + uuid4().hex[:22],
            }
            sessions.add_turn(sid, "Investigate " + CASE, response, principal=principal)
            binding = sessions.last_committed_case_binding(sid, owner_user_id=owner)
            assert binding is not None and binding["source_sha256"] == RELEASE_SHA
            auth.revoke_session(principal)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = "http://127.0.0.1:" + str(port)
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "retailiq.api:app",
             "--host", "127.0.0.1", "--port", str(port),
             "--log-level", "warning", "--no-access-log"],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError("G1 local API exited before browser started")
                try:
                    with urlopen(base + "/health", timeout=.5) as reply:
                        if reply.status == 200:
                            break
                except (URLError, OSError, TimeoutError):
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError("G1 local API did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=chrome, headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"])
                try:
                    page = browser.new_page(viewport={"width": 1440, "height": 900})
                    journey(page, base, analyst, manager, CASE)
                finally:
                    browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        assert digest(args.db) == source_hash == RELEASE_SHA, (
            "Fiction release changed during Chromium authenticated local review")
    print("T06 G1 Chromium: PASS — Analyst → Manager → owner reload; "
          "Fiction SHA unchanged; no live LLM or warehouse mutation")


if __name__ == "__main__":
    main()
