"""
Admin Tools — İşletmeci için LLM destekli yönetim araçları
=============================================================
Müşteri auth gerekmez. Tüm ürün/sipariş/bilet verilerine tam erişim.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langchain_core.tools import tool
from database.db import get_connection


# ---------------------------------------------------------------------------
# Yardımcı — Ürün bul
# ---------------------------------------------------------------------------

def _find_product(urun_adi: str):
    """Ürün adına göre aktif ürünleri bulur. (name LIKE %...%)"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, stock_quantity FROM products WHERE name LIKE ? AND is_active = 1",
        (f"%{urun_adi}%",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _do_stok_guncelle(urun_adi: str, miktar: int, neden: str) -> dict:
    matches = _find_product(urun_adi)
    if not matches:
        return {"hata": f"'{urun_adi}' adında aktif ürün bulunamadı."}
    if len(matches) > 1:
        isimler = [r["name"] for r in matches]
        return {"hata": f"'{urun_adi}' için {len(matches)} ürün bulundu: {isimler}. Daha spesifik isim girin."}

    r = matches[0]
    new_qty = r["stock_quantity"] + miktar
    if new_qty < 0:
        return {"hata": f"Stok sıfırın altına düşemez. Mevcut: {r['stock_quantity']}, delta: {miktar}"}

    conn = get_connection()
    conn.execute("UPDATE products SET stock_quantity = ? WHERE id = ?", (new_qty, r["id"]))
    conn.execute(
        "INSERT INTO stock_movements (product_id, delta, reason, before_qty, after_qty) VALUES (?,?,?,?,?)",
        (r["id"], miktar, neden, r["stock_quantity"], new_qty),
    )
    conn.commit()
    conn.close()
    return {
        "basari": True,
        "urun": r["name"],
        "urun_id": r["id"],
        "onceki_stok": r["stock_quantity"],
        "yeni_stok": new_qty,
        "delta": miktar,
        "neden": neden,
    }


# ---------------------------------------------------------------------------
# Stok Araçları
# ---------------------------------------------------------------------------

@tool
def admin_stok_guncelle(urun_adi: str, miktar: int, neden: str = "Stok girişi") -> dict:
    """Ürün adına göre stok miktarını günceller ve hareket logu yazar.
    miktar pozitifse stok artar (giriş), negatifse azalır (çıkış).
    Örnek: urun_adi='zeytinyağı', miktar=50, neden='Kargo geldi'
    Admin kullanımı — müşteri auth gerekmez."""
    return _do_stok_guncelle(urun_adi, miktar, neden)


@tool
def admin_toplu_stok_guncelle(guncellemeler: list) -> dict:
    """Birden fazla ürün için tek seferde stok güncelleme yapar.
    guncellemeler formatı: [{"urun_adi": "Zeytinyağı", "miktar": 50, "neden": "Kargo"}, ...]
    Doğal dilde 'şunları ekle: zeytinyağı 50, domates 30' gibi komutlar için kullan.
    Admin kullanımı."""
    sonuclar = []
    for g in guncellemeler:
        sonuclar.append(_do_stok_guncelle(
            g.get("urun_adi", ""),
            int(g.get("miktar", 0)),
            g.get("neden", "Toplu giriş"),
        ))
    basarili = sum(1 for r in sonuclar if r.get("basari"))
    hatali   = len(sonuclar) - basarili
    return {
        "toplam": len(sonuclar),
        "basarili": basarili,
        "hatali": hatali,
        "detaylar": sonuclar,
    }


# ---------------------------------------------------------------------------
# Sipariş Araçları
# ---------------------------------------------------------------------------

def _do_siparis_guncelle(siparis_no: int, yeni_durum: str,
                          kargo_kodu=None, kargo_firmasi=None, siparis_notu=None) -> dict:
    GECERLI = ("hazırlanıyor", "kargoda", "teslim_edildi", "iptal")
    if yeni_durum not in GECERLI:
        return {"hata": f"Geçersiz durum: '{yeni_durum}'. Geçerli: {list(GECERLI)}"}

    conn = get_connection()
    order = conn.execute(
        "SELECT id, status, customer_name FROM orders WHERE id = ?", (siparis_no,)
    ).fetchone()
    if not order:
        conn.close()
        return {"hata": f"Sipariş #{siparis_no} bulunamadı."}

    fields = ["status = ?", "updated_at = datetime('now', 'localtime')"]
    params = [yeni_durum]
    if kargo_kodu:
        fields.append("cargo_tracking_code = ?"); params.append(kargo_kodu)
    if kargo_firmasi:
        fields.append("cargo_company = ?");       params.append(kargo_firmasi)
    if siparis_notu:
        fields.append("notes = ?");               params.append(siparis_notu)
    params.append(siparis_no)

    conn.execute(f"UPDATE orders SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return {
        "basari": True,
        "siparis_no": siparis_no,
        "musteri": order["customer_name"],
        "eski_durum": order["status"],
        "yeni_durum": yeni_durum,
        "kargo_kodu": kargo_kodu,
        "kargo_firmasi": kargo_firmasi,
    }


@tool
def admin_siparis_guncelle(
    siparis_no: int,
    yeni_durum: str,
    kargo_kodu: str = None,
    kargo_firmasi: str = None,
    siparis_notu: str = None,
) -> dict:
    """Sipariş durumunu günceller. Kargoya verirken kargo kodu ve firma da atanabilir.
    yeni_durum: hazırlanıyor | kargoda | teslim_edildi | iptal
    Örnek: siparis_no=5, yeni_durum='kargoda', kargo_kodu='TRK123456', kargo_firmasi='Aras'
    Admin kullanımı."""
    return _do_siparis_guncelle(siparis_no, yeni_durum, kargo_kodu, kargo_firmasi, siparis_notu)


@tool
def admin_toplu_siparis_guncelle(guncellemeler: list) -> dict:
    """Birden fazla siparişi tek seferde günceller.
    guncellemeler: [{"siparis_no": 5, "yeni_durum": "kargoda", "kargo_kodu": "TRK001", "kargo_firmasi": "Aras"}, ...]
    'Şu siparişleri kargoya verdim' gibi toplu komutlar için kullan.
    Admin kullanımı."""
    sonuclar = []
    for g in guncellemeler:
        sonuclar.append(_do_siparis_guncelle(
            int(g.get("siparis_no", 0)),
            g.get("yeni_durum", ""),
            g.get("kargo_kodu"),
            g.get("kargo_firmasi"),
            g.get("siparis_notu"),
        ))
    basarili = sum(1 for r in sonuclar if r.get("basari"))
    return {"toplam": len(sonuclar), "basarili": basarili, "detaylar": sonuclar}


# ---------------------------------------------------------------------------
# Ürün Araçları
# ---------------------------------------------------------------------------

@tool
def admin_urun_ekle(
    isim: str,
    fiyat: float,
    stok: int,
    kategori: str = None,
    stok_esigi: int = 10,
) -> dict:
    """Sisteme yeni ürün ekler.
    Örnek: isim='Çiçekyağı 1L', fiyat=45.0, stok=100, kategori='Gıda', stok_esigi=20
    Admin kullanımı."""
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM products WHERE name = ? AND is_active = 1", (isim,)
    ).fetchone()
    if existing:
        conn.close()
        return {"hata": f"'{isim}' adında ürün zaten mevcut (ID: {existing['id']})."}

    conn.execute(
        "INSERT INTO products (name, category, price, stock_quantity, low_stock_threshold) VALUES (?,?,?,?,?)",
        (isim, kategori, fiyat, stok, stok_esigi),
    )
    product_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return {
        "basari": True,
        "urun_id": product_id,
        "isim": isim,
        "fiyat": fiyat,
        "stok": stok,
        "kategori": kategori,
        "stok_esigi": stok_esigi,
    }


