"""
Admin tools for the business owner.

Mutating operations use two phases: *_onay_iste (preview + token) and
admin_pending_uygula(onay_token) or HTTP /admin/pending/confirm.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from agent.admin_user_context import get_admin_user_id
from agent.pending_admin_mutations import register_pending, take_pending
from agent.tenant_context import get_tenant_id
from database.db import get_connection
from repositories.orders import get_order
from repositories.products import get_product, list_products, search_products
from tools.admin_mutation_apply import apply_pending_payload


def _tenant_id() -> int:
    return int(get_tenant_id() or 1)


def _require_user_id() -> int | None:
    return get_admin_user_id()


def _pending_response(ozet: str, payload: dict) -> dict:
    uid = _require_user_id()
    if uid is None:
        return {
            "hata": "Islem baglami eksik. Lutfen panelden Admin Asistan uzerinden deneyin.",
        }
    token = register_pending(_tenant_id(), uid, payload)
    return {
        "onay_bekliyor": True,
        "onay_token": token,
        "ozet": ozet,
        "detay": payload,
    }


# Veritabanındaki sipariş durumları (seed / orders router ile uyumlu)
_VALID_ORDER_STATUSES = frozenset(
    {"hazırlanıyor", "kargoda", "teslim_edildi", "tamamlandi", "tamamlandı", "iptal"}
)


def _normalize_order_status_for_list(durum: str | None) -> str | None:
    if durum is None or not str(durum).strip():
        return None
    s = str(durum).strip().lower().replace(" ", "_").replace("-", "_")
    ascii_fix = {
        "hazirlaniyor": "hazırlanıyor",
        "hazirlanıyor": "hazırlanıyor",
        "tamamlandi": "tamamlandi",
    }
    s = ascii_fix.get(s, s)
    if s in _VALID_ORDER_STATUSES:
        return s
    return None


def _normalize_siparis_guncelle_status(yeni_durum: str) -> str | None:
    raw = (yeni_durum or "").strip()
    if not raw:
        return None
    s = raw.lower().replace(" ", "_").replace("-", "_")
    ascii_fix = {
        "hazirlaniyor": "hazırlanıyor",
        "hazirlanıyor": "hazırlanıyor",
        "tamamlandi": "tamamlandi",
    }
    s = ascii_fix.get(s, s)
    if s in _VALID_ORDER_STATUSES:
        return s
    return None


def _find_product(urun_adi: str, threshold: float = 0.38) -> list[dict]:
    return search_products(urun_adi, tenant_id=_tenant_id(), threshold=threshold, limit=5)


def _resolve_stok_satir(urun_adi: str, miktar: int, neden: str) -> dict:
    """Tek satır için ürün çözümü; basari yoksa hata + oneriler."""
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

    before = int(match["stock_quantity"])
    delta = int(miktar)
    after = before + delta
    if after < 0:
        return {
            "hata": f"Stok sifirin altina dusmez. Urun: {match['name']} (ID {match['id']}), mevcut: {before}, delta: {delta}",
        }
    return {
        "product_id": match["id"],
        "ad": match["name"],
        "onceki_stok": before,
        "delta": delta,
        "yeni_stok": after,
        "neden": neden,
    }


@tool
def admin_urun_listesi(
    kategori: str | None = None,
    arama: str | None = None,
    limit: int = 120,
) -> dict:
    """Aktif tum urunleri (stok, fiyat, esik) listeler. Kategori veya isim aramasi opsiyonel."""
    lim = min(max(int(limit), 1), 200)
    rows = list_products(
        tenant_id=_tenant_id(),
        category=kategori,
        search=arama,
        limit=lim,
    )
    items = [
        {
            "id": r["id"],
            "ad": r["name"],
            "kategori": r["category"],
            "fiyat": r["price"],
            "stok": r["stock_quantity"],
            "stok_esigi": r["low_stock_threshold"],
        }
        for r in rows
    ]
    return {
        "mesaj": f"{len(items)} urun listelendi.",
        "urunler": items,
    }


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
def admin_stok_onay_iste(urun_adi: str, miktar: int, neden: str = "Stok girisi") -> dict:
    """Stok degisikligi icin onay talebi olusturur (DB yazmaz). Onay: admin_pending_uygula veya panel Onayla."""
    r = _resolve_stok_satir(urun_adi, int(miktar), neden)
    if r.get("hata"):
        return r
    ozet = (
        f"Urun #{r['product_id']} ({r['ad']}): stok {r['onceki_stok']} → {r['yeni_stok']} "
        f"(degisim {r['delta']:+d}). Neden: {r['neden']}."
    )
    payload = {
        "kind": "stok_single",
        "product_id": r["product_id"],
        "delta": r["delta"],
        "neden": r["neden"],
    }
    return _pending_response(ozet, payload)


class _StokGuncellemeKaydi(BaseModel):
    urun_adi: str = Field(description="Guncellenecek urunun adi veya fuzzy eslesen ifade")
    miktar: int = Field(description="Stok degisimi; pozitif artis, negatif azalis")
    neden: str = Field(default="Toplu stok guncelleme", description="Hareket nedeni")


class _AdminTopluStokOnayArgs(BaseModel):
    guncellemeler: list[_StokGuncellemeKaydi] = Field(
        description="Stok guncelleme listesi; her elemanda urun_adi ve miktar zorunlu"
    )


@tool(args_schema=_AdminTopluStokOnayArgs)
def admin_stok_toplu_onay_iste(guncellemeler: list[_StokGuncellemeKaydi]) -> dict:
    """Birden fazla urun icin stok onayi (tek token)."""
    satirlar: list[dict] = []
    hatalar: list[dict] = []
    for g in guncellemeler:
        d = g.model_dump() if hasattr(g, "model_dump") else g
        r = _resolve_stok_satir(
            str(d.get("urun_adi", "")),
            int(d.get("miktar", 0)),
            str(d.get("neden", "Toplu stok guncelleme")),
        )
        if r.get("hata"):
            hatalar.append(r)
        else:
            satirlar.append(r)
    if hatalar and not satirlar:
        return {
            "hata": "Hicbir satir uygulanamaz.",
            "hatalar": hatalar,
        }
    items = [
        {
            "product_id": s["product_id"],
            "delta": s["delta"],
            "neden": s["neden"],
        }
        for s in satirlar
    ]
    ozet_parts = [
        f"- #{s['product_id']} {s['ad']}: {s['onceki_stok']} → {s['yeni_stok']} ({s['delta']:+d})"
        for s in satirlar
    ]
    ozet = "Toplu stok guncellemesi:\n" + "\n".join(ozet_parts)
    if hatalar:
        ozet += f"\n\nUyari: {len(hatalar)} satir atlandi (hata)."
    payload = {"kind": "stok_bulk", "items": items}
    base = _pending_response(ozet, payload)
    if hatalar:
        base["uyari_hatalar"] = hatalar
    return base


@tool
def admin_siparis_listesi(durum: str | None = None, limit: int = 40) -> dict:
    """Belirli durumdaki veya son siparisleri listeler."""
    lim = min(max(int(limit), 1), 100)
    tid = _tenant_id()
    raw = (durum or "").strip() or None
    canon = _normalize_order_status_for_list(raw) if raw else None
    if raw and canon is None:
        return {
            "hata": f"Gecersiz durum: {durum!r}. Gecerli: {', '.join(sorted(_VALID_ORDER_STATUSES))}",
            "siparisler": [],
        }

    conn = get_connection()
    if canon:
        rows = conn.execute(
            """
            SELECT id, tracking_code, customer_name, customer_phone, status,
                   total_price, created_at, cargo_company, cargo_tracking_code
            FROM orders
            WHERE tenant_id = ? AND status = ?
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            (tid, canon, lim),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, tracking_code, customer_name, customer_phone, status,
                   total_price, created_at, cargo_company, cargo_tracking_code
            FROM orders
            WHERE tenant_id = ?
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            (tid, lim),
        ).fetchall()
    conn.close()

    items = [dict(r) for r in rows]
    filtre_txt = f"durum={canon}" if canon else "tum son siparisler"
    return {
        "mesaj": f"{len(items)} siparis listelendi ({filtre_txt}).",
        "durum_filtre": canon,
        "siparisler": items,
    }


