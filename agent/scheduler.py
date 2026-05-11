"""
APScheduler — Zamanlanmış Görevler
=====================================
Sabah raporu (LLM destekli), stok alarm + bilet, kargo gecikme + bilet.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import json
from datetime import datetime, date

from tools.order_product_tools import gunluk_ozet, kritik_stok_listesi
from tools.kargo_tools import kargo_takip
from database.db import get_connection
from agent.llm_service import (
    agenerate_daily_report,
    agenerate_stock_alert_content,
)

scheduler = AsyncIOScheduler()

# Bildirim kuyruğu — UI/Telegram/log için
notification_queue: list[dict] = []


def _add_notification(tip: str, baslik: str, icerik: str, oncelik: str = "normal"):
    notification_queue.append({
        "tip": tip,
        "baslik": baslik,
        "icerik": icerik,
        "oncelik": oncelik,
        "zaman": datetime.now().isoformat(),
    })
    if len(notification_queue) > 50:
        notification_queue.pop(0)
    print(f"[BİLDİRİM][{oncelik.upper()}] {baslik}: {icerik[:150]}")


def _create_ticket_in_db(
    type_: str,
    title: str,
    description: str,
    llm_content: str = None,
    priority: str = "normal",
    related_order_id: int = None,
    related_product_id: int = None,
) -> int:
    """Doğrudan DB'ye bilet yazar ve id döner."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO tickets (type, title, description, llm_content, priority, related_order_id, related_product_id)
        VALUES (?,?,?,?,?,?,?)
    """, (type_, title, description, llm_content, priority, related_order_id, related_product_id))
    ticket_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return ticket_id


def _save_daily_report(report_text: str, raw_data: dict) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO daily_reports (date, report_text, raw_data)
        VALUES (?, ?, ?)
    """, (date.today().isoformat(), report_text, json.dumps(raw_data, ensure_ascii=False)))
    report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return report_id


# ---------------------------------------------------------------------------
# Sabah Raporu (08:00) — LLM destekli
# ---------------------------------------------------------------------------

async def sabah_raporu():
    """Her gün sabah çalışır — LLM ile kapsamlı günlük rapor üretir."""
    try:
        ozet = gunluk_ozet.invoke({})
        kritik = kritik_stok_listesi.invoke({})

        conn = get_connection()
        cursor = conn.cursor()
        cargo_delays = cursor.execute("""
            SELECT o.id, o.customer_name, o.cargo_tracking_code, ct.current_status
            FROM orders o
            JOIN cargo_tracking ct ON ct.tracking_code = o.cargo_tracking_code
            WHERE o.status = 'kargoda' AND ct.current_status IN ('Şubede Bekliyor', 'Gecikti')
        """).fetchall()
        conn.close()

        raw_data = {
            "ozet": ozet,
            "kritik_stok": kritik,
            "kargo_gecikmeleri": [dict(r) for r in cargo_delays],
            "rapor_tarihi": date.today().isoformat(),
        }

        report_text = await agenerate_daily_report(raw_data)
        report_id = _save_daily_report(report_text, raw_data)

        _add_notification(
            "rapor",
            "Sabah Raporu Hazır",
            f"LLM destekli günlük rapor oluşturuldu (Rapor #{report_id}). Dashboard'da görüntüleyebilirsiniz.",
            "normal",
        )

        if kritik.get("urunler"):
            _add_notification(
                "alarm",
                "Kritik Stok Uyarısı",
                f"{len(kritik['urunler'])} ürün kritik seviyede. Tedarik süreci başlatılmalı.",
                "yuksek",
            )
    except Exception as e:
        print(f"[HATA] Sabah raporu hatası: {e}")


# ---------------------------------------------------------------------------
# Stok Alarm (her 2 saat) — LLM bilet üretir
# ---------------------------------------------------------------------------

async def stok_alarm():
    """Her 2 saatte çalışır — kritik stok tespiti + LLM bilet oluşturma."""
    try:
        kritik = kritik_stok_listesi.invoke({})
        urunler = kritik.get("urunler", [])
        if not urunler:
            return

        for urun in urunler:
            # Aynı ürün için bugün açık bilet var mı?
            conn = get_connection()
            cursor = conn.cursor()
            existing = cursor.execute("""
                SELECT id FROM tickets
                WHERE type = 'stock_alert'
                  AND related_product_id = ?
                  AND status != 'resolved'
                  AND DATE(created_at) = DATE('now', 'localtime')
            """, (urun["id"],)).fetchone()
            conn.close()

            if existing:
                continue  # Bugün zaten bilet var

            llm_data = await agenerate_stock_alert_content(urun)
            llm_json = json.dumps(llm_data, ensure_ascii=False)

            ticket_id = _create_ticket_in_db(
                type_="stock_alert",
                title=f"Kritik Stok: {urun['name']} ({urun['stock_quantity']} adet)",
                description=(
                    f"Ürün '{urun['name']}' stok seviyesi kritik eşiğin altına düştü. "
                    f"Mevcut: {urun['stock_quantity']} adet, Eşik: {urun['low_stock_threshold']} adet."
                ),
                llm_content=llm_json,
                priority="high",
                related_product_id=urun["id"],
            )

            _add_notification(
                "alarm",
                f"Stok Bileti Oluşturuldu: {urun['name']}",
                f"Bilet #{ticket_id} — Önerilen sipariş: {llm_data.get('onerilen_miktar', '?')} adet",
                "yuksek",
            )

    except Exception as e:
        print(f"[HATA] Stok alarm hatası: {e}")


