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


def chat_query_journey(page) -> None:
    """Real browser conversational journeys with SQL-independent stock expectations."""
    import json
    from collections import defaultdict

    from scripts.audit_queries import Oracle

    oracle = Oracle(Path("data/retailiq.sqlite3"))

    page.locator("#tab-assistant").click()

    def new_chat() -> None:
        page.locator("#chat-new").click()
        expect(page.locator("#chat-welcome")).to_be_visible()

    def submit(question: str) -> tuple[list[dict], str]:
        field = page.locator("#q")
        field.fill(question)
        before = field.evaluate("""el => ({
          value:el.value, valid:el.checkValidity(),
          validation:el.validationMessage, form:el.form?.id
        })""")
        page.evaluate("""() => {
          window.__riChatSubmitCount = 0;
          document.querySelector('#ask-form').addEventListener(
            'submit', () => window.__riChatSubmitCount += 1, {once: true}
          );
        }""")
        page.locator("#ask-submit").click()
        try:
            expect(page.locator("#response-state")).to_contain_text("COMPLETE", timeout=15000)
        except AssertionError:
            after = page.evaluate("""() => ({
              formSubmitCount:window.__riChatSubmitCount,
              inputValue:document.querySelector('#q').value,
              formValid:document.querySelector('#ask-form').checkValidity(),
              submitDisabled:document.querySelector('#ask-submit').disabled,
              error:document.querySelector('#chat-error').textContent,
              welcomeHidden:document.querySelector('#chat-welcome').hidden,
              state:document.querySelector('#response-state').textContent
            })""")
            raise AssertionError(f"Browser chat submit diagnostic: before={before}, after={after}") from None
        payload = json.loads(page.locator("#raw").text_content())
        return payload["records"], page.locator("#answer").inner_text()

    def verify_stock(records: list[dict], answer: str, period: str, count: int,
                     rank: int | None = None) -> None:
        ordered = oracle.top(period, count if rank is None else max(5,rank))
        skus = ([ordered[rank - 1]["sku"]] if rank is not None else
                [row["sku"] for row in ordered])
        expected = {sku: oracle.available(sku) for sku in skus}
        actual = defaultdict(int)
        for row in records:
            actual[row["sku"]] += row["available"]
        assert dict(actual) == expected, f"Browser output did not match SQLite: {dict(actual)} != {expected}"
        for sku in expected:
            assert sku in answer, f"Browser answer omitted {sku}"
        expect(page.locator("#summary-agent")).to_have_text("inventory agent")

    # Direct multi-product stock, not a replenishment decision.
    new_chat()
    rows, answer = submit("Tồn kho của top 5 sản phẩm bán chạy tháng 10 năm 2026?")
    verify_stock(rows, answer, "2026-10", 5)

    # Pronoun refers to exactly the preceding user's September ranking.
    new_chat()
    submit("Top 5 sản phẩm bán chạy tháng 9 năm 2026?")
    rows, answer = submit("Tồn kho của các sản phẩm đó?")
    verify_stock(rows, answer, "2026-09", 5)

    # Ranked reference must use second September seller, not top one.
    new_chat()
    submit("Top 5 sản phẩm bán chạy tháng 9 năm 2026?")
    rows, answer = submit("Tồn kho của sản phẩm đứng thứ 2?")
    verify_stock(rows, answer, "2026-09", 5, rank=2)


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
                chat_query_journey(page)
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
