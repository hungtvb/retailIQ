"""Read-only sales revenue query contract.

Represent filters before SQL execution. Unsupported combinations must clarify
instead of silently returning an unrelated store-wide aggregate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import re
from typing import Callable, Literal

from retailiq.domain.analytics import _ENGLISH_MONTHS, fold_text, requested_month

Scope = Literal["store", "product", "ranked_product", "clarify"]

# A location-shaped subject. Revenue cannot be filtered by location, so even a
# resolvable one must ask for clarification rather than answer the store total.
_LOCATION_SUBJECT_RE = re.compile(
    r'\b(?:tại|tai|at|in)\s+([^\s,?.!]+(?:\s+[^\s,?.!]+){0,2})'
)

# Channel and period words are not locations; "tại cửa hàng" or "at present"
# describe a sales channel or a reporting period, not a city.
_GENERIC_SUBJECT_WORDS = frozenset({
    'store', 'warehouse', 'shop', 'branch', 'outlet', 'online', 'hub', 'kenh',
    'kho', 'cua hang', 'cua hang vat ly', 'chi nhanh', 'physical',
})
_NON_LOCATION_HEADS = frozenset({
    'the', 'a', 'an', 'this', 'that', 'these', 'those', 'present', 'moment',
    'now', 'most', 'least', 'all', 'each', 'every', 'which', 'what', 'your',
    'our', 'my',
}) | frozenset(_ENGLISH_MONTHS) | frozenset({'month', 'months', 'quarter', 'year', 'years', 'q1', 'q2', 'q3', 'q4', 'online', 'channel', 'oct', 'sept'})

# An explicit SKU-shaped token that the catalog lookup could not resolve.
_SKU_TOKEN_RE = re.compile(r'\b[A-Z]{2,5}-\d{2,}\b')

# Product subject after a marker; the marker alone is not proof (the following
# phrase may be a month, channel or ranking rather than a product).
_PRODUCT_MARKER_RE = re.compile(
    r'(?:\bof\b|\bfor\b|doanh\s+thu\s+của|doanh\s+thu\s+cua'
    r'|của\s+sản\s+phẩm|cua\s+san\s+pham)'
    r'\s+([^\s,?.!]+(?:\s+[^\s,?.!]+){0,3})'
)
_NON_PRODUCT_HEADS = frozenset({
    'the', 'a', 'an', 'this', 'that', 'these', 'those', 'all', 'both', 'every',
    'most', 'least', 'month', 'months', 'thang', 'year', 'years', 'nam',
    'quarter', 'quy', 'q1', 'q2', 'q3', 'q4', 'last', 'previous', 'next',
    'online', 'store', 'kenh', 'channel', 'completed', 'top', 'sellers',
    'seller', 'best', 'us',
    # Generic Vietnamese store words are not a product subject.
    'cua', 'hang', 'kho', 'chung', 'toi', 'minh', 'cong', 'ty',
}) | frozenset(_ENGLISH_MONTHS)


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


def _names_known_location(text: str, known_locations) -> bool:
    """Case- and diacritic-insensitive match against the location vocabulary."""
    if known_locations is None:
        names = []
    elif callable(known_locations):
        names = known_locations()
    else:
        names = known_locations
    if not isinstance(names, (list, tuple)):
        return False
    folded = fold_text(text)
    compact = re.sub(r'\s+', '', folded)
    for raw in names:
        if not isinstance(raw, str) or not raw.strip():
            continue
        name = fold_text(raw).strip()
        if name in _GENERIC_SUBJECT_WORDS:
            continue  # "Store"/"Warehouse" are channel words, not cities.
        if name in folded or re.sub(r'\s+', '', name) in compact:
            return True
        head = name.split()[0]
        if len(head) >= 4 and head not in _GENERIC_SUBJECT_WORDS and head in compact:
            return True
    return False


def _names_location_subject(text: str, known_locations) -> bool:
    folded = fold_text(text)
    if _names_known_location(text, known_locations):
        return True
    for match in _LOCATION_SUBJECT_RE.finditer(folded):
        subject = match.group(1)
        head = subject.split()[0]
        if head in _NON_LOCATION_HEADS or re.fullmatch(r'20\d{2}(?:[-/]\d{1,2})?', head):
            continue
        if any(word in subject.split() for word in _GENERIC_SUBJECT_WORDS):
            continue
        return True
    return False


def _names_product_subject(question: str, text: str) -> bool:
    """True when the question names a product this resolver could not bind."""
    if _SKU_TOKEN_RE.search(question):
        return True
    for match in _PRODUCT_MARKER_RE.finditer(text):
        head = fold_text(match.group(1)).split()[0]
        if head not in _NON_PRODUCT_HEADS and not head.isdigit():
            return True
    return False


def build_revenue_plan(
    question: str,
    *,
    resolve_sku: Callable[[str], str | None],
    is_ranked: Callable[[str], bool],
    ranked_position: Callable[[str], int | None],
    known_locations: Callable[[], list[str]] | None = None,
) -> RevenuePlan:
    """Parse a bounded revenue query without LLM-generated SQL."""
    text = question.casefold()
    period = requested_month(question)
    if re.search(r"(?:thang|month)\s*(?:0|1[3-9]|[2-9]\d)\b", fold_text(question)):
        return RevenuePlan(period, "clarify", reason="Invalid calendar month")

    # A location filter cannot be inferred from the store/online channel.
    if _names_location_subject(question, known_locations):
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

    # A named but unresolved subject is not a store-wide question.
    if _names_product_subject(question, text):
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
