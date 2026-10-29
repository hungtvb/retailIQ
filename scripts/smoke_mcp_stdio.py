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


def as_object(value):
    if hasattr(value, "artifact") and value.artifact:
        value = value.artifact
    if hasattr(value, "content") and not isinstance(value, (str, dict, list)):
        value = value.content
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    if isinstance(value, list):
        texts = [
            item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
            for item in value
        ]
        if len(texts) == 1 and isinstance(texts[0], str):
            return as_object(texts[0])
    raise ValueError(f"Unrecognized MCP tool result type: {type(value).__name__}")


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
    return as_object(await order_tool.ainvoke({"order_id": ORDER_ID}))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="retailiq-mcp-") as root:
        db = Path(root)/"retail.sqlite3"
        seed(db, write_support_files=False, reference_date=date(2026, 10, 28))
        with patch.dict(os.environ, {
            "RETAILIQ_DATA_DB": str(db),
            "RETAILIQ_AS_OF": "2026-10-28"
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
            print(json.dumps({
                "mode": "real_stdio_mcp", "status": "PASS",
                "inventory_rows": len(rows), "stock_units": sum(item["available"] for item in rows),
                "order_id": ORDER_ID, "order_lines": len(order_lines_expected),
                "note": "Real local stdio MCP Inventory + Order, not cloud MCP or production data"
            }))


if __name__ == "__main__":
    main()
