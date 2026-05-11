"""Yapılandırılmış günlük brifing JSON — UI ve API için."""

import json
from typing import Any


def build_briefing_json(raw_data: dict, report_text: str) -> str:
    """Ham rapor verisi ve metinden headlines / kpis / risks üretir."""
    ozet = raw_data.get("ozet") if isinstance(raw_data.get("ozet"), dict) else {}
    kritik = raw_data.get("kritik_stok") if isinstance(raw_data.get("kritik_stok"), dict) else {}
    headlines: list[str] = []
    if ozet.get("ozet_metin"):
        headlines.append(str(ozet["ozet_metin"])[:280])
    text = (report_text or "").strip()
    if text:
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            clean = line.lstrip("#").strip()
            if clean and len(headlines) < 4:
                headlines.append(clean[:280])
            if len(headlines) >= 4:
                break

    kpis: dict[str, Any] = {
        "toplam_siparis": ozet.get("toplam_siparis"),
        "toplam_gelir": ozet.get("toplam_gelir"),
        "kritik_stok_sayisi": ozet.get("kritik_stok_sayisi"),
    }
    durum = ozet.get("durum_dagilimi")
    if isinstance(durum, dict):
        kpis["durum_dagilimi"] = durum

    risks: list[dict[str, Any]] = []
    for u in (kritik.get("urunler") or [])[:8]:
        if isinstance(u, dict) and u.get("name"):
            risks.append(
                {
                    "type": "low_stock",
                    "title": str(u.get("name")),
                    "detail": f"Stok {u.get('stock_quantity')}, eşik {u.get('low_stock_threshold')}",
                }
            )
    for row in (raw_data.get("kargo_gecikmeleri") or [])[:6]:
        if isinstance(row, dict):
            risks.append(
                {
                    "type": "cargo_delay",
                    "title": f"Sipariş #{row.get('id')}",
                    "detail": str(row.get("current_status") or ""),
                }
            )

    payload = {"headlines": headlines, "kpis": kpis, "risks": risks[:12]}
    return json.dumps(payload, ensure_ascii=False)