@tool
def admin_siparis_onay_iste(
    siparis_no: int,
    yeni_durum: str,
    kargo_kodu: str | None = None,
    kargo_firmasi: str | None = None,
    siparis_notu: str | None = None,
) -> dict:
    """Siparis/kargo durum guncellemesi icin onay talebi (DB yazmaz)."""
    st = _normalize_siparis_guncelle_status(yeni_durum)
    if st is None:
        return {
            "hata": f"Gecersiz durum: {yeni_durum!r}. Gecerli: {', '.join(sorted(_VALID_ORDER_STATUSES))}",
        }
    o = get_order(int(siparis_no), tenant_id=_tenant_id())
    if not o:
        return {"hata": f"Siparis #{siparis_no} bulunamadi."}
    ozet = (
        f"Siparis #{siparis_no} ({o.get('customer_name')}): durum {o.get('status')} → {st}."
    )
    if kargo_kodu:
        ozet += f" Kargo kodu: {kargo_kodu}."
    if kargo_firmasi:
        ozet += f" Kargo firmasi: {kargo_firmasi}."
    if siparis_notu:
        ozet += f" Not eklenecek."
    payload = {
        "kind": "siparis_update",
        "siparis_no": int(siparis_no),
        "yeni_durum": st,
        "kargo_kodu": kargo_kodu,
        "kargo_firmasi": kargo_firmasi,
        "siparis_notu": siparis_notu,
    }
    return _pending_response(ozet, payload)


