"""
AI Agent Tool Fonksiyonlari — Auth-Aware
==========================================
Tum siparis sorgulari musteri scope'una gore kisitlanir.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langchain_core.tools import tool
from database.db import get_connection
from agent.auth import get_active_scope, check_order_access, get_customer_orders_filter


@tool
def siparis_sorgula(siparis_no: int = None, takip_kodu: str = None) -> dict:
    """Siparis numarasi VEYA takip kodu ile siparisin durumunu, kargo bilgisini ve urunlerini getirir.
    Musteri 'siparisim nerede?' dediginde bu tool kullanilir.
    takip_kodu SIP-XXXXXX formatindadir."""

    conn = get_connection()
    cursor = conn.cursor()

    # Takip kodu veya siparis no ile sorgula
    if takip_kodu:
        order = cursor.execute(
            "SELECT * FROM orders WHERE tracking_code = ?", (takip_kodu,)
        ).fetchone()
    elif siparis_no:
        order = cursor.execute(
            "SELECT * FROM orders WHERE id = ?", (siparis_no,)
        ).fetchone()
    else:
        conn.close()
        return {"hata": "Siparis numarasi veya takip kodu gerekli."}

    if not order:
        conn.close()
        return {"hata": f"Siparis bulunamadi."}

    # Yetki kontrolu
    order_dict = dict(order)
    is_allowed, reason = check_order_access(order_dict)
    if not is_allowed:
        conn.close()
        return {"hata": reason}

    items = cursor.execute("""
        SELECT p.name, oi.quantity, oi.unit_price
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ?
    """, (order["id"],)).fetchall()

    conn.close()

    durum_mesaji = {
        "hazırlanıyor": "Siparisiniz hazirlaniyor, henuz kargoya verilmedi.",
        "kargoda":      f"Siparisiniz kargoda! Takip kodu: {order['cargo_tracking_code']} ({order['cargo_company']})",
        "teslim_edildi": "Siparisiniz teslim edildi.",
        "iptal":        "Bu siparis iptal edilmistir."
    }

    return {
        "siparis_no": order["id"],
        "takip_kodu": order["tracking_code"],
        "musteri": order["customer_name"],
        "durum": order["status"],
        "durum_aciklamasi": durum_mesaji.get(order["status"], "Bilinmeyen durum"),
        "kargo_kodu": order["cargo_tracking_code"],
        "kargo_firmasi": order["cargo_company"],
        "urunler": [
            {"urun": i["name"], "adet": i["quantity"], "fiyat": i["unit_price"]}
            for i in items
        ],
        "toplam": order["total_price"],
        "tarih": order["created_at"]
    }


@tool
def musteri_siparisleri() -> dict:
    """Mevcut musterinin tum siparislerini listeler.
    Musteri telefon numarasi ile dogrulanmissa, sadece o musterinin siparislerini getirir.
    Musteri 'siparislerim neler?' veya 'tum siparislerimi goster' dediginde kullanilir."""

    scope = get_active_scope()
    conn = get_connection()
    cursor = conn.cursor()

    if scope.get("telefon"):
        rows = cursor.execute(
            "SELECT id, tracking_code, status, total_price, created_at FROM orders WHERE customer_phone = ? ORDER BY created_at DESC",
            (scope["telefon"],)
        ).fetchall()
    elif scope.get("takip_kodu"):
        rows = cursor.execute(
            "SELECT id, tracking_code, status, total_price, created_at FROM orders WHERE tracking_code = ?",
            (scope["takip_kodu"],)
        ).fetchall()
    else:
        conn.close()
        return {"hata": "Siparislerinizi gorebilmem icin telefon numaraniz veya takip kodunuz gerekli."}

    conn.close()

    if not rows:
        return {"mesaj": "Kayitli siparisiniz bulunamadi."}

    return {
        "siparis_sayisi": len(rows),
        "siparisler": [
            {
                "siparis_no": r["id"],
                "takip_kodu": r["tracking_code"],
                "durum": r["status"],
                "toplam": r["total_price"],
                "tarih": r["created_at"]
            }
            for r in rows
        ]
    }


@tool
def urun_stok_kontrol(urun_adi: str) -> dict:
    """Urun adina gore stok durumunu, fiyatini ve mevcut adedini kontrol eder.
    Musteri 'bu urun var mi?' veya 'fiyati ne?' dediginde bu tool kullanilir."""

    conn = get_connection()
    cursor = conn.cursor()

    rows = cursor.execute("""
        SELECT id, name, category, price, stock_quantity, low_stock_threshold
        FROM products
        WHERE name LIKE ? AND is_active = 1
    """, (f"%{urun_adi}%",)).fetchall()

    conn.close()

    if not rows:
        return {"sonuc": "bulunamadi", "mesaj": f"'{urun_adi}' adinda urun bulunamadi."}

    urunler = []
    for r in rows:
        stok_durumu = "mevcut" if r["stock_quantity"] > r["low_stock_threshold"] else \
                      "sinirli stok" if r["stock_quantity"] > 0 else "tukendi"
        urunler.append({
            "id": r["id"],
            "ad": r["name"],
            "kategori": r["category"],
            "fiyat": r["price"],
            "stok_durumu": stok_durumu,
            "adet": r["stock_quantity"]
        })

    return {"sonuc": "bulundu", "urunler": urunler}


@tool
def kritik_stok_listesi() -> dict:
    """Stok seviyesi kritik esigin altina dusmus tum urunleri listeler.
    Yonetici stok durumu sordugunda veya uyari gerektiginde kullanilir."""

    conn = get_connection()
    cursor = conn.cursor()

    rows = cursor.execute("""
        SELECT id, name, category, stock_quantity, low_stock_threshold
        FROM products
        WHERE stock_quantity <= low_stock_threshold AND is_active = 1
        ORDER BY stock_quantity ASC
    """).fetchall()

    conn.close()

    if not rows:
        return {"mesaj": "Tum urunler yeterli stok seviyesinde.", "urunler": []}

    return {
        "mesaj": f"{len(rows)} urun kritik stok seviyesinde!",
        "urunler": [dict(r) for r in rows]
    }


@tool
def create_ticket(
    type: str,
    title: str,
    description: str,
    priority: str = "normal",
    related_order_id: int = None,
) -> dict:
    """İnsan incelemesi gerektiren durumlarda bilet oluşturur.
    Müşteri sipariş iptali, teslimat şikayeti, iade talebi veya başka bir escalation gerektiğinde kullanılır.
    type değerleri: cancellation_request | complaint | refund_request | other
    priority değerleri: low | normal | high | critical"""

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO tickets (type, title, description, priority, related_order_id)
        VALUES (?,?,?,?,?)
    """, (type, title, description, priority, related_order_id))
    ticket_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "bilet_id": ticket_id,
        "mesaj": f"Talebiniz #{ticket_id} numaralı bilet olarak kaydedildi. Ekibimiz en kısa sürede sizinle iletişime geçecek.",
        "tip": type,
        "oncelik": priority,
    }