# ---------------------------------------------------------------------------
# Bilet Araçları
# ---------------------------------------------------------------------------

@tool
def admin_bilet_guncelle(
    bilet_id: int,
    yeni_durum: str,
    cozum_notu: str = None,
) -> dict:
    """Bilet durumunu günceller ve opsiyonel çözüm notu ekler.
    yeni_durum: open | in_progress | resolved
    Örnek: bilet_id=3, yeni_durum='resolved', cozum_notu='Müşteriye iade yapıldı'
    Admin kullanımı."""
    GECERLI = ("open", "in_progress", "resolved")
    if yeni_durum not in GECERLI:
        return {"hata": f"Geçersiz durum: '{yeni_durum}'. Geçerli: {list(GECERLI)}"}

    conn = get_connection()
    ticket = conn.execute(
        "SELECT id, title, status FROM tickets WHERE id = ?", (bilet_id,)
    ).fetchone()
    if not ticket:
        conn.close()
        return {"hata": f"Bilet #{bilet_id} bulunamadı."}

    ek_not = f"\n\nNot: {cozum_notu}" if cozum_notu else ""
    if yeni_durum == "resolved":
        conn.execute(
            "UPDATE tickets SET status=?, resolved_at=datetime('now','localtime'), description=description||? WHERE id=?",
            (yeni_durum, ek_not, bilet_id),
        )
    else:
        conn.execute(
            "UPDATE tickets SET status=?, description=description||? WHERE id=?",
            (yeni_durum, ek_not, bilet_id),
        )
    conn.commit()
    conn.close()
    return {
        "basari": True,
        "bilet_id": bilet_id,
        "baslik": ticket["title"],
        "eski_durum": ticket["status"],
        "yeni_durum": yeni_durum,
    }


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

ADMIN_TOOLS = [
    admin_stok_guncelle,
    admin_toplu_stok_guncelle,
    admin_siparis_guncelle,
    admin_toplu_siparis_guncelle,
    admin_urun_ekle,
    admin_bilet_guncelle,
]
