"""
Tickets Router — İnsan İncelemesi Gerektiren Biletler
"""

from __future__ import annotations

import json
import sys
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import get_connection
from database.schemas import TicketCreate, TicketStatusUpdate
from repositories.tickets import create_ticket as repo_create_ticket
from repositories.orders import (
    create_order_from_items,
    delete_order_and_restore_stock,
    get_order,
)
from integrations.notifier import send_customer_telegram_message

router = APIRouter(prefix="/tickets", tags=["Biletler"])

VALID_TYPES = {
    "cargo_delay",
    "stock_alert",
    "cancellation_request",
    "telegram_order_request",
    "complaint",
    "refund_request",
    "anomaly",
    "other",
}
VALID_STATUSES = {"open", "in_progress", "resolved"}
VALID_PRIORITIES = {"low", "normal", "high", "critical"}


@router.get("/", summary="Bilet listesi")
def list_tickets(
    status: Optional[str] = None,
    type: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 50,
):
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM tickets WHERE 1=1"
    params: list = []

    if status:
        query += " AND status = ?"
        params.append(status)
    if type:
        query += " AND type = ?"
        params.append(type)
    if priority:
        query += " AND priority = ?"
        params.append(priority)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = cursor.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/{ticket_id}", summary="Bilet detayı")
def get_ticket(ticket_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Bilet #{ticket_id} bulunamadı.")
    return dict(row)


@router.post("/", summary="Manuel bilet oluştur", status_code=201)
def create_ticket(body: TicketCreate):
    """Repository katmanı üzerinden bilet oluşturur; notifier otomatik tetiklenir."""
    if body.type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"Gecersiz tip: {body.type}")
    ticket_id = repo_create_ticket(
        payload={
            "type": body.type,
            "title": body.title,
            "description": body.description,
            "priority": body.priority,
            "llm_content": body.llm_content,
            "related_order_id": body.related_order_id,
            "related_product_id": body.related_product_id,
        },
        tenant_id=1,  # TODO: JWT'den al
    )
    return {"message": "Bilet oluşturuldu.", "ticket_id": ticket_id}


def _parse_telegram_order_payload(llm_raw: str | None) -> dict:
    try:
        return json.loads(llm_raw or "{}")
    except json.JSONDecodeError:
        return {}


