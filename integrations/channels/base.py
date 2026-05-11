"""
Channel adapter protocol.

Selective adaptation from langgraph-sales-agent: each platform maps into a
common inbound/outbound shape so Telegram, Web and future WhatsApp Business
can share auth, tenant and graph invocation rules.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass
class InboundMessage:
    channel: str
    channel_user_id: str
    text: str
    tenant_id: int = 1
    channel_message_id: str | None = None
    received_at: datetime = field(default_factory=datetime.utcnow)
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutboundMessage:
    text: str
    buttons: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ChannelAdapter(Protocol):
    channel: str

    def parse_update(self, raw: Any) -> InboundMessage:
        ...

    async def send_reply(self, channel_user_id: str, message: OutboundMessage) -> None:
        ...
