"""Kritik stok müdahale kaydı — zamanlayıcı ve ürün API ortak."""

from __future__ import annotations

import json

from database.db import get_connection
from agent.llm_service import agenerate_stock_alert_content
from repositories.tickets import create_ticket as repo_create_ticket


async def ensure_stock_alert_ticket(urun: dict, tenant_id: int) -> int | None:
    """
    Stok eşik altındaysa stock_alert bilet oluşturur (aynı ürün için açık kayıt dedupe).
    Aktif olmayan ürünlerde None döner.
    """
    if not urun.get("is_active", 1):
        return None
    if urun.get("stock_quantity", 10**9) > urun.get("low_stock_threshold", 0):
        return None

    llm_data = await agenerate_stock_alert_content(urun)
    llm_json = json.dumps(llm_data, ensure_ascii=False)

    ticket_id = repo_create_ticket(
        payload={
            "type": "stock_alert",
            "title": f"Kritik Stok: {urun['name']} ({urun['stock_quantity']} adet)",
            "description": (
                f"Urun '{urun['name']}' stok seviyesi kritik esigi altinda. "
                f"Mevcut: {urun['stock_quantity']} adet, Esik: {urun['low_stock_threshold']} adet."
            ),
            "llm_content": llm_json,
            "priority": "high",
            "related_product_id": urun["id"],
        },
        tenant_id=tenant_id,
        dedupe_key={"type": "stock_alert", "related_product_id": urun["id"]},
    )
    return ticket_id


async def schedule_stock_intervention_check(product_id: int, tenant_id: int) -> None:
    """Ürün güncellemesi / stok hareketinden sonra DB'den okuyup kritikse bilet açar."""
    conn = get_connection()
    row = conn.execute(
        """
        SELECT id, name, category, stock_quantity, low_stock_threshold, is_active
        FROM products WHERE id = ? AND tenant_id = ?
        """,
        (product_id, tenant_id),
    ).fetchone()
    conn.close()
    if not row:
        return
    await ensure_stock_alert_ticket(dict(row), tenant_id)
