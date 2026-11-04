"""Conservative Fiction Retail request parsing; no business-source or model authority.

This module contains only bounded scope interpretation and canonical input
validation. Keeping the exceptions here preserves their identity for the
existing HTTP 422 and graph compatibility imports.
"""
from __future__ import annotations

import re


_CASE_ID = re.compile(
    r"(?<![A-Za-z0-9])CASE-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}(?![A-Za-z0-9])",
    re.IGNORECASE,
)


class InvalidCaseId(ValueError):
    """Invalid/ambiguous UC-01 input, not a provider or data-source failure."""


class InvalidFictionScope(InvalidCaseId):
    """Invalid or unsupported Fiction inventory query constraint (HTTP 422)."""




class UnresolvedCaseReference(InvalidCaseId):
    """Case/warehouse reference requires clarification or current-source review."""


def _uc01_followup_kind(question: str) -> str | None:
    """Small conservative UC-01 anaphora grammar, never a policy/entity oracle."""
    q = ' '.join(question.casefold().split())
    if len(q) > 160:
        return None
    # A numbered warehouse has no authority unless its displayed order was
    # committed; no such ordering is persisted in this first T03 slice.
    if re.search(r'kho\s+(?:thứ\s*(?:hai|2)|số\s*2)|(?:second|2nd)\s+warehouse', q):
        return 'ambiguous_warehouse'
    if 'case-' in q:
        return None  # Explicit CASE-ID uses the original reviewed T02 route.
    if any(term in q for term in ('refund', 'return', 'hoàn tiền', 'đổi trả',
                                  'bảo hành', 'pricing', 'chính sách giá')):
        return None  # A topic switch must not inherit a previous case.
    if (('đơn hàng này' in q or 'đơn này' in q or 'this order' in q) and
            any(x in q for x in ('trạng thái', 'shipment status', 'delivery status', 'giao chưa')) and
            any(x in q for x in ('cutoff', 'lúc đó', 'tại thời điểm', 'khi đó'))):
        return 'order_status_at_cutoff'
    if (('đơn hàng này' in q or 'đơn này' in q or 'this order' in q) and
            any(token in q for token in ('gồm', 'sản phẩm', 'chi tiết', 'items', 'lines', 'details', 'contain'))):
        return 'order_details'
    if (('chính sách' in q and any(x in q for x in ('áp dụng', 'nào', 'đó')))
            or ('policy' in q and any(x in q for x in ('appl', 'which', 'warehouse', 'transfer')))):
        return 'policy'
    if any(x in q for x in ('kho khác', 'còn kho', 'kho nào khác',
                           'other warehouse', 'another warehouse',
                           'alternative warehouse', 'other warehouses')):
        return 'alternatives'
    return None


def _case_id_for_uc01(question: str) -> str:
    matches = _CASE_ID.findall(question)
    if len(matches) != 1 or question.casefold().count("case-") != 1:
        raise InvalidCaseId("UC-01 requires exactly one explicit canonical CASE-ID")
    return "CASE-" + matches[0][5:].lower()


_FR_SKU_MATCH = re.compile(r"(?<![A-Za-z0-9-])FR-[0-9A-F]{16}(?![A-Za-z0-9-])")
_UUID_IN_QUESTION = re.compile(
    r"(?<![A-Za-z0-9])(?:[0-9a-f]{8}-)(?:[0-9a-f]{4}-){3}[0-9a-f]{12}(?![A-Za-z0-9])",
    re.I,
)
_WAREHOUSE_ID_IN_QUESTION = re.compile(
    r"(?<!\w)(?:warehouse|kho)(?:\s+id)?\s*[:=#]?\s*"
    r"([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})(?![A-Za-z0-9])",
    re.I,
)
_STOCK_DATE = re.compile(
    r"(?<!\w)(?:20\d{2}(?:[-/]\d{1,2}(?:[-/]\d{1,2})?)?"
    r"|\d{1,2}[-/]\d{1,2}(?:[-/]\d{2,4})?|\d{1,2}/20\d{2})(?!\w)"
)
_STOCK_VI_TIME_WORDS = (
    'hiện tại', 'hiện nay', 'hiện giờ', 'ngay lúc này', 'bây giờ',
    'hôm nay', 'hôm qua', 'hôm kia', 'hôm trước', 'ngày', 'tháng',
    'năm', 'tuần', 'quý', 'tính đến', 'tại thời điểm',
    'vào lúc', 'cuối kỳ', 'đầu kỳ',
)
_STOCK_EN_TIME = re.compile(
    r'\b(?:today|yesterday|tomorrow|now|currently|current|'
    r'right now|at the moment|as of|as at|this (?:week|month|year|quarter)|'
    r'last (?:week|month|year|quarter)|next (?:week|month|year)|'
    r'since|before|after|historical|historic|realtime|real-time|'
    r'real time|live|latest)\b'
)
_STOCK_CALENDAR = re.compile(
    r'\b(?:january|february|march|april|may|june|july|august|'
    r'september|october|november|december)\b'
)


def _fiction_inventory_request(question: str) -> tuple[str, str | None] | None:
    """Only an unambiguous, undated single-SKU inventory request can use MCP.

    No LLM or unverified chat history can supply identity, location or time
    scope. Reject unsupported qualified asks instead of dropping constraints.
    """
    lower = question.casefold()
    stock_words = ('stock', 'inventory', 'tồn kho', 'còn hàng', 'available', 'còn bao nhiêu')
    if 'case-' in lower or not any(token in lower for token in stock_words) or 'fr-' not in lower:
        return None
    matches = _FR_SKU_MATCH.findall(question.upper())
    if len(matches) != 1 or lower.count('fr-') != 1:
        raise InvalidFictionScope('Exactly one complete FR-SKU is required for Fiction inventory')
    if (_STOCK_DATE.search(lower) or
            any(token in lower for token in _STOCK_VI_TIME_WORDS) or
            _STOCK_EN_TIME.search(lower) or _STOCK_CALENDAR.search(lower)):
        raise InvalidFictionScope('UNSUPPORTED_TEMPORAL_SCOPE: Fiction stock has no observation timestamp')
    # A multi-intent query cannot be silently reduced to one SKU's stock.
    if (re.search(r'\b(?:revenue|profit|sales|orders?|refund|returns?|compare|backorder)\b', lower)
            or any(token in lower for token in (
                'doanh thu', 'doanh số', 'lợi nhuận', 'bán chạy',
                'so sánh', 'đơn hàng', 'hoàn tiền', 'đổi trả'))):
        raise InvalidFictionScope('MULTI_INTENT_UNSUPPORTED: request only undated stock for one SKU')
    from retailiq.domain.fiction import _id
    ids = _UUID_IN_QUESTION.findall(question)
    warehouses = _WAREHOUSE_ID_IN_QUESTION.findall(question)
    if len(ids) > 1 or len(warehouses) != len(ids):
        raise InvalidFictionScope('Specify at most one explicitly labeled warehouse UUID')
    # "tồn kho FR-..." contains the word "kho", but that is not a
    # warehouse filter unless a separate canonical warehouse UUID follows it.
    warehouse = _id(warehouses[0]) if warehouses else None
    return matches[0], warehouse