@router.patch("/{ticket_id}/status", summary="Bilet durumunu güncelle")
def update_ticket_status(ticket_id: int, body: TicketStatusUpdate):
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Geçersiz durum: {body.status}")

    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Bilet #{ticket_id} bulunamadı.")
    ticket = dict(row)
    conn.close()

    if ticket.get("status") == "resolved" and body.status == "resolved":
        raise HTTPException(status_code=400, detail="Bilet zaten cozuldu.")

    # --- Telegram siparis talebi: onay / red (siparis olusturma veya iptal mesaji) ---
    if body.status == "resolved" and ticket.get("type") == "telegram_order_request":
        resolution = (body.resolution or "").strip().lower()
        if resolution not in ("approve", "reject"):
            raise HTTPException(
                status_code=400,
                detail="telegram_order_request icin resolution: 'approve' veya 'reject' gerekli.",
            )

        payload = _parse_telegram_order_payload(ticket.get("llm_content"))
        chat_id = str(payload.get("telegram_chat_id") or "")

        if resolution == "reject":
            if chat_id:
                send_customer_telegram_message(
                    chat_id,
                    "Siparis talebiniz isletme tarafindan reddedildi. "
                    "Yeni talep icin urunleri sepete ekleyip tekrar gonderebilirsiniz.",
                )
            payload["panel_resolution"] = "reject"
            payload["resolved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_llm = json.dumps(payload, ensure_ascii=False)
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE tickets
                SET status = 'resolved', resolved_at = datetime('now', 'localtime'),
                    llm_content = ?
                WHERE id = ?
                """,
                (new_llm, ticket_id),
            )
            conn.commit()
            conn.close()
            return {
                "message": f"Bilet #{ticket_id} reddedildi ve kapatildi.",
                "resolution": "reject",
            }

        # approve
        fulfilled = payload.get("fulfilled_order_id")
        if fulfilled:
            new_llm = json.dumps(payload, ensure_ascii=False)
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE tickets
                SET status = 'resolved', resolved_at = datetime('now', 'localtime'),
                    llm_content = ?
                WHERE id = ?
                """,
                (new_llm, ticket_id),
            )
            conn.commit()
            conn.close()
            return {
                "message": f"Bilet #{ticket_id} zaten islenmisti. Siparis #{fulfilled}.",
                "order_id": int(fulfilled),
            }

        items = payload.get("items") or []
        if not items:
            raise HTTPException(
                status_code=400,
                detail="Bilet icinde siparis kalemi yok (items).",
            )
        tenant_id = int(payload.get("tenant_id") or 1)
        name = str(payload.get("customer_name") or "").strip() or "Musteri"
        phone = payload.get("customer_phone")
        notes = str(payload.get("notes") or "Telegram onay")

        result = create_order_from_items(
            customer_name=name,
            customer_phone=phone,
            notes=notes,
            items=items,
            tenant_id=tenant_id,
        )
        if result.get("hata"):
            raise HTTPException(status_code=400, detail=result["hata"])

        payload["fulfilled_order_id"] = result["order_id"]
        payload["fulfilled_total"] = result["total_price"]
        payload["fulfilled_tracking_code"] = result["tracking_code"]
        payload["panel_resolution"] = "approve"
        payload["fulfilled_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_llm = json.dumps(payload, ensure_ascii=False)

        if chat_id:
            send_customer_telegram_message(
                chat_id,
                "Talebiniz onaylandi.\n"
                f"Siparis numaraniz: #{result['order_id']}\n"
                f"Ucret: {result['total_price']:.2f} TL\n"
                f"Takip kodunuz: {result['tracking_code']}\n"
                "Tesekkurler!",
            )

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE tickets
            SET status = 'resolved', resolved_at = datetime('now', 'localtime'),
                llm_content = ?, related_order_id = ?
            WHERE id = ?
            """,
            (new_llm, int(result["order_id"]), ticket_id),
        )
        conn.commit()
        conn.close()
        return {
            "message": f"Bilet #{ticket_id} onaylandi; siparis #{result['order_id']} olusturuldu.",
            "order_id": result["order_id"],
            "total_price": result["total_price"],
            "tracking_code": result["tracking_code"],
        }

    # --- Iptal talebi: yalnizca approve_cancel ile siparis sil + stok iade + Telegram ---
    if body.status == "resolved" and ticket.get("type") == "cancellation_request":
        resolution = (body.resolution or "").strip().lower()
        if resolution != "approve_cancel":
            raise HTTPException(
                status_code=400,
                detail=(
                    "Iptal talebini tamamlamak icin panelden 'Iptali onayla' kullanin "
                    "(resolution=approve_cancel)."
                ),
            )
        oid_raw = ticket.get("related_order_id")
        if not oid_raw:
            raise HTTPException(status_code=400, detail="Bilette iliskili siparis yok.")
        oid = int(oid_raw)
        order = get_order(oid, tenant_id=1)
        if not order:
            raise HTTPException(status_code=400, detail=f"Siparis #{oid} bulunamadi.")
        st = order.get("status") or ""
        if st not in ("hazırlanıyor", "kargoda"):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Siparis #{oid} durumu ({st}) iptal ve stok iadesi icin uygun degil. "
                    "Once siparisi uygun duruma getirin veya manuel islem yapin."
                ),
            )
        del_res = delete_order_and_restore_stock(oid, tenant_id=1)
        if del_res.get("hata"):
            raise HTTPException(status_code=400, detail=del_res["hata"])

        chat_id = str(ticket.get("source_channel_user_id") or "").strip()
        if chat_id:
            send_customer_telegram_message(
                chat_id,
                "İptal talebiniz onaylandı. "
                f"Siparişiniz (#{oid}) iptal edildi; stoklar iade edildi. "
                "Başka bir konuda yardıma ihtiyacınız olursa yazabilirsiniz.",
            )

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE tickets
            SET status = 'resolved', resolved_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (ticket_id,),
        )
        conn.commit()
        conn.close()
        return {
            "message": (
                f"Bilet #{ticket_id} kapatildi; siparis #{oid} silindi, stok iade edildi."
            ),
            "resolution": "approve_cancel",
            "order_id": oid,
        }

    conn = get_connection()
    cursor = conn.cursor()
    resolved_at_sql = "datetime('now', 'localtime')" if body.status == "resolved" else "NULL"
    cursor.execute(
        f"""
        UPDATE tickets
        SET status = ?, resolved_at = {resolved_at_sql}
        WHERE id = ?
    """,
        (body.status, ticket_id),
    )
    conn.commit()
    conn.close()
    return {"message": f"Bilet #{ticket_id} durumu '{body.status}' olarak güncellendi."}


@router.get("/stats/summary", summary="Bilet istatistikleri")
def ticket_stats():
    conn = get_connection()
    cursor = conn.cursor()

    by_status = cursor.execute(
        "SELECT status, COUNT(*) as c FROM tickets GROUP BY status"
    ).fetchall()
    by_type = cursor.execute(
        "SELECT type, COUNT(*) as c FROM tickets GROUP BY type"
    ).fetchall()
    by_priority = cursor.execute(
        "SELECT priority, COUNT(*) as c FROM tickets WHERE status != 'resolved' GROUP BY priority"
    ).fetchall()

    conn.close()
    return {
        "by_status": {r["status"]: r["c"] for r in by_status},
        "by_type": {r["type"]: r["c"] for r in by_type},
        "open_by_priority": {r["priority"]: r["c"] for r in by_priority},
    }
