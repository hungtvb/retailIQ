"""One real Chromium smoke journey across all four local workflow scenarios.

Runs the actual FastAPI app, SQLite fixture, JavaScript and browser DOM.
No LLM provider or external business service is needed for these simulations.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright


BASE = "http://127.0.0.1:8767"
SCREENSHOT = Path("data/workflow_week4_chromium.png")


def wait_for_app() -> None:
    for _ in range(60):
        try:
            with urlopen(BASE + "/api/workflows/definitions", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("Local API did not become ready")


def journey(page) -> None:
    page.goto(BASE, wait_until="domcontentloaded")
    page.locator("#tab-workflows").click()
    picker = page.locator("#workflow-scenario")
    expect(picker.locator("option")).to_have_count(5)

    def run(scenario: str, expected_node: str):
        picker.select_option(scenario)
        page.locator("#workflow-run").click()
        expect(page.locator("#workflow-run-id")).to_contain_text("Run ")
        expect(page.locator(f'.graph-node[data-node="{expected_node}"]')).to_have_attribute(
            "data-status", "completed"
        )
        expect(page.locator("#workflow-timeline .workflow-timeline-item")).not_to_have_count(0)

    run("week1", "sql_tool")
    run("week2", "freshness_guard")
    run("alerts", "kpi_alert")

    run("week3", "verification")
    expect(page.locator("#workflow-review-controls")).to_be_visible()
    expect(page.locator('.graph-node[data-node="manager_approval"]')).to_have_attribute(
        "data-status", "awaiting"
    )
    page.locator("#workflow-role").select_option("manager")
    page.locator("#workflow-approve").click()
    expect(page.locator("#workflow-run-id")).to_contain_text("approved simulated")
    expect(page.locator('.graph-node[data-node="finalize"]')).to_have_attribute(
        "data-status", "completed"
    )

    page.locator("#workflow-quantity").fill("2")
    run("week4", "verification")
    page.locator('[data-workflow-view="detailed"]').click()
    expect(page.locator(".graph-provenance")).to_contain_text(
        "SQLite: inventory + products + locations"
    )
    page.locator('.graph-node[data-node="inventory_search_agent"]').click()
    expect(page.locator("#workflow-node-detail")).to_contain_text("preflight data")
    expect(page.locator("#workflow-node-detail")).to_contain_text("no agent-owned tool call")
    expect(page.locator("#workflow-timeline .workflow-timeline-item")).to_have_count(8)
    SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SCREENSHOT), full_page=True)

    page.locator("#workflow-replay").click()
    expect(page.locator('.graph-node[data-node="manager_approval"]')).to_have_attribute(
        "data-status", "awaiting", timeout=10000
    )
    page.locator("#workflow-reject").click()
    expect(page.locator("#workflow-run-id")).to_contain_text("rejected")
    expect(page.locator('.graph-node[data-node="finalize"]')).to_have_attribute(
        "data-status", "completed"
    )


def main() -> None:
    chrome = next((p for name in ("google-chrome", "google-chrome-stable", "chromium")
                   if (p := shutil.which(name))), None)
    if not chrome:
        raise RuntimeError("Chromium/Chrome not installed on browser smoke runner")
    env = dict(os.environ, RETAILIQ_MODE="offline")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "retailiq.api:app",
         "--host", "127.0.0.1", "--port", "8767", "--log-level", "warning"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
    )
    try:
        wait_for_app()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chrome, headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 960})
                journey(page)
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
