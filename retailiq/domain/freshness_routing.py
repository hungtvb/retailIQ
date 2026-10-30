"""W2-01 freshness-aware routing: source choice and measured evidence are separate.

The router selects a source/tool but NEVER treats selection as execution or
a source's target SLA as an observed guarantee. A stale/unknown snapshot does
not silently satisfy a stricter caller request. No production/live assertion
can be inferred from a synthetic SQLite snapshot.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from retailiq.domain.semantic import FRESHNESS_TIERS

Metric = Literal["available_stock", "net_revenue", "top_sellers",
                 "product_knowledge", "order_state"]
Tier = Literal["live", "15_min", "hourly", "daily"]

_SOURCE = {
    "available_stock": {
        "source": "inventory", "tool_sql": "inventory",
        "tool_mcp": "inventory_lookup", "tier": "15_min",
    },
    "net_revenue": {
        "source": "completed_orders", "tool_sql": "revenue", "tier": "hourly",
    },
    "top_sellers": {
        "source": "completed_orders", "tool_sql": "top", "tier": "daily",
    },
    "product_knowledge": {
        "source": "product_documents", "tool_sql": "vector_search",
        "tier": "daily",
    },
    "order_state": {
        "source": "orders_mcp", "tool_sql": "order_lookup",
        "tier": "live",
    },
}
_RANK = {"live": 0, "15_min": 1, "hourly": 2, "daily": 3}


def _timestamp(raw: str) -> datetime:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Missing source update timestamp")
    try:
        stamp = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("Invalid source update timestamp") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("Source timestamp must include timezone")
    return stamp.astimezone(timezone.utc)


def route_freshness(
    metric: Metric, *,
    requested_tier: Tier | None = None,
    inventory_rows: list[dict] | None = None,
    observed_at: str | None = None,
    now: datetime | None = None,
    use_mcp: bool = False,
) -> dict:
    """Select authoritative source and evaluate only recorded update evidence.

    All-location stock requires every included location to be fresh. A live
    target has no tolerance for cached snapshots; it is unverified unless a
    future actual source-specific live evidence contract exists.
    """
    if metric not in _SOURCE:
        raise ValueError("Unsupported metric for freshness-aware routing")
    if requested_tier is not None and requested_tier not in FRESHNESS_TIERS:
        raise ValueError("Unsupported requested freshness tier")
    if not isinstance(use_mcp, bool):
        raise ValueError("use_mcp must be boolean")
    spec = _SOURCE[metric]
    baseline = spec["tier"]
    # Request may strengthen the default SLA, but cannot silently loosen it.
    applied = (requested_tier if requested_tier is not None
               and _RANK[requested_tier] < _RANK[baseline] else baseline)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("Reference time must include timezone")
    current = current.astimezone(timezone.utc)

    if metric != "available_stock" and inventory_rows is not None:
        raise ValueError("Inventory evidence provided for another metric")
    if metric == "available_stock" and observed_at is not None:
        raise ValueError("Inventory freshness must be derived from all location rows")
    if inventory_rows is not None and not isinstance(inventory_rows, list):
        raise ValueError("Inventory evidence must be a list")

    times = []
    if inventory_rows is not None:
        if not inventory_rows:
            times = []
        else:
            if any(not isinstance(r, dict) for r in inventory_rows):
                raise ValueError("Malformed inventory evidence")
            locations = [r.get("location_id") for r in inventory_rows]
            if any(not isinstance(x, str) or not x for x in locations) or len(locations) != len(set(locations)):
                raise ValueError("Malformed/duplicate inventory location")
            times = [_timestamp(r.get("updated_at")) for r in inventory_rows]
    elif observed_at is not None:
        times = [_timestamp(observed_at)]

    oldest = min(times) if times else None
    age = (current - oldest).total_seconds() if oldest else None
    if applied == "live":
        status = "UNVERIFIED"
        reason = "Live consistency cannot be established from snapshot timestamps"
    elif age is None:
        status = "UNVERIFIED"
        reason = "No trustworthy source-refresh timestamp is available"
    elif age < 0:
        status = "STALE"
        reason = "Source update timestamp is in the future"
    elif age <= FRESHNESS_TIERS[applied]["target_seconds"]:
        status = "PASS"
        reason = "Oldest included source timestamp meets the requested target"
    else:
        status = "STALE"
        reason = "At least one source update is older than the target"

    tool = (spec.get("tool_mcp") if metric == "available_stock" and use_mcp
            else spec["tool_sql"])
    # A route is a proposed read, not evidence that the tool was invoked.
    return {
        "metric": metric, "source": spec["source"],
        "selected_tool": tool, "selected_transport": (
            "mcp_stdio" if metric == "available_stock" and use_mcp
            else "mcp_stdio" if metric == "order_state" else
            "chroma" if metric == "product_knowledge" else "readonly_sqlite"
        ),
        "tool_execution": "not_executed_by_router",
        "baseline_tier": baseline, "requested_tier": requested_tier,
        "applied_tier": applied, "target_seconds": FRESHNESS_TIERS[applied]["target_seconds"],
        "observed_at": oldest.isoformat() if oldest else None,
        "age_seconds": round(age, 3) if age is not None else None,
        "checked_records": len(inventory_rows) if inventory_rows is not None else (
            1 if observed_at else 0),
        "status": status, "meets_target": status == "PASS",
        "reason": reason, "guaranteed": False,
    }
