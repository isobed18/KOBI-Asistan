"""
Telegram Bot — Musteri FSM (siparis, urun, sepet, iptal)
"""

import json
import re
import time
from io import BytesIO
from collections import defaultdict
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from agent.auth import (
    activate_scope,
    set_session_scope,
    validate_phone,
    validate_tracking_code,
)
from agent.guard import check_message
from integrations.channels.telegram_adapter import TelegramAdapter
from config import settings
from repositories.products import list_products, normalize_name
from repositories.tickets import (
    create_ticket as repo_create_ticket,
    has_open_telegram_order_request,
)
from tools.order_product_tools import musteri_siparisleri, siparis_sorgula
from services.visual_stock_ingestion import search_by_uploaded_image

telegram_app = None
adapter = TelegramAdapter()

TENANT_ID = 1
PRODUCTS_PAGE = 5

# ---------------------------------------------------------------------------
# Durumlar
# ---------------------------------------------------------------------------
S_MENU = "menu"
S_WAIT_ORDER_DETAIL = "wait_order_detail"
S_ORDER_NAME = "order_name"
S_ORDER_PHONE = "order_phone"
S_CANCEL_REF = "cancel_ref"
S_CANCEL_NAME = "cancel_name"
S_CANCEL_PHONE = "cancel_phone"

# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------
_rate: dict = defaultdict(list)
MAX_PER_MIN = 10
MAX_PER_HOUR = 40


def _rate_ok(uid: int):
    now = time.time()
    _rate[uid] = [t for t in _rate[uid] if now - t < 3600]
    per_min = sum(1 for t in _rate[uid] if now - t < 60)
    per_hour = len(_rate[uid])
    if per_min >= MAX_PER_MIN:
        return False, "Cok fazla istek. 1 dakika bekleyin."
    if per_hour >= MAX_PER_HOUR:
        return False, "Saatlik limit doldu. Daha sonra deneyin."
    _rate[uid].append(now)
    return True, ""


def _sess(update: Update) -> str:
    inbound = adapter.parse_update(update)
    return f"tg_{inbound.channel_user_id}"


def _ud(context) -> dict:
    d = context.user_data
    d.setdefault("state", S_MENU)
    d.setdefault("telefon", None)
    d.setdefault("takip_kodu", None)
    d.setdefault("cart", {})
    d.setdefault("product_page", 0)
    d.setdefault("last_visual_product_id", None)
    d.setdefault("pending_name", None)
    d.setdefault("cancel_order_id", None)
    d.setdefault("cancel_name", None)
    return d


def _normalize_phone(raw: str) -> str | None:
    s = re.sub(r"\s+", "", (raw or "").strip())
    m = re.fullmatch(r"(05\d{9})", s)
    return m.group(1) if m else None


def _phone_match(a: str | None, b: str | None) -> bool:
    da = "".join(c for c in (a or "") if c.isdigit())
    db = "".join(c for c in (b or "") if c.isdigit())
    return bool(da) and da == db


def _extract_sip(text: str) -> str | None:
    m = re.search(r"(SIP-[A-Z0-9]{6})", text, re.IGNORECASE)
    return m.group(1).upper() if m else None


def _extract_phone_token(text: str) -> str | None:
    m = re.search(r"(05\d{9})", text)
    return m.group(1) if m else None


def _set_scope_phone(sess: str, ud: dict, phone: str):
    ud["telefon"] = phone
    ud["takip_kodu"] = None
    set_session_scope(sess, telefon=phone)
    activate_scope(sess)


def _set_scope_sip(sess: str, ud: dict, code: str):
    ud["takip_kodu"] = code
    ud["telefon"] = None
    set_session_scope(sess, takip_kodu=code)
    activate_scope(sess)


def _sync_scope_from_ud(sess: str, ud: dict):
    """Session deposunu user_data ile esitler; siparis araclari icin zorunlu."""
    if ud.get("telefon"):
        set_session_scope(sess, telefon=ud["telefon"])
    elif ud.get("takip_kodu"):
        set_session_scope(sess, takip_kodu=ud["takip_kodu"])
    else:
        return
    activate_scope(sess)


