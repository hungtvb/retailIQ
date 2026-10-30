"""Read-only sales revenue query contract.

Represent filters before SQL execution. Unsupported combinations must clarify
instead of silently returning an unrelated store-wide aggregate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import re
from typing import Callable, Literal

from retailiq.domain.analytics import requested_month

Scope = Literal["store", "product", "ranked_product", "clarify"]


@dataclass(frozen=True)
class RevenuePlan:
    period: str
    scope: Scope
    sku: str | None = None
    rank: int | None = None
    channel: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict:
        return {"metric": "net_revenue_vnd", **asdict(self)}


def build_revenue_plan(
    question: str,
    *,
    resolve_sku: Callable[[str], str | None],
    is_ranked: Callable[[str], bool],
    ranked_position: Callable[[str], int | None],
) -> RevenuePlan:
    """Parse a bounded revenue query without LLM-generated SQL."""
    text = question.casefold()
    period = requested_month(question)
    if re.search(r"(?:tháng\s*|month\s*)(?:0|1[3-9]|[2-9]\d)\b", text):
        return RevenuePlan(period, "clarify", reason="Invalid calendar month")

    # A location such as Hanoi cannot be inferred from the store/online channel.
    if any(location in text for location in (
        "hà nội", "ha noi", "hanoi", "hồ chí minh", "ho chi minh",
        "saigon", "sài gòn", "hcmc"
    )):
        return RevenuePlan(period, "clarify", reason="Location-filtered revenue is not supported")

    online = bool(re.search(r"\b(?:online|ecommerce|e-commerce)\b", text))
    store_channel = any(label in text for label in (
        "kênh cửa hàng", "tại cửa hàng vật lý", "store channel", "in-store channel"
    ))
    if online and store_channel:
        return RevenuePlan(period, "clarify", reason="Choose one sales channel")
    channel = "online" if online else "store" if store_channel else None

    sku = resolve_sku(question)
    if is_ranked(question):
        rank = ranked_position(question)
        if sku:
            return RevenuePlan(period, "clarify", reason="Specify either SKU or ranking, not both")
        if rank is None or rank < 1 or rank > 5:
            return RevenuePlan(period, "clarify", reason="Specify one ranked product (rank 1–5)")
        return RevenuePlan(period, "ranked_product", rank=rank, channel=channel)
    if sku:
        return RevenuePlan(period, "product", sku=sku, channel=channel)

    product_reference = bool(re.search(
        r"(?:của\s+(?:sản phẩm|mặt hàng)|do\s+sản phẩm|"
        r"for\s+(?:the\s+)?product|product\s+(?:with\s+)?sku\b)", text
    ))
    if product_reference:
        return RevenuePlan(period, "clarify", reason="Identify the product by a known name or SKU")
    return RevenuePlan(period, "store", channel=channel)


def with_selected_sku(plan: RevenuePlan, sku: str) -> RevenuePlan:
    if plan.scope != "ranked_product" or not sku:
        raise ValueError("Only a ranked product can receive a selected SKU")
    return replace(plan, sku=sku)


def verify_revenue_evidence(plan: RevenuePlan, rows: list[dict]) -> None:
    """Verify response scope from execution evidence, not the LLM's wording."""
    if plan.scope == "clarify":
        if rows:
            raise ValueError("A clarification cannot include revenue records")
        return
    if not isinstance(rows, list):
        raise ValueError("Revenue evidence must be a list")
    if plan.scope in ("product", "ranked_product") and not plan.sku:
        if rows:
            raise ValueError("Unresolved product cannot have revenue evidence")
        return
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Malformed revenue record")
        if plan.scope in ("product", "ranked_product"):
            if row.get("sku") != plan.sku:
                raise ValueError("Revenue record is from a different SKU")
        elif "sku" in row:
            raise ValueError("Store revenue evidence unexpectedly includes a product scope")
        if plan.channel and row.get("channel") != plan.channel:
            raise ValueError("Revenue record has a different channel")
        amount = row.get("net_revenue_vnd")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise ValueError("Invalid revenue evidence amount")
