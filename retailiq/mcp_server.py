"""Read-only Fiction Retail Inventory/Order MCP tools over local stdio.

The server verifies the pinned Fiction SQLite release; it never falls back to
the legacy retail fixture or treats undated stock as live/current inventory.
Do not expose this unauthenticated process to an untrusted network.
"""
from functools import lru_cache
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from retailiq.domain.fiction import FictionStore

ROOT = Path(__file__).resolve().parents[1]
mcp = FastMCP("RetailIQ Fiction Read-only Tools")


@lru_cache(maxsize=1)
def _store(db: str, manifest: str) -> FictionStore:
    """Verify release once per immutable process-local snapshot."""
    return FictionStore.open(db, manifest)


def _fiction() -> FictionStore:
    db = os.getenv("RETAILIQ_FICTION_DB") or str(ROOT / "data/fiction/fiction_retail.sqlite")
    manifest = os.getenv("RETAILIQ_FICTION_MANIFEST") or str(ROOT / "data/fiction/manifest.json")
    return _store(str(Path(db).resolve()), str(Path(manifest).resolve()))


@mcp.tool()
def inventory_lookup(product: str, warehouse_id: str | None = None) -> dict:
    """Read recorded, UNDATED base stock for one Fiction UUID or FR-SKU.

    Not historical-as-of or live inventory. Missing observations never mean 0.
    """
    return _fiction().inventory(product, warehouse_id)


@mcp.tool()
def order_lookup(order_id: str) -> dict:
    """Read a validated Fiction order, lines and shipments without customer PII.

    The release's shipment/order state is not state at a backorder case cutoff.
    """
    return _fiction().order(order_id)


@mcp.resource("retailiq://semantics")
def semantic_definitions() -> str:
    """Minimal source semantics; not the legacy analytics metric contract."""
    return ("Fiction unified v1 local read-only snapshot. Inventory is UNDATED, "
            "not live or case-cutoff stock. Order/shipment state is release-recorded; "
            "case evidence and policies have separate historical time scopes.")


if __name__ == "__main__":
    mcp.run(transport="stdio")