def _has_scope(ud: dict) -> bool:
    return bool(ud.get("telefon") or ud.get("takip_kodu"))


def _product_stock(product_id: int) -> int:
    from database.db import get_connection

    conn = get_connection()
    row = conn.execute(
        """
        SELECT stock_quantity FROM products
        WHERE id = ? AND tenant_id = ? AND is_active = 1
        """,
        (product_id, TENANT_ID),
    ).fetchone()
    conn.close()
    return int(row["stock_quantity"]) if row else 0


def _product_detail(product_id: int) -> dict | None:
    from database.db import get_connection

    conn = get_connection()
    row = conn.execute(
        """
        SELECT id, name, category, price, stock_quantity, description, size_guide,
               ingredients, allergens, advisory_notes, image_url
        FROM products
        WHERE id = ? AND tenant_id = ? AND is_active = 1
        """,
        (product_id, TENANT_ID),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _fmt_visual_product(product: dict, score: float | None = None) -> str:
    lines = [
        "Gorselden en yakin urunu buldum:",
        f"#{product['id']} - {product['name']}",
        f"Kategori: {product.get('category') or 'Genel'}",
        f"Fiyat: {float(product.get('price') or 0):.2f} TL",
        f"Stok: {int(product.get('stock_quantity') or 0)}",
    ]
    if score is not None:
        lines.append(f"Benzerlik: %{round(score * 100)}")
    if product.get("size_guide"):
        lines.append(f"Beden notu: {product['size_guide']}")
    if product.get("description"):
        lines.append(f"Not: {product['description'][:220]}")
    lines.append("\nBunu mu istiyorsunuz?")
    return "\n".join(lines)


def _ticket_desc_lines_for_cart(ud: dict) -> str:
    cart = ud.get("cart") or {}
    if not cart:
        return ""
    from database.db import get_connection

    conn = get_connection()
    lines = []
    try:
        for k in sorted(cart.keys(), key=int):
            pid = int(k)
            qty = int(cart[k])
            row = conn.execute(
                "SELECT name, price FROM products WHERE id = ? AND tenant_id = ?",
                (pid, TENANT_ID),
            ).fetchone()
            if row:
                lines.append(
                    f"  • #{pid} — {row['name']} x{qty} — {row['price'] * qty:.2f} TL"
                )
            else:
                lines.append(f"  • #{pid} — (bulunamadi) x{qty}")
    finally:
        conn.close()
    return "\n".join(lines)


MENU_TEXT = (
    "Hosgeldiniz! Asagidaki menuden secim yapin.\n"
    "• Telefon (05XXXXXXXXX), SIP takip (SIP-XXXXXX) veya kargo takip kodunuzu yazarak da "
    "ilgili siparis ozetine ulasabilirsiniz."
)

MENU_KB = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("Siparislerim", callback_data="m:list"),
            InlineKeyboardButton("Siparis detayi", callback_data="m:detay"),
        ],
        [
            InlineKeyboardButton("Ürün Listesi", callback_data="m:urun_new"),
            InlineKeyboardButton("Sepetim", callback_data="cart"),
        ],
        [
            InlineKeyboardButton("Siparisi onayla", callback_data="chk"),
            InlineKeyboardButton("Iptal talebi", callback_data="m:iptal"),
        ],
    ]
)

BACK_KB = InlineKeyboardMarkup([[InlineKeyboardButton("Ana menu", callback_data="m:home")]])


async def _reply_text(target, text: str, kb=None):
    await target.reply_text(text, reply_markup=kb or BACK_KB)


async def _menu_message(update: Update, context, text=MENU_TEXT):
    ud = _ud(context)
    ud["state"] = S_MENU
    if update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=MENU_KB)
    else:
        await update.message.reply_text(text, reply_markup=MENU_KB)


def _fmt_orders(data: dict) -> str:
    if data.get("hata"):
        return f"Hata: {data['hata']}"
    if data.get("mesaj") and not data.get("siparisler"):
        return data["mesaj"]
    lines = [f"{data.get('siparis_sayisi', 0)} siparis:"]
    for s in data.get("siparisler", []):
        lines.append(
            f"• #{s['siparis_no']} ({s['takip_kodu']}) — {s['durum']} — {s.get('toplam', 0):.2f} TL"
        )
    return "\n".join(lines)


