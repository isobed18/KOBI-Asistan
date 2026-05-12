"""Contextvar for admin user id (pending mutation ownership)."""

from __future__ import annotations

import contextvars

_admin_user_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "admin_user_id", default=None
)


def set_admin_user_id(user_id: int | None) -> None:
    _admin_user_id.set(int(user_id) if user_id is not None else None)


def get_admin_user_id() -> int | None:
    v = _admin_user_id.get()
    return int(v) if v is not None else None
