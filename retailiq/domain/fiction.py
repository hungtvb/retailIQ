"""Read-only analytics on the frozen Fiction Retail SQLite snapshot.

Business semantics are explicit. These functions do NOT promise live stock,
recognized revenue, return-adjusted net revenue, or real customer sentiment.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import re
import sqlite3
from typing import Iterator

PRODUCT_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
PERIOD = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")
CENTS = Decimal('0.01')


class FictionDataError(ValueError):
    """Invalid source data or invalid query scope; do not invent an answer."""


def _product_id(value: str) -> str:
    if not isinstance(value, str) or not PRODUCT_ID.fullmatch(value):
        raise ValueError('A valid Fiction product UUID is required')
    return value.lower()


def _bounds(period: str) -> tuple[str, str]:
    if not isinstance(period, str) or not PERIOD.fullmatch(period):
        raise ValueError('period must have YYYY-MM format')
    first = date.fromisoformat(period + '-01')
    end = date(first.year + 1, 1, 1) if first.month == 12 else date(first.year, first.month + 1, 1)
    return first.isoformat(), end.isoformat()


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    # Never create/modify the uploaded dataset. Explicitly prevent writes.
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        yield db
    finally:
        db.close()


def product(path: Path, product_id: str) -> dict | None:
    with connect(path) as db:
        row = db.execute('SELECT product_id, name, category, brand, price, weight_kg '
                         'FROM products WHERE product_id=?', (_product_id(product_id),)).fetchone()
        return dict(row) if row else None


def stock(path: Path, product_id: str) -> list[dict]:
    """Stock is an undated snapshot; last_restocked_date is not freshness."""
    with connect(path) as db:
        rows = db.execute("""
            SELECT i.product_id, i.warehouse_id, w.name AS warehouse,
                   i.quantity_on_hand, i.reserved_quantity, i.reorder_threshold,
                   i.last_restocked_date
            FROM inventory i JOIN warehouses w ON w.warehouse_id=i.warehouse_id
            WHERE i.product_id=? ORDER BY i.warehouse_id
        """, (_product_id(product_id),)).fetchall()
    output = []
    for row in rows:
        item = dict(row)
        a, r, threshold = item['quantity_on_hand'], item['reserved_quantity'], item['reorder_threshold']
        if any(type(x) is not int or x < 0 for x in (a, r, threshold)) or r > a:
            raise FictionDataError('Invalid inventory quantities')
        item['available'] = a - r
        item['below_reorder_threshold'] = item['available'] <= threshold
        item['freshness'] = 'UNVERIFIED_HISTORICAL_SNAPSHOT'
        output.append(item)
    return output


def top_sellers(path: Path, period: str, *, limit: int = 5) -> list[dict]:
    """Ranking on delivered-order units, not canceled or returned orders."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('limit must be an integer between 1 and 100')
    first, end = _bounds(period)
    with connect(path) as db:
        rows = db.execute("""
            SELECT p.product_id, p.name, p.category, SUM(oi.quantity) AS delivered_units
            FROM orders o JOIN order_items oi ON oi.order_id=o.order_id
            JOIN products p ON p.product_id=oi.product_id
            WHERE o.order_status='delivered' AND o.order_date>=? AND o.order_date<?
            GROUP BY p.product_id, p.name, p.category
            ORDER BY delivered_units DESC, p.product_id ASC LIMIT ?
        """, (first, end, limit)).fetchall()
    return [dict(r) for r in rows]


def delivered_merchandise_value(path: Path, period: str, *, product_id: str | None = None) -> dict:
    """USD line value of delivered orders, before returns/tax/shipping; NOT net revenue."""
    first, end = _bounds(period)
    product_key = _product_id(product_id) if product_id is not None else None
    with connect(path) as db:
        rows = db.execute("""
            SELECT oi.quantity, oi.unit_price, oi.discount_pct
            FROM orders o JOIN order_items oi ON oi.order_id=o.order_id
            WHERE o.order_status='delivered' AND o.order_date>=? AND o.order_date<?
              AND (? IS NULL OR oi.product_id=?)
        """, (first, end, product_key, product_key))
        total = Decimal('0')
        lines = 0
        units = 0
        for row in rows:
            q, price, discount = row
            if (type(q) is not int or q <= 0 or price is None or discount is None):
                raise FictionDataError('Invalid delivered order line')
            try:
                price_d, discount_d = Decimal(str(price)), Decimal(str(discount))
            except Exception as exc:
                raise FictionDataError('Invalid price or discount') from exc
            if not price_d.is_finite() or not discount_d.is_finite() or price_d < 0 or not 0 <= discount_d <= 100:
                raise FictionDataError('Out-of-range price/discount')
            total += Decimal(q) * price_d * (Decimal(100) - discount_d) / Decimal(100)
            lines += 1
            units += q
    return {'period': period, 'product_id': product_key, 'currency': 'USD',
            'metric': 'delivered_merchandise_value_before_returns',
            'amount_usd': str(total.quantize(CENTS, rounding=ROUND_HALF_UP)),
            'order_lines': lines, 'units': units}


def return_reasons(path: Path, period: str, *, product_id: str | None = None) -> list[dict]:
    """Count recorded return events by return_date (not customer opinion)."""
    first, end = _bounds(period)
    product_key = _product_id(product_id) if product_id is not None else None
    with connect(path) as db:
        rows = db.execute("""
            SELECT return_reason_code AS reason_code, COUNT(*) AS return_events
            FROM returns WHERE return_date>=? AND return_date<?
              AND (? IS NULL OR product_id=?)
            GROUP BY return_reason_code ORDER BY return_events DESC, reason_code
        """, (first, end, product_key, product_key)).fetchall()
    return [dict(r) for r in rows]
