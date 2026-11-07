"""Trusted application principal; model, request bodies, and graph state cannot mint it."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class SecurityContext:
    user_id: str
    role: Literal["analyst", "manager"]
    auth_session_id: str
