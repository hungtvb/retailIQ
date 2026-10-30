"""Real Chromium acceptance of the React product workspace with isolated seeded data.

Run after \`cd frontend && npm install && npm run build\`.
Records both desktop and mobile screenshots. Not a fake browser fixture.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:8769"
OUT = Path("data")


def wait_server():
    for _ in range(75):
        try:
            with urlopen(BASE + "/workspace", timeout=1) as reply:
                if reply.status == 200:
                    return
        except OSError:
            time.sleep(.2)
    raise RuntimeError("Product workspace did not start: build frontend first")


def assert_no_node_overlap(page):
    nodes = page.locator(".matrix-node").evaluate_all(
        """elements => elements.map(el => {
            const r = el.getBoundingClientRect();
            return {name: el.getAttribute('aria-label'),left:r.left,right:r.right,
                    top:r.top,bottom:r.bottom};
        })""")
    for i, a in enumerate(nodes):
        for b in nodes[i+1:]:
            horizontal = min(a['right'],b['right'])-max(a['left'],b['left'])
            vertical = min(a['bottom'],b['bottom'])-max(a['top'],b['top'])
            assert not (horizontal > 3 and vertical > 3), (
                f"Execution node overlap: {a['name']} and {b['name']}, "
                f"{horizontal:.1f}x{vertical:.1f}px")


def run_journey(page):
    js_errors = []
    page.on("pageerror", lambda error: js_errors.append(str(error)))
    page.goto(BASE + "/workspace", wait_until="domcontentloaded")
    expect(page.locator(".network-pane")).to_be_visible()
    expect(page.locator(".chat-pane")).to_be_visible()
    expect(page.locator(".matrix-empty")).to_contain_text("Execution network")
    assert page.locator("#tab-workflows").count() == 0, "Legacy Graph tab leaked into the new workspace"

    # Actual POST -> SSE -> backend SQL -> persisted conversation.
    page.get_by_role("button", name="Top sellers").click()
    expect(page.locator(".chat-state")).to_contain_text("Complete", timeout=25000)
    expect(page.locator(".message-assistant")).to_have_count(1)
    expect(page.locator(".matrix-svg")).to_be_visible()
    assert page.locator(".matrix-node").count() >= 2
    assert page.locator(".matrix-node.matrix-agent").count() >= 1, "No routed agent from real SSE"
    assert page.locator(".matrix-node.matrix-tool").count() >= 1, "No observed tool invocation"
    assert page.locator(".matrix-link").count() >= 1, "No observed agent connections"
    expect(page.locator(".answer-evidence")).to_be_visible()
    assert not js_errors, f"Browser exceptions: {js_errors}"
    OUT.mkdir(exist_ok=True)
    assert_no_node_overlap(page)
    page.screenshot(path=str(OUT / "retailiq_product_workspace_desktop.png"), full_page=True)

    # Offline follow-up transfers context deterministically. It is NOT a
    # live LangGraph Command handoff and must be labeled accordingly.
    page.locator("textarea").fill("How many units of the top seller are in stock?")
    page.get_by_role("button", name="Send message").click()
    expect(page.locator(".chat-state")).to_contain_text("Complete", timeout=25000)
    expect(page.locator(".message-assistant")).to_have_count(2)
    expect(page.locator(".matrix-link-context")).to_have_count(1)
    expect(page.locator(".matrix-link-handoff")).to_have_count(0)
    expect(page.locator(".matrix-edge-caption-context")).to_contain_text("OFFLINE CONTEXT")
    # The response must be attributed to the observed inventory agent, not
    # the handoff source or the last node inserted into the frontend map.
    expect(page.locator('.matrix-link-result[data-from="agent:inventory_agent"][data-to="answer"]')).to_have_count(1)
    assert_no_node_overlap(page)
    page.screenshot(path=str(OUT / "retailiq_product_workspace_handoff.png"), full_page=True)
    handoff_count = page.locator(".matrix-node").count()
    assert handoff_count >= 4

    # Actual persisted request ID + privacy-filtered execution events survive reload.
    page.reload(wait_until="domcontentloaded")
    expect(page.locator(".message-assistant")).to_have_count(2)
    expect(page.locator(".matrix-link-context")).to_have_count(1)
    assert page.locator(".matrix-node").count() == handoff_count
    assert page.locator(".matrix-empty").count() == 0

    # Switch between actual saved answer traces; no fabricated handoff on first answer.
    page.get_by_role("button", name="Show execution for answer 2").click()
    expect(page.locator(".matrix-link-context")).to_have_count(0)
    expect(page.locator(".matrix-node.matrix-agent")).to_have_count(1)
    page.get_by_role("button", name="Show execution for answer 4").click()
    expect(page.locator(".matrix-link-context")).to_have_count(1)
    assert not js_errors, f"Browser exceptions: {js_errors}"

    # New session is a draft: no extra record created until first message.
    old_sessions = page.locator(".session-row").count()
    page.get_by_role("button", name="New conversation").click()
    expect(page.locator(".chat-onboarding")).to_be_visible()
    assert page.locator(".session-row").count() == old_sessions
    page.locator("textarea").fill("How many units of AlphaBook Pro 14 are in stock?")
    page.get_by_role("button", name="Send message").click()
    expect(page.locator(".chat-state")).to_contain_text("Complete", timeout=25000)
    expect(page.locator(".session-row")).to_have_count(old_sessions + 1)
    inventory_columns = page.locator(".message-assistant").last.locator(".answer-evidence th").all_text_contents()
    assert len(inventory_columns) > 5, f"Inventory evidence columns unexpectedly dropped: {inventory_columns}"
    assert any("available" in item.lower() for item in inventory_columns), (
        f"Inventory availability evidence hidden from table: {inventory_columns}")
    assert "available" in [x.lower().strip() for x in inventory_columns[:4]], (
        f"Important quantity cannot be seen without horizontal scrolling: {inventory_columns}")

    # Mobile: no horizontal page overflow; real chat and canvas remain accessible.
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.locator(".matrix-svg")).to_be_visible()
    # Wait for the sidebar transform to finish after resizing desktop -> mobile,
    # otherwise the screenshot captures a mid-transition overlay.
    expect(page.locator(".sidebar")).not_to_be_in_viewport()
    page.evaluate("window.scrollTo(0,0)")
    assert_no_node_overlap(page)
    page.screenshot(path=str(OUT / "retailiq_product_workspace_mobile_live.png"), full_page=True)
    page.reload(wait_until="domcontentloaded")
    expect(page.locator(".chat-pane")).to_be_visible()
    expect(page.locator(".network-pane")).to_be_visible()
    page.evaluate("window.scrollTo(0,0)")
    viewport_width = page.evaluate("document.documentElement.scrollWidth")
    assert viewport_width <= 392, f"Mobile horizontal overflow: {viewport_width}"
    page.screenshot(path=str(OUT / "retailiq_product_workspace_mobile.png"), full_page=True)

    # Deletion is real API-backed session removal, including on narrow screens.
    page.get_by_role("button", name="Toggle conversations").click()
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator(".session-row.selected .session-delete").click()
    expect(page.locator(".session-row")).to_have_count(old_sessions)
    expect(page.locator(".chat-onboarding")).to_be_visible()
    assert not js_errors, f"Browser exceptions: {js_errors}"


def main():
    chrome = next((p for name in ("google-chrome", "google-chrome-stable", "chromium")
                   if (p := shutil.which(name))), None)
    if not chrome:
        raise RuntimeError("Chrome/Chromium not installed")
    if not Path("frontend/dist/index.html").is_file():
        raise RuntimeError("Build React workspace before browser E2E: cd frontend && npm install && npm run build")
    from scripts.seed import seed
    with tempfile.TemporaryDirectory(prefix="retailiq-product-e2e-") as temp:
        root = Path(temp)
        db = root / "retail.sqlite3"
        seed(db, write_support_files=False, reference_date=date(2026, 10, 28))
        env = dict(os.environ,
                   RETAILIQ_MODE="offline", RETAILIQ_AS_OF="2026-10-28",
                   RETAILIQ_WORKFLOW_USE_MCP="0",
                   RETAILIQ_DATA_DB=str(db),
                   RETAILIQ_CHAT_DB=str(root / "chat.sqlite3"),
                   RETAILIQ_WORKFLOW_DB=str(root / "runs.sqlite3"),
                   RETAILIQ_CHECKPOINT_DB=str(root / "checkpoints.sqlite3"),
                   RETAILIQ_LOG_FILE=str(root / "events.jsonl"))
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "retailiq.api:app",
             "--host", "127.0.0.1", "--port", "8769", "--log-level", "warning"],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
        )
        try:
            wait_server()
            with sync_playwright() as browser_api:
                browser = browser_api.chromium.launch(
                    executable_path=chrome, headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                try:
                    page = browser.new_page(viewport={"width": 1440, "height": 900})
                    run_journey(page)
                finally:
                    browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


if __name__ == "__main__":
    main()
