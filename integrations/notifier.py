"""
Admin Bildirim Servisi — Telegram + in-app notifications
==========================================================
Bilet oluştuğunda veya kritik bir olay gerçekleştiğinde
hem Telegram kanalına mesaj gönderir hem de in-app bildirim
listesine ekler.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from collections import deque

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-app bildirim kuyrukları (son 50 bildirim bellekte tutulur)
# ---------------------------------------------------------------------------

_notifications: deque = deque(maxlen=50)
_notif_id_counter = 0


def _next_id() -> int:
    global _notif_id_counter
    _notif_id_counter += 1
    return _notif_id_counter


def add_notification(type_: str, title: str, body: str, link: str = None):
    """In-app bildirim kuyruğuna ekle."""
    _notifications.appendleft({
        "id":    _next_id(),
        "type":  type_,   # ticket | stock | order | system
        "title": title,
        "body":  body,
        "link":  link,
        "read":  False,
        "ts":    datetime.now().strftime("%H:%M"),
    })


def get_notifications(limit: int = 20) -> list:
    return list(_notifications)[:limit]


def mark_read(notif_id: int):
    for n in _notifications:
        if n["id"] == notif_id:
            n["read"] = True
            break


# ---------------------------------------------------------------------------
# Telegram gönderici
# ---------------------------------------------------------------------------

async def _send_telegram(message: str):
    """Telegram admin kanalına mesaj gönderir."""
    try:
        from config import settings
        if not settings.TELEGRAM_ENABLED or not settings.TELEGRAM_BOT_TOKEN:
            return
        if not settings.TELEGRAM_ADMIN_CHAT_ID:
            logger.debug("TELEGRAM_ADMIN_CHAT_ID ayarlanmamış, bildirim atlandı.")
            return

        from telegram import Bot
        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=settings.TELEGRAM_ADMIN_CHAT_ID,
            text=message,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Telegram bildirimi gönderilemedi: {e}")


def _fire_telegram(message: str):
    """Sync wrapper — mevcut event loop'a göre davranır."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send_telegram(message))
    except RuntimeError:
        asyncio.run(_send_telegram(message))


# ---------------------------------------------------------------------------
# Yüksek seviyeli bildirim fonksiyonları
# ---------------------------------------------------------------------------

def notify_new_ticket(
    ticket_id: int,
    title: str,
    priority: str,
    type_: str,
    description: str = "",
):
    """Yeni bilet oluşunca çağrılır."""
    priority_emoji = {"high": "🔴", "normal": "🟡", "low": "🟢"}.get(priority, "⚪")
    short_desc = description[:200] + "…" if len(description) > 200 else description

    # In-app bildirim
    add_notification(
        type_="ticket",
        title=f"{priority_emoji} Yeni Bilet: {title}",
        body=short_desc,
        link=f"/tickets",
    )

    # Telegram mesajı
    msg = (
        f"🎫 <b>Yeni Bilet #{ticket_id}</b>\n"
        f"{priority_emoji} <b>Öncelik:</b> {priority}\n"
        f"<b>Tür:</b> {type_}\n"
        f"<b>Başlık:</b> {title}\n"
        f"<b>Açıklama:</b> {short_desc}"
    )
    _fire_telegram(msg)


def notify_critical_stock(product_name: str, current_qty: int, threshold: int):
    """Kritik stok seviyesinde bildirim."""
    add_notification(
        type_="stock",
        title=f"⚠️ Kritik Stok: {product_name}",
        body=f"Mevcut: {current_qty} adet (eşik: {threshold})",
        link="/inventory",
    )
    msg = (
        f"⚠️ <b>Kritik Stok Uyarısı</b>\n"
        f"<b>Ürün:</b> {product_name}\n"
        f"<b>Mevcut:</b> {current_qty} adet\n"
        f"<b>Eşik:</b> {threshold} adet"
    )
    _fire_telegram(msg)


def notify_order_shipped(order_id: int, customer_name: str, cargo_company: str = None):
    """Sipariş kargoya verilince bildirim."""
    cargo_info = f" ({cargo_company})" if cargo_company else ""
    add_notification(
        type_="order",
        title=f"🚚 Sipariş #{order_id} Kargoya Verildi",
        body=f"Müşteri: {customer_name}{cargo_info}",
        link="/orders",
    )
