from fastapi import APIRouter, BackgroundTasks, HTTPException
from typing import Optional
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import get_connection
from database.schemas import ProductCreate, ProductPatch, StockUpdateRequest
from agent.tenant_context import get_tenant_id
from repositories.products import deactivate_product as repo_deactivate_product
from repositories.products import patch_product as repo_patch_product
from services.stock_intervention import schedule_stock_intervention_check

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

    query = "SELECT * FROM products WHERE is_active = 1 AND tenant_id = ?"
    params = [get_tenant_id()]

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
        "SELECT * FROM products WHERE id = ? AND is_active = 1 AND tenant_id = ?",
        (product_id, get_tenant_id())
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
        INSERT INTO products (
            tenant_id, name, category, price, stock_quantity, low_stock_threshold,
            description, ingredients, allergens, size_guide, advisory_notes, image_url, visual_keywords
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        get_tenant_id(), body.name, body.category, body.price, body.stock_quantity, body.low_stock_threshold,
        body.description, body.ingredients, body.allergens, body.size_guide, body.advisory_notes,
        body.image_url, body.visual_keywords,
    ))
    product_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"message": "Ürün eklendi.", "product_id": product_id}


#  PATCH /products/{id}
@router.patch("/{product_id}", summary="Ürün alanlarını güncelle")
def patch_product(product_id: int, body: ProductPatch, background_tasks: BackgroundTasks):
    """İsim, kategori, fiyat, stok ve eşik değerlerini doğrudan günceller; stok değişirse hareket kaydı oluşturulur."""
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok.")

    out = repo_patch_product(product_id, get_tenant_id(), data)
    if out.get("hata"):
        code = 404 if "bulunamadi" in (out["hata"] or "").lower() else 400
        raise HTTPException(status_code=code, detail=out["hata"])
    urun = _add_low_stock_flag(dict(out["urun"]))
    if {"stock_quantity", "low_stock_threshold"} & data.keys():
        if urun.get("is_active", 1) and urun.get("stock_quantity", 10**9) <= urun.get("low_stock_threshold", 0):
            tid = get_tenant_id()
            background_tasks.add_task(schedule_stock_intervention_check, product_id, tid)
    return urun


#  PATCH /products/{id}/stock
@router.patch("/{product_id}/stock", summary="Stok güncelle")
def update_stock(product_id: int, body: StockUpdateRequest, background_tasks: BackgroundTasks):
    """
    quantity_change pozitif ise stok artar, negatif ise azalır.
    Örnek: {"quantity_change": 50, "reason": "Yeni sevkiyat"}
    """
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT id, stock_quantity FROM products WHERE id = ? AND is_active = 1 AND tenant_id = ?",
        (product_id, get_tenant_id())
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
        "UPDATE products SET stock_quantity = ? WHERE id = ? AND tenant_id = ?",
        (new_qty, product_id, get_tenant_id())
    )
    cursor.execute("""
        INSERT INTO stock_movements (tenant_id, product_id, delta, reason, before_qty, after_qty)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (get_tenant_id(), product_id, body.quantity_change, body.reason or "manuel", old_qty, new_qty))
    conn.commit()
    conn.close()
    tid = get_tenant_id()
    background_tasks.add_task(schedule_stock_intervention_check, product_id, tid)
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
        WHERE product_id = ? AND tenant_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (product_id, get_tenant_id(), limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# DELETE /products/{id} (soft delete)
@router.delete("/{product_id}", summary="Ürünü pasife al")
def deactivate_product(product_id: int):
    out = repo_deactivate_product(product_id, get_tenant_id())
    if out.get("hata"):
        raise HTTPException(status_code=404, detail=out["hata"])
    return {"message": f"Ürün #{product_id} pasife alındı."}
