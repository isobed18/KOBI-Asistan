"""
In-memory pending admin DB mutations (preview → confirm).
Thread-safe; single-use tokens; TTL.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

PENDING_TTL_SEC = 900


@dataclass
class PendingRecord:
    tenant_id: int
    user_id: int
    payload: dict[str, Any]
    expires_at: float


_lock = threading.Lock()
_store: dict[str, PendingRecord] = {}


def _purge_expired_unlocked(now: float) -> None:
    dead = [k for k, v in _store.items() if v.expires_at <= now]
    for k in dead:
        del _store[k]


def register_pending(tenant_id: int, user_id: int, payload: dict[str, Any]) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _lock:
        _purge_expired_unlocked(now)
        _store[token] = PendingRecord(
            tenant_id=int(tenant_id),
            user_id=int(user_id),
            payload=dict(payload),
            expires_at=now + PENDING_TTL_SEC,
        )
    return token


def take_pending(token: str, tenant_id: int, user_id: int) -> PendingRecord | None:
    """Validate tenant/user, not expired; remove and return record (single use)."""
    now = time.time()
    with _lock:
        _purge_expired_unlocked(now)
        rec = _store.get(token)
        if rec is None:
            return None
        if rec.expires_at <= now:
            del _store[token]
            return None
        if rec.tenant_id != int(tenant_id) or rec.user_id != int(user_id):
            return None
        del _store[token]
        return rec
