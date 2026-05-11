"""
Reports Router — LLM Destekli Günlük Raporlar
"""

from fastapi import APIRouter, HTTPException, Depends
import json
import sys
import os
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import get_connection
from database.briefing import build_briefing_json
from agent.llm_service import generate_daily_report
from tools.order_product_tools import gunluk_ozet, kritik_stok_listesi
from routers.auth_router import CurrentUser, get_current_user
from config import settings

router = APIRouter(prefix="/reports", tags=["AI Raporlar"])


def _model_version_tag() -> str:
    prov = getattr(settings, "LLM_PROVIDER", "ollama").lower()
    if prov == "openai":
        return f"openai:{getattr(settings, 'OPENAI_MODEL', '')}"
    if prov == "anthropic":
        return f"anthropic:{getattr(settings, 'ANTHROPIC_MODEL', '')}"
    if prov == "gemini":
        return f"gemini:{getattr(settings, 'GEMINI_MODEL', '')}"
    return f"ollama:{getattr(settings, 'OLLAMA_MODEL', '')}"


def _collect_raw_data(tenant_id: int) -> dict:
    """Rapor için ham veriyi toplar (kiracı kapsamlı)."""
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
    conn.close()

    return {
        "tenant_id": tenant_id,
        "ozet": ozet,
        "kritik_stok": kritik,
        "kargo_gecikmeleri": [dict(r) for r in cargo_delays],
        "rapor_tarihi": date.today().isoformat(),
    }


def _save_report(
    report_text: str,
    raw_data: dict,
    tenant_id: int,
    *,
    source: str = "api",
    briefing_json: str | None = None,
) -> int:
    bj = briefing_json if briefing_json is not None else build_briefing_json(raw_data, report_text)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO daily_reports (
            tenant_id, date, report_text, raw_data, briefing_json,
            model_version, source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tenant_id,
            date.today().isoformat(),
            report_text,
            json.dumps(raw_data, ensure_ascii=False),
            bj,
            _model_version_tag(),
            source,
        ),
    )
    report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return report_id


@router.post("/generate", summary="LLM ile günlük rapor oluştur")
def generate_report(current_user: CurrentUser = Depends(get_current_user)):
    """
    Mevcut sipariş, stok ve kargo verilerini toplayıp LLM ile
    kapsamlı bir yönetici raporu üretir ve kaydeder.
    """
    tid = current_user.tenant_id
    raw_data = _collect_raw_data(tid)
    report_text = generate_daily_report(raw_data)
    bj_str = build_briefing_json(raw_data, report_text)
    report_id = _save_report(report_text, raw_data, tid, source="manual", briefing_json=bj_str)

    return {
        "message": "Rapor oluşturuldu.",
        "report_id": report_id,
        "date": date.today().isoformat(),
        "report_text": report_text,
        "briefing_json": json.loads(bj_str),
        "tenant_id": tid,
    }


@router.get("/", summary="Rapor listesi")
def list_reports(limit: int = 20, current_user: CurrentUser = Depends(get_current_user)):
    conn = get_connection()
    cursor = conn.cursor()
    rows = cursor.execute(
        """
        SELECT id, date, created_at, tenant_id,
               SUBSTR(report_text, 1, 300) AS preview
        FROM daily_reports
        WHERE tenant_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (current_user.tenant_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/latest/today", summary="Bugünün son raporu")
def get_today_report(current_user: CurrentUser = Depends(get_current_user)):
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        """
        SELECT * FROM daily_reports
        WHERE tenant_id = ? AND date = DATE('now', 'localtime')
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (current_user.tenant_id,),
    ).fetchone()
    conn.close()
    if not row:
        return {"message": "Bugün için henüz rapor oluşturulmadı.", "report": None}
    return {"report": dict(row)}


@router.get("/{report_id}", summary="Rapor detayı")
def get_report(report_id: int, current_user: CurrentUser = Depends(get_current_user)):
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM daily_reports WHERE id = ? AND tenant_id = ?",
        (report_id, current_user.tenant_id),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Rapor #{report_id} bulunamadı.")
    return dict(row)
