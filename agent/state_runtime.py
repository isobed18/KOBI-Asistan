from __future__ import annotations

from contextvars import ContextVar


_channel: ContextVar[str | None] = ContextVar("channel", default=None)
_channel_user_id: ContextVar[str | None] = ContextVar("channel_user_id", default=None)


def set_channel_context(channel: str | None, channel_user_id: str | None) -> None:
    _channel.set(channel)
    _channel_user_id.set(channel_user_id)


def get_channel_context() -> tuple[str | None, str | None]:
    return _channel.get(), _channel_user_id.get()

