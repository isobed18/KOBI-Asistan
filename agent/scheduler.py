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
from database.briefing import build_briefing_json
from database.daily_metrics import rollup_yesterday_all_tenants, refresh_forecasts_all_tenants
from agent.llm_service import agenerate_daily_report
from services.cargo_intervention import CARGO_DELAY_STATUSES, create_cargo_delay_ticket_for_order
from services.stock_intervention import ensure_stock_alert_ticket


def _active_tenant_ids() -> list[int]:
    """Sistemdeki tüm aktif tenant_id'leri döner (users tablosundan)."""
    try:
        conn = get_connection()
        rows = conn.execute("SELECT DISTINCT tenant_id FROM users WHERE is_active=1").fetchall()
        conn.close()
        ids = [r["tenant_id"] for r in rows] if rows else []
        return ids if ids else [1]
    except Exception:
        return [1]

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


def _save_daily_report(report_text: str, raw_data: dict, tenant_id: int) -> int:
    bj = build_briefing_json(raw_data, report_text)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO daily_reports (
            tenant_id, date, report_text, raw_data, briefing_json, model_version, source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tenant_id,
            date.today().isoformat(),
            report_text,
            json.dumps(raw_data, ensure_ascii=False),
            bj,
            "scheduler",
            "scheduler",
        ),
    )
    report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return report_id


# ---------------------------------------------------------------------------
# Sabah Raporu (08:00) — LLM destekli
# ---------------------------------------------------------------------------

async def _sabah_raporu_for_tenant(tenant_id: int):
    """Tek bir tenant için sabah raporu üretir."""
    ozet = gunluk_ozet.invoke({"tenant_id": tenant_id})
    kritik = kritik_stok_listesi.invoke({"tenant_id": tenant_id})

    conn = get_connection()
    cursor = conn.cursor()
    cargo_delays = cursor.execute("""
        SELECT o.id, o.customer_name, o.cargo_tracking_code, ct.current_status
        FROM orders o
        JOIN cargo_tracking ct ON ct.tracking_code = o.cargo_tracking_code
        WHERE o.status = 'kargoda' AND o.tenant_id = ?
          AND ct.current_status IN ('Şubede Bekliyor', 'Gecikti')
    """, (tenant_id,)).fetchall()
    open_tickets = cursor.execute("""
        SELECT id, type, priority, title, created_at
        FROM tickets
        WHERE status != 'resolved' AND tenant_id = ?
        ORDER BY priority DESC, created_at ASC
    """, (tenant_id,)).fetchall()
    conn.close()

    raw_data = {
        "tenant_id": tenant_id,
        "ozet": ozet,
        "kritik_stok": kritik,
        "kargo_gecikmeleri": [dict(r) for r in cargo_delays],
        "acik_biletler": [dict(r) for r in open_tickets],
        "rapor_tarihi": date.today().isoformat(),
    }

    # AI actionable tasks JSON'u raw_data'ya ekle (LLM yoksa template fallback)
    try:
        from agent.llm_service import agenerate_ai_tasks
        ai_tasks = await agenerate_ai_tasks(raw_data)
        raw_data["ai_tasks"] = ai_tasks
    except Exception:
        raw_data["ai_tasks"] = None

    report_text = await agenerate_daily_report(raw_data)
    report_id = _save_daily_report(report_text, raw_data, tenant_id)

    _add_notification(
        "rapor",
        f"Sabah Raporu Hazır (tenant={tenant_id})",
        f"Rapor #{report_id} olusturuldu.",
        "normal",
    )
    if kritik.get("urunler"):
        _add_notification(
            "alarm",
            "Kritik Stok Uyarisi",
            f"{len(kritik['urunler'])} urun kritik seviyede.",
            "yuksek",
        )


async def sabah_raporu():
    """Her gün sabah çalışır — tüm tenant'lar için rapor üretir."""
    for tenant_id in _active_tenant_ids():
        try:
            await _sabah_raporu_for_tenant(tenant_id)
        except Exception as e:
            print(f"[HATA] Sabah raporu (tenant={tenant_id}): {e}")


