"""
Execute pending admin mutation payloads (used by HTTP confirm and admin_pending_uygula tool).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import get_connection
from repositories.orders import UNSET, delete_order_and_restore_stock, update_order_status
from repositories.products import deactivate_product, patch_product, update_stock

_ALLOWED_DELETE_STATUSES = frozenset({"hazırlanıyor", "kargoda"})


def apply_pending_payload(payload: dict, tenant_id: int) -> dict:
    kind = payload.get("kind")
    if kind == "stok_single":
        return update_stock(
            int(payload["product_id"]),
            int(payload["delta"]),
            str(payload.get("neden") or "Stok guncelleme"),
            tenant_id=tenant_id,
        )
    if kind == "stok_bulk":
        detaylar = []
        for it in payload.get("items") or []:
            detaylar.append(
                update_stock(
                    int(it["product_id"]),
                    int(it["delta"]),
                    str(it.get("neden") or "Toplu stok"),
                    tenant_id=tenant_id,
                )
            )
        basarili = sum(1 for r in detaylar if r.get("basari"))
        return {
            "basari": basarili == len(detaylar),
            "toplam": len(detaylar),
            "basarili": basarili,
            "detaylar": detaylar,
        }
    if kind == "siparis_update":
        return update_order_status(
            int(payload["siparis_no"]),
            str(payload["yeni_durum"]),
            tenant_id=tenant_id,
            cargo_tracking_code=payload["kargo_kodu"]
            if payload.get("kargo_kodu") is not None
            else UNSET,
            cargo_company=payload["kargo_firmasi"]
            if payload.get("kargo_firmasi") is not None
            else UNSET,
            notes=payload["siparis_notu"] if payload.get("siparis_notu") is not None else UNSET,
        )
    if kind == "siparis_bulk":
        detaylar = []
        for it in payload.get("items") or []:
            detaylar.append(
                update_order_status(
                    int(it["siparis_no"]),
                    str(it["yeni_durum"]),
                    tenant_id=tenant_id,
                    cargo_tracking_code=it["kargo_kodu"]
                    if it.get("kargo_kodu") is not None
                    else UNSET,
                    cargo_company=it["kargo_firmasi"]
                    if it.get("kargo_firmasi") is not None
                    else UNSET,
                    notes=it["siparis_notu"] if it.get("siparis_notu") is not None else UNSET,
                )
            )
        basarili = sum(1 for r in detaylar if r.get("basari"))
        return {
            "basari": basarili == len(detaylar),
            "toplam": len(detaylar),
            "basarili": basarili,
            "detaylar": detaylar,
        }
    if kind == "siparis_delete":
        oid = int(payload["siparis_no"])
        conn = get_connection()
        row = conn.execute(
            "SELECT id, status, customer_name FROM orders WHERE id = ? AND tenant_id = ?",
            (oid, tenant_id),
        ).fetchone()
        conn.close()
        if not row:
            return {"hata": f"Siparis #{oid} bulunamadi."}
        if row["status"] not in _ALLOWED_DELETE_STATUSES:
            return {
                "hata": (
                    f"Siparis #{oid} silinemez (durum: {row['status']}). "
                    f"Yalnizca hazirlaniyor veya kargoda siparisler silinebilir."
                ),
            }
        return delete_order_and_restore_stock(oid, tenant_id=tenant_id)
    if kind == "urun_ekle":
        isim = str(payload["isim"])
        conn = get_connection()
        existing = conn.execute(
            "SELECT id FROM products WHERE name = ? AND is_active = 1 AND tenant_id = ?",
            (isim, tenant_id),
        ).fetchone()
        if existing:
            conn.close()
            return {"hata": f"'{isim}' adinda urun zaten mevcut (ID: {existing['id']})."}
        conn.execute(
            """
            INSERT INTO products (tenant_id, name, category, price, stock_quantity, low_stock_threshold)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                isim,
                payload.get("kategori"),
                float(payload["fiyat"]),
                int(payload["stok"]),
                int(payload.get("stok_esigi") or 10),
            ),
        )
        product_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        conn.close()
        return {
            "basari": True,
            "urun_id": product_id,
            "isim": isim,
            "fiyat": float(payload["fiyat"]),
            "stok": int(payload["stok"]),
            "kategori": payload.get("kategori"),
            "stok_esigi": int(payload.get("stok_esigi") or 10),
        }
    if kind == "urun_duzenle":
        pid = int(payload["urun_id"])
        p = payload.get("patch") or {}
        return patch_product(pid, tenant_id, p)
    if kind == "urun_sil":
        return deactivate_product(int(payload["urun_id"]), tenant_id)

    return {"hata": f"Bilinmeyen islem turu: {kind!r}"}
