"""
Kargo Takip Tool — Simülasyon
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langchain_core.tools import tool
from database.db import get_connection


@tool
def kargo_takip(kargo_kodu: str) -> dict:
    """Kargo takip koduna göre kargonun güncel durumunu, kargo firmasını ve
    tahmini teslimat tarihini sorgular. Sipariş kargodaysa ve müşteri
    kargo durumunu öğrenmek isterse bu tool kullanılır."""

    conn = get_connection()
    cursor = conn.cursor()

    row = cursor.execute(
        "SELECT * FROM cargo_tracking WHERE tracking_code = ?", (kargo_kodu,)
    ).fetchone()

    conn.close()

    if not row:
        return {"hata": f"'{kargo_kodu}' kargo kodu bulunamadı."}

    return {
        "kargo_kodu": row["tracking_code"],
        "firma": row["company"],
        "guncel_durum": row["current_status"],
        "tahmini_teslimat": row["estimated_delivery"],
        "son_guncelleme": row["last_update"]
    }
