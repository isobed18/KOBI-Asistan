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
from agent.tenant_context import get_tenant_id
from agent.otp import create_otp_challenge, verify_otp_challenge
from repositories.products import search_products, search_products_by_visual_description
from repositories.tickets import create_ticket as repo_create_ticket


@tool
def siparis_sorgula(siparis_no: int = None, takip_kodu: str = None) -> dict:
    """Siparis numarasi VEYA takip kodu ile siparisin durumunu, kargo bilgisini ve urunlerini getirir.
    Musteri 'siparisim nerede?' dediginde bu tool kullanilir.
    takip_kodu SIP-XXXXXX formatindadir."""

    conn = get_connection()
    cursor = conn.cursor()

    # Takip kodu veya siparis no ile sorgula
    tenant_id = int(get_tenant_id() or 1)
    if takip_kodu:
        order = cursor.execute(
            "SELECT * FROM orders WHERE tracking_code = ? AND tenant_id = ?",
            (takip_kodu, tenant_id),
        ).fetchone()
    elif siparis_no:
        order = cursor.execute(
            "SELECT * FROM orders WHERE id = ? AND tenant_id = ?",
            (siparis_no, tenant_id),
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
            "SELECT id, tracking_code, status, total_price, created_at FROM orders WHERE customer_phone = ? AND tenant_id = ? ORDER BY created_at DESC",
            (scope["telefon"], int(get_tenant_id() or 1)),
        ).fetchall()
    elif scope.get("takip_kodu"):
        rows = cursor.execute(
            "SELECT id, tracking_code, status, total_price, created_at FROM orders WHERE tracking_code = ? AND tenant_id = ?",
            (scope["takip_kodu"], int(get_tenant_id() or 1)),
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

    rows = search_products(urun_adi, tenant_id=int(get_tenant_id() or 1), threshold=0.25, limit=8)

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
def urun_danismani(
    urun_adi: str,
    soru: str,
    musteri_olculeri: str = "",
    alerjiler: str = "",
    kullanim_amaci: str = "",
) -> dict:
    """Urun detaylarina gore musteriye yaratici ama guvenli danismanlik verir.

    Beden/olcu, alerjen, icerik, kullanim amaci, hediye onerisi, kombin/eslesme
    gibi klasik stok sorgusundan daha nitelikli sorularda kullan.

    Ornekler:
    - "Keten gomlek hangi bedeni bana olur? Gogsum 101 cm."
    - "Cevize alerjim var, bu urun sorun olur mu?"
    - "Bal polen hassasiyetinde uygun mu?"
    """
    matches = search_products(urun_adi, tenant_id=int(get_tenant_id() or 1), threshold=0.25, limit=5)
    if not matches:
        return {
            "sonuc": "bulunamadi",
            "mesaj": f"'{urun_adi}' icin urun bulunamadi.",
        }

    strong = [m for m in matches if m.get("match_score", 0) >= 0.78]
    product = strong[0] if len(strong) == 1 else matches[0]
    alternatives = [
        {"id": m["id"], "ad": m["name"], "skor": m.get("match_score")}
        for m in matches[1:4]
    ]

    metadata = {
        "description": product.get("description"),
        "ingredients": product.get("ingredients"),
        "allergens": product.get("allergens"),
        "size_guide": product.get("size_guide"),
        "advisory_notes": product.get("advisory_notes"),
    }


@tool
def urun_gorsel_ara(gorsel_aciklamasi: str, kategori: str = "") -> dict:
    """Musterinin fotografinda veya tarifinde gordugu urune benzer katalog urunlerini bulur.

    Bu tool dusuk maliyetli demo/MVP yaklasimidir: gercek goruntu embedding'i yerine
    gorselin kisa metin aciklamasi ve urunlerin visual_keywords alanini eslestirir.
    Telegramda musteri foto attiginda vision modeli varsa once fotograf metne
    cevrilebilir; yoksa bot musteriden kisa tarif isteyebilir.
    """
    rows = search_products_by_visual_description(
        gorsel_aciklamasi,
        tenant_id=int(get_tenant_id() or 1),
        category=kategori or None,
        limit=5,
    )
    if not rows:
        return {
            "sonuc": "bulunamadi",
            "mesaj": "Bu gorsel/tarif ile eslesen urun bulamadim. Daha net renk, kalip veya kategori tarifi isteyin.",
        }
    return {
        "sonuc": "bulundu",
        "sorgu": gorsel_aciklamasi,
        "urunler": [
            {
                "id": r["id"],
                "ad": r["name"],
                "kategori": r.get("category"),
                "fiyat": r.get("price"),
                "stok": r.get("stock_quantity"),
                "gorsel": r.get("image_url"),
                "skor": r.get("visual_match_score"),
                "not": r.get("advisory_notes"),
            }
            for r in rows
        ],
        "maliyet_notu": "Bu arama LLM/vision maliyeti olmadan katalog anahtar kelimeleriyle yapildi.",
    }
    missing = [k for k, v in metadata.items() if not v]
    q = f"{soru} {musteri_olculeri} {alerjiler} {kullanim_amaci}".lower()
    is_allergy = any(w in q for w in ("alerji", "alerjen", "gluten", "laktoz", "fistik", "findik", "ceviz", "sut", "yumurta"))
    is_size = any(w in q for w in ("beden", "olcu", "ölçü", "gogus", "bel", "omuz", "boy", "kilo", "size"))

    guidance: list[str] = []
    if is_size:
        if product.get("size_guide"):
            guidance.append("Beden cevabini size_guide alanina dayanarak ver; olcu eksikse net olcu iste.")
        else:
            guidance.append("Bu urun icin beden rehberi girilmemis; kesin beden soyleme, isletmeden beden tablosu istenmesini oner.")
    if is_allergy:
        if product.get("allergens") or product.get("ingredients"):
            guidance.append("Alerjen cevabini ingredients/allergens alanina dayandir; kesin tibbi guvence verme.")
        else:
            guidance.append("Icerik/alerjen bilgisi yoksa urunu onermeden once isletmeden dogrulama iste.")
    if not guidance:
        guidance.append("Urun detaylarina gore kisa, yardimci ve satisa donuk bir danismanlik cevabi ver.")

    return {
        "sonuc": "bulundu",
        "urun": {
            "id": product["id"],
            "ad": product["name"],
            "kategori": product.get("category"),
            "fiyat": product.get("price"),
            "stok": product.get("stock_quantity"),
            **metadata,
        },
        "musteri_sorusu": soru,
        "musteri_olculeri": musteri_olculeri,
        "musteri_alerjileri": alerjiler,
        "kullanim_amaci": kullanim_amaci,
        "alternatif_eslesmeler": alternatives,
        "eksik_detaylar": missing,
        "cevap_rehberi": guidance,
        "guvenlik_notu": (
            "Alerjen/uygunluk cevaplari tibbi tavsiye degildir. Risk varsa musteri doktora veya urun etiketine yonlendirilmeli."
            if is_allergy else None
        ),
    }


@tool
def siparis_iptal_otp_gonder(siparis_no: int) -> dict:
    """Siparis iptali gibi kritik aksiyonlar icin OTP baslatir.

    Musteri once telefon/takip kodu ile yetkilendirilmis olmalidir. Bu tool
    sadece OTP uretir ve mumkunse aktif Telegram kanalina gonderir. OTP
    dogrulanmadan cancellation_request bileti acilmaz.
    """
    conn = get_connection()
    order = conn.execute(
        "SELECT * FROM orders WHERE id = ? AND tenant_id = ?",
        (siparis_no, int(get_tenant_id() or 1)),
    ).fetchone()
    conn.close()
    if not order:
        return {"hata": f"Siparis #{siparis_no} bulunamadi."}

    allowed, reason = check_order_access(dict(order))
    if not allowed:
        return {"hata": reason}

    try:
        from agent.state_runtime import get_channel_context
        channel, channel_user_id = get_channel_context()
    except Exception:
        channel, channel_user_id = None, None

    challenge = create_otp_challenge(
        order_id=siparis_no,
        action="cancel_order",
        channel=channel,
        channel_user_id=channel_user_id,
        tenant_id=int(get_tenant_id() or 1),
    )

    sent = False
    if channel == "telegram" and channel_user_id:
        try:
            from integrations.notifier import send_customer_telegram_message

            send_customer_telegram_message(
                channel_user_id,
                f"Siparis #{siparis_no} iptal dogrulama kodunuz: {challenge['code']}. Kod 10 dakika gecerlidir.",
            )
            sent = True
        except Exception:
            sent = False

    return {
        "basari": True,
        "siparis_no": siparis_no,
        "otp_gonderildi": sent,
        "kanal": channel,
        "mesaj": "Iptal icin 6 haneli OTP kodu gerekli. Kodu paylastiktan sonra iptal talebi insan incelemesine acilir.",
        "debug_otp": challenge["code"] if not sent else None,
    }


@tool
def siparis_iptal_otp_dogrula_ve_bilet_ac(siparis_no: int, otp_kodu: str, iptal_nedeni: str = "") -> dict:
    """OTP dogrulandiysa siparis iptal talebi icin human-review ticket acar."""
    verified = verify_otp_challenge(
        order_id=siparis_no,
        action="cancel_order",
        code=otp_kodu,
        tenant_id=int(get_tenant_id() or 1),
    )
    if not verified.get("ok"):
        return verified

    ticket_id = repo_create_ticket(
        {
            "type": "cancellation_request",
            "title": f"Siparis #{siparis_no} iptal talebi",
            "description": iptal_nedeni or "Musteri OTP ile dogrulanmis iptal talebi olusturdu.",
            "priority": "high",
            "related_order_id": siparis_no,
        },
        tenant_id=int(get_tenant_id() or 1),
        dedupe_key={"type": "cancellation_request", "related_order_id": siparis_no},
    )
    return {
        "basari": True,
        "bilet_id": ticket_id,
        "mesaj": f"OTP dogrulandi. Iptal talebiniz #{ticket_id} numarali bilet olarak insan incelemesine alindi.",
    }


@tool
def kritik_stok_listesi(tenant_id: int | None = None) -> dict:
    """Stok seviyesi kritik esigin altina dusmus tum urunleri listeler.
    Yonetici stok durumu sordugunda veya uyari gerektiginde kullanilir."""

    tid = int(tenant_id) if tenant_id is not None else int(get_tenant_id() or 1)

    conn = get_connection()
    cursor = conn.cursor()

    rows = cursor.execute("""
        SELECT id, name, category, stock_quantity, low_stock_threshold
        FROM products
        WHERE stock_quantity <= low_stock_threshold AND is_active = 1 AND tenant_id = ?
        ORDER BY stock_quantity ASC
    """, (tid,)).fetchall()

    conn.close()

    if not rows:
        return {"tenant_id": tid, "mesaj": "Tum urunler yeterli stok seviyesinde.", "urunler": []}

    return {
        "tenant_id": tid,
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

    if type == "cancellation_request":
        return {
            "hata": "Siparis iptali icin once siparis_iptal_otp_gonder, sonra siparis_iptal_otp_dogrula_ve_bilet_ac tool'u kullanilmalidir.",
            "otp_gerekli": True,
        }

    ticket_id = repo_create_ticket(
        {
            "type": type,
            "title": title,
            "description": description,
            "priority": priority,
            "related_order_id": related_order_id,
        },
        tenant_id=int(get_tenant_id() or 1),
    )

    return {
        "bilet_id": ticket_id,
        "mesaj": f"Talebiniz #{ticket_id} numaralı bilet olarak kaydedildi. Ekibimiz en kısa sürede sizinle iletişime geçecek.",
        "tip": type,
        "oncelik": priority,
    }


def _fmt_try_tr(n: float) -> str:
    """Turkce binlik ayraci: 174149.61 -> 174.149,61"""
    neg = n < 0
    x = abs(float(n))
    whole, frac = f"{x:.2f}".split(".")
    parts: list[str] = []
    while whole:
        parts.append(whole[-3:])
        whole = whole[:-3]
    whole_g = ".".join(reversed(parts))
    s = f"{whole_g},{frac}"
    return ("-" if neg else "") + s


@tool
def gunluk_ozet(tenant_id: int | None = None) -> dict:
    """Bugunku (yerel tarih) siparis sayisi, durum dagilimi, bugunku ciro ve guncel kritik stok.

    Sadece bugun `created_at` tarihli siparisler sayilir; gelir iptaller haric toplam tutardir.
    Yonetici 'bugunku ozet' dediginde bu tool kullanilir."""

    from datetime import date

    tid = int(tenant_id) if tenant_id is not None else int(get_tenant_id() or 1)
    bugun = date.today().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    rows = cursor.execute(
        """
        SELECT status,
               COUNT(*) AS c,
               COALESCE(SUM(CASE WHEN status != 'iptal' THEN total_price ELSE 0 END), 0) AS rev
        FROM orders
        WHERE tenant_id = ? AND date(created_at) = date('now', 'localtime')
        GROUP BY status
        """,
        (tid,),
    ).fetchall()

    by_status: dict[str, int] = {}
    gelir_bugun = 0.0
    siparis_bugun = 0
    for r in rows:
        s = r["status"]
        c = int(r["c"] or 0)
        rev = float(r["rev"] or 0)
        by_status[s] = c
        siparis_bugun += c
        gelir_bugun += rev

    kritik = cursor.execute("""
        SELECT name, stock_quantity, low_stock_threshold FROM products
        WHERE stock_quantity <= low_stock_threshold AND is_active = 1 AND tenant_id = ?
        ORDER BY stock_quantity ASC
    """, (tid,)).fetchall()

    conn.close()

    durum_parts = [f"{d}: {adet}" for d, adet in sorted(by_status.items()) if adet > 0]
    durum_str = ", ".join(durum_parts) if durum_parts else "bugün yeni sipariş kaydı yok"

    gelir_fmt = _fmt_try_tr(gelir_bugun)
    ozet_metin = (
        f"**Bugün ({bugun})** oluşturulan **{siparis_bugun}** sipariş var. "
        f"**Bugünkü ciro** (iptaller hariç): **{gelir_fmt} TL**. "
        f"Durumlara göre: {durum_str}. "
        f"**{len(kritik)}** ürün şu an kritik stok seviyesinde."
    )

    return {
        "tenant_id": tid,
        "bugun_tarihi": bugun,
        "siparis_sayisi_bugun": siparis_bugun,
        "gelir_bugun_try": round(gelir_bugun, 2),
        "durum_dagilimi_bugun": by_status,
        # Geriye donuk alanlar: artik *bugunun* siparis/ cirosu anlamina gelir
        "toplam_siparis": siparis_bugun,
        "durum_dagilimi": by_status,
        "toplam_gelir": round(gelir_bugun, 2),
        "kritik_stok_sayisi": len(kritik),
        "kritik_urunler": [r["name"] for r in kritik],
        "kritik_urunler_detay": [dict(r) for r in kritik],
        "ozet_metin": ozet_metin,
    }
