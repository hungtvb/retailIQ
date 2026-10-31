"""Explicitly consented, bounded customer context for a local chat session.

This is NOT a cross-session customer identity store. Until authentication and
authorization exist, a session must never read another session's preferences.
Only predetermined retail preference enums are accepted; no free-text PII,
secrets, untrusted LLM output or automatic extraction from chat.
"""
from __future__ import annotations

import re
from typing import Mapping

ALLOWED_CATEGORIES = frozenset({
    "Accessory", "Laptop", "Phone", "Audio", "Peripheral",
    "Display", "Tablet",
})
ALLOWED_CHANNELS = frozenset({"online", "store"})
ALLOWED_KEYS = frozenset({"preferred_category", "preferred_channel"})


def validate_preferences(values: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(values, dict):
        raise ValueError("Customer memory preferences must be an object")
    if set(values) - ALLOWED_KEYS:
        raise ValueError("Unsupported customer memory preference")
    clean = {}
    for key, value in values.items():
        if not isinstance(value, str):
            raise ValueError("Customer memory preference must be a string")
        allowed = ALLOWED_CATEGORIES if key == "preferred_category" else ALLOWED_CHANNELS
        if value not in allowed:
            raise ValueError("Unsupported value for " + key)
        clean[key] = value
    return clean


def is_memory_question(question: str) -> bool:
    """Only direct questions asking the assistant to recall saved preferences."""
    q = question.casefold().strip()
    if re.search(r"\b(?:my|saved|remembered)\s+(?:preferred\s+)?(?:category|channel|preferences?)\b", q):
        return True
    return any(phrase in q for phrase in (
        "sở thích đã lưu", "sở thích của tôi", "danh mục ưa thích",
        "kênh mua hàng ưa thích", "tôi thích danh mục nào",
        "tôi đã chọn kênh nào",
    ))


def memory_answer(question: str, stored: dict | None) -> str:
    """Use only explicitly approved structured values, never model guesses."""
    preferences = (stored or {}).get("preferences") if (stored or {}).get("consent") else {}
    if not isinstance(preferences, dict) or not preferences:
        return ("Chưa có sở thích bán lẻ nào được lưu với sự đồng ý của bạn trong phiên này."
                if _vietnamese(question) else
                "No retail preferences have been saved with your consent in this session.")
    fields = []
    if "preferred_category" in preferences:
        fields.append(("danh mục" if _vietnamese(question) else "category")
                      + ": " + preferences["preferred_category"])
    if "preferred_channel" in preferences:
        fields.append(("kênh" if _vietnamese(question) else "channel")
                      + ": " + preferences["preferred_channel"])
    prefix = ("Sở thích đã lưu trong phiên này: " if _vietnamese(question)
              else "Preferences saved in this session: ")
    return prefix + "; ".join(fields) + "."


def _vietnamese(question: str) -> bool:
    from retailiq.language import is_vietnamese
    return is_vietnamese(question) or any(
        word in question.casefold() for word in ("sở thích", "ưa thích", "tôi đã")
    )
