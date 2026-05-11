"""
Telegram Bot - Interaktif Menu + State Machine + Rate Limiting
"""

import re
import time
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from langchain_core.messages import HumanMessage

from agent.graph import agent_graph
from agent.guard import check_message
from agent.auth import (
    set_session_scope,
    activate_scope,
    validate_phone,
    validate_tracking_code,
)
from agent.intent_classifier import classify, fast_response, IntentResult
from integrations.channels.telegram_adapter import TelegramAdapter
from config import settings

telegram_app = None
adapter = TelegramAdapter()

# ---------------------------------------------------------------------------
# Durum Sabitleri
# ---------------------------------------------------------------------------
S_MENU          = "menu"
S_WAITING_PHONE = "waiting_phone"
S_WAITING_ORDER = "waiting_order"
S_WAITING_PROD  = "waiting_product"
S_WAITING_CANCEL= "waiting_cancel"
S_WAITING_OTP   = "waiting_otp"    # OTP dogrulama bekleniyor
S_FREE_CHAT     = "free_chat"

# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------
_rate: dict = defaultdict(list)
MAX_PER_MIN  = 10
MAX_PER_HOUR = 40

def _rate_ok(uid: int):
    now = time.time()
    _rate[uid] = [t for t in _rate[uid] if now - t < 3600]
    per_min  = sum(1 for t in _rate[uid] if now - t < 60)
    per_hour = len(_rate[uid])
    if per_min  >= MAX_PER_MIN:
        return False, "Cok fazla istek. 1 dakika bekleyin."
    if per_hour >= MAX_PER_HOUR:
        return False, "Saatlik limit doldu. Daha sonra deneyin."
    _rate[uid].append(now)
    return True, ""

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
MENU_TEXT = (
    "Hosgeldiniz! Ne yapmak istersiniz?\n"
    "Asagidaki seceneklerden birini secin veya dogrudan yazin."
)

MENU_KB = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("Siparis Durumu",  callback_data="siparis_durumu"),
        InlineKeyboardButton("Siparislerim",    callback_data="siparislerim"),
    ],
    [
        InlineKeyboardButton("Kargo Takibi",    callback_data="kargo_takip"),
        InlineKeyboardButton("Iptal Talebi",    callback_data="iptal_talebi"),
    ],
    [
        InlineKeyboardButton("Stok Sorgula",   callback_data="stok_sorgu"),
        InlineKeyboardButton("Gunluk Ozet",    callback_data="gunluk_ozet"),
    ],
    [InlineKeyboardButton("Serbest Soru",      callback_data="serbest_soru")],
])

BACK_KB = InlineKeyboardMarkup([[InlineKeyboardButton("Ana Menu", callback_data="back_menu")]])

def _sess(update: Update) -> str:
    inbound = adapter.parse_update(update)
    return f"tg_{inbound.channel_user_id}"

def _ud(context) -> dict:
    d = context.user_data
    d.setdefault("state", S_MENU)
    d.setdefault("intent", None)
    d.setdefault("telefon", None)
    d.setdefault("takip_kodu", None)
    d.setdefault("pending_action", None)
    d.setdefault("otp_order_id", None)   # OTP akışındaki sipariş no
    return d

async def _menu(update: Update, context, text=MENU_TEXT):
    ud = _ud(context)
    ud["state"]  = S_MENU
    ud["intent"] = None
    ud["pending_action"] = None
    target = update.callback_query.message if update.callback_query else update.message
    await target.reply_text(text, reply_markup=MENU_KB)

async def _reply(update: Update, text: str, kb=None):
    target = update.callback_query.message if update.callback_query else update.message
    await target.reply_text(text, reply_markup=kb or BACK_KB)

async def _ensure_auth(update, context, pending: str) -> bool:
    ud = _ud(context)
    if ud.get("telefon") or ud.get("takip_kodu"):
        sess = _sess(update)
        if ud["telefon"]:
            set_session_scope(sess, telefon=ud["telefon"])
        else:
            set_session_scope(sess, takip_kodu=ud["takip_kodu"])
        activate_scope(sess)
        return True
    ud["state"] = S_WAITING_PHONE
    ud["pending_action"] = pending
    await _reply(update,
        "Kimlik dogrulama gerekli.\n\n"
        "Telefon numaranizi (05XXXXXXXXX) veya\n"
        "Siparis takip kodunuzu (SIP-XXXXXX) girin:"
    )
    return False