def _cargo_delay_template(order_info: dict) -> dict:
    name = order_info.get("customer_name", "Müşteri")
    code = order_info.get("cargo_tracking_code", "")
    status = order_info.get("cargo_status", "Gecikti")
    delivery = order_info.get("estimated_delivery") or "yakın zamanda"
    musteri_mesaji = (
        f"Sayın {name},\n\n"
        f"{code} takip numaralı siparişinizde kargo sürecinde gecikme yaşanmaktadır. "
        f"Güncel durum: {status}. Tahmini teslimat: {delivery}.\n\n"
        f"Gecikmeden dolayı özür dileriz. Kargo durumunuzu {code} koduyla takip edebilirsiniz. "
        f"Herhangi bir sorunuz için müşteri hizmetlerimize ulaşabilirsiniz.\n\n"
        f"Saygılarımızla,\nMüşteri Hizmetleri"
    )
    ic_not = (
        f"Sipariş #{order_info.get('id')} — Kargo: {code} — "
        f"Durum: {status} — Müşteri: {name} ({order_info.get('customer_phone', '-')})"
    )
    return {"musteri_mesaji": musteri_mesaji, "ic_not": ic_not}


# ---------------------------------------------------------------------------
# Kargo Gecikme Kontrolü (her 4 saat) — Template bilet üretir
# ---------------------------------------------------------------------------

async def kargo_gecikme_kontrol():
    """Her 4 saatte çalışır — kargo gecikmelerini tespit eder + LLM bilet açar."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        kargodakiler = cursor.execute("""
            SELECT id, customer_name, customer_phone, cargo_tracking_code, total_price
            FROM orders
            WHERE status = 'kargoda' AND cargo_tracking_code IS NOT NULL
        """).fetchall()
        conn.close()

        for row in kargodakiler:
            kargo_bilgi = kargo_takip.invoke({"kargo_kodu": row["cargo_tracking_code"]})
            durum = kargo_bilgi.get("guncel_durum", "")

            if durum not in ("Şubede Bekliyor", "Gecikti", "İade Sürecinde"):
                continue

            # Bugün bu sipariş için açık gecikme bileti var mı?
            conn = get_connection()
            cursor = conn.cursor()
            existing = cursor.execute("""
                SELECT id FROM tickets
                WHERE type = 'cargo_delay'
                  AND related_order_id = ?
                  AND status != 'resolved'
                  AND DATE(created_at) = DATE('now', 'localtime')
            """, (row["id"],)).fetchone()
            conn.close()

            if existing:
                continue

            order_info = {
                "id": row["id"],
                "customer_name": row["customer_name"],
                "customer_phone": row["customer_phone"],
                "cargo_tracking_code": row["cargo_tracking_code"],
                "cargo_status": durum,
                "estimated_delivery": kargo_bilgi.get("tahmini_teslimat"),
                "total_price": row["total_price"],
            }

            llm_data = _cargo_delay_template(order_info)
            llm_json = json.dumps(llm_data, ensure_ascii=False)

            ticket_id = _create_ticket_in_db(
                type_="cargo_delay",
                title=f"Kargo Gecikmesi — Sipariş #{row['id']} ({row['customer_name']})",
                description=(
                    f"Sipariş #{row['id']} ({row['customer_name']}) kargo durumu: '{durum}'. "
                    f"Kargo kodu: {row['cargo_tracking_code']}."
                ),
                llm_content=llm_json,
                priority="high",
                related_order_id=row["id"],
            )

            _add_notification(
                "alarm",
                f"Kargo Gecikme Bileti: Sipariş #{row['id']}",
                f"Bilet #{ticket_id} açıldı — {row['customer_name']} — Durum: {durum}",
                "yuksek",
            )

    except Exception as e:
        print(f"[HATA] Kargo kontrol hatası: {e}")


# ---------------------------------------------------------------------------
# Scheduler Setup
# ---------------------------------------------------------------------------

def setup_scheduler():
    scheduler.add_job(
        sabah_raporu,
        CronTrigger(hour=8, minute=0),
        id="sabah_raporu",
        name="Günlük Sabah Raporu (LLM)",
        replace_existing=True,
    )
    scheduler.add_job(
        stok_alarm,
        IntervalTrigger(hours=2),
        id="stok_alarm",
        name="Kritik Stok Kontrolü + Bilet",
        replace_existing=True,
    )
    scheduler.add_job(
        kargo_gecikme_kontrol,
        IntervalTrigger(hours=4),
        id="kargo_gecikme",
        name="Kargo Gecikme Kontrolü + Bilet",
        replace_existing=True,
    )
    scheduler.start()
    print("[OK] Scheduler başlatıldı (sabah_raporu: 08:00, stok_alarm: 2sa, kargo: 4sa)")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("[STOP] Scheduler durduruldu")
