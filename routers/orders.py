from __future__ import annotations

import os
import sys
from typing import Optional

from fastapi import APIRouter, HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import get_connection
from database.schemas import OrderCreate, OrderStatusUpdate
from repositories.orders import update_order_status as repo_update_order_status

router = APIRouter(prefix="/orders", tags=["Siparisler"])


def _enrich_order(row, cursor) -> dict:
    order = dict(row)
    items_rows = cursor.execute(
        """
        SELECT oi.product_id, p.name AS product_name,
               oi.quantity, oi.unit_price,
               (oi.quantity * oi.unit_price) AS subtotal
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ?
        """,
        (order["id"],),
    ).fetchall()
    order["items"] = [dict(i) for i in items_rows]
    return order


@router.get("/", summary="Siparis listesi")
def list_orders(status: Optional[str] = None, today: bool = False):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM orders WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if today:
        query += " AND DATE(created_at) = DATE('now', 'localtime')"
    query += " ORDER BY created_at DESC"
    rows = cursor.execute(query, params).fetchall()
    result = [_enrich_order(r, cursor) for r in rows]
    conn.close()
    return result


@router.get("/summary", summary="Gunluk ozet")
def daily_summary():
    conn = get_connection()
    cursor = conn.cursor()
    rows = cursor.execute("SELECT status, total_price FROM orders").fetchall()
    by_status = {}
    total_revenue = 0.0
    for row in rows:
        status = row["status"]
        by_status[status] = by_status.get(status, 0) + 1
        if row["total_price"] and status != "iptal":
            total_revenue += row["total_price"]

    low_stock = cursor.execute(
        """
        SELECT id, name, stock_quantity, low_stock_threshold
        FROM products
        WHERE stock_quantity <= low_stock_threshold AND is_active = 1
        """
    ).fetchall()
    pending = cursor.execute(
        "SELECT COUNT(*) as c FROM orders WHERE status = 'hazÄ±rlanÄ±yor'"
    ).fetchone()["c"]
    conn.close()
    return {
        "total_orders": len(rows),
        "by_status": by_status,
        "total_revenue": total_revenue,
        "low_stock_products": [dict(r) for r in low_stock],
        "pending_shipments": pending,
    }


@router.get("/{order_id}", summary="Siparis detayi")
def get_order(order_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Siparis #{order_id} bulunamadi.")
    result = _enrich_order(row, cursor)
    conn.close()
    return result


@router.put("/{order_id}/status", summary="Siparis durumunu guncelle")
def update_order_status(order_id: int, body: OrderStatusUpdate):
    valid = {"hazÄ±rlanÄ±yor", "kargoda", "teslim_edildi", "tamamlandi", "tamamlandı", "iptal"}
    if body.status not in valid:
        raise HTTPException(status_code=400, detail=f"Gecersiz durum. Secenekler: {sorted(valid)}")

    result = repo_update_order_status(
        order_id,
        body.status,
        tenant_id=1,
        cargo_tracking_code=body.cargo_tracking_code,
        cargo_company=body.cargo_company,
    )
    if result.get("hata"):
        raise HTTPException(status_code=404, detail=result["hata"])
    return {"message": f"Siparis #{order_id} durumu '{body.status}' olarak guncellendi.", "result": result}


@router.post("/", summary="Yeni siparis olustur", status_code=201)
def create_order(body: OrderCreate):
    conn = get_connection()
    cursor = conn.cursor()

    total = 0.0
    item_rows = []
    for item in body.items:
        product = cursor.execute(
            "SELECT id, price, stock_quantity FROM products WHERE id = ? AND is_active = 1",
            (item["product_id"],),
        ).fetchone()
        if not product:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Urun #{item['product_id']} bulunamadi.")
        if product["stock_quantity"] < item["quantity"]:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=f"Urun #{item['product_id']} icin yeterli stok yok. Mevcut: {product['stock_quantity']}",
            )
        subtotal = product["price"] * item["quantity"]
        total += subtotal
        item_rows.append((item["product_id"], item["quantity"], product["price"]))

    cursor.execute(
        """
        INSERT INTO orders (customer_name, customer_phone, notes, total_price)
        VALUES (?, ?, ?, ?)
        """,
        (body.customer_name, body.customer_phone, body.notes, total),
    )
    order_id = cursor.lastrowid

    for product_id, quantity, unit_price in item_rows:
        cursor.execute(
            """
            INSERT INTO order_items (order_id, product_id, quantity, unit_price)
            VALUES (?, ?, ?, ?)
            """,
            (order_id, product_id, quantity, unit_price),
        )

    conn.commit()
    conn.close()
    return {"message": "Siparis olusturuldu.", "order_id": order_id, "total_price": total}