async def _fast(update, context, intent: str, params: dict):
    ir = IntentResult(intent=intent, params=params, confidence=0.9, bypass_llm=True)
    r  = fast_response(ir)
    await _reply(update, r or "Sorgu tamamlanamadi.")

async def _llm(update, context, text: str):
    sess = _sess(update)
    inbound = adapter.parse_update(update)
    try:
        result = agent_graph.invoke(
            {
                "messages": [HumanMessage(content=text)],
                "tenant_id": inbound.tenant_id,
                "channel": inbound.channel,
                "channel_user_id": inbound.channel_user_id,
            },
            config={"configurable": {"thread_id": sess, "tenant_id": inbound.tenant_id}},
        )
        resp = result["messages"][-1].content
        if len(resp) > 4000:
            resp = resp[:4000] + "\n_(kisaltildi)_"
        await _reply(update, resp)
    except Exception as e:
        await _reply(update, f"Hata: {str(e)[:200]}")

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def start_command(update: Update, context):
    _ud(context)["state"] = S_MENU
    await update.message.reply_text(
        "KOBİ Asistan'a hosgeldiniz!", reply_markup=MENU_KB
    )

async def menu_command(update: Update, context):
    await _menu(update, context)

async def button_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    ud = _ud(context)

    ok, msg = _rate_ok(update.effective_user.id)
    if not ok:
        await query.message.reply_text(msg)
        return

    action = query.data

    if action == "back_menu":
        await _menu(update, context)

    elif action == "siparis_durumu":
        ud["state"]  = S_WAITING_ORDER
        ud["intent"] = "siparis_sorgula"
        await _reply(update,
            "Siparis Durumu Sorgulama\n\n"
            "Siparis numaranizi veya takip kodunuzu girin:\n"
            "- Ornek: 5\n"
            "- Ornek: SIP-MD3R45"
        )

    elif action == "siparislerim":
        if not await _ensure_auth(update, context, "musteri_siparisleri"):
            return
        ud["state"] = S_MENU
        await query.message.reply_text("Siparisleriniz getiriliyor...")
        await _fast(update, context, "musteri_siparisleri", {})

    elif action == "kargo_takip":
        ud["state"]  = S_WAITING_ORDER
        ud["intent"] = "kargo_takip"
        await _reply(update,
            "Kargo Takibi\n\n"
            "Siparis numaranizi veya takip kodunuzu girin:"
        )

    elif action == "iptal_talebi":
        if not await _ensure_auth(update, context, "iptal_talebi"):
            return
        ud["state"]  = S_WAITING_CANCEL
        ud["intent"] = "iptal_talebi"
        await _reply(update, "Hangi siparisi iptal etmek istiyorsunuz? (No veya SIP-XXXXXX):")

    elif action == "stok_sorgu":
        ud["state"]  = S_WAITING_PROD
        ud["intent"] = "stok_sorgu"
        await _reply(update, "Aramak istediginiz urunu yazin:\nOrnek: zeytinyagi, domates")

    elif action == "gunluk_ozet":
        activate_scope(_sess(update))
        await query.message.reply_text("Gunluk ozet getiriliyor...")
        await _fast(update, context, "gunluk_ozet", {})

    elif action == "serbest_soru":
        ud["state"] = S_FREE_CHAT
        await _reply(update, "Serbest Soru Modu - Sorunuzu yazin. /menu ile ana menuye donebilirsiniz.")


