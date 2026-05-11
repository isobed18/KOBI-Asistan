"""
Reports Router — LLM Destekli Günlük Raporlar
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
import json
import sys
import os
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import get_connection
from agent.llm_service import generate_daily_report
from tools.order_product_tools import gunluk_ozet, kritik_stok_listesi

router = APIRouter(prefix="/reports", tags=["AI Raporlar"])


def _collect_raw_data() -> dict:
    """Rapor için ham veriyi toplar."""
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

    return {
        "ozet": ozet,
        "kritik_stok": kritik,
        "kargo_gecikmeleri": [dict(r) for r in cargo_delays],
        "rapor_tarihi": date.today().isoformat(),
    }


def _save_report(report_text: str, raw_data: dict) -> int:
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


@router.post("/generate", summary="LLM ile günlük rapor oluştur")
def generate_report():
    """
    Mevcut sipariş, stok ve kargo verilerini toplayıp LLM ile
    kapsamlı bir yönetici raporu üretir ve kaydeder.
    """
    raw_data = _collect_raw_data()
    report_text = generate_daily_report(raw_data)
    report_id = _save_report(report_text, raw_data)

    return {
        "message": "Rapor oluşturuldu.",
        "report_id": report_id,
        "date": date.today().isoformat(),
        "report_text": report_text,
    }


@router.get("/", summary="Rapor listesi")
def list_reports(limit: int = 20):
    conn = get_connection()
    cursor = conn.cursor()
    rows = cursor.execute("""
        SELECT id, date, created_at,
               SUBSTR(report_text, 1, 300) AS preview
        FROM daily_reports
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/{report_id}", summary="Rapor detayı")
def get_report(report_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM daily_reports WHERE id = ?", (report_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Rapor #{report_id} bulunamadı.")
    return dict(row)


@router.get("/latest/today", summary="Bugünün son raporu")
def get_today_report():
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute("""
        SELECT * FROM daily_reports
        WHERE date = DATE('now', 'localtime')
        ORDER BY created_at DESC
        LIMIT 1
    """).fetchone()
    conn.close()
    if not row:
        return {"message": "Bugün için henüz rapor oluşturulmadı.", "report": None}
    return {"report": dict(row)}
