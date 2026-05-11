from fastapi import APIRouter, HTTPException
from typing import Optional
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import get_connection
from database.schemas import ProductCreate, StockUpdateRequest

router = APIRouter(prefix="/products", tags=["Ürünler"])


#  YARDIMCI
def _add_low_stock_flag(product: dict) -> dict:
    product["is_low_stock"] = product["stock_quantity"] <= product["low_stock_threshold"]
    return product


#  GET /products
@router.get("/", summary="Ürün listesi")
def list_products(
    category: Optional[str] = None,
    low_stock: bool = False,
    search: Optional[str] = None
):
    """
    - ?category=Gıda        → kategoriye göre filtrele
    - ?low_stock=true       → yalnızca kritik stoklu ürünler
    - ?search=domates       → isimde arama
    """
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM products WHERE is_active = 1"
    params = []

    if category:
        query += " AND category = ?"
        params.append(category)
    if low_stock:
        query += " AND stock_quantity <= low_stock_threshold"
    if search:
        query += " AND name LIKE ?"
        params.append(f"%{search}%")

    query += " ORDER BY name ASC"
    rows = cursor.execute(query, params).fetchall()
    conn.close()
    return [_add_low_stock_flag(dict(r)) for r in rows]


#  GET /products/{id}
@router.get("/{product_id}", summary="Ürün detayı")
def get_product(product_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM products WHERE id = ? AND is_active = 1", (product_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Ürün #{product_id} bulunamadı.")
    conn.close()
    return _add_low_stock_flag(dict(row))


#  POST /products
@router.post("/", summary="Yeni ürün ekle", status_code=201)
def create_product(body: ProductCreate):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO products (name, category, price, stock_quantity, low_stock_threshold)
        VALUES (?,?,?,?,?)
    """, (body.name, body.category, body.price, body.stock_quantity, body.low_stock_threshold))
    product_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"message": "Ürün eklendi.", "product_id": product_id}


#  PATCH /products/{id}/stock
@router.patch("/{product_id}/stock", summary="Stok güncelle")
def update_stock(product_id: int, body: StockUpdateRequest):
    """
    quantity_change pozitif ise stok artar, negatif ise azalır.
    Örnek: {"quantity_change": 50, "reason": "Yeni sevkiyat"}
    """
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT id, stock_quantity FROM products WHERE id = ? AND is_active = 1", (product_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Ürün #{product_id} bulunamadı.")

    new_qty = row["stock_quantity"] + body.quantity_change
    if new_qty < 0:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=f"Stok miktarı 0'ın altına düşemez. Mevcut: {row['stock_quantity']}"
        )

    old_qty = row["stock_quantity"]
    cursor.execute(
        "UPDATE products SET stock_quantity = ? WHERE id = ?",
        (new_qty, product_id)
    )
    cursor.execute("""
        INSERT INTO stock_movements (product_id, delta, reason, before_qty, after_qty)
        VALUES (?, ?, ?, ?, ?)
    """, (product_id, body.quantity_change, body.reason or "manuel", old_qty, new_qty))
    conn.commit()
    conn.close()
    return {
        "message": "Stok güncellendi.",
        "product_id": product_id,
        "old_quantity": old_qty,
        "new_quantity": new_qty,
        "change": body.quantity_change,
        "reason": body.reason
    }


#  GET /products/{id}/movements
@router.get("/{product_id}/movements", summary="Stok hareket geçmişi")
def stock_movements(product_id: int, limit: int = 50):
    conn = get_connection()
    cursor = conn.cursor()
    rows = cursor.execute("""
        SELECT id, delta, reason, note, before_qty, after_qty, created_at
        FROM stock_movements
        WHERE product_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (product_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# DELETE /products/{id} (soft delete)
@router.delete("/{product_id}", summary="Ürünü pasife al")
def deactivate_product(product_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT id FROM products WHERE id = ? AND is_active = 1", (product_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Ürün #{product_id} bulunamadı.")
    cursor.execute("UPDATE products SET is_active = 0 WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    return {"message": f"Ürün #{product_id} pasife alındı."}
