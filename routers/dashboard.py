"""
Dashboard Router — Yönetici Paneli için Toplu KPI Verisi
"""

from fastapi import APIRouter
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import get_connection

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", summary="Dashboard KPI özeti")
def get_dashboard_stats():
    """
    Genel bakış sayfası için tek seferde tüm KPI'ları döner:
    sipariş özeti, gelir, stok uyarıları, açık biletler, son bildirimler.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Sipariş durumları
    orders = cursor.execute("SELECT status, total_price FROM orders").fetchall()
    by_status = {}
    total_revenue = 0.0
    for r in orders:
        s = r["status"]
        by_status[s] = by_status.get(s, 0) + 1
        if r["total_price"] and s != "iptal":
            total_revenue += r["total_price"]

    # Kritik stok
    low_stock = cursor.execute("""
        SELECT id, name, category, stock_quantity, low_stock_threshold
        FROM products
        WHERE stock_quantity <= low_stock_threshold AND is_active = 1
        ORDER BY stock_quantity ASC
    """).fetchall()

    # Kargodaki siparişler
    cargo_rows = cursor.execute("""
        SELECT o.id, o.customer_name, o.cargo_tracking_code, o.cargo_company,
               ct.current_status, ct.estimated_delivery
        FROM orders o
        LEFT JOIN cargo_tracking ct ON ct.tracking_code = o.cargo_tracking_code
        WHERE o.status = 'kargoda'
    """).fetchall()

    delayed = [r for r in cargo_rows if r["current_status"] in ("Şubede Bekliyor", "Gecikti", "İade Sürecinde")]

    # Açık biletler
    ticket_stats = cursor.execute("""
        SELECT status, COUNT(*) as c FROM tickets GROUP BY status
    """).fetchall()
    tickets_by_status = {r["status"]: r["c"] for r in ticket_stats}

    # Son biletler
    recent_tickets = cursor.execute("""
        SELECT id, type, priority, status, title, created_at
        FROM tickets
        ORDER BY created_at DESC
        LIMIT 5
    """).fetchall()

    # Son 5 sipariş
    recent_orders = cursor.execute("""
        SELECT id, customer_name, status, total_price, created_at
        FROM orders
        ORDER BY created_at DESC
        LIMIT 5
    """).fetchall()

    # Son rapor var mı?
    latest_report = cursor.execute("""
        SELECT id, date, report_text, created_at
        FROM daily_reports
        ORDER BY created_at DESC
        LIMIT 1
    """).fetchone()

    conn.close()

    return {
        "orders": {
            "total": len(orders),
            "by_status": by_status,
            "total_revenue": round(total_revenue, 2),
            "pending": by_status.get("hazırlanıyor", 0),
            "in_cargo": by_status.get("kargoda", 0),
            "delivered": by_status.get("teslim_edildi", 0),
            "cancelled": by_status.get("iptal", 0),
        },
        "stock": {
            "critical_count": len(low_stock),
            "critical_products": [dict(r) for r in low_stock],
        },
        "cargo": {
            "active_count": len(cargo_rows),
            "delayed_count": len(delayed),
            "delayed": [dict(r) for r in delayed],
        },
        "tickets": {
            "open": tickets_by_status.get("open", 0),
            "in_progress": tickets_by_status.get("in_progress", 0),
            "resolved": tickets_by_status.get("resolved", 0),
            "total": sum(tickets_by_status.values()),
            "recent": [dict(r) for r in recent_tickets],
        },
        "recent_orders": [dict(r) for r in recent_orders],
        "latest_report": dict(latest_report) if latest_report else None,
    }


@router.get("/cargo", summary="Kargo yönetim özeti")
def get_cargo_dashboard():
    """
    Kargodaki tüm siparişler + takip bilgisi.
    Gecikme tespiti ve durum bilgisi ile.
    """
    conn = get_connection()
    cursor = conn.cursor()

    rows = cursor.execute("""
        SELECT
            o.id          AS order_id,
            o.tracking_code,
            o.customer_name,
            o.customer_phone,
            o.cargo_tracking_code,
            o.cargo_company,
            o.total_price,
            o.created_at  AS order_date,
            o.updated_at,
            ct.current_status AS cargo_status,
            ct.estimated_delivery,
            ct.last_update    AS cargo_last_update
        FROM orders o
        LEFT JOIN cargo_tracking ct ON ct.tracking_code = o.cargo_tracking_code
        WHERE o.status = 'kargoda'
        ORDER BY o.updated_at DESC
    """).fetchall()

    DELAY_STATUSES = {"Şubede Bekliyor", "Gecikti", "İade Sürecinde"}

    result = []
    for r in rows:
        d = dict(r)
        d["is_delayed"] = d.get("cargo_status") in DELAY_STATUSES
        result.append(d)

    conn.close()
    return {
        "total": len(result),
        "delayed_count": sum(1 for r in result if r["is_delayed"]),
        "shipments": result,
    }
