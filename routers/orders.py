from __future__ import annotations

import os
import sys
from typing import Optional

from fastapi import APIRouter, HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import get_connection
from database.schemas import OrderCreate, OrderPatch, OrderStatusUpdate
from repositories.orders import (
    UNSET,
    create_order_from_items,
    delete_order_and_restore_stock,
    fetch_orders_page_enriched,
    get_order_enriched,
    patch_order,
    update_order_status as repo_update_order_status,
)

router = APIRouter(prefix="/orders", tags=["Siparisler"])

TENANT_ID = 1

VALID_STATUSES = frozenset(
    {"hazırlanıyor", "kargoda", "teslim_edildi", "tamamlandi", "tamamlandı", "iptal"}
)


@router.get("/status-counts", summary="Durumlara gore siparis adetleri")
def order_status_counts():
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT status, COUNT(*) AS c
        FROM orders
        WHERE tenant_id = ?
        GROUP BY status
        """,
        (TENANT_ID,),
    ).fetchall()
    conn.close()
    by_status = {r["status"]: int(r["c"]) for r in rows}
    total = sum(by_status.values())
    return {"total": total, "by_status": by_status}


@router.get("/", summary="Sayfali siparis listesi")
def list_orders(
    status: Optional[str] = None,
    today: bool = False,
    search: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
):
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit 1-200 arasinda olmalidir.")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset negatif olamaz.")
    items, total = fetch_orders_page_enriched(
        tenant_id=TENANT_ID,
        status=status,
        search=search,
        today=today,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total}


@router.get("/summary", summary="Gunluk ozet")
def daily_summary():
    conn = get_connection()
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT status, total_price FROM orders WHERE tenant_id = ?", (TENANT_ID,)
    ).fetchall()
    by_status = {}
    total_revenue = 0.0
    for row in rows:
        st = row["status"]
        by_status[st] = by_status.get(st, 0) + 1
        if row["total_price"] and st != "iptal":
            total_revenue += row["total_price"]

    low_stock = cursor.execute(
        """
        SELECT id, name, stock_quantity, low_stock_threshold
        FROM products
        WHERE stock_quantity <= low_stock_threshold AND is_active = 1
        AND tenant_id = ?
        """,
        (TENANT_ID,),
    ).fetchall()
    pending = cursor.execute(
        "SELECT COUNT(*) as c FROM orders WHERE status = 'hazırlanıyor' AND tenant_id = ?",
        (TENANT_ID,),
    ).fetchone()["c"]
    conn.close()
    return {
        "total_orders": len(rows),
        "by_status": by_status,
        "total_revenue": total_revenue,
        "low_stock_products": [dict(r) for r in low_stock],
        "pending_shipments": int(pending),
    }


@router.get("/{order_id}", summary="Siparis detayi")
def get_order(order_id: int):
    result = get_order_enriched(order_id, tenant_id=TENANT_ID)
    if not result:
        raise HTTPException(status_code=404, detail=f"Siparis #{order_id} bulunamadi.")
    return result


@router.put("/{order_id}/status", summary="Siparis durumunu guncelle")
def update_order_status(order_id: int, body: OrderStatusUpdate):
    if body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Gecersiz durum. Secenekler: {sorted(VALID_STATUSES)}",
        )

    sent = body.model_dump(exclude_unset=True)
    result = repo_update_order_status(
        order_id,
        body.status,
        tenant_id=TENANT_ID,
        cargo_tracking_code=sent["cargo_tracking_code"] if "cargo_tracking_code" in sent else UNSET,
        cargo_company=sent["cargo_company"] if "cargo_company" in sent else UNSET,
    )
    if result.get("hata"):
        raise HTTPException(status_code=404, detail=result["hata"])
    return {"message": f"Siparis #{order_id} durumu '{body.status}' olarak guncellendi.", "result": result}


@router.patch("/{order_id}", summary="Siparis bilgi ve kalemleri guncelle")
def patch_order_route(order_id: int, body: OrderPatch):
    result = patch_order(
        order_id,
        tenant_id=TENANT_ID,
        customer_name=body.customer_name,
        customer_phone=body.customer_phone,
        notes=body.notes,
        created_at=body.created_at,
        items=[i.model_dump() for i in body.items] if body.items is not None else None,
    )
    if result.get("hata"):
        raise HTTPException(status_code=400, detail=result["hata"])
    return {"message": f"Siparis #{order_id} guncellendi.", "result": result}


@router.delete("/{order_id}", summary="Siparisi sil ve stogu iade et")
def delete_order_route(order_id: int):
    result = delete_order_and_restore_stock(order_id, tenant_id=TENANT_ID)
    if result.get("hata"):
        raise HTTPException(status_code=404, detail=result["hata"])
    return {"message": f"Siparis #{order_id} silindi.", "result": result}


@router.post("/", summary="Yeni siparis olustur", status_code=201)
def create_order(body: OrderCreate):
    result = create_order_from_items(
        customer_name=body.customer_name,
        customer_phone=body.customer_phone,
        notes=body.notes,
        items=list(body.items),
        tenant_id=TENANT_ID,
    )
    if result.get("hata"):
        msg = result["hata"]
        code = 404 if "bulunamadi" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg)
    return {
        "message": "Siparis olusturuldu.",
        "order_id": result["order_id"],
        "total_price": result["total_price"],
        "tracking_code": result["tracking_code"],
    }
