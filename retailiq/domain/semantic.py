"""Canonical read-only KPI semantics and source freshness expectations.

An SLA target is not a guarantee: actual evidence must carry timestamps.
"""
from __future__ import annotations

METRICS = {
    "available_stock": {
        "source": "inventory",
        "definition": "SUM(on_hand - reserved) by SKU and permitted location",
        "unit": "units",
        "source_of_truth": "SQLite inventory snapshot",
    },
    "net_revenue": {
        "source": "orders",
        "definition": "SUM(quantity * unit_price_vnd - discount_vnd) on completed order lines before returns",
        "unit": "VND",
        "source_of_truth": "SQLite completed orders and order_lines",
    },
    "top_sellers": {
        "source": "orders",
        "definition": "Rank product SKUs by quantity sold in completed orders for the selected calendar month",
        "unit": "units",
        "source_of_truth": "SQLite completed orders and order_lines",
    },
}
FRESHNESS_TIERS = {
    "live": {"target_seconds": 0, "purpose": "live order state", "guaranteed": False},
    "15_min": {"target_seconds": 900, "purpose": "inventory snapshot", "guaranteed": False},
    "hourly": {"target_seconds": 3600, "purpose": "sales revenue KPI", "guaranteed": False},
    "daily": {"target_seconds": 86400, "purpose": "top-seller reporting and product knowledge", "guaranteed": False},
}


def semantic_summary() -> str:
    return "; ".join(key + ": " + value["definition"]
                     for key, value in METRICS.items())


def contracts() -> dict:
    return {"metrics": METRICS, "freshness_tiers": FRESHNESS_TIERS,
            "notice": "Targets only. No source meets a freshness SLA without an observed timestamp."}
