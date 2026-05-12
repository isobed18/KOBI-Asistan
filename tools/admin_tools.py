"""
Admin tools for the business owner.

These tools are intentionally scoped to admin conversations. Customer auth
does not apply here; tenant_id is taken from the active tenant context.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langchain_core.tools import tool

from agent.tenant_context import get_tenant_id
from database.db import get_connection
from repositories.orders import UNSET, update_order_status
from repositories.products import search_products, update_stock


def _tenant_id() -> int:
    return int(get_tenant_id() or 1)


def _find_product(urun_adi: str, threshold: float = 0.38) -> list[dict]:
    return search_products(urun_adi, tenant_id=_tenant_id(), threshold=threshold, limit=5)


def _do_stok_guncelle(urun_adi: str, miktar: int, neden: str) -> dict:
    matches = _find_product(urun_adi)
    if not matches:
        return {
            "hata": f"'{urun_adi}' adinda aktif urun bulunamadi.",
            "oneriler": [],
        }

    strong = [m for m in matches if m.get("match_score", 0) >= 0.78]
    if len(strong) == 1:
        match = strong[0]
    elif len(matches) == 1:
        match = matches[0]
    else:
        return {
            "hata": f"'{urun_adi}' icin birden fazla olasi urun bulundu. Daha spesifik yazin.",
            "oneriler": [
                {
                    "id": m["id"],
                    "ad": m["name"],
                    "stok": m["stock_quantity"],
                    "skor": m.get("match_score"),
                }
                for m in matches
            ],
        }

    return update_stock(match["id"], int(miktar), neden, tenant_id=_tenant_id())


@tool
def admin_urun_ara_fuzzy(urun_adi: str) -> dict:
    """Urun adini esnek arama ile bulur. Yazim hatalarina dayanir."""
    matches = _find_product(urun_adi, threshold=0.25)
    return {
        "sorgu": urun_adi,
        "sonuclar": [
            {
                "id": m["id"],
                "ad": m["name"],
                "kategori": m["category"],
                "fiyat": m["price"],
                "stok": m["stock_quantity"],
                "skor": m.get("match_score"),
            }
            for m in matches
        ],
    }


@tool
def admin_stok_guncelle(urun_adi: str, miktar: int, neden: str = "Stok girisi") -> dict:
    """Urun adina gore stok miktarini gunceller ve stock_movements logu yazar.

    miktar pozitifse stok artar, negatifse azalir.
    Ornek: urun_adi='ceviz ici 500 gram', miktar=12, neden='Yeni stok girisi'
    """
    return _do_stok_guncelle(urun_adi, int(miktar), neden)


@tool
def admin_toplu_stok_guncelle(guncellemeler: list) -> dict:
    """Birden fazla urun icin stok gunceller.

    Format: [{"urun_adi": "Ceviz ici 500 gram", "miktar": 12, "neden": "Kargo geldi"}]
    """
    sonuclar = []
    for g in guncellemeler:
        sonuclar.append(
            _do_stok_guncelle(
                g.get("urun_adi", ""),
                int(g.get("miktar", 0)),
                g.get("neden", "Toplu stok guncelleme"),
            )
        )
    basarili = sum(1 for r in sonuclar if r.get("basari"))
    return {
        "toplam": len(sonuclar),
        "basarili": basarili,
        "hatali": len(sonuclar) - basarili,
        "detaylar": sonuclar,
    }


@tool
def admin_siparis_guncelle(
    siparis_no: int,
    yeni_durum: str,
    kargo_kodu: str = None,
    kargo_firmasi: str = None,
    siparis_notu: str = None,
) -> dict:
    """Siparis durumunu gunceller.

    Durumlar: hazirlaniyor/hazirlanıyor, kargoda, teslim_edildi, tamamlandi, iptal.
    Siparis kargoda/teslim_edildi/tamamlandi durumuna gecerse stok dusme eventi ve
    stock_movements logu repository katmaninda otomatik calisir.
    """
    aliases = {
        "hazirlaniyor": "hazÄ±rlanÄ±yor",
        "hazirlanıyor": "hazÄ±rlanÄ±yor",
        "tamamlandı": "tamamlandı",
    }
    status = aliases.get(yeni_durum, yeni_durum)
    valid = {"hazÄ±rlanÄ±yor", "kargoda", "teslim_edildi", "tamamlandi", "tamamlandı", "iptal"}
    if status not in valid:
        return {"hata": f"Gecersiz durum: {yeni_durum}. Gecerli: {sorted(valid)}"}
    return update_order_status(
        int(siparis_no),
        status,
        tenant_id=_tenant_id(),
        cargo_tracking_code=kargo_kodu if kargo_kodu is not None else UNSET,
        cargo_company=kargo_firmasi if kargo_firmasi is not None else UNSET,
        notes=siparis_notu if siparis_notu is not None else UNSET,
    )


@tool
def admin_toplu_siparis_guncelle(guncellemeler: list) -> dict:
    """Birden fazla siparisi tek seferde gunceller."""
    sonuclar = []
    for g in guncellemeler:
        sonuclar.append(
            admin_siparis_guncelle.invoke(
                {
                    "siparis_no": int(g.get("siparis_no", 0)),
                    "yeni_durum": g.get("yeni_durum", ""),
                    "kargo_kodu": g.get("kargo_kodu"),
                    "kargo_firmasi": g.get("kargo_firmasi"),
                    "siparis_notu": g.get("siparis_notu"),
                }
            )
        )
    basarili = sum(1 for r in sonuclar if r.get("basari"))
    return {"toplam": len(sonuclar), "basarili": basarili, "detaylar": sonuclar}


@tool
def admin_urun_ekle(
    isim: str,
    fiyat: float,
    stok: int,
    kategori: str = None,
    stok_esigi: int = 10,
) -> dict:
    """Sisteme yeni urun ekler."""
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM products WHERE name = ? AND is_active = 1 AND tenant_id = ?",
        (isim, _tenant_id()),
    ).fetchone()
    if existing:
        conn.close()
        return {"hata": f"'{isim}' adinda urun zaten mevcut (ID: {existing['id']})."}

    conn.execute(
        """
        INSERT INTO products (tenant_id, name, category, price, stock_quantity, low_stock_threshold)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (_tenant_id(), isim, kategori, float(fiyat), int(stok), int(stok_esigi)),
    )
    product_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return {
        "basari": True,
        "urun_id": product_id,
        "isim": isim,
        "fiyat": float(fiyat),
        "stok": int(stok),
        "kategori": kategori,
        "stok_esigi": int(stok_esigi),
    }