def _fmt_order_detail(data: dict) -> str:
    if data.get("hata"):
        return f"Hata: {data['hata']}"
    lines = [
        f"Siparis #{data.get('siparis_no')}",
        f"Takip: {data.get('takip_kodu')}",
        f"Musteri: {data.get('musteri')}",
        f"Durum: {data.get('durum_aciklamasi', data.get('durum'))}",
    ]
    if data.get("kargo_kodu"):
        lines.append(f"Kargo: {data['kargo_kodu']} ({data.get('kargo_firmasi', '')})")
    if data.get("urunler"):
        lines.append("Ürün listesi:")
        for u in data["urunler"]:
            lines.append(f"  • {u['urun']} x{u['adet']} — {u['fiyat']:.2f} TL")
    if data.get("toplam") is not None:
        lines.append(f"Toplam: {data['toplam']:.2f} TL")
    return "\n".join(lines)


def _cart_lines(ud: dict) -> tuple[str, dict[int, int]]:
    cart = ud.get("cart") or {}
    if not cart:
        return "Sepetiniz bos.", {}
    conn_items = []
    total = 0.0
    by_id: dict[int, int] = {}
    for k, qty in cart.items():
        pid = int(k)
        by_id[pid] = int(qty)
    from database.db import get_connection

    conn = get_connection()
    try:
        for pid, qty in sorted(by_id.items()):
            row = conn.execute(
                "SELECT name, price FROM products WHERE id = ? AND tenant_id = ? AND is_active = 1",
                (pid, TENANT_ID),
            ).fetchone()
            if not row:
                conn_items.append(f"• #{pid} — (bulunamadi) x{qty}")
                continue
            sub = row["price"] * qty
            total += sub
            conn_items.append(f"• #{pid} — {row['name']} x{qty} — {sub:.2f} TL")
    finally:
        conn.close()
    body = "Sepet:\n" + "\n".join(conn_items) + f"\n\nAra toplam: {total:.2f} TL"
    return body, by_id


def _cart_keyboard(ud: dict) -> InlineKeyboardMarkup:
    """Sepette + / - ile miktar (stok tavani urun listesi ve burada kontrol edilir)."""
    cart = ud.get("cart") or {}
    rows = []
    for k in sorted(cart.keys(), key=int):
        pid = int(k)
        qty = int(cart[k])
        # Uzun urun adi 3 sutunlu satirda kesilir; tam bilgi yukaridaki sepet metninde.
        rows.append(
            [
                InlineKeyboardButton("+", callback_data=f"a:{pid}"),
                InlineKeyboardButton(f"{qty} ad · #{pid}", callback_data="noop"),
                InlineKeyboardButton("−", callback_data=f"x:{pid}"),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton("Siparisi onayla", callback_data="chk"),
            InlineKeyboardButton("Sepeti bosalt", callback_data="clr"),
        ]
    )
    # Tek dugme = tam satir genisligi; uzun Turkce etiketler kesilmesin.
    rows.append([InlineKeyboardButton("Urun listesine don", callback_data="m:urun_ret")])
    rows.append([InlineKeyboardButton("Ana menu", callback_data="m:home")])
    return InlineKeyboardMarkup(rows)


