"""Real local MCP stdio handshake acceptance (optional Week 2 dependency group).

This is NOT an adapter stub or in-process mock:
  python -m pip install 'mcp>=1.28,<2' 'langchain-mcp-adapters>=0.1,<1'
  python -m scripts.smoke_mcp_stdio
"""
from __future__ import annotations

import asyncio
from contextlib import closing
from datetime import date
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from unittest.mock import patch

from scripts.seed import seed

SKU = "EL-003"
ORDER_ID = "ORD-0001"




async def read_order() -> dict:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient({
        "retailiq": {
            "command": sys.executable, "args": ["-m", "retailiq.mcp_server"],
            "transport": "stdio",
        }
    })
    tools = await client.get_tools()
    names = {tool.name for tool in tools}
    assert {"inventory_lookup", "order_lookup"} <= names, (
        f"Expected two real MCP tools; got {sorted(names)}"
    )
    order_tool = next(tool for tool in tools if tool.name == "order_lookup")
    from retailiq.mcp_adapter import decode_tool_result
    return decode_tool_result(await order_tool.ainvoke({"order_id": ORDER_ID}))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="retailiq-mcp-") as root:
        db = Path(root)/"retail.sqlite3"
        seed(db, write_support_files=False, reference_date=date(2026, 10, 28))
        with patch.dict(os.environ, {
            "RETAILIQ_DATA_DB": str(db),
            "RETAILIQ_AS_OF": "2026-10-28",
            "RETAILIQ_CHAT_DB": str(Path(root)/"sessions.sqlite3"),
            "RETAILIQ_LOG_FILE": str(Path(root)/"events.jsonl"),
            "RETAILIQ_INVENTORY_USE_MCP": "1",
            "RETAILIQ_MODE": "offline"
        }):
            from retailiq.mcp_adapter import read_inventory
            rows = read_inventory(SKU)  # actual subprocess/MCP tool invocation
            with closing(sqlite3.connect(db)) as conn:
                stock_expected = conn.execute(
                    "SELECT location_id, on_hand-reserved FROM inventory "
                    "WHERE sku=? ORDER BY location_id", (SKU,)
                ).fetchall()
                order_expected = conn.execute(
                    "SELECT id,status FROM orders WHERE id=?", (ORDER_ID,)
                ).fetchone()
                order_lines_expected = conn.execute(
                    "SELECT sku,quantity FROM order_lines WHERE order_id=? ORDER BY id",
                    (ORDER_ID,)
                ).fetchall()
            observed = sorted((item["location_id"], item["available"]) for item in rows)
            assert observed == stock_expected, (
                f"Inventory tool values mismatch: actual={observed}, expected={stock_expected}"
            )
            order = asyncio.run(read_order())
            assert order["order"]["id"] == order_expected[0]
            assert order["order"]["status"] == order_expected[1]
            assert [(item["sku"], item["quantity"]) for item in order["lines"]] == order_lines_expected
            assert order["source"] == "local_readonly_sqlite"
            # API -> SSE -> real MCP stdio -> validated stock -> persisted
            # request-scoped execution trace, without an external LLM.
            from fastapi.testclient import TestClient
            from retailiq.api import app
            web = TestClient(app)
            sid = web.post('/api/sessions', json={}).json()['id']
            reply = web.post('/ask/stream', json={
                'question': 'How many units of EL-003 are in stock?',
                'session_id': sid,
            })
            assert reply.status_code == 200
            frames = []
            for raw in reply.text.split('\n\n'):
                if not raw.startswith('event: '):
                    continue
                lines = raw.split('\n')
                kind = lines[0][len('event: '):]
                data_line = next((line for line in lines if line.startswith('data: ')), None)
                if data_line:
                    frames.append((kind, json.loads(data_line[len('data: '):])))
            events = [payload for kind, payload in frames if kind == 'log']
            starts = [e for e in events if e.get('event') == 'mcp.tool.started']
            completions = [e for e in events if e.get('event') == 'mcp.tool.completed']
            assert len(starts) == len(completions) == 1, (
                f'MCP calls not actually instrumented: {events}')
            assert all(e.get('tool') == 'inventory_lookup' and
                       e.get('mcp_server') == 'retailiq' for e in starts + completions)
            assert not any(e.get('event') == 'tool.offline_lookup.completed' for e in events), (
                'Claimed an offline lookup when MCP actually executed')
            result = next(payload for kind, payload in frames if kind == 'result')
            assert result['records'] == rows
            trace = web.get(f"/api/sessions/{sid}/traces/{result['request_id']}")
            assert trace.status_code == 200
            saved = trace.json()['events']
            assert any(e['event'] == 'mcp.tool.completed' and e['mcp_server'] == 'retailiq'
                       for e in saved)
            assert all('answer' not in e and 'prompt' not in e for e in saved)

            print(json.dumps({
                "mode": "real_stdio_mcp", "status": "PASS",
                "inventory_rows": len(rows), "stock_units": sum(item["available"] for item in rows),
                "order_id": ORDER_ID, "order_lines": len(order_lines_expected),
                "api_sse_mcp_spans": len(starts) + len(completions),
                "trace_event_count": len(saved),
                "note": "Real local stdio MCP Inventory + Order, API SSE, saved trace; not cloud MCP or production data"
            }))


if __name__ == "__main__":
    main()