@tool
def admin_bilet_guncelle(bilet_id: int, yeni_durum: str, cozum_notu: str = None) -> dict:
    """Bilet durumunu gunceller. yeni_durum: open | in_progress | resolved."""
    valid = {"open", "in_progress", "resolved"}
    if yeni_durum not in valid:
        return {"hata": f"Gecersiz durum: {yeni_durum}. Gecerli: {sorted(valid)}"}

    conn = get_connection()
    ticket = conn.execute(
        "SELECT id, title, status FROM tickets WHERE id = ? AND tenant_id = ?",
        (int(bilet_id), _tenant_id()),
    ).fetchone()
    if not ticket:
        conn.close()
        return {"hata": f"Bilet #{bilet_id} bulunamadi."}

    note = f"\n\nNot: {cozum_notu}" if cozum_notu else ""
    if yeni_durum == "resolved":
        conn.execute(
            """
            UPDATE tickets
            SET status = ?, resolved_at = datetime('now','localtime'), description = COALESCE(description, '') || ?
            WHERE id = ? AND tenant_id = ?
            """,
            (yeni_durum, note, int(bilet_id), _tenant_id()),
        )
    else:
        conn.execute(
            """
            UPDATE tickets
            SET status = ?, description = COALESCE(description, '') || ?
            WHERE id = ? AND tenant_id = ?
            """,
            (yeni_durum, note, int(bilet_id), _tenant_id()),
        )
    conn.commit()
    conn.close()
    return {
        "basari": True,
        "bilet_id": int(bilet_id),
        "baslik": ticket["title"],
        "eski_durum": ticket["status"],
        "yeni_durum": yeni_durum,
    }


ADMIN_TOOLS = [
    admin_urun_ara_fuzzy,
    admin_stok_guncelle,
    admin_toplu_stok_guncelle,
    admin_siparis_guncelle,
    admin_toplu_siparis_guncelle,
    admin_urun_ekle,
    admin_bilet_guncelle,
]
