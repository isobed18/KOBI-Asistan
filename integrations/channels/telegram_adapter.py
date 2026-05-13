"""Telegram channel adapter."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

from config import settings
from integrations.channels.base import InboundMessage, OutboundMessage


class TelegramAdapter:
    channel = "telegram"

    def parse_update(self, update: Update) -> InboundMessage:
        message = update.effective_message
        return InboundMessage(
            channel=self.channel,
            channel_user_id=str(update.effective_chat.id),
            channel_message_id=str(message.message_id) if message else None,
            text=(message.text or "") if message else "",
            tenant_id=int(settings.TELEGRAM_TENANT_ID or 2),
            raw_payload=update.to_dict() if hasattr(update, "to_dict") else {},
        )

    async def send_reply(self, channel_user_id: str, message: OutboundMessage) -> None:
        # python-telegram-bot sends through Update objects in our current runtime;
        # this method is kept for webhook/WhatsApp parity and future extraction.
        print(f"[TelegramAdapter] {channel_user_id}: {message.text[:200]}")


def keyboard_from_buttons(buttons: list[dict[str, str]] | None):
    if not buttons:
        return None
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(b["text"], callback_data=b["callback_data"])]
        for b in buttons
    ])
