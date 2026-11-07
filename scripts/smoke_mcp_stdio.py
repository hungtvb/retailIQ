"""Real Fiction MCP stdio + local API scenario acceptance; NOT a live LLM test.

Run with Python 3.12 and requirements-mcp.txt:
    python -m scripts.smoke_mcp_stdio

Uses the manifest-verified 27-table mini Fiction release from the existing
test fixture, never an in-process MCP mock or legacy EL-003 data. Real 199MiB
release acceptance remains a separate data-artifact gate.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

from scripts._evidence_io import safe_tempdir

ROOT = Path(__file__).resolve().parents[1]


def _scenario_fixture(root: Path):
    # Reuse the reviewed adversarial Fiction fixture rather than generating
    # a second schema that might silently drift from production contracts.
    sys.path.insert(0, str(ROOT / "tests"))
    from test_fiction_unified import fiction, reseal, O1, P1, W1, C1
    path, manifest, _ = fiction.__wrapped__(root)
    shipment_id = "88888888-8888-4888-8888-888888888888"
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO shipments VALUES (?,?,?,?,?,?)",
                     (shipment_id, O1, W1, "2026-10-17", "2026-10-18", "delivered"))
    reseal(path, manifest)
    return path, manifest, O1, P1, W1, C1


def _frames(reply):
    frames = []
    for raw in reply.text.split("\n\n"):
        if not raw.startswith("event: "):
            continue
        kind = raw.split("\n", 1)[0][len("event: "):]
        line = next((x for x in raw.split("\n") if x.startswith("data: ")), None)
        if line is not None:
            frames.append((kind, json.loads(line[6:])))
    if not any(kind == "done" for kind, _ in frames):
        raise AssertionError("SSE did not complete")
    return frames


def _assert_failed_mcp_attempts(product: str, warehouse_id: str) -> None:
    """Fault-injected discovery/timeout: failed spans, never false completed."""
    import asyncio
    from langchain_mcp_adapters import client as mcp_client
    from retailiq import mcp_adapter
    from retailiq.observability import bind_event_sink

    class DiscoveryFailure:
        def __init__(self, *args, **kwargs):
            pass

        async def get_tools(self):
            raise OSError("injected MCP subprocess discovery failure")

    class SlowDiscovery:
        def __init__(self, *args, **kwargs):
            pass

        async def get_tools(self):
            await asyncio.sleep(60)

    def assert_failed(events):
        names = [item.get("event") for item in events]
        assert "mcp.tool.started" in names, names
        assert "mcp.tool.failed" in names, names
        assert "mcp.tool.completed" not in names, names

    failed_events: list[dict] = []
    with patch.object(mcp_client, "MultiServerMCPClient", DiscoveryFailure):
        with bind_event_sink(failed_events.append):
            try:
                mcp_adapter.read_fiction_inventory(product, warehouse_id)
            except OSError as exc:
                assert "discovery" in str(exc)
            else:
                raise AssertionError("MCP discovery failure was misclassified as success")
    assert_failed(failed_events)

    timeout_events: list[dict] = []
    with patch.object(mcp_client, "MultiServerMCPClient", SlowDiscovery):
        with patch.object(mcp_adapter, "TIMEOUT_SECONDS", 0.02):
            with bind_event_sink(timeout_events.append):
                try:
                    mcp_adapter.read_fiction_inventory(product, warehouse_id)
                except TimeoutError:
                    pass
                else:
                    raise AssertionError("MCP timeout was misclassified as success")
    assert_failed(timeout_events)


class _FakeRoutingModel:
    """Only the initial explicit CASE-ID router uses a fake provider here."""

    def with_structured_output(self, model):
        return self

    def invoke(self, messages):
        return SimpleNamespace(intent="backorder")


def main() -> None:
    from fastapi.testclient import TestClient
    from retailiq.mcp_adapter import read_fiction_inventory, read_fiction_order
    from retailiq.api import app

    with safe_tempdir(prefix="retailiq-fiction-mcp-") as tmp:
        root = Path(tmp)
        db, manifest, order_id, product_id, warehouse_id, case_id = _scenario_fixture(root)
        original_db_sha = sha256(db.read_bytes()).hexdigest()
        sku = "FR-" + sha256(product_id.encode()).hexdigest()[:16].upper()
        env = {
            "RETAILIQ_MODE": "full",
            "RETAILIQ_FICTION_DB": str(db),
            "RETAILIQ_FICTION_MANIFEST": str(manifest),
            "RETAILIQ_FICTION_KNOWLEDGE_ROOT": str(ROOT / "data/fiction/knowledge"),
            "RETAILIQ_CHAT_DB": str(root / "chat.sqlite3"),
            "RETAILIQ_CHECKPOINT_DB": str(root / "checkpoint.sqlite3"),
            "RETAILIQ_LOG_FILE": str(root / "events.jsonl"),
        }
        with patch.dict(os.environ, env):
            started = time.monotonic()
            inventory = read_fiction_inventory(sku, warehouse_id)
            order = read_fiction_order(order_id)
            direct_elapsed = round(time.monotonic() - started, 3)
            with sqlite3.connect(db) as conn:
                expected_stock = conn.execute(
                    "SELECT quantity_on_hand-reserved_quantity FROM inventory "
                    "WHERE product_id=? AND warehouse_id=?", (product_id, warehouse_id)
                ).fetchone()[0]
                expected_lines = conn.execute(
                    "SELECT order_item_id, product_id, quantity FROM order_items "
                    "WHERE order_id=? ORDER BY order_item_id", (order_id,)
                ).fetchall()
                expected_shipments = conn.execute(
                    "SELECT shipment_id, warehouse_id FROM shipments WHERE order_id=?", (order_id,)
                ).fetchall()
            assert [r["available_snapshot"] for r in inventory["data"]] == [expected_stock]
            assert inventory["scope"]["product_id"] == product_id
            assert any("UNDATED_INVENTORY" in x for x in inventory["limitations"])
            assert [(x["order_item_id"], x["product_id"], x["quantity"])
                    for x in order["data"]["lines"]] == expected_lines
            assert [(x["shipment_id"], x["warehouse_id"])
                    for x in order["data"]["shipments"]] == expected_shipments
            assert order["source"]["sha256"] == inventory["source"]["sha256"]
            assert "CUSTOMER_SECRET" not in json.dumps(order)
            missing_product = read_fiction_inventory("FR-AAAAAAAAAAAAAAAA")
            assert missing_product["data"] == []
            assert missing_product["limitations"] == ["PRODUCT_NOT_FOUND"]
            missing_warehouse = read_fiction_inventory(sku, "00000000-0000-4000-8000-000000000000")
            assert missing_warehouse["data"] == []
            assert missing_warehouse["limitations"] == ["WAREHOUSE_NOT_FOUND"]
            unknown_order = read_fiction_order("00000000-0000-4000-8000-000000000000")
            assert unknown_order["data"] is None
            assert unknown_order["limitations"] == ["ORDER_NOT_FOUND"]
            _assert_failed_mcp_attempts(sku, warehouse_id)

            with patch("retailiq.orchestration.week1_graph.chat_model",
                       return_value=_FakeRoutingModel()):
                client = TestClient(app)
                session = client.post("/api/sessions", json={}).json()["id"]
                temporal = client.post("/ask", json={
                    "session_id": session,
                    "question": f"Stock for {sku} as of 2026-10-01",
                })
                assert temporal.status_code == 422
                assert "UNSUPPORTED_TEMPORAL_SCOPE" in temporal.json()["detail"]
                unbound = client.post("/ask", json={
                    "session_id": session,
                    "question": "Đơn hàng này gồm những sản phẩm nào?",
                })
                assert unbound.status_code == 422
                stock = _frames(client.post("/ask/stream", json={
                    "session_id": session,
                    "question": f"Show stock for {sku} at warehouse {warehouse_id}",
                }))
                stock_result = next(payload for kind, payload in stock if kind == "result")
                assert stock_result["intent"] == "fiction_stock"
                assert stock_result["as_of"] is None  # undated; not a stock snapshot time
                assert stock_result["source"]["sha256"] == order["source"]["sha256"]
                assert any(e.get("event") == "mcp.tool.completed" and
                           e.get("tool") == "inventory_lookup"
                           for kind, e in stock if kind == "log")

                # A new session is used so the most recent committed
                # assistant turn can be the verified backorder binding.
                case_session = client.post("/api/sessions", json={}).json()["id"]
                investigated = _frames(client.post("/ask/stream", json={
                    "session_id": case_session,
                    "question": f"Investigate backorder case {case_id}",
                }))
                initial = next(payload for kind, payload in investigated if kind == "result")
                assert initial["intent"] == "backorder"
                follow = _frames(client.post("/ask/stream", json={
                    "session_id": case_session,
                    "question": "Đơn hàng này gồm những sản phẩm nào?",
                }))
                answer = next(payload for kind, payload in follow if kind == "result")
                assert answer["intent"] == "backorder"
                assert answer["temporal"]["evidence_cutoff"] == initial["temporal"]["evidence_cutoff"]
                assert answer["source"]["sha256"] == initial["source"]["sha256"]
                assert answer["capability_plan"]["capabilities"] == [
                    "fiction.backorder.investigate", "mcp.order_lookup"]
                assert any(e.get("event") == "mcp.tool.completed" and
                           e.get("tool") == "order_lookup"
                           for kind, e in follow if kind == "log")
                historical = client.post("/ask", json={
                    "session_id": case_session,
                    "question": "Trạng thái đơn hàng này tại thời điểm cutoff?",
                })
                assert historical.status_code == 200
                assert historical.json()["disposition"] == "INSUFFICIENT_EVIDENCE"
                assert "ORDER_STATUS_AT_CUTOFF_UNVERIFIED" in historical.json()["reason_codes"]
                trace = client.get(
                    f"/api/sessions/{case_session}/traces/{answer['request_id']}")
                assert trace.status_code == 200
                assert any(x["event"] == "mcp.tool.completed" for x in trace.json()["events"])
                # No order/stock/source write has occurred.
                with sqlite3.connect(db) as conn:
                    assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1
                assert sha256(db.read_bytes()).hexdigest() == original_db_sha

        print(json.dumps({
            "mode": "real_stdio_mcp_with_manifest_verified_fixture",
            "status": "PASS",
            "tool_names": ["inventory_lookup", "order_lookup"],
            "sql_oracle_available": expected_stock,
            "order_lines": len(expected_lines),
            "shipments": len(expected_shipments),
            "stdio_tool_calls": 7,  # 5 direct calls + 2 actual API/graph tool calls
            "direct_tools_elapsed_s": direct_elapsed,
            "provider": "FAKE_ROUTER_FOR_CASE_ONLY",
            "scope": "fixture + FastAPI/SSE/compiled LangGraph; not real release or live LLM",
        }))


if __name__ == "__main__":
    main()
