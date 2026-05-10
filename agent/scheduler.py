"""
APScheduler — Zamanli Gorevler
===============================
Sabah raporu, stok alarm, kargo gecikme kontrolu.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import json
from datetime import datetime

from tools.order_product_tools import gunluk_ozet, kritik_stok_listesi
from tools.kargo_tools import kargo_takip
from database.db import get_connection

scheduler = AsyncIOScheduler()

# Bildirim kuyrugu — UI/Telegram/log icin
notification_queue: list[dict] = []


def _add_notification(tip: str, baslik: str, icerik: str, oncelik: str = "normal"):
    """Bildirim kuyuruguna ekler."""
    notification_queue.append({
        "tip": tip,
        "baslik": baslik,
        "icerik": icerik,
        "oncelik": oncelik,
        "zaman": datetime.now().isoformat(),
    })
    # Son 50 bildirimi tut
    if len(notification_queue) > 50:
        notification_queue.pop(0)
    print(f"[BILDIRIM][{oncelik.upper()}] {baslik}: {icerik[:150]}")


async def sabah_raporu():
    """Her gun sabah calisir — gunluk ozet + kritik stok uyarisi."""
    try:
        ozet = gunluk_ozet.invoke({})
        kritik = kritik_stok_listesi.invoke({})

        rapor = (
            f"Gunluk Ozet:\n"
            f"  Toplam siparis: {ozet.get('toplam_siparis', 0)}\n"
            f"  Toplam gelir: {ozet.get('toplam_gelir', 0):.2f} TL\n"
            f"  Durum dagilimi: {json.dumps(ozet.get('durum_dagilimi', {}), ensure_ascii=False)}\n"
        )

        if kritik.get("urunler"):
            rapor += f"\n  KRITIK STOK: {len(kritik['urunler'])} urun esik altinda!"
            for u in kritik["urunler"]:
                rapor += f"\n    - {u.get('name', '?')}: {u.get('stock_quantity', 0)} adet"

        _add_notification("rapor", "Sabah Raporu", rapor, "normal")

        # Kritik stok varsa ayrica alarm
        if kritik.get("urunler"):
            _add_notification(
                "alarm",
                "Kritik Stok Uyarisi",
                f"{len(kritik['urunler'])} urun kritik seviyede. Tedarik sureci baslatilmali.",
                "yuksek"
            )
    except Exception as e:
        print(f"[HATA] Sabah raporu hatasi: {e}")


async def stok_alarm():
    """Her 2 saatte calisir — kritik stok kontrolu."""
    try:
        kritik = kritik_stok_listesi.invoke({})
        if kritik.get("urunler"):
            urunler = ", ".join([u.get("name", "?") for u in kritik["urunler"]])
            _add_notification(
                "alarm",
                "Stok Uyarisi",
                f"{len(kritik['urunler'])} urun kritik: {urunler}",
                "yuksek"
            )
    except Exception as e:
        print(f"[HATA] Stok alarm hatasi: {e}")


async def kargo_gecikme_kontrol():
    """Her 4 saatte calisir — kargodaki siparislerin gecikme kontrolu."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        kargodakiler = cursor.execute(
            "SELECT id, customer_name, cargo_tracking_code FROM orders WHERE status = 'kargoda' AND cargo_tracking_code IS NOT NULL"
        ).fetchall()
        conn.close()

        gecikmeler = []
        for row in kargodakiler:
            kargo_bilgi = kargo_takip.invoke({"kargo_kodu": row["cargo_tracking_code"]})
            if kargo_bilgi.get("guncel_durum") == "Subede Bekliyor":
                gecikmeler.append(f"Siparis #{row['id']} ({row['customer_name']}): {row['cargo_tracking_code']} subede bekliyor")

        if gecikmeler:
            _add_notification(
                "alarm",
                "Kargo Gecikme Uyarisi",
                "\n".join(gecikmeler),
                "yuksek"
            )
    except Exception as e:
        print(f"[HATA] Kargo kontrol hatasi: {e}")


def setup_scheduler():
    """Zamanlayiciyi konfigure eder ve baslatir."""
    # Sabah raporu — her gun 08:00
    scheduler.add_job(
        sabah_raporu,
        CronTrigger(hour=8, minute=0),
        id="sabah_raporu",
        name="Gunluk Sabah Raporu",
        replace_existing=True
    )

    # Stok alarm — her 2 saatte
    scheduler.add_job(
        stok_alarm,
        IntervalTrigger(hours=2),
        id="stok_alarm",
        name="Kritik Stok Kontrolu",
        replace_existing=True
    )

    # Kargo gecikme — her 4 saatte
    scheduler.add_job(
        kargo_gecikme_kontrol,
        IntervalTrigger(hours=4),
        id="kargo_gecikme",
        name="Kargo Gecikme Kontrolu",
        replace_existing=True
    )

    scheduler.start()
    print("[OK] Scheduler baslatildi (sabah_raporu: 08:00, stok_alarm: 2sa, kargo: 4sa)")


def stop_scheduler():
    """Zamanlayiciyi durdurur."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("[STOP] Scheduler durduruldu")
