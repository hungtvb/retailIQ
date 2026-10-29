"""Optional real stdio MCP Inventory + Order tools (read-only synthetic SQLite).

Install requirements-mcp.txt then run: python -m retailiq.mcp_server
Never expose this unauthenticated demo service to an untrusted network.
"""
import re
from mcp.server.fastmcp import FastMCP

from retailiq.domain.analytics import inventory, month
from retailiq.infrastructure.sqlite import query

mcp = FastMCP("RetailIQ Synthetic Retail Tools")


@mcp.tool()
def inventory_lookup(sku: str) -> dict:
    """Read available stock for a known product SKU across synthetic locations."""
    rows = inventory(sku)
    return {"sku": sku, "records": rows,
            "available": sum(row["available"] for row in rows),
            "source": "local_readonly_sqlite", "freshness": "snapshot_timestamp_only"}


@mcp.tool()
def order_lookup(order_id: str) -> dict:
    """Read a synthetic order and its lines; never update order status."""
    if not re.fullmatch(r"ORD-[0-9]{4}", order_id):
        raise ValueError("Invalid demo order ID")
    orders = query("""SELECT id,ordered_at,channel,status FROM orders
                      WHERE id=? LIMIT 1""", (order_id,))
    lines = query("""SELECT sku,quantity,unit_price_vnd,discount_vnd
                     FROM order_lines WHERE order_id=? ORDER BY id""", (order_id,))
    return {"order": orders[0] if orders else None, "lines": lines if orders else [],
            "source": "local_readonly_sqlite"}


@mcp.resource("retailiq://semantics")
def semantic_definitions() -> str:
    """Definitions shared with the local retail analytics query layer."""
    return ("available=on_hand-reserved; net_revenue=sum(quantity*unit_price-discount) "
            "for completed orders; top_sellers=completed order quantity in " + month() +
            "; inventory freshness is reported from snapshot timestamps")


if __name__ == "__main__":
    mcp.run(transport="stdio")