async def handle_message(update: Update, context):
    text = update.message.text.strip()
    ud   = _ud(context)
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

    # --- Auth Bekleniyor ---
    if state == S_WAITING_PHONE:
        pm = re.search(r"(05\d{9})", text)
        cm = re.search(r"(SIP-[A-Z0-9]{6})", text, re.IGNORECASE)

        if pm and validate_phone(pm.group(1)):
            ud["telefon"] = pm.group(1)
            set_session_scope(sess, telefon=ud["telefon"])
            activate_scope(sess)
            await update.message.reply_text(f"{pm.group(1)} dogrulandi!")
            pending = ud.get("pending_action")
            if pending == "musteri_siparisleri":
                ud["state"] = S_MENU
                await _fast(update, context, "musteri_siparisleri", {})
            elif pending == "iptal_talebi":
                ud["state"] = S_WAITING_CANCEL
                await update.message.reply_text("Hangi siparisi iptal etmek istersiniz?", reply_markup=BACK_KB)
            else:
                await _menu(update, context)
        elif cm and validate_tracking_code(cm.group(1).upper()):
            ud["takip_kodu"] = cm.group(1).upper()
            set_session_scope(sess, takip_kodu=ud["takip_kodu"])
            activate_scope(sess)
            await update.message.reply_text(f"{ud['takip_kodu']} dogrulandi!")
            await _menu(update, context)
        else:
            await update.message.reply_text(
                "Numara bulunamadi. Telefon (05XXXXXXXXX) veya takip kodu (SIP-XXXXXX) girin:",
                reply_markup=BACK_KB
            )
        return

    # --- Siparis/Kargo Bekleniyor ---
    if state == S_WAITING_ORDER:
        intent = ud.get("intent", "siparis_sorgula")
        cm = re.search(r"(SIP-[A-Z0-9]{6})", text, re.IGNORECASE)
        nm = re.search(r"\b(\d{1,6})\b", text)

        if cm:
            params = {"takip_kodu": cm.group(1).upper()}
        elif nm:
            params = {"siparis_no": int(nm.group(1))}
        else:
            await update.message.reply_text("Gecerli bir siparis no veya SIP-XXXXXX kodu girin.", reply_markup=BACK_KB)
            return

        await update.message.chat.send_action("typing")
        if intent == "kargo_takip":
            activate_scope(sess)
            await _llm(update, context, f"Siparis {text} kargo durumu nedir?")
        else:
            if params.get("takip_kodu"):
                set_session_scope(sess, takip_kodu=params["takip_kodu"])
            activate_scope(sess)
            await _fast(update, context, "siparis_sorgula", params)
        ud["state"] = S_MENU
        return

    # --- Urun Bekleniyor ---
    if state == S_WAITING_PROD:
        if len(text) < 2:
            await update.message.reply_text("Urun adi cok kisa.", reply_markup=BACK_KB)
            return
        await update.message.chat.send_action("typing")
        await _fast(update, context, "stok_sorgu", {"urun_adi": text})
        ud["state"] = S_MENU
        return

    # --- Iptal Talebi: siparis no al, OTP gonder ---
    if state == S_WAITING_CANCEL:
        nm = re.search(r"\b(\d{1,6})\b", text)
        cm = re.search(r"(SIP-[A-Z0-9]{6})", text, re.IGNORECASE)
        order_ref = nm.group(1) if nm else (cm.group(1) if cm else None)
        if not order_ref:
            await update.message.reply_text(
                "Lutfen gecerli bir siparis numarasi girin (ornek: 42 ya da SIP-ABC123):",
                reply_markup=BACK_KB,
            )
            return
        # Siparis no'yu resolve et
        from database.db import get_connection as _gc
        conn = _gc()
        if nm:
            order_row = conn.execute(
                "SELECT id, customer_name FROM orders WHERE id = ?", (int(order_ref),)
            ).fetchone()
        else:
            order_row = conn.execute(
                "SELECT id, customer_name FROM orders WHERE tracking_code = ?", (order_ref.upper(),)
            ).fetchone()
        conn.close()
        if not order_row:
            await update.message.reply_text(
                f"Siparis #{order_ref} bulunamadi. Tekrar deneyin:",
                reply_markup=BACK_KB,
            )
            return
        order_id = int(order_row["id"])
        # OTP olustur
        from agent.otp import create_otp_challenge
        tg_user_id = str(update.effective_user.id)
        challenge = create_otp_challenge(
            order_id=order_id,
            action="cancellation",
            channel="telegram",
            channel_user_id=tg_user_id,
        )
        ud["otp_order_id"] = order_id
        ud["state"] = S_WAITING_OTP
        # DEBUG/DEMO: OTP'yi kullaniciya da gonder (production'da sadece kayitli numaraya gidecek)
        await update.message.reply_text(
            f"Siparis #{order_id} ({order_row['customer_name']}) iptal talebi icin dogrulama kodu:\n\n"
            f"Kod: *{challenge['code']}*\n\n"
            f"Bu kodu girin (10 dakika gecerli, {challenge.get('max_attempts',5)} deneme hakki):",
            parse_mode="Markdown",
            reply_markup=BACK_KB,
        )
        return

    # --- OTP Dogrulama ---
    if state == S_WAITING_OTP:
        code = text.strip()
        order_id = ud.get("otp_order_id")
        if not order_id:
            await _menu(update, context, "Oturum suresi doldu. Ana menuye yonlendiriliyor.")
            return
        from agent.otp import verify_otp_challenge
        result = verify_otp_challenge(order_id=order_id, action="cancellation", code=code)
        if not result["ok"]:
            hata = result.get("hata", "Dogrulama basarisiz.")
            # Deneme hakki doldu mu?
            if "hakki doldu" in hata.lower():
                await _menu(update, context, f"{hata} Ana menuye yonlendiriliyor.")
                ud["otp_order_id"] = None
            else:
                await update.message.reply_text(
                    f"Yanlis kod. {hata} Tekrar deneyin:", reply_markup=BACK_KB
                )
            return
        # OTP dogrulandi — iptal biletini ac
        from repositories.tickets import create_ticket as _create_ticket
        ticket_id = _create_ticket(
            payload={
                "type": "cancellation_request",
                "title": f"Musteri Iptal Talebi — Siparis #{order_id}",
                "description": (
                    f"Telegram kullanicisi siparis #{order_id} icin OTP dogrulamali "
                    f"iptal talebinde bulundu. (tg_user_id={update.effective_user.id})"
                ),
                "priority": "high",
                "related_order_id": order_id,
            },
        )
        ud["otp_order_id"] = None
        ud["state"] = S_MENU
        await update.message.reply_text(
            f"Iptal talebiniz alindi. Bilet #{ticket_id} olusturuldu.\n"
            f"Ekibimiz en kisa surede sizi arayacak.",
            reply_markup=MENU_KB,
        )
        return

    # --- Serbest Soru ---
    if state == S_FREE_CHAT:
        classified = classify(text)
        if classified.bypass_llm:
            if classified.intent in ("musteri_siparisleri", "iptal_talebi"):
                if not ud.get("telefon") and not ud.get("takip_kodu"):
                    await update.message.reply_text("Bu islem icin kimlik dogrulama gerekli. /menu yazin.")
                    return
            activate_scope(sess)
            resp = fast_response(classified)
            if resp:
                await update.message.reply_text(resp, reply_markup=BACK_KB)
                return
        # Auth extraction
        pm = re.search(r"(05\d{9})", text)
        cm = re.search(r"(SIP-[A-Z0-9]{6})", text, re.IGNORECASE)
        if pm and validate_phone(pm.group(1)):
            ud["telefon"] = pm.group(1)
            set_session_scope(sess, telefon=ud["telefon"])
        elif cm and validate_tracking_code(cm.group(1).upper()):
            ud["takip_kodu"] = cm.group(1).upper()
            set_session_scope(sess, takip_kodu=ud["takip_kodu"])
        activate_scope(sess)
        await update.message.chat.send_action("typing")
        await _llm(update, context, text)
        return

    # --- Varsayilan: Classifier dene, yoksa menu goster ---
    classified = classify(text)
    if classified.bypass_llm:
        activate_scope(sess)
        resp = fast_response(classified)
        if resp:
            await update.message.reply_text(resp, reply_markup=BACK_KB)
            return
    await _menu(update, context, text="Bir secenek secin veya sorunuzu yazin:")


# ---------------------------------------------------------------------------
# Setup / Teardown
# ---------------------------------------------------------------------------

async def setup_telegram():
    global telegram_app
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ENABLED:
        print("[WARN] Telegram devre disi.")
        return

    telegram_app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("menu",  menu_command))
    telegram_app.add_handler(CallbackQueryHandler(button_handler))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(drop_pending_updates=True)
    print("[OK] Telegram bot baslatildi (interaktif menu aktif)!")


async def stop_telegram():
    global telegram_app
    if telegram_app:
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()
        print("[STOP] Telegram bot durduruldu.")
