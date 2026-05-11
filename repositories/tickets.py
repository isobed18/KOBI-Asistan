from __future__ import annotations

from database.db import get_connection


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