# ---------------------------------------------------------------------------
# Stok Alarm (her 2 saat) — LLM bilet üretir
# ---------------------------------------------------------------------------

async def stok_alarm():
    """Her 2 saatte çalışır — tüm tenant'lar için kritik stok tespiti + bilet."""
    for tenant_id in _active_tenant_ids():
        await _stok_alarm_for_tenant(tenant_id)


async def _stok_alarm_for_tenant(tenant_id: int):
    try:
        kritik = kritik_stok_listesi.invoke({"tenant_id": tenant_id})
        urunler = kritik.get("urunler", [])
        if not urunler:
            return

        for urun in urunler:
            urun_full = {**urun, "is_active": 1}
            ticket_id = await ensure_stock_alert_ticket(urun_full, tenant_id)
            if ticket_id is None:
                continue
            _add_notification(
                "alarm",
                f"Stok Bileti Oluşturuldu: {urun['name']}",
                f"Bilet #{ticket_id} — stok kritik",
                "yuksek",
            )

    except Exception as e:
        print(f"[HATA] Stok alarm hatası: {e}")


# ---------------------------------------------------------------------------
# Kargo Gecikme Kontrolü (her 4 saat) — Template bilet üretir
# ---------------------------------------------------------------------------

async def kargo_gecikme_kontrol():
    """Her 4 saatte çalışır — tüm tenant'lar için kargo gecikme kontrolü."""
    for tenant_id in _active_tenant_ids():
        try:
            await _kargo_gecikme_for_tenant(tenant_id)
        except Exception as e:
            print(f"[HATA] Kargo kontrol (tenant={tenant_id}): {e}")


async def _kargo_gecikme_for_tenant(tenant_id: int):
    conn = get_connection()
    kargodakiler = conn.execute("""
        SELECT id, customer_name, customer_phone, cargo_tracking_code, total_price
        FROM orders
        WHERE status = 'kargoda' AND cargo_tracking_code IS NOT NULL AND tenant_id = ?
    """, (tenant_id,)).fetchall()
    conn.close()

    for row in kargodakiler:
        kargo_bilgi = kargo_takip.invoke({"kargo_kodu": row["cargo_tracking_code"]})
        durum = kargo_bilgi.get("guncel_durum", "")
        if durum not in CARGO_DELAY_STATUSES:
            continue

        ticket_id = create_cargo_delay_ticket_for_order(
            order_id=row["id"],
            customer_name=row["customer_name"],
            customer_phone=row["customer_phone"],
            cargo_tracking_code=row["cargo_tracking_code"],
            cargo_status=durum,
            estimated_delivery=kargo_bilgi.get("tahmini_teslimat"),
            tenant_id=tenant_id,
        )
        _add_notification(
            "alarm",
            f"Kargo Gecikme Bileti: Siparis #{row['id']}",
            f"Bilet #{ticket_id} acildi — {row['customer_name']} — Durum: {durum}",
            "yuksek",
        )


# ---------------------------------------------------------------------------
# Scheduler Setup
# ---------------------------------------------------------------------------

def rollup_ve_tahmin():
    """Gece: dünün metrikleri + basit ileri tahmin."""
    try:
        rollup_yesterday_all_tenants()
        refresh_forecasts_all_tenants()
    except Exception as e:
        print(f"[HATA] rollup_ve_tahmin: {e}")


def setup_scheduler():
    scheduler.add_job(
        rollup_ve_tahmin,
        CronTrigger(hour=0, minute=15),
        id="rollup_metrics",
        name="Gunluk metrik rollup + tahmin",
        replace_existing=True,
    )
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
    print("[OK] Scheduler baslatildi (rollup: 00:15, sabah_raporu: 08:00, stok_alarm: 2sa, kargo: 4sa)")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("[STOP] Scheduler durduruldu")
