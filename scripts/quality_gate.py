"""Live localhost HTTP/SSE E2E + bounded synthetic benchmark (NO remote LLM).

This command launches a real Uvicorn process and talks through TCP, not TestClient.
External model and tracing services are deliberately disabled; the offline
deterministic agent is the documented mock substitute for provider-only logic.

Run with: python -m scripts.quality_gate --samples 50
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = {
    "stock": "How many units of AlphaBook Pro 14 are currently in stock?",
    "top": "Which products are top sellers?",
    "revenue": "What is the revenue this month?",
    "product": "Tell me about USB-C GaN Charger 65W",
    "decision": "Which top seller needs a replenishment review based on stock?",
}
SCHEMA_VERSION = 1
FIXTURE_AS_OF = "2026-10-28"


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def percentile(values, p):
    sorted_values = sorted(values)
    if not sorted_values:
        return None
    idx = (len(sorted_values) - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_values) - 1)
    return round(sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (idx - lo), 3)


class LocalHTTP:
    def __init__(self, port):
        self.url = "http://127.0.0.1:" + str(port)

    def call(self, path, *, method="GET", payload=None, host=None, timeout=15):
        headers = {}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if host:
            headers["Host"] = host
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(self.url + path, data=body, headers=headers, method=method)
        started = time.perf_counter_ns()
        try:
            with urlopen(request, timeout=timeout) as response:
                status = response.status
                hdrs = dict(response.headers)
                raw = response.read().decode("utf-8", errors="replace")
        except HTTPError as error:
            status = error.code
            hdrs = dict(error.headers)
            raw = error.read().decode("utf-8", errors="replace")
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        return status, hdrs, raw, elapsed_ms

    def json(self, path, *, method="GET", payload=None, expected=200, host=None):
        status, headers, raw, latency = self.call(
            path, method=method, payload=payload, host=host)
        check(status == expected, "Unexpected HTTP status on " + path + ": " + str(status))
        try:
            value = json.loads(raw) if raw else None
        except ValueError as exc:
            raise AssertionError("Invalid JSON on " + path) from exc
        return value, headers, latency


def parse_events(raw):
    events = []
    for frame in raw.replace("\r\n", "\n").split("\n\n"):
        if not frame.strip() or frame.startswith(":"):
            continue
        lines = frame.split("\n")
        kinds = [line[6:].strip() for line in lines if line.startswith("event:")]
        data = "\n".join(line[5:].lstrip() for line in lines if line.startswith("data:"))
        if data:
            events.append((kinds[0] if kinds else "message", json.loads(data)))
    return events


def assert_stock(rows):
    check(bool(rows), "Stock response has no evidence rows")
    for row in rows:
        check(isinstance(row["available"], int), "Stock availability must be integer")
        check(row["available"] == row["on_hand"] - row["reserved"],
              "Stock arithmetic does not match SQL evidence")
        check(row["available"] >= 0, "Stock must be nonnegative")


def assert_revenue(rows, db_path):
    check(bool(rows), "Revenue response has no evidence rows")
    with sqlite3.connect(db_path) as db:
        oracle = dict(db.execute("""
            SELECT o.channel, SUM(li.quantity*li.unit_price_vnd-li.discount_vnd)
            FROM orders o JOIN order_lines li ON li.order_id=o.id
            WHERE o.status='completed'
              AND o.ordered_at >= '2026-10-01' AND o.ordered_at < '2026-11-01'
            GROUP BY o.channel
        """).fetchall())
    check({row["channel"]: row["net_revenue_vnd"] for row in rows} == oracle,
          "Revenue mismatches independent SQLite query")
    check(sum(row["net_revenue_vnd"] for row in rows) > 0,
          "Revenue must be nonzero for this fixture")


def exercise_e2e(http, report, db_path):
    cases = report["e2e"]["cases"]

    def run(name, action):
        try:
            detail = action() or {}
            cases.append({"name": name, "status": "PASS", **detail})
        except Exception as error:
            cases.append({"name": name, "status": "FAIL",
                          "error_type": type(error).__name__,
                          "reason": str(error)[:180]})

    def endpoints():
        health, _, _ = http.json("/health")
        check(health == {"status": "ok"}, "Health contract changed")
        page, headers, _, _ = http.call("/")
        check(page == 200, "Home page unavailable")
        check(headers.get("content-type", "").startswith("text/html"), "Home type invalid")
        assets, _, _, _ = http.call("/assets/response-format.js")
        check(assets == 200, "Static renderer unavailable")
        defaults, _, _ = http.json("/api/roi/defaults")
        check("monthly_questions" in defaults, "ROI defaults missing")
        roi, _, _ = http.json("/api/roi/estimate", method="POST", payload={})
        check(roi["report_type"] == "illustrative_estimate", "ROI must be illustrative")
        check(roi["business"]["payback_months"] == 3.75, "ROI default payback changed")
        return {"routes_checked": 5}
    run("HTTP UI, health, static assets and ROI", endpoints)

    def conversation():
        session, _, _ = http.json("/api/sessions", method="POST", payload={}, expected=201)
        sid = session["id"]
        status, headers, raw, _ = http.call(
            "/ask/stream", method="POST",
            payload={"question": QUESTIONS["top"], "session_id": sid})
        check(status == 200, "SSE request failed")
        check(headers.get("content-type", "").startswith("text/event-stream"),
              "SSE content type missing")
        events = parse_events(raw)
        types = [kind for kind, _ in events]
        check(types and types[0] == "started" and types[-1] == "done",
              "SSE event boundary broken")
        check("result" in types and "log" in types, "SSE result or logs missing")
        started = events[0][1]
        answer = next(value for kind, value in events if kind == "result")
        check(answer["intent"] == "top" and answer["mode"].startswith("OFFLINE"),
              "Top agent routing mismatch")
        http_request_id = next((value for key, value in headers.items()
                                if key.casefold() == "x-request-id"), None)
        check(http_request_id is not None and
              started["request_id"] == answer["request_id"] == http_request_id,
              "SSE request ID correlation failed")
        followup, _, _ = http.json(
            "/ask", method="POST",
            payload={"question": "How many units of the top seller are in stock?",
                     "session_id": sid})
        check(followup["intent"] == "stock", "Followup routing incorrect")
        check(followup["handoff"]["to"] == "inventory_agent", "Sales-to-inventory handoff missing")
        assert_stock(followup["records"])
        history, _, _ = http.json("/api/sessions/" + sid)
        check([message["role"] for message in history["messages"]] ==
              ["user", "assistant", "user", "assistant"],
              "Session writes not atomic/ordered")
        check(history["active_agent"] == "inventory_agent", "Active agent not persisted")
        status, _, _, _ = http.call("/api/sessions/" + sid, method="DELETE")
        check(status == 204, "Session deletion failed")
        http.json("/api/sessions/" + sid, expected=404)
        return {"turns": 2, "persisted_messages": 4,
                "sse_events": len(events), "session_deleted": True}
    run("Real TCP SSE + agent handoff + session lifecycle", conversation)

    def business():
        checked = []
        for name in ("stock", "revenue", "product", "decision"):
            result, _, _ = http.json("/ask", method="POST",
                                      payload={"question": QUESTIONS[name]})
            check(result["intent"] == name, "Wrong intent: " + name)
            check(result["mode"].startswith("OFFLINE"), "Unexpected provider mode")
            check(isinstance(result["answer"], str) and bool(result["answer"].strip()),
                  "Empty answer: " + name)
            if name == "stock":
                assert_stock(result["records"])
            elif name == "revenue":
                assert_revenue(result["records"], db_path)
            elif name == "product":
                check(bool(result["contexts"]), "Product retrieval returned no evidence")
                check("EL-003" in result["answer"] or
                      any("EL-003" in item["source"] for item in result["contexts"]),
                      "Product source provenance missing")
            elif name == "decision":
                check(result["active_agent"] == "retail_supervisor", "Wrong supervisor")
                check(result["subagents"] == ["sales_agent", "inventory_agent"],
                      "Decision does not identify required specialists")
            checked.append(name)
        return {"intents": checked, "oracle": "SQLite completed orders"}
    run("Five business routes including product lexical and decision review", business)

    def isolation():
        def one(_):
            session, _, _ = http.json("/api/sessions", method="POST", payload={}, expected=201)
            sid = session["id"]
            result, _, _ = http.json("/ask", method="POST", payload={
                "question": QUESTIONS["stock"], "session_id": sid})
            stored, _, _ = http.json("/api/sessions/" + sid)
            check(stored["messages"][0]["content"] == QUESTIONS["stock"],
                  "Cross-session history leaked")
            check(len(stored["messages"]) == 2 and result["intent"] == "stock",
                  "Concurrent independent session lost a turn")
            return sid
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(one, range(8)))
        check(len(set(ids)) == 8, "Duplicate session ID")
        return {"parallel_sessions": len(ids)}
    run("Concurrent independent session isolation", isolation)

    def boundaries():
        http.json("/ask", method="POST", payload={"question": "no"}, expected=422)
        http.json("/ask", method="POST",
                  payload={"question": "A" * 501}, expected=422)
        http.json("/ask", method="POST", payload={
            "question": QUESTIONS["top"],
            "session_id": "00000000-0000-0000-0000-000000000000"}, expected=404)
        http.json("/api/roi/estimate", method="POST",
                  payload={"assisted_share": -0.1}, expected=422)
        http.json("/api/sessions", expected=403, host="untrusted.example")
        logs, _, _ = http.json("/api/logs?limit=5")
        check(isinstance(logs["events"], list), "Log API contract missing")
        check("OPENAI_API_KEY" not in json.dumps(logs), "API secret key name exposed")
        return {"negative_cases": 5, "observability": "local-redacted"}
    run("422, 404, 403, host guard and log viewer", boundaries)


def benchmark(http, samples, report):
    workload = [
        ("health", "GET", "/health", None),
        ("stock", "POST", "/ask", {"question": QUESTIONS["stock"]}),
    ]
    results = []
    for label, method, path, payload in workload:
        for concurrency in (1, 4, 8, 16):
            # Warm-up is not included in latency/throughput measurement.
            for _ in range(3):
                status, _, _, _ = http.call(path, method=method, payload=payload)
                check(status == 200, "Warmup failed for " + label)
            times = []
            failures = []
            def request_one(_):
                status, _, raw, elapsed = http.call(path, method=method, payload=payload)
                valid = status == 200
                if valid and label == "stock":
                    try:
                        value = json.loads(raw)
                        valid = (value["intent"] == "stock" and
                                 len(value["records"]) == 3 and
                                 all(row["available"] ==
                                     row["on_hand"] - row["reserved"]
                                     for row in value["records"]))
                    except (TypeError, KeyError, ValueError):
                        valid = False
                return status, valid, elapsed
            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [executor.submit(request_one, i) for i in range(samples)]
                for future in as_completed(futures):
                    try:
                        status, valid, elapsed = future.result()
                        times.append(elapsed)
                        if not valid:
                            failures.append("HTTP " + str(status))
                    except Exception as error:
                        failures.append(type(error).__name__)
            elapsed_wall = time.perf_counter() - start
            results.append({
                "workload": label,
                "concurrency": concurrency,
                "attempts": samples,
                "completed": len(times),
                "failed": len(failures),
                "errors_sample": failures[:5],
                "p50_ms": percentile(times, 50),
                "p95_ms": percentile(times, 95),
                "p99_ms": percentile(times, 99),
                "max_ms": round(max(times), 3) if times else None,
                "throughput_rps": round(samples / elapsed_wall, 2),
                "wall_seconds": round(elapsed_wall, 3),
            })
    report["benchmark"]["scenarios"] = results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=50)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "quality_reports" / "e2e_benchmark.json")
    opts = parser.parse_args()
    if not 20 <= opts.samples <= 500:
        parser.error("samples must be 20..500")

    from scripts.seed import seed
    report = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": os.environ.get("GITHUB_SHA", "local-unpinned"),
        "runner": {"os": platform.platform(), "python": platform.python_version(),
                   "cpu_count": os.cpu_count()},
        "mode": "real localhost HTTP/SSE with deterministic offline provider substitute",
        "remote_llm_verified": False,
        "real_vector_db_verified": False,
        "real_langsmith_traces_verified": False,
        "browser_e2e_verified": False,
        "e2e": {"cases": []},
        "benchmark": {
            "workload": "fresh localhost TCP calls, synthetic fixture, no keep-alive SLA",
            "samples_per_scenario": opts.samples,
            "latency_unit": "ms",
            "scenarios": []
        }
    }
    with tempfile.TemporaryDirectory(prefix="retailiq-quality-") as temporary:
        temp = Path(temporary)
        db_path = temp / "retailiq.sqlite3"
        seed(db_path, write_support_files=False,
             reference_date=date.fromisoformat(FIXTURE_AS_OF))
        initial_db = sha256(db_path.read_bytes()).hexdigest()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = os.environ.copy()
        env.update({
            "RETAILIQ_MODE": "offline",
            "RETAILIQ_AS_OF": FIXTURE_AS_OF,
            "RETAILIQ_DATA_DB": str(db_path),
            "RETAILIQ_CHAT_DB": str(temp / "sessions.sqlite3"),
            "RETAILIQ_LOG_FILE": str(temp / "events.jsonl"),
            "LANGSMITH_TRACING": "false",
        })
        for key in ("OPENAI_API_KEY", "LANGSMITH_API_KEY", "OPENAI_BASE_URL"):
            env.pop(key, None)
        logfile = (temp / "server.txt").open("w", encoding="utf-8")
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "retailiq.api:app",
             "--host", "127.0.0.1", "--port", str(port),
             "--log-level", "warning", "--no-access-log"],
            cwd=ROOT, env=env, stdout=logfile, stderr=subprocess.STDOUT)
        http = LocalHTTP(port)
        try:
            healthy = False
            for _ in range(100):
                if server.poll() is not None:
                    break
                try:
                    status, _, _, _ = http.call("/health", timeout=0.3)
                    if status == 200:
                        healthy = True
                        break
                except (URLError, OSError, TimeoutError):
                    pass
                time.sleep(0.1)
            check(healthy, "Uvicorn failed to start on localhost")
            exercise_e2e(http, report, db_path)
            benchmark(http, opts.samples, report)
        except Exception as error:
            report["runner_failure"] = {
                "error_type": type(error).__name__, "reason": str(error)[:180]}
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
            logfile.close()
        report["fixture_read_only"] = sha256(db_path.read_bytes()).hexdigest() == initial_db

    report["e2e"]["passed"] = sum(case["status"] == "PASS" for case in report["e2e"]["cases"])
    report["e2e"]["failed"] = sum(case["status"] != "PASS" for case in report["e2e"]["cases"])
    report["benchmark"]["total_requests"] = sum(
        row["attempts"] for row in report["benchmark"]["scenarios"])
    report["benchmark"]["total_failed"] = sum(
        row["failed"] for row in report["benchmark"]["scenarios"])
    report["status"] = "PASS" if (
        "runner_failure" not in report
        and report["e2e"]["failed"] == 0
        and report["e2e"]["passed"] == 5
        and report["benchmark"]["total_requests"] == opts.samples * 8
        and report["benchmark"]["total_failed"] == 0
        and report["fixture_read_only"]
    ) else "FAIL"
    opts.output.parent.mkdir(parents=True, exist_ok=True)
    opts.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "e2e": report["e2e"],
        "benchmark": report["benchmark"],
        "fixture_read_only": report["fixture_read_only"],
        "runner_failure": report.get("runner_failure"),
        "report_file": str(opts.output.resolve())
    }, ensure_ascii=False))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