async def _send_product_page(update: Update, context, page: int):
    ud = _ud(context)
    ud["product_page"] = page
    prods = list_products(
        tenant_id=TENANT_ID, limit=500, in_stock_only=True, order_by="id"
    )
    if not prods:
        t = update.callback_query.message if update.callback_query else update.message
        await t.reply_text("Stokta urun yok.", reply_markup=BACK_KB)
        return
    start = page * PRODUCTS_PAGE
    chunk = prods[start : start + PRODUCTS_PAGE]
    lines = [
        "Stoktaki urunler, urun numarasina gore sirali (sayfa basi 5). "
        "Fiyat TL; + ile sepete ekleyin, miktari Sepetim'den ayarlayin.",
    ]
    for p in chunk:
        sq = int(p.get("stock_quantity") or 0)
        lines.append(
            f"• #{p['id']} — {p['name']} — {p['price']:.2f} TL (stok: {sq})"
        )
    rows = []
    for p in chunk:
        short = p["name"][:26] + ("…" if len(p["name"]) > 26 else "")
        rows.append(
            [InlineKeyboardButton(f"+ {short}", callback_data=f"a:{p['id']}")]
        )
    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton("Onceki", callback_data=f"v:{page-1}"))
    if start + PRODUCTS_PAGE < len(prods):
        nav.append(InlineKeyboardButton("Sonraki", callback_data=f"v:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton("Sepetim", callback_data="cart"),
            InlineKeyboardButton("Ana menu", callback_data="m:home"),
        ]
    )
    kb = InlineKeyboardMarkup(rows)
    t = update.callback_query.message if update.callback_query else update.message
    await t.reply_text("\n".join(lines), reply_markup=kb)


async def _try_cargo_from_message(update: Update, context, text: str) -> bool:
    """Kargo takip kodu (orders.cargo_tracking_code) ile eslesen siparisi bul; scope kur."""
    t = (text or "").strip()
    if len(t) < 2:
        return False
    if _extract_phone_token(t):
        return False
    if _extract_sip(t):
        return False
    from database.db import get_connection

    conn = get_connection()
    row = conn.execute(
        """
        SELECT * FROM orders
        WHERE tenant_id = ?
          AND cargo_tracking_code IS NOT NULL
          AND TRIM(cargo_tracking_code) = ?
        LIMIT 1
        """,
        (TENANT_ID, t),
    ).fetchone()
    conn.close()
    if not row:
        return False
    od = dict(row)
    ud = _ud(context)
    sess = _sess(update)
    ph = (od.get("customer_phone") or "").strip()
    if ph:
        ud["telefon"] = ph
        ud["takip_kodu"] = None
        set_session_scope(sess, telefon=ph)
    elif od.get("tracking_code"):
        ud["takip_kodu"] = od["tracking_code"]
        ud["telefon"] = None
        set_session_scope(sess, takip_kodu=od["tracking_code"])
    else:
        return False
    activate_scope(sess)
    data = musteri_siparisleri.invoke({})
    await update.message.reply_text(
        f"Kargo kodu eslesti.\n\n{_fmt_orders(data)}",
        reply_markup=MENU_KB,
    )
    return True


async def _try_scope_from_message(update: Update, context, text: str) -> bool:
    """Telefon veya SIP ile scope kur; basariliysa True."""
    ud = _ud(context)
    sess = _sess(update)
    phone = _extract_phone_token(text)
    sip = _extract_sip(text)
    if phone and validate_phone(phone):
        _set_scope_phone(sess, ud, phone)
        _sync_scope_from_ud(sess, ud)
        data = musteri_siparisleri.invoke({})
        await update.message.reply_text(
            f"Telefon dogrulandi.\n\n{_fmt_orders(data)}", reply_markup=MENU_KB
        )
        return True
    if sip and validate_tracking_code(sip):
        _set_scope_sip(sess, ud, sip)
        _sync_scope_from_ud(sess, ud)
        data = musteri_siparisleri.invoke({})
        await update.message.reply_text(
            f"Takip kodu dogrulandi.\n\n{_fmt_orders(data)}", reply_markup=MENU_KB
        )
        return True
    if phone or sip:
        await update.message.reply_text(
            "Kayit bulunamadi. Telefon (05XXXXXXXXX) veya gecerli SIP-XXXXXX kullanin.",
            reply_markup=BACK_KB,
        )
        return True
    return False


async def start_command(update: Update, context):
    ud = _ud(context)
    ud["state"] = S_MENU
    ud["cart"] = {}
    ud["pending_name"] = None
    await update.message.reply_text("KOBİ musteri asistanina hosgeldiniz!", reply_markup=MENU_KB)


async def menu_command(update: Update, context):
    await _menu_message(update, context)


