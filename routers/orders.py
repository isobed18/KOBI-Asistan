from fastapi import APIRouter, HTTPException
from typing import Optional
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import get_connection
from database.schemas import OrderResponse, OrderStatusUpdate, OrderCreate, OrderItemResponse

router = APIRouter(prefix="/orders", tags=["Siparişler"])


#  YARDIMCI: sipariş satırlarını zenginleştir
def _enrich_order(row, cursor) -> dict:
    order = dict(row)
    items_rows = cursor.execute("""
        SELECT oi.product_id, p.name AS product_name,
               oi.quantity, oi.unit_price,
               (oi.quantity * oi.unit_price) AS subtotal
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ?
    """, (order["id"],)).fetchall()
    order["items"] = [dict(i) for i in items_rows]
    return order


# GET /orders
@router.get("/", summary="Sipariş listesi")
def list_orders(
    status: Optional[str] = None,
    today: bool = False
):
    """
    - ?status=kargoda   → duruma göre filtrele
    - ?today=true       → yalnızca bugünkü siparişler
    """
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


#  GET /orders/summary
@router.get("/summary", summary="Günlük özet")
def daily_summary():
    """
    Yönetici paneli için: bugünkü siparişler, gelir, kritik stoklar.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Tüm siparişleri al (demo için tarih filtresi yok)
    rows = cursor.execute("SELECT status, total_price FROM orders").fetchall()
    by_status = {}
    total_revenue = 0.0
    for r in rows:
        s = r["status"]
        by_status[s] = by_status.get(s, 0) + 1
        if r["total_price"] and s != "iptal":
            total_revenue += r["total_price"]

    # Kritik stok ürünler
    low_stock = cursor.execute("""
        SELECT id, name, stock_quantity, low_stock_threshold
        FROM products
        WHERE stock_quantity <= low_stock_threshold AND is_active = 1
    """).fetchall()

    # Bekleyen kargolar
    pending = cursor.execute(
        "SELECT COUNT(*) as c FROM orders WHERE status = 'hazırlanıyor'"
    ).fetchone()["c"]

    conn.close()
    return {
        "total_orders": len(rows),
        "by_status": by_status,
        "total_revenue": total_revenue,
        "low_stock_products": [dict(r) for r in low_stock],
        "pending_shipments": pending
    }


#  GET /orders/{id}
@router.get("/{order_id}", summary="Sipariş detayı")
def get_order(order_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Sipariş #{order_id} bulunamadı.")
    result = _enrich_order(row, cursor)
    conn.close()
    return result


#  PUT /orders/{id}/status
@router.put("/{order_id}/status", summary="Sipariş durumunu güncelle")
def update_order_status(order_id: int, body: OrderStatusUpdate):
    """
    Geçerli durumlar: hazırlanıyor | kargoda | teslim_edildi | iptal
    """
    valid = {"hazırlanıyor", "kargoda", "teslim_edildi", "iptal"}
    if body.status not in valid:
        raise HTTPException(status_code=400, detail=f"Geçersiz durum. Seçenekler: {valid}")

    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT id FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Sipariş #{order_id} bulunamadı.")

    cursor.execute("""
        UPDATE orders
        SET status = ?,
            cargo_tracking_code = COALESCE(?, cargo_tracking_code),
            cargo_company       = COALESCE(?, cargo_company),
            updated_at          = datetime('now', 'localtime')
        WHERE id = ?
    """, (body.status, body.cargo_tracking_code, body.cargo_company, order_id))
    conn.commit()
    conn.close()
    return {"message": f"Sipariş #{order_id} durumu '{body.status}' olarak güncellendi."}


# POST /orders
@router.post("/", summary="Yeni sipariş oluştur", status_code=201)
def create_order(body: OrderCreate):
    conn = get_connection()
    cursor = conn.cursor()

    total = 0.0
    item_rows = []
    for item in body.items:
        product = cursor.execute(
            "SELECT id, price, stock_quantity FROM products WHERE id = ? AND is_active = 1",
            (item["product_id"],)
        ).fetchone()
        if not product:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Ürün #{item['product_id']} bulunamadı.")
        if product["stock_quantity"] < item["quantity"]:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=f"Ürün #{item['product_id']} için yeterli stok yok. Mevcut: {product['stock_quantity']}"
            )
        subtotal = product["price"] * item["quantity"]
        total += subtotal
        item_rows.append((item["product_id"], item["quantity"], product["price"]))

    # Siparişi ekle
    cursor.execute("""
        INSERT INTO orders (customer_name, customer_phone, notes, total_price)
        VALUES (?,?,?,?)
    """, (body.customer_name, body.customer_phone, body.notes, total))
    order_id = cursor.lastrowid

    # Kalemleri ekle + stoğu düş
    for product_id, quantity, unit_price in item_rows:
        cursor.execute("""
            INSERT INTO order_items (order_id, product_id, quantity, unit_price)
            VALUES (?,?,?,?)
        """, (order_id, product_id, quantity, unit_price))
        cursor.execute("""
            UPDATE products SET stock_quantity = stock_quantity - ? WHERE id = ?
        """, (quantity, product_id))

    conn.commit()
    conn.close()
    return {"message": "Sipariş oluşturuldu.", "order_id": order_id, "total_price": total}
