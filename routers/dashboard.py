"""
Dashboard Router — Yönetici Paneli için Toplu KPI Verisi
"""

from fastapi import APIRouter, BackgroundTasks
import asyncio
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import get_connection

# ---------------------------------------------------------------------------
# AI Tasks cache (15 dakika TTL)
# ---------------------------------------------------------------------------
_ai_tasks_cache: dict | None = None
_ai_tasks_ts: float = 0
_AI_TASKS_TTL = 900  # 15 dakika

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


@router.get("/sales-chart", summary="Son 7 günlük satış grafiği")
def get_sales_chart():
    """Son 7 günün günlük sipariş sayısı ve gelir verisi."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            date(created_at) AS day,
            COUNT(*)         AS order_count,
            COALESCE(SUM(CASE WHEN status != 'iptal' THEN total_price ELSE 0 END), 0) AS revenue
        FROM orders
        WHERE created_at >= date('now', '-6 days', 'localtime')
        GROUP BY day
        ORDER BY day ASC
    """).fetchall()
    conn.close()

    # Son 7 günün tamamını doldur (veri olmayan günler 0 olsun)
    from datetime import date, timedelta
    today = date.today()
    data_map = {r["day"]: dict(r) for r in rows}
    result = []
    for i in range(6, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        result.append({
            "day": d,
            "order_count": data_map.get(d, {}).get("order_count", 0),
            "revenue": round(data_map.get(d, {}).get("revenue", 0.0), 2),
        })
    return {"days": result}


@router.post("/ai-tasks", summary="LLM destekli günlük görev listesi üret")
async def generate_ai_tasks(background_tasks: BackgroundTasks):
    """
    İşletme verilerine bakıp LLM'e proaktif görev listesi ürettirir.
    15 dakika önbelleğe alınır. Anlık veri döner, LLM yoksa template kullanılır.
    """
    global _ai_tasks_cache, _ai_tasks_ts

    now = time.time()
    if _ai_tasks_cache and (now - _ai_tasks_ts) < _AI_TASKS_TTL:
        return _ai_tasks_cache

    # Ham veri topla
    conn = get_connection()
    low_stock = conn.execute("""
        SELECT name, stock_quantity, low_stock_threshold FROM products
        WHERE stock_quantity <= low_stock_threshold AND is_active = 1
        ORDER BY stock_quantity ASC LIMIT 5
    """).fetchall()
    open_tickets = conn.execute(
        "SELECT COUNT(*) AS c FROM tickets WHERE status IN ('open','in_progress')"
    ).fetchone()["c"]
    pending_orders = conn.execute(
        "SELECT COUNT(*) AS c FROM orders WHERE status = 'hazırlanıyor'"
    ).fetchone()["c"]
    delayed_cargo = conn.execute("""
        SELECT COUNT(*) AS c FROM orders o
        LEFT JOIN cargo_tracking ct ON ct.tracking_code = o.cargo_tracking_code
        WHERE o.status = 'kargoda' AND ct.current_status IN ('Şubede Bekliyor','Gecikti','İade Sürecinde')
    """).fetchone()["c"]
    conn.close()

    # LLM ile görev üret (başarısız olursa template)
    try:
        from agent.llm_service import agenerate_ai_tasks
        result = await agenerate_ai_tasks({
            "low_stock": [dict(r) for r in low_stock],
            "open_tickets": open_tickets,
            "pending_orders": pending_orders,
            "delayed_cargo": delayed_cargo,
        })
    except Exception:
        result = _build_template_tasks(low_stock, open_tickets, pending_orders, delayed_cargo)

    _ai_tasks_cache = result
    _ai_tasks_ts = now
    return result


def _build_template_tasks(low_stock, open_tickets, pending_orders, delayed_cargo) -> dict:
    """LLM yokken basit kural tabanlı görev listesi."""
    tasks = []
    if low_stock:
        names = ", ".join(r["name"] for r in low_stock[:3])
        tasks.append({
            "id": "stock_replenish",
            "icon": "📦",
            "title": f"{len(low_stock)} ürün kritik stokta",
            "body": f"{names} stok siparişi ver.",
            "priority": "high",
            "link": "/inventory",
            "action": "inventory",
        })
    if open_tickets > 0:
        tasks.append({
            "id": "tickets_pending",
            "icon": "🎫",
            "title": f"{open_tickets} açık bilet bekliyor",
            "body": "Müşteri taleplerini incele ve yanıtla.",
            "priority": "high" if open_tickets > 5 else "normal",
            "link": "/tickets",
            "action": "tickets",
        })
    if pending_orders > 0:
        tasks.append({
            "id": "orders_prepare",
            "icon": "📋",
            "title": f"{pending_orders} sipariş hazırlanmayı bekliyor",
            "body": "Siparişleri hazırlayıp kargoya ver.",
            "priority": "normal",
            "link": "/orders",
            "action": "orders",
        })
    if delayed_cargo > 0:
        tasks.append({
            "id": "cargo_delay",
            "icon": "🚚",
            "title": f"{delayed_cargo} kargo gecikmesi var",
            "body": "Geciken kargolar için müşterileri bilgilendir.",
            "priority": "high",
            "link": "/cargo",
            "action": "cargo",
        })
    return {
        "briefing": f"Bugün {len(tasks)} öncelikli konu var.",
        "tasks": tasks,
        "generated_at": time.strftime("%H:%M"),
        "source": "template",
    }