@tool
def gunluk_ozet() -> dict:
    """Gunluk siparis durumu, gelir ve kritik stok ozetini getirir.
    Yonetici 'bugunku durum nedir?' dediginde bu tool kullanilir."""

    conn = get_connection()
    cursor = conn.cursor()

    siparisler = cursor.execute("SELECT status, total_price FROM orders").fetchall()
    by_status = {}
    gelir = 0.0
    for s in siparisler:
        by_status[s["status"]] = by_status.get(s["status"], 0) + 1
        if s["total_price"] and s["status"] not in ("iptal",):
            gelir += s["total_price"]

    kritik = cursor.execute("""
        SELECT name, stock_quantity FROM products
        WHERE stock_quantity <= low_stock_threshold AND is_active = 1
    """).fetchall()

    conn.close()

    return {
        "toplam_siparis": len(siparisler),
        "durum_dagilimi": by_status,
        "toplam_gelir": gelir,
        "kritik_stok_sayisi": len(kritik),
        "kritik_urunler": [r["name"] for r in kritik],
        "ozet_metin": (
            f"Toplam {len(siparisler)} siparis var. "
            f"{by_status.get('hazırlanıyor', 0)} siparis hazirlaniyor, "
            f"{by_status.get('kargoda', 0)} siparis kargoda. "
            f"{len(kritik)} urun kritik stok seviyesinde."
        )
    }
