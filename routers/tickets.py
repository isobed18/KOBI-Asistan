"""
Tickets Router — İnsan İncelemesi Gerektiren Biletler
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import get_connection
from database.schemas import TicketCreate, TicketStatusUpdate
from repositories.tickets import create_ticket as repo_create_ticket

router = APIRouter(prefix="/tickets", tags=["Biletler"])

VALID_TYPES = {"cargo_delay", "stock_alert", "cancellation_request", "complaint", "refund_request", "anomaly", "other"}
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


@router.patch("/{ticket_id}/status", summary="Bilet durumunu güncelle")
def update_ticket_status(ticket_id: int, body: TicketStatusUpdate):
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Geçersiz durum: {body.status}")

    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Bilet #{ticket_id} bulunamadı.")

    resolved_at_sql = "datetime('now', 'localtime')" if body.status == "resolved" else "NULL"
    cursor.execute(f"""
        UPDATE tickets
        SET status = ?, resolved_at = {resolved_at_sql}
        WHERE id = ?
    """, (body.status, ticket_id))
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
