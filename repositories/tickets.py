from __future__ import annotations

from database.db import get_connection

# ---------------------------------------------------------------------------
# Okuma fonksiyonları
# ---------------------------------------------------------------------------

def list_tickets(
    tenant_id: int = 1,
    status: str | None = None,
    type_: str | None = None,
    priority: str | None = None,
    limit: int = 50,
) -> list[dict]:
    conn = get_connection()
    q = "SELECT * FROM tickets WHERE tenant_id = ?"
    params: list = [tenant_id]
    if status:
        q += " AND status = ?"; params.append(status)
    if type_:
        q += " AND type = ?"; params.append(type_)
    if priority:
        q += " AND priority = ?"; params.append(priority)
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_ticket(ticket_id: int, tenant_id: int = 1) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM tickets WHERE id = ? AND tenant_id = ?", (ticket_id, tenant_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_ticket_status(ticket_id: int, status: str, tenant_id: int = 1) -> bool:
    conn = get_connection()
    resolved_sql = "datetime('now','localtime')" if status == "resolved" else "NULL"
    cur = conn.execute(
        f"UPDATE tickets SET status = ?, resolved_at = {resolved_sql} "
        f"WHERE id = ? AND tenant_id = ?",
        (status, ticket_id, tenant_id),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0

# ---------------------------------------------------------------------------
# Yazma fonksiyonları
# ---------------------------------------------------------------------------

def create_ticket(payload: dict, tenant_id: int = 1, dedupe_key: dict | None = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()

    if dedupe_key:
        query = "SELECT id FROM tickets WHERE tenant_id = ? AND status != 'resolved'"
        params: list = [tenant_id]
        for key, value in dedupe_key.items():
            query += f" AND {key} = ?"
            params.append(value)
        existing = cursor.execute(query, params).fetchone()
        if existing:
            conn.close()
            return int(existing["id"])

    cursor.execute(
        """
        INSERT INTO tickets (
            tenant_id, type, title, description, priority, llm_content,
            related_order_id, related_product_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tenant_id,
            payload.get("type", "other"),
            payload.get("title", "Inceleme gerekli"),
            payload.get("description", ""),
            payload.get("priority", "normal"),
            payload.get("llm_content"),
            payload.get("related_order_id"),
            payload.get("related_product_id"),
        ),
    )
    ticket_id = int(cursor.lastrowid)
    conn.commit()
    conn.close()

    try:
        from integrations.notifier import notify_new_ticket

        notify_new_ticket(
            ticket_id,
            payload.get("title", "Inceleme gerekli"),
            payload.get("priority", "normal"),
            payload.get("type", "other"),
            payload.get("description", ""),
        )
    except Exception:
        pass

    return ticket_id