async def unified_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    ud = _ud(context)

    ok, msg = _rate_ok(update.effective_user.id)
    if not ok:
        await query.message.reply_text(msg)
        return

    if data == "noop":
        return

    if data == "m:home":
        ud["state"] = S_MENU
        await query.message.reply_text(MENU_TEXT, reply_markup=MENU_KB)
        return

    if data == "m:list":
        if not _has_scope(ud):
            ud["state"] = S_MENU
            await query.message.reply_text(
                "Siparislerinizi gormek icin telefon (05XXXXXXXXX) veya siparis numaranizi "
                "#XX seklinde yazin (ornek: #12 veya 12).",
                reply_markup=BACK_KB,
            )
            return
        sess = _sess(update)
        _sync_scope_from_ud(sess, ud)
        out = musteri_siparisleri.invoke({})
        await query.message.reply_text(_fmt_orders(out), reply_markup=MENU_KB)
        return

    if data == "m:detay":
        if not _has_scope(ud):
            await query.message.reply_text(
                "Once telefon veya takip kodu ile kimlik dogrulayin.",
                reply_markup=BACK_KB,
            )
            return
        ud["state"] = S_WAIT_ORDER_DETAIL
        await query.message.reply_text(
            "Kayitli telefon numaranizla eslesen siparis icin siparis numarasini "
            "#XX olarak yazin (ornek: #12 veya 12; yalnizca numara, baska metin eklemeyin).",
            reply_markup=BACK_KB,
        )
        return

    if data == "m:urun_new":
        ud["state"] = S_MENU
        ud["cart"] = {}
        ud["product_page"] = 0
        await _send_product_page(update, context, 0)
        return

    if data == "m:urun_ret":
        ud["state"] = S_MENU
        await _send_product_page(update, context, ud.get("product_page", 0))
        return

    if data.startswith("v:"):
        page = int(data.split(":")[1])
        await _send_product_page(update, context, page)
        return

    if data.startswith("a:"):
        pid = int(data.split(":")[1])
        cart = ud.setdefault("cart", {})
        stock = _product_stock(pid)
        cur = int(cart.get(str(pid), 0))
        if stock <= 0:
            await query.message.reply_text(
                f"Urun #{pid} stokta yok.", reply_markup=BACK_KB
            )
            return
        if cur + 1 > stock:
            await query.message.reply_text(
                f"Urun #{pid} icin en fazla {stock} adet ekleyebilirsiniz.",
                reply_markup=BACK_KB,
            )
            return
        cart[str(pid)] = cur + 1
        await query.message.reply_text(
            f"Urun #{pid} sepete eklendi ({cart[str(pid)]}/{stock}).",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Sepetim", callback_data="cart"),
                        InlineKeyboardButton("Ürün Listesi", callback_data="m:urun_ret"),
                    ],
                    [InlineKeyboardButton("Ana menu", callback_data="m:home")],
                ]
            ),
        )
        return

    if data.startswith("x:"):
        pid = int(data.split(":")[1])
        cart = ud.setdefault("cart", {})
        key = str(pid)
        if key in cart:
            cart[key] = int(cart[key]) - 1
            if cart[key] <= 0:
                del cart[key]
        body, _ = _cart_lines(ud)
        await query.message.reply_text(body, reply_markup=_cart_keyboard(ud))
        return

    if data == "cart":
        body, _ = _cart_lines(ud)
        await query.message.reply_text(body, reply_markup=_cart_keyboard(ud))
        return

    if data == "clr":
        ud["cart"] = {}
        await query.message.reply_text("Sepet bosaltildi.", reply_markup=MENU_KB)
        return

    if data == "chk":
        cart = ud.get("cart") or {}
        if not cart:
            await query.message.reply_text(
                "Sepet bos. Once urun ekleyin.", reply_markup=MENU_KB
            )
            return
        chat_uid = str(update.effective_chat.id)
        if has_open_telegram_order_request(TENANT_ID, chat_uid):
            await query.message.reply_text(
                "Zaten onay bekleyen bir siparis talebiniz var. "
                "Mudahale kaydi cozulene kadar yeni talep gonderemezsiniz.",
                reply_markup=MENU_KB,
            )
            return
        ud["state"] = S_ORDER_NAME
        await query.message.reply_text(
            "Siparis icin adinizi ve soyadinizi yazin:",
            reply_markup=BACK_KB,
        )
        return

    if data == "m:iptal":
        ud["state"] = S_CANCEL_REF
        ud["cancel_order_id"] = None
        ud["cancel_name"] = None
        await query.message.reply_text(
            "Iptal etmek istediginiz siparis numarasini veya SIP-XXXXXX kodunu yazin:",
            reply_markup=BACK_KB,
        )
        return


