"""
Admin Tools — İşletmeci için LLM destekli yönetim araçları
=============================================================
Müşteri auth gerekmez. Tüm ürün/sipariş/bilet verilerine tam erişim.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from difflib import SequenceMatcher
from langchain_core.tools import tool
from database.db import get_connection
from agent.tenant_context import get_tenant_id


# ---------------------------------------------------------------------------
# Yardımcı — Türkçe karakter normalleştirme & fuzzy arama
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Türkçe karakterleri ASCII'ye dönüştürür, küçük harfe çevirir."""
    return (
        text.upper()
        .replace('İ', 'I').replace('Ş', 'S').replace('Ğ', 'G')
        .replace('Ü', 'U').replace('Ö', 'O').replace('Ç', 'C')
        .lower()
        .strip()
    )


def _fuzzy_score(query: str, name: str) -> float:
    """
    Sorgu ile ürün adı arasındaki benzerlik skoru (0-1).
    Üç metrik karması: tam içerik eşleşmesi, kelime örtüşmesi, dizi benzerliği.
    """
    q = _normalize(query)
    n = _normalize(name)

    # Tam içerik eşleşmesi en yüksek öncelik
    if q == n:
        return 1.0
    if q in n or n in q:
        return 0.95

    # Kelime bazlı örtüşme (yazım hatalarına dayanıklı)
    q_words = q.split()
    n_words = n.split()
    if q_words:
        hits = 0
        for qw in q_words:
            for nw in n_words:
                # Kelime 4+ char ise prefix eşleşmesi yeterli
                if qw == nw:
                    hits += 1; break
                if len(qw) >= 4 and (nw.startswith(qw[:4]) or qw.startswith(nw[:4])):
                    hits += 0.85; break
                if len(qw) >= 3 and (qw in nw or nw in qw):
                    hits += 0.7; break
        word_score = hits / len(q_words)
    else:
        word_score = 0.0

    # Genel dizi benzerliği (Levenshtein'a yakın)
    seq_score = SequenceMatcher(None, q, n).ratio()

    return max(word_score * 0.88, seq_score * 0.72)


def _find_product(urun_adi: str, threshold: float = 0.42):
    """
    Fuzzy search ile aktif ürünleri bulur.
    Yazım hataları ve Türkçe karakter farklılıklarına dayanıklı.
    En iyi 5 eşleşmeyi döner.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, stock_quantity FROM products WHERE is_active = 1 AND tenant_id = ?",
        (get_tenant_id(),),
    ).fetchall()
    conn.close()

    scored = []
    for r in rows:
        s = _fuzzy_score(urun_adi, r["name"])
        if s >= threshold:
            scored.append((s, dict(r)))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:5]]


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
    conn.execute("UPDATE products SET stock_quantity = ? WHERE id = ? AND tenant_id = ?", (new_qty, r["id"], get_tenant_id()))
    conn.execute(
        "INSERT INTO stock_movements (tenant_id, product_id, delta, reason, before_qty, after_qty) VALUES (?,?,?,?,?,?)",
        (get_tenant_id(), r["id"], miktar, neden, r["stock_quantity"], new_qty),
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

def _deduct_stock_for_order(conn, siparis_no: int) -> list:
    """
    Sipariş kargoya verilirken ürün stoklarını düşürür.
    Her sipariş kalemi için stock_movements kaydı yazar.
    Stok yetersizse negatife düşmez — uyarı döner.
    """
    items = conn.execute(
        "SELECT oi.product_id, oi.quantity, p.name, p.stock_quantity "
        "FROM order_items oi JOIN products p ON p.id = oi.product_id "
        "JOIN orders o ON o.id = oi.order_id "
        "WHERE oi.order_id = ? AND o.tenant_id = ?",
        (siparis_no, get_tenant_id()),
    ).fetchall()

    warnings = []
    for item in items:
        before = item["stock_quantity"]
        after  = before - item["quantity"]
        if after < 0:
            warnings.append(
                f"{item['name']}: stok yetersiz (mevcut {before}, gereken {item['quantity']})"
            )
            after = 0  # sıfırda bırak, negatife düşürme
        conn.execute(
            "UPDATE products SET stock_quantity = ? WHERE id = ?",
            (after, item["product_id"]),
        )
        conn.execute(
            "INSERT INTO stock_movements "
            "(tenant_id, product_id, delta, reason, before_qty, after_qty) VALUES (?,?,?,?,?,?)",
            (get_tenant_id(), item["product_id"], -item["quantity"],
             f"Sipariş #{siparis_no} kargoya verildi", before, after),
        )
    return warnings


def _do_siparis_guncelle(siparis_no: int, yeni_durum: str,
                          kargo_kodu=None, kargo_firmasi=None, siparis_notu=None) -> dict:
    GECERLI = ("hazırlanıyor", "kargoda", "teslim_edildi", "iptal")
    if yeni_durum not in GECERLI:
        return {"hata": f"Geçersiz durum: '{yeni_durum}'. Geçerli: {list(GECERLI)}"}

    conn = get_connection()
    order = conn.execute(
        "SELECT id, status, customer_name FROM orders WHERE id = ? AND tenant_id = ?",
        (siparis_no, get_tenant_id()),
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

    params.append(get_tenant_id())
    conn.execute(f"UPDATE orders SET {', '.join(fields)} WHERE id = ? AND tenant_id = ?", params)

    # Kargoya geçişte stok otomatik düşür (sadece hazırlanıyor → kargoda)
    stok_uyarilari = []
    if yeni_durum == "kargoda" and order["status"] == "hazırlanıyor":
        stok_uyarilari = _deduct_stock_for_order(conn, siparis_no)

    conn.commit()
    conn.close()

    result = {
        "basari": True,
        "siparis_no": siparis_no,
        "musteri": order["customer_name"],
        "eski_durum": order["status"],
        "yeni_durum": yeni_durum,
        "kargo_kodu": kargo_kodu,
        "kargo_firmasi": kargo_firmasi,
    }
    if stok_uyarilari:
        result["stok_uyarilari"] = stok_uyarilari
    return result


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
        "SELECT id FROM products WHERE name = ? AND is_active = 1 AND tenant_id = ?",
        (isim, get_tenant_id()),
    ).fetchone()
    if existing:
        conn.close()
        return {"hata": f"'{isim}' adında ürün zaten mevcut (ID: {existing['id']})."}

    conn.execute(
        "INSERT INTO products (tenant_id, name, category, price, stock_quantity, low_stock_threshold) VALUES (?,?,?,?,?,?)",
        (get_tenant_id(), isim, kategori, fiyat, stok, stok_esigi),
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
        "SELECT id, title, status FROM tickets WHERE id = ? AND tenant_id = ?",
        (bilet_id, get_tenant_id()),
    ).fetchone()
    if not ticket:
        conn.close()
        return {"hata": f"Bilet #{bilet_id} bulunamadı."}

    ek_not = f"\n\nNot: {cozum_notu}" if cozum_notu else ""
    if yeni_durum == "resolved":
        conn.execute(
            "UPDATE tickets SET status=?, resolved_at=datetime('now','localtime'), description=description||? WHERE id=? AND tenant_id=?",
            (yeni_durum, ek_not, bilet_id, get_tenant_id()),
        )
    else:
        conn.execute(
            "UPDATE tickets SET status=?, description=description||? WHERE id=? AND tenant_id=?",
            (yeni_durum, ek_not, bilet_id, get_tenant_id()),
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