class _SiparisGuncellemeKaydi(BaseModel):
    siparis_no: int = Field(description="Siparis ID / numarasi")
    yeni_durum: str = Field(
        description="hazirlaniyor, kargoda, teslim_edildi, tamamlandi veya iptal"
    )
    kargo_kodu: str | None = Field(default=None, description="Kargo takip kodu (istege bagli)")
    kargo_firmasi: str | None = Field(default=None, description="Kargo firmasi (istege bagli)")
    siparis_notu: str | None = Field(default=None, description="Siparis notu (istege bagli)")


class _AdminTopluSiparisOnayArgs(BaseModel):
    guncellemeler: list[_SiparisGuncellemeKaydi] = Field(
        description="Siparis durum guncellemeleri listesi"
    )


@tool(args_schema=_AdminTopluSiparisOnayArgs)
def admin_siparis_toplu_onay_iste(guncellemeler: list[_SiparisGuncellemeKaydi]) -> dict:
    """Birden fazla siparis icin tek onay tokeni."""
    items: list[dict] = []
    hatalar: list[dict] = []
    for g in guncellemeler:
        d = g.model_dump() if hasattr(g, "model_dump") else g
        st = _normalize_siparis_guncelle_status(str(d.get("yeni_durum", "")))
        sid = int(d.get("siparis_no", 0))
        if st is None:
            hatalar.append({"hata": f"Siparis #{sid}: gecersiz durum {d.get('yeni_durum')!r}"})
            continue
        o = get_order(sid, tenant_id=_tenant_id())
        if not o:
            hatalar.append({"hata": f"Siparis #{sid} bulunamadi."})
            continue
        items.append(
            {
                "siparis_no": sid,
                "yeni_durum": st,
                "kargo_kodu": d.get("kargo_kodu"),
                "kargo_firmasi": d.get("kargo_firmasi"),
                "siparis_notu": d.get("siparis_notu"),
            }
        )
    if not items:
        return {"hata": "Uygulanabilir siparis yok.", "hatalar": hatalar}
    ozet = "Toplu siparis guncellemesi:\n" + "\n".join(
        f"- #{it['siparis_no']}: → {it['yeni_durum']}" for it in items
    )
    if hatalar:
        ozet += f"\n\nUyari: {len(hatalar)} satir atlandi."
    payload = {"kind": "siparis_bulk", "items": items}
    base = _pending_response(ozet, payload)
    if hatalar:
        base["uyari_hatalar"] = hatalar
    return base


@tool
def admin_siparis_sil_onay_iste(siparis_no: int) -> dict:
    """Siparis silme (stok iadesi) icin onay. Yalnizca hazirlaniyor veya kargoda."""
    oid = int(siparis_no)
    o = get_order(oid, tenant_id=_tenant_id())
    if not o:
        return {"hata": f"Siparis #{oid} bulunamadi."}
    if o["status"] not in ("hazırlanıyor", "kargoda"):
        return {
            "hata": (
                f"Siparis #{oid} silinemez (durum: {o['status']}). "
                "Yalnizca hazirlaniyor veya kargoda olanlar silinebilir."
            ),
        }
    ozet = (
        f"Siparis #{oid} silinecek (musteri: {o.get('customer_name')}, durum: {o['status']}). "
        "Kalemler stoka iade edilir."
    )
    return _pending_response(ozet, {"kind": "siparis_delete", "siparis_no": oid})


@tool
def admin_urun_ekle_onay_iste(
    isim: str,
    fiyat: float,
    stok: int,
    kategori: str | None = None,
    stok_esigi: int = 10,
) -> dict:
    """Yeni urun ekleme onayi (DB yazmaz)."""
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM products WHERE name = ? AND is_active = 1 AND tenant_id = ?",
        (isim, _tenant_id()),
    ).fetchone()
    conn.close()
    if existing:
        return {"hata": f"'{isim}' adinda urun zaten mevcut (ID: {existing['id']})."}
    ozet = f"Yeni urun: {isim}, fiyat {fiyat}, stok {stok}, esik {stok_esigi}, kategori: {kategori or '-'}"
    payload = {
        "kind": "urun_ekle",
        "isim": isim,
        "fiyat": float(fiyat),
        "stok": int(stok),
        "kategori": kategori,
        "stok_esigi": int(stok_esigi),
    }
    return _pending_response(ozet, payload)