async def handle_message(update: Update, context):
    text = (update.message.text or "").strip()
    ud = _ud(context)
    sess = _sess(update)

    ok, msg = _rate_ok(update.effective_user.id)
    if not ok:
        await update.message.reply_text(msg)
        return

    police = check_message(text)
    if not police.is_safe:
        await update.message.reply_text(police.reason)
        return

    state = ud["state"]

    if state == S_MENU:
        low = normalize_name(text)
        if ud.get("last_visual_product_id") and any(
            key in low for key in ("beden", "size", "olcu", "olcu", "fit", "kac beden")
        ):
            product = _product_detail(int(ud["last_visual_product_id"]))
            if product and product.get("size_guide"):
                await update.message.reply_text(
                    f"{product['name']} icin beden rehberi:\n{product['size_guide']}\n\n"
                    "Net olcu icin boy/kilo veya kullandiginiz bedeni yazabilirsiniz; isletme gerekirse size donus yapar.",
                    reply_markup=MENU_KB,
                )
                return
            await update.message.reply_text(
                "Bu urun icin kayitli beden rehberi yok. Isterseniz sepete ekleyip isletmeden onay bekleyebilirsiniz.",
                reply_markup=MENU_KB,
            )
            return
        if await _try_scope_from_message(update, context, text):
            return
        if await _try_cargo_from_message(update, context, text):
            return

    if state == S_WAIT_ORDER_DETAIL:
        if not _has_scope(ud):
            await update.message.reply_text(
                "Once telefon, SIP veya kargo kodu ile kimlik dogrulayin.",
                reply_markup=BACK_KB,
            )
            return
        t = (text or "").strip().replace(" ", "")
        m = re.fullmatch(r"#?(\d{1,8})", t)
        if not m:
            await update.message.reply_text(
                "Siparis numarasini yalnizca #12 veya 12 seklinde yazin.",
                reply_markup=BACK_KB,
            )
            return
        params = {"siparis_no": int(m.group(1))}
        _sync_scope_from_ud(sess, ud)
        data = siparis_sorgula.invoke(params)
        await update.message.reply_text(
            _fmt_order_detail(data), reply_markup=MENU_KB
        )
        ud["state"] = S_MENU
        return

    if state == S_ORDER_NAME:
        if len(text) < 2:
            await update.message.reply_text("Lutfen gecerli bir ad girin.", reply_markup=BACK_KB)
            return
        ud["pending_name"] = text
        ud["state"] = S_ORDER_PHONE
        await update.message.reply_text(
            "Cep telefonunuzu yazin (05XXXXXXXXX):", reply_markup=BACK_KB
        )
        return

    if state == S_ORDER_PHONE:
        phone = _normalize_phone(text)
        if not phone:
            await update.message.reply_text(
                "Gecerli telefon: 05XXXXXXXXX", reply_markup=BACK_KB
            )
            return
        name = ud.get("pending_name") or ""
        cart = ud.get("cart") or {}
        chat_uid = str(update.effective_chat.id)
        if has_open_telegram_order_request(TENANT_ID, chat_uid):
            ud["state"] = S_MENU
            ud["pending_name"] = None
            await update.message.reply_text(
                "Zaten onay bekleyen bir talebiniz var.", reply_markup=MENU_KB
            )
            return
        items = [{"product_id": int(k), "quantity": int(v)} for k, v in cart.items()]
        for it in items:
            st = _product_stock(int(it["product_id"]))
            if int(it["quantity"]) > st:
                await update.message.reply_text(
                    f"Urun #{it['product_id']} icin stok yetersiz (max {st}). "
                    "Sepeti guncelleyin.",
                    reply_markup=MENU_KB,
                )
                return
        llm_payload = {
            "telegram_chat_id": chat_uid,
            "tenant_id": TENANT_ID,
            "items": items,
            "customer_name": name,
            "customer_phone": phone,
            "submitted_at": datetime.now().isoformat(timespec="seconds"),
            "notes": "Telegram talep",
        }
        desc_body = _ticket_desc_lines_for_cart(ud)
        _ = repo_create_ticket(
            payload={
                "type": "telegram_order_request",
                "title": f"Telegram siparis — {name}",
                "description": (
                    f"Musteri: {name}\nTel: {phone}\n{desc_body}\n"
                    f"(tg chat_id={chat_uid})"
                ),
                "priority": "high",
                "llm_content": json.dumps(llm_payload, ensure_ascii=False),
                "source_channel_user_id": chat_uid,
            },
            tenant_id=TENANT_ID,
            dedupe_key={
                "type": "telegram_order_request",
                "source_channel_user_id": chat_uid,
            },
        )
        ud["cart"] = {}
        ud["pending_name"] = None
        ud["state"] = S_MENU
        await update.message.reply_text(
            "Sipariş talebiniz alınmıştır, işletmenin onaylaması beklenmektedir. "
            "Siparişiniz onaylanınca geri dönüş yapılacaktır.",
            reply_markup=MENU_KB,
        )
        return

    if state == S_CANCEL_REF:
        cm = _extract_sip(text)
        nm = re.search(r"\b(\d{1,8})\b", text)
        from database.db import get_connection

        conn = get_connection()
        if nm and not cm:
            row = conn.execute(
                """
                SELECT id, customer_name, customer_phone, status
                FROM orders WHERE id = ? AND tenant_id = ?
                """,
                (int(nm.group(1)), TENANT_ID),
            ).fetchone()
        elif cm:
            row = conn.execute(
                """
                SELECT id, customer_name, customer_phone, status
                FROM orders WHERE tracking_code = ? AND tenant_id = ?
                """,
                (cm, TENANT_ID),
            ).fetchone()
        else:
            row = None
        conn.close()
        if not row:
            await update.message.reply_text(
                "Siparis bulunamadi. Tekrar deneyin.", reply_markup=BACK_KB
            )
            return
        status = row["status"] or ""
        if status in ("iptal", "teslim_edildi", "tamamlandi", "tamamlandı"):
            await update.message.reply_text(
                f"Bu siparis ({status}) iptal talebi icin uygun degil.",
                reply_markup=BACK_KB,
            )
            return
        ud["cancel_order_id"] = int(row["id"])
        ud["state"] = S_CANCEL_NAME
        await update.message.reply_text(
            "Guvenlik: sipariste kayitli ad soyad bilgisini aynen yazin:",
            reply_markup=BACK_KB,
        )
        return

    if state == S_CANCEL_NAME:
        ud["cancel_name"] = text
        ud["state"] = S_CANCEL_PHONE
        await update.message.reply_text(
            "Kayitli telefon numarasini yazin (05XXXXXXXXX):", reply_markup=BACK_KB
        )
        return

    if state == S_CANCEL_PHONE:
        phone = _normalize_phone(text)
        if not phone:
            await update.message.reply_text(
                "Gecerli telefon: 05XXXXXXXXX", reply_markup=BACK_KB
            )
            return
        oid = ud.get("cancel_order_id")
        from database.db import get_connection

        conn = get_connection()
        row = conn.execute(
            "SELECT customer_name, customer_phone FROM orders WHERE id = ? AND tenant_id = ?",
            (oid, TENANT_ID),
        ).fetchone()
        conn.close()
        if not row:
            await _menu_message(update, context, "Siparis bulunamadi.")
            return
        if not _phone_match(row["customer_phone"], phone):
            ud["state"] = S_MENU
            await update.message.reply_text(
                "Telefon bilgisi eslesmedi. Iptal talebi olusturulmadi.",
                reply_markup=MENU_KB,
            )
            return
        if normalize_name(ud.get("cancel_name") or "") != normalize_name(
            row["customer_name"] or ""
        ):
            ud["state"] = S_MENU
            await update.message.reply_text(
                "Isim bilgisi eslesmedi. Iptal talebi olusturulmadi.",
                reply_markup=MENU_KB,
            )
            return
        chat_uid = str(update.effective_chat.id)
        _ = repo_create_ticket(
            payload={
                "type": "cancellation_request",
                "title": f"Telegram iptal talebi — Siparis #{oid}",
                "description": (
                    f"Musteri Telegram uzerinden iptal talebinde bulundu. "
                    f"Siparis #{oid}. (tg chat_id={chat_uid})"
                ),
                "priority": "high",
                "related_order_id": oid,
                "source_channel_user_id": chat_uid,
            },
            tenant_id=TENANT_ID,
            dedupe_key={"type": "cancellation_request", "related_order_id": oid},
        )
        ud["state"] = S_MENU
        ud["cancel_order_id"] = None
        ud["cancel_name"] = None
        await update.message.reply_text(
            "İptal talebiniz alınmıştır, işletmenin onaylaması beklenmektedir. "
            "İptal işleminiz sonuçlandığında size bu sohbetten geri dönüş sağlanacaktır.",
            reply_markup=MENU_KB,
        )
        return

    if state == S_MENU:
        await update.message.reply_text(
            "İsterseniz aşağıdaki menü seçeneklerini kullanın ya da telefon numaranızı, "
            "SIP takip kodunuzu (SIP-XXXXXX) veya kargo takip kodunuzu gönderin.",
            reply_markup=MENU_KB,
        )
        return

    ud["state"] = S_MENU
    await update.message.reply_text("Ana menuye donuldu.", reply_markup=MENU_KB)


