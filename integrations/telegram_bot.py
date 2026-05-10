"""
Telegram Bot Entegrasyonu
=========================
FastAPI ile aynı process içinde çalışır.
LangGraph agent'ı doğrudan kullanır.
"""

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters
from langchain_core.messages import HumanMessage

from agent.graph import agent_graph
from agent.guard import check_message
from agent.auth import set_session_scope, activate_scope, validate_phone, validate_tracking_code
from config import settings

telegram_app = None


async def start_command(update: Update, context):
    await update.message.reply_text(
        "🏪 *KOBİ Asistan'a hoş geldiniz!*\n\n"
        "Sipariş, ürün, stok ve kargo sorularınız için buradayım.\n\n"
        "📦 Sipariş sorgula: _'2 numaralı siparişim nerede?'_\n"
        "🔍 Stok kontrol: _'Zeytinyağı var mı?'_\n"
        "📊 Günlük özet: _'Bugünkü durum nedir?'_\n"
        "⚠️ Kritik stoklar: _'Hangi ürünler azaldı?'_",
        parse_mode="Markdown"
    )


async def handle_message(update: Update, context):
    user_msg = update.message.text
    chat_id = str(update.effective_chat.id)

    # Prompt police
    police_result = check_message(user_msg)
    if not police_result.is_safe:
        await update.message.reply_text(police_result.reason)
        return

    # Auth: telefon veya takip kodu cikar
    import re
    phone_match = re.search(r"(05\d{9})", user_msg)
    code_match = re.search(r"SIP-[A-Z0-9]{6}", user_msg, re.IGNORECASE)

    session_key = f"tg_{chat_id}"

    if phone_match and validate_phone(phone_match.group(1)):
        set_session_scope(session_key, telefon=phone_match.group(1))
    elif code_match and validate_tracking_code(code_match.group(0).upper()):
        set_session_scope(session_key, takip_kodu=code_match.group(0).upper())

    activate_scope(session_key)

    # Typing indicator
    await update.message.chat.send_action("typing")

    try:
        config = {"configurable": {"thread_id": session_key}}
        result = agent_graph.invoke(
            {"messages": [HumanMessage(content=user_msg)]},
            config=config
        )
        response = result["messages"][-1].content
        if len(response) > 4000:
            response = response[:4000] + "\n\n_(Devami kisaltildi)_"
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(
            f"Bir hata olustu, lutfen tekrar deneyin.\nHata: {str(e)[:200]}"
        )


async def setup_telegram():
    """Telegram bot'u başlatır (FastAPI startup'ında çağrılır)."""
    global telegram_app

    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ENABLED:
        print("[WARN] Telegram devre disi (token yok veya TELEGRAM_ENABLED=false).")
        return

    telegram_app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling(drop_pending_updates=True)
    print("[OK] Telegram bot baslatildi!")


async def stop_telegram():
    """Telegram bot'u durdurur (FastAPI shutdown'ında çağrılır)."""
    global telegram_app
    if telegram_app:
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()
        print("[STOP] Telegram bot durduruldu.")
