"""Bounded LangChain-to-Fiction MCP stdio adapter; no SQL or business decisions."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
import sys
from uuid import UUID
from hashlib import sha256

from retailiq.observability import observed

ROOT = Path(__file__).resolve().parents[1]
FR_SKU = re.compile(r"^FR-[0-9A-F]{16}$")
TIMEOUT_SECONDS = 45


def decode_tool_result(value) -> dict:
    """Reject MCP errors and ambiguous wrappers before trusting structured content."""
    if getattr(value, "status", None) == "error":
        raise ValueError("MCP tool returned execution error")
    if hasattr(value, "structured_content"):
        structured = getattr(value, "structured_content")
        if structured is not None:
            return decode_tool_result(structured)
    if hasattr(value, "artifact") and getattr(value, "artifact") is not None:
        artifact = value.artifact
        try:
            return decode_tool_result(artifact)
        except ValueError:
            # Old adapters can attach metadata-only artifacts; inspect content.
            pass
    if isinstance(value, dict):
        if value.get("isError") or value.get("is_error") or value.get("status") == "error":
            raise ValueError("MCP tool returned execution error")
        if all(k in value for k in ("data", "source", "scope", "record_refs", "limitations")):
            return value
        if "records" in value or "order" in value:
            return value  # Legacy decoder compatibility; NOT a valid Fiction envelope.
        for key in ("structuredContent", "structured_content", "content", "result", "data"):
            if key in value:
                return decode_tool_result(value[key])
        raise ValueError("MCP result has no recognized structured payload")
    if isinstance(value, str):
        try:
            return decode_tool_result(json.loads(value))
        except (ValueError, TypeError) as exc:
            raise ValueError("MCP text is not a valid structured result") from exc
    if isinstance(value, (list, tuple)):
        if len(value) != 1:
            raise ValueError("MCP returned ambiguous content blocks")
        item = value[0]
        if isinstance(item, dict) and item.get("type") == "text":
            return decode_tool_result(item.get("text"))
        return decode_tool_result(getattr(item, "text", item))
    if hasattr(value, "content"):
        return decode_tool_result(value.content)
    raise ValueError("Unsupported MCP result shape")


def _uuid(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid Fiction UUID")
    try:
        val = str(UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("Invalid Fiction UUID") from exc
    if val != value or len(value) != 36:
        raise ValueError("Fiction ID must be canonical")
    return val


def _source_expected() -> str:
    file = Path(os.getenv("RETAILIQ_FICTION_MANIFEST") or
                ROOT / "data/fiction/manifest.json").resolve()
    expected = json.loads(file.read_text(encoding="utf-8"))
    if expected.get("pack_version") != "fiction-retail-unified-v1.0.0":
        raise ValueError("Unexpected Fiction source release")
    checksum = expected.get("runtime_sha256")
    if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ValueError("Invalid Fiction source checksum")
    return checksum


def _verify_envelope(result: dict, expected_sha: str, tool: str, arguments: dict) -> dict:
    if not isinstance(result, dict) or set(result) - {
        "data", "source", "scope", "record_refs", "temporal", "limitations", "aggregate_evidence"
    }:
        raise ValueError("Unexpected Fiction MCP envelope")
    source, scope = result.get("source"), result.get("scope")
    refs, limits = result.get("record_refs"), result.get("limitations")
    if (not isinstance(source, dict) or source.get("id") != "fiction-retail/sqlite" or
            source.get("version") != "fiction-retail-unified-v1.0.0" or
            source.get("sha256") != expected_sha or not isinstance(scope, dict) or
            not isinstance(refs, list) or len(refs) > 100 or
            not isinstance(limits, list) or not all(isinstance(x, str) for x in limits)):
        raise ValueError("Fiction MCP source or evidence invalid")
    if not isinstance(result.get("temporal"), dict):
        raise ValueError("Fiction MCP temporal metadata missing")
    if tool == "inventory_lookup":
        product = arguments["product"]
        if scope.get("requested_product") != product:
            raise ValueError("Inventory MCP changed product scope")
        wid = arguments.get("warehouse_id")
        if scope.get("warehouse_id") != wid:
            raise ValueError("Inventory MCP changed warehouse scope")
        pid = scope.get("product_id")
        if pid is not None:
            _uuid(pid)
            if FR_SKU.fullmatch(product):
                if "FR-" + sha256(pid.encode()).hexdigest()[:16].upper() != product:
                    raise ValueError("Inventory MCP SKU-product mismatch")
            elif pid != product:
                raise ValueError("Inventory MCP product ID mismatch")
        rows = result.get("data")
        if not isinstance(rows, list) or len(rows) > 100:
            raise ValueError("Inventory MCP records malformed")
        if pid is None and "PRODUCT_NOT_FOUND" not in limits:
            raise ValueError("Inventory MCP missing product status")
        expected_refs = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {
                "inventory_id", "product_id", "warehouse_id", "quantity_on_hand",
                "reserved_quantity", "last_restocked_date", "available_snapshot"
            }:
                raise ValueError("Inventory MCP row schema mismatch")
            iid, rpid, rwid = _uuid(row["inventory_id"]), _uuid(row["product_id"]), _uuid(row["warehouse_id"])
            if rpid != pid or (wid is not None and rwid != wid):
                raise ValueError("Inventory MCP row changed scope")
            on, reserved, available = row["quantity_on_hand"], row["reserved_quantity"], row["available_snapshot"]
            if any(type(n) is not int for n in (on, reserved, available)) or not 0 <= reserved <= on or available != on - reserved:
                raise ValueError("Inventory MCP arithmetic mismatch")
            expected_refs.append("inventory/" + iid)
        if refs != expected_refs:
            raise ValueError("Inventory MCP source references mismatch")
        known_missing = ("PRODUCT_NOT_FOUND" in limits or "WAREHOUSE_NOT_FOUND" in limits)
        if not known_missing and not any(x.startswith("UNDATED_INVENTORY") for x in limits):
            raise ValueError("Inventory MCP lacks undated warning")
        if known_missing and (rows or refs):
            raise ValueError("Inventory MCP claims absence with records")
        if not rows and pid and not any(x.startswith("NO_INVENTORY_RECORDS") or x == "WAREHOUSE_NOT_FOUND" for x in limits):
            raise ValueError("Inventory MCP missing evidence status")
    elif tool == "order_lookup":
        oid = arguments["order_id"]
        if scope.get("order_id") != oid:
            raise ValueError("Order MCP changed order scope")
        data = result.get("data")
        if data is None:
            if refs or "ORDER_NOT_FOUND" not in limits:
                raise ValueError("Order MCP missing order status")
        elif not isinstance(data, dict) or set(data) != {"order", "lines", "shipments"}:
            raise ValueError("Order MCP malformed order data")
        else:
            order = data["order"]
            lines, shipments = data["lines"], data["shipments"]
            if (not isinstance(order, dict) or order.get("order_id") != oid or
                    not isinstance(lines, list) or not isinstance(shipments, list) or
                    len(lines) > 100 or len(shipments) > 100):
                raise ValueError("Order MCP invalid identity/size")
            if any(k in order for k in ("customer_id", "name", "email", "address", "payment_method")):
                raise ValueError("Order MCP leaked customer data")
            expected_refs = ["orders/" + oid]
            for line in lines:
                if not isinstance(line, dict) or set(line) != {
                    "order_item_id", "product_id", "quantity", "unit_price", "discount_pct"
                }:
                    raise ValueError("Order MCP line schema mismatch")
                _uuid(line["product_id"])
                if type(line["quantity"]) is not int or line["quantity"] <= 0:
                    raise ValueError("Order MCP invalid line quantity")
                if type(line["discount_pct"]) is not int or not 0 <= line["discount_pct"] <= 100:
                    raise ValueError("Order MCP invalid discount")
                expected_refs.append("order_items/" + _uuid(line["order_item_id"]))
            for shipment in shipments:
                if not isinstance(shipment, dict) or set(shipment) != {
                    "shipment_id", "warehouse_id", "shipped_date", "delivered_date", "shipment_state"
                }:
                    raise ValueError("Order MCP shipment schema mismatch")
                _uuid(shipment["warehouse_id"])
                expected_refs.append("shipments/" + _uuid(shipment["shipment_id"]))
            if refs != expected_refs:
                raise ValueError("Order MCP source refs mismatch")
    else:
        raise ValueError("Unknown MCP tool")
    return result


async def _call(tool_name: str, args: dict) -> dict:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient({
        "retailiq": {"command": sys.executable,
                     "args": ["-m", "retailiq.mcp_server"],
                     "transport": "stdio"}
    }, handle_tool_errors=False)
    expected_sha = _source_expected()
    tools = await client.get_tools()
    tool = next((x for x in tools if x.name == tool_name), None)
    if tool is None or sum(x.name == tool_name for x in tools) != 1:
        raise RuntimeError("Required Fiction MCP tool not discovered")
    with observed("mcp.tool", agent="backorder_agent" if tool_name == "order_lookup" else "inventory_agent",
                  tool=tool_name, mcp_server="retailiq", execution_mode="full"):
        raw = await tool.ainvoke(args)
        if getattr(raw, "status", None) == "error":
            raise ValueError("MCP tool execution failed")
        return _verify_envelope(decode_tool_result(raw), expected_sha, tool_name, args)


def _bounded_call(tool_name: str, args: dict) -> dict:
    async def run():
        return await asyncio.wait_for(_call(tool_name, args), timeout=TIMEOUT_SECONDS)
    return asyncio.run(run())


def read_fiction_inventory(product: str, warehouse_id: str | None = None) -> dict:
    if not isinstance(product, str) or not (FR_SKU.fullmatch(product) or _canonical_uuid(product)):
        raise ValueError("Expected one Fiction UUID or FR-SKU")
    if warehouse_id is not None:
        _uuid(warehouse_id)
    return _bounded_call("inventory_lookup", {"product": product, "warehouse_id": warehouse_id})


def _canonical_uuid(value: str) -> bool:
    try:
        _uuid(value)
        return True
    except ValueError:
        return False


def read_fiction_order(order_id: str) -> dict:
    _uuid(order_id)
    return _bounded_call("order_lookup", {"order_id": order_id})


def read_inventory(sku: str) -> list[dict]:
    """Compatibility caller must not route legacy stock through Fiction MCP."""
    raise ValueError("Legacy EL-SKU MCP lookup unavailable; Fiction MCP requires full-mode FR-SKU")