async def handle_photo(update: Update, context):
    ud = _ud(context)

    ok, msg = _rate_ok(update.effective_user.id)
    if not ok:
        await update.message.reply_text(msg)
        return

    if not update.message.photo:
        await update.message.reply_text("Gorsel bulunamadi.", reply_markup=MENU_KB)
        return

    await update.message.reply_text("Gorseli katalogda ariyorum...")
    photo = update.message.photo[-1]
    file = await photo.get_file()
    payload = await file.download_as_bytearray()
    out = search_by_uploaded_image(
        TENANT_ID,
        f"telegram-{photo.file_unique_id}.jpg",
        BytesIO(payload),
        "giyim",
    )
    results = out.get("results") or []
    if not results:
        await update.message.reply_text(
            "Bu gorsele benzeyen stokta urun bulamadim. Urun listesinden bakabilirsiniz.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Urun Listesi", callback_data="m:urun_new")],
                    [InlineKeyboardButton("Ana menu", callback_data="m:home")],
                ]
            ),
        )
        return

    top = results[0]
    product_id = int(top.get("product_id") or top.get("id"))
    product = _product_detail(product_id)
    if not product:
        await update.message.reply_text(
            "Benzer bir urun bulundu ama stok kaydi aktif degil. Urun listesinden devam edebilirsiniz.",
            reply_markup=MENU_KB,
        )
        return

    ud["state"] = S_MENU
    ud["last_visual_product_id"] = product_id
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Sepete ekle", callback_data=f"a:{product_id}"),
                InlineKeyboardButton("Urun Listesi", callback_data="m:urun_new"),
            ],
            [InlineKeyboardButton("Sepetim", callback_data="cart")],
        ]
    )
    await update.message.reply_text(_fmt_visual_product(product, top.get("score")), reply_markup=kb)


async def setup_telegram():
    global telegram_app
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ENABLED:
        print("[WARN] Telegram devre disi.")
        return

    telegram_app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("menu", menu_command))
    telegram_app.add_handler(CallbackQueryHandler(unified_callback))
    telegram_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(drop_pending_updates=True)
    print("[OK] Telegram musteri botu baslatildi.")


async def stop_telegram():
    global telegram_app
    if telegram_app:
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()
        print("[STOP] Telegram bot durduruldu.")