@tool
def admin_urun_duzenle_onay_iste(
    urun_id: int,
    yeni_isim: str | None = None,
    kategori: str | None = None,
    fiyat: float | None = None,
    stok: int | None = None,
    stok_esigi: int | None = None,
) -> dict:
    """Urun alanlarini guncelleme onayi. Sadece verilen alanlar degisir."""
    p = get_product(int(urun_id), tenant_id=_tenant_id())
    if not p:
        return {"hata": f"Urun #{urun_id} bulunamadi."}
    patch: dict = {}
    if yeni_isim is not None:
        patch["name"] = yeni_isim
    if kategori is not None:
        patch["category"] = kategori
    if fiyat is not None:
        patch["price"] = float(fiyat)
    if stok is not None:
        patch["stock_quantity"] = int(stok)
    if stok_esigi is not None:
        patch["low_stock_threshold"] = int(stok_esigi)
    if not patch:
        return {"hata": "Guncellenecek alan belirtilmedi."}
    degisiklikler = []
    if "name" in patch:
        degisiklikler.append(f"isim: {p['name']!r} → {patch['name']!r}")
    if "category" in patch:
        degisiklikler.append(f"kategori: {p.get('category')} → {patch.get('category')}")
    if "price" in patch:
        degisiklikler.append(f"fiyat: {p['price']} → {patch['price']}")
    if "stock_quantity" in patch:
        degisiklikler.append(f"stok: {p['stock_quantity']} → {patch['stock_quantity']}")
    if "low_stock_threshold" in patch:
        degisiklikler.append(
            f"esik: {p['low_stock_threshold']} → {patch['low_stock_threshold']}"
        )
    ozet = f"Urun #{urun_id} ({p['name']}): " + "; ".join(degisiklikler)
    payload = {"kind": "urun_duzenle", "urun_id": int(urun_id), "patch": patch}
    return _pending_response(ozet, payload)


@tool
def admin_urun_sil_onay_iste(urun_id: int) -> dict:
    """Urunu pasife alma (soft delete) onayi."""
    p = get_product(int(urun_id), tenant_id=_tenant_id())
    if not p:
        return {"hata": f"Urun #{urun_id} bulunamadi."}
    ozet = f"Urun #{urun_id} ({p['name']}) pasife alinacak (satistan dusecek)."
    return _pending_response(ozet, {"kind": "urun_sil", "urun_id": int(urun_id)})


@tool
def admin_pending_uygula(onay_token: str) -> dict:
    """Kayitli onay tokenini uygular (DB yazar). Kullanici chatte onayladiginda cagrilir."""
    uid = _require_user_id()
    if uid is None:
        return {"hata": "Oturum baglami eksik."}
    rec = take_pending(onay_token.strip(), _tenant_id(), uid)
    if rec is None:
        return {"hata": "Gecersiz veya suresi dolmus onay. Yeniden onay isteyin."}
    return apply_pending_payload(rec.payload, _tenant_id())


@tool
def admin_bilet_listesi(sadece_acik: bool = True, limit: int = 40) -> dict:
    """Biletleri oncelik ve tarihe gore listeler."""
    lim = min(max(int(limit), 1), 100)
    tid = _tenant_id()
    conn = get_connection()
    if sadece_acik:
        rows = conn.execute(
            """
            SELECT id, type, title, status, priority, related_order_id, created_at
            FROM tickets
            WHERE tenant_id = ? AND status IN ('open', 'in_progress')
            ORDER BY
              CASE priority
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'normal' THEN 3
                WHEN 'low' THEN 4
                ELSE 5
              END,
              datetime(created_at) DESC
            LIMIT ?
            """,
            (tid, lim),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, type, title, status, priority, related_order_id, created_at
            FROM tickets
            WHERE tenant_id = ?
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            (tid, lim),
        ).fetchall()
    conn.close()

    items = [dict(r) for r in rows]
    return {
        "mesaj": f"{len(items)} bilet listelendi"
        + (" (yalnizca acik / uzerinde calisilan)." if sadece_acik else "."),
        "biletler": items,
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
    admin_urun_listesi,
    admin_urun_ara_fuzzy,
    admin_stok_onay_iste,
    admin_stok_toplu_onay_iste,
    admin_siparis_listesi,
    admin_siparis_onay_iste,
    admin_siparis_toplu_onay_iste,
    admin_siparis_sil_onay_iste,
    admin_urun_ekle_onay_iste,
    admin_urun_duzenle_onay_iste,
    admin_urun_sil_onay_iste,
    admin_pending_uygula,
    admin_bilet_listesi,
    admin_bilet_guncelle,
]
