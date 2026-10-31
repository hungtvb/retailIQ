"""Reviewed read-only business queries and strict retail data invariants.

All monetary amounts are integer VND. Sales report scope is completed orders
in the demo's configured calendar month; returns are NOT represented in the
Week 1 data model. Inventory snapshots are validated, not freshness-filtered.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import os
import re

from retailiq.infrastructure.sqlite import query


class DomainDataError(ValueError):
    """Source data violates a business invariant; do not retry as transient IO."""


_SKU = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,63}$")


def month() -> str:
    """Configured date is deliberate and reproducible for the synthetic demo."""
    return date.fromisoformat(os.getenv('RETAILIQ_AS_OF', '2026-10-28')).strftime('%Y-%m')


def requested_month(question: str) -> str:
    """Resolve an explicit sales month against the demo reference year."""
    reference = date.fromisoformat(os.getenv('RETAILIQ_AS_OF', '2026-10-28'))
    text = question.casefold()
    if 'tháng trước' in text or 'last month' in text:
        previous = reference.replace(day=1) - timedelta(days=1)
        return previous.strftime('%Y-%m')
    english_months = ('january', 'february', 'march', 'april', 'may', 'june',
                      'july', 'august', 'september', 'october', 'november', 'december')
    english = re.search(
        r'\b(' + '|'.join(english_months) + r')\s*(20\d{2})?\b', text
    )
    if english:
        return f'{int(english.group(2) or reference.year):04d}-{english_months.index(english.group(1)) + 1:02d}'
    match = re.search(r'tháng\s+(1[0-2]|0?[1-9])(?:\s*(?:năm|/|-)\s*(20\d{2}))?', text)
    if not match:
        match = re.search(r'\b(20\d{2})[-/](1[0-2]|0?[1-9])\b', text)
        if match:
            return f'{int(match.group(1)):04d}-{int(match.group(2)):02d}'
        return reference.strftime('%Y-%m')
    return f'{int(match.group(2) or reference.year):04d}-{int(match.group(1)):02d}'


def _month_bounds(period: str | None = None) -> tuple[str, str]:
    start = date.fromisoformat((period or month()) + '-01')
    end = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
    return start.isoformat(), end.isoformat()


def products() -> list[dict]:
    return query('SELECT * FROM products ORDER BY sku')


def newest_products(limit: int = 5) -> list[dict]:
    """Newest entries in the synthetic catalog, not market release dates."""
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10:
        raise ValueError('Invalid newest-products limit')
    return query('''SELECT sku, name, category, price_vnd, catalog_added_at
                    FROM products ORDER BY catalog_added_at DESC, sku DESC LIMIT ?''', (limit,))


def catalog_product(sku: str) -> dict | None:
    rows = query('''SELECT sku, name, category, price_vnd, catalog_added_at
                    FROM products WHERE sku = ? LIMIT 1''', (_sku(sku),))
    if not rows:
        return None
    item = rows[0]
    # Never offer a manager an actionable-looking proposal from corrupt
    # catalog values. Zero may legitimately represent a free item; negative,
    # null and non-integer prices are invalid input evidence.
    _nonnegative_int(item.get('price_vnd'), field='catalog price_vnd')
    if not isinstance(item.get('name'), str) or not item['name'].strip():
        raise DomainDataError('Catalog product name is missing')
    return item


def _nonnegative_int(value, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DomainDataError(f'Invalid non-negative integer in {field}')
    return value


def _sku(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('SKU must be a string')
    normalized = value.strip().upper()
    if not _SKU.fullmatch(normalized):
        raise ValueError('SKU format is invalid')
    return normalized


def _validate_inventory(rows: list[dict], sku: str) -> list[dict]:
    locations: set[str] = set()
    for row in rows:
        if row.get('sku') != sku:
            raise DomainDataError('Inventory SKU does not match the request')
        location = row.get('location_id')
        if not isinstance(location, str) or not location or location in locations:
            raise DomainDataError('Missing or duplicate inventory location')
        locations.add(location)
        on_hand = _nonnegative_int(row.get('on_hand'), field='on_hand')
        reserved = _nonnegative_int(row.get('reserved'), field='reserved')
        available = _nonnegative_int(row.get('available'), field='available')
        if reserved > on_hand or available != on_hand - reserved:
            raise DomainDataError('Inventory availability is inconsistent')
        if not isinstance(row.get('name'), str) or not row['name'].strip():
            raise DomainDataError('Inventory product name is missing')
        if not isinstance(row.get('location'), str) or not row['location'].strip():
            raise DomainDataError('Inventory location name is missing')
        try:
            updated = datetime.fromisoformat(row['updated_at'])
        except (TypeError, ValueError, KeyError) as exc:
            raise DomainDataError('Inventory update timestamp is invalid') from exc
        if updated.tzinfo is None:
            raise DomainDataError('Inventory update timestamp lacks timezone')
    return rows


def inventory(sku: str) -> list[dict]:
    normalized = _sku(sku)
    rows = query('''
        SELECT p.sku, p.name, l.id AS location_id, l.name AS location,
               l.channel, i.on_hand, i.reserved,
               (i.on_hand - i.reserved) AS available, i.updated_at
        FROM inventory AS i
        JOIN products AS p ON p.sku = i.sku
        LEFT JOIN locations AS l ON l.id = i.location_id
        WHERE p.sku = ?
        ORDER BY l.id
    ''', (normalized,))
    # No stock rows is a valid empty result; never invent stock or index rows[0].
    return _validate_inventory(rows, normalized)


def _ensure_sales_lines_valid(start: str, end: str) -> None:
    """Fail on malformed completed-order lines instead of silently summing them."""
    invalid = query('''
        SELECT li.id FROM order_lines AS li JOIN orders AS o ON o.id=li.order_id
        LEFT JOIN products AS p ON p.sku=li.sku
        WHERE o.status='completed' AND o.ordered_at>=? AND o.ordered_at<?
          AND (p.sku IS NULL OR li.quantity IS NULL OR typeof(li.quantity)!='integer'
               OR li.quantity<=0 OR li.unit_price_vnd IS NULL
               OR typeof(li.unit_price_vnd)!='integer' OR li.unit_price_vnd<0
               OR li.discount_vnd IS NULL OR typeof(li.discount_vnd)!='integer'
               OR li.discount_vnd<0
               OR li.discount_vnd>li.quantity*li.unit_price_vnd)
        LIMIT 1
    ''', (start, end))
    if invalid:
        raise DomainDataError('Invalid completed-order line in sales period')


def revenue(period: str | None = None) -> list[dict]:
    start, end = _month_bounds(period)
    _ensure_sales_lines_valid(start, end)
    rows = query('''
        SELECT o.channel, COUNT(DISTINCT o.id) AS orders,
               SUM(li.quantity*li.unit_price_vnd-li.discount_vnd) AS net_revenue_vnd
        FROM orders AS o JOIN order_lines AS li ON li.order_id=o.id
        WHERE o.status='completed' AND o.ordered_at>=? AND o.ordered_at<?
        GROUP BY o.channel ORDER BY o.channel
    ''', (start, end))
    for row in rows:
        if not isinstance(row.get('channel'), str) or not row['channel'].strip():
            raise DomainDataError('Sales channel is missing')
        _nonnegative_int(row.get('orders'), field='orders')
        _nonnegative_int(row.get('net_revenue_vnd'), field='net_revenue_vnd')
    return rows



def revenue_for_sku(sku: str, period: str | None = None) -> list[dict]:
    """Revenue for exactly one verified SKU in a reporting month.

    Product selection/ranking is done separately by top(period), always using
    the same period. Never substitute store-wide revenue for a ranked SKU.
    """
    normalized = _sku(sku)
    start, end = _month_bounds(period)
    _ensure_sales_lines_valid(start, end)
    rows = query("""
        SELECT p.sku, p.name, o.channel, COUNT(DISTINCT o.id) AS orders,
               SUM(li.quantity) AS units_sold,
               SUM(li.quantity * li.unit_price_vnd - li.discount_vnd) AS net_revenue_vnd
        FROM orders AS o
        JOIN order_lines AS li ON li.order_id = o.id
        JOIN products AS p ON p.sku = li.sku
        WHERE o.status = 'completed'
          AND o.ordered_at >= ? AND o.ordered_at < ?
          AND li.sku = ?
        GROUP BY p.sku, p.name, o.channel
        ORDER BY o.channel
    """, (start, end, normalized))
    for row in rows:
        if row.get('sku') != normalized:
            raise DomainDataError('Revenue evidence SKU mismatch')
        if not isinstance(row.get('name'), str) or not row['name'].strip():
            raise DomainDataError('Revenue product name is missing')
        if not isinstance(row.get('channel'), str) or not row['channel'].strip():
            raise DomainDataError('Sales channel is missing')
        _nonnegative_int(row.get('orders'), field='orders')
        _nonnegative_int(row.get('units_sold'), field='units_sold')
        _nonnegative_int(row.get('net_revenue_vnd'), field='net_revenue_vnd')
    return rows


def top(period: str | None = None) -> list[dict]:
    start, end = _month_bounds(period)
    _ensure_sales_lines_valid(start, end)
    rows = query('''
        SELECT p.sku, p.name, SUM(li.quantity) AS units_sold
        FROM orders AS o JOIN order_lines AS li ON li.order_id=o.id
        JOIN products AS p ON p.sku=li.sku
        WHERE o.status='completed' AND o.ordered_at>=? AND o.ordered_at<?
        GROUP BY p.sku,p.name ORDER BY units_sold DESC,p.sku LIMIT 5
    ''', (start, end))
    seen = set()
    for row in rows:
        sku = row.get('sku')
        if not isinstance(sku, str) or not _SKU.fullmatch(sku) or sku in seen:
            raise DomainDataError('Invalid or duplicate top-selling SKU')
        seen.add(sku)
        if not isinstance(row.get('name'), str) or not row['name'].strip():
            raise DomainDataError('Top-selling product name is missing')
        _nonnegative_int(row.get('units_sold'), field='units_sold')
    return rows


def price_extreme(*, highest: bool, category: str | None = None) -> list[dict]:
    """Rank synthetic list prices with reviewed SQL; only allow known category."""
    if category is not None and category not in {"Accessory", "Laptop", "Phone", "Audio",
                                                  "Peripheral", "Display", "Tablet"}:
        raise ValueError("Unsupported catalog category")
    direction = "DESC" if highest else "ASC"  # fixed SQL token, never user SQL
    if category is None:
        return query("SELECT sku,name,category,price_vnd FROM products "
                     f"ORDER BY price_vnd {direction},sku LIMIT 1")
    return query("SELECT sku,name,category,price_vnd FROM products WHERE category=? "
                 f"ORDER BY price_vnd {direction},sku LIMIT 1", (category,))
