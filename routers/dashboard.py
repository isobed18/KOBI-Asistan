"""
Dashboard Router — Yönetici Paneli için Toplu KPI Verisi
"""

from fastapi import APIRouter, BackgroundTasks, Depends
import asyncio
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import get_connection
from agent.tenant_config import tenant_public_payload
from routers.auth_router import CurrentUser, get_current_user

# ---------------------------------------------------------------------------
# AI Tasks cache (15 dakika TTL)
# ---------------------------------------------------------------------------
_ai_tasks_cache: dict | None = None
_ai_tasks_ts: float = 0
_AI_TASKS_TTL = 900  # 15 dakika

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", summary="Dashboard KPI özeti")
def get_dashboard_stats(current_user: CurrentUser = Depends(get_current_user)):
    """
    Genel bakış sayfası için tek seferde tüm KPI'ları döner:
    sipariş özeti, gelir, stok uyarıları, açık biletler, son bildirimler.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Sipariş durumları
    tenant_id = current_user.tenant_id
    orders = cursor.execute("SELECT status, total_price FROM orders WHERE tenant_id = ?", (tenant_id,)).fetchall()
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
        WHERE stock_quantity <= low_stock_threshold AND is_active = 1 AND tenant_id = ?
        ORDER BY stock_quantity ASC
    """, (tenant_id,)).fetchall()

    # Kargodaki siparişler
    cargo_rows = cursor.execute("""
        SELECT o.id, o.customer_name, o.cargo_tracking_code, o.cargo_company,
               ct.current_status, ct.estimated_delivery
        FROM orders o
        LEFT JOIN cargo_tracking ct ON ct.tracking_code = o.cargo_tracking_code
        WHERE o.status = 'kargoda' AND o.tenant_id = ?
    """, (tenant_id,)).fetchall()

    delayed = [r for r in cargo_rows if r["current_status"] in ("Şubede Bekliyor", "Gecikti", "İade Sürecinde")]

    # Açık biletler
    ticket_stats = cursor.execute("""
        SELECT status, COUNT(*) as c FROM tickets WHERE tenant_id = ? GROUP BY status
    """, (tenant_id,)).fetchall()
    tickets_by_status = {r["status"]: r["c"] for r in ticket_stats}

    # Son biletler
    recent_tickets = cursor.execute("""
        SELECT id, type, priority, status, title, created_at
        FROM tickets
        WHERE tenant_id = ?
        ORDER BY created_at DESC
        LIMIT 5
    """, (tenant_id,)).fetchall()

    # Son 5 sipariş
    recent_orders = cursor.execute("""
        SELECT id, customer_name, status, total_price, created_at
        FROM orders
        WHERE tenant_id = ?
        ORDER BY created_at DESC
        LIMIT 5
    """, (tenant_id,)).fetchall()

    # Son rapor var mı?
    latest_report = cursor.execute("""
        SELECT id, date, report_text, created_at
        FROM daily_reports
        ORDER BY created_at DESC
        LIMIT 1
    """).fetchone()

    conn.close()

    return {
        "tenant": tenant_public_payload(tenant_id),
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


@router.get("/analytics", summary="Analitik ve icgoru ozeti")
def get_analytics(current_user: CurrentUser = Depends(get_current_user)):
    """
    Task 6 icin lightweight analitik katmani:
    satis trendi, urun performansi, tekrar eden musteriler ve risk sinyalleri.
    """
    conn = get_connection()
    cursor = conn.cursor()
    tenant_id = current_user.tenant_id

    top_products = cursor.execute("""
        SELECT p.id, p.name, p.category,
               SUM(oi.quantity) AS sold_qty,
               SUM(oi.quantity * oi.unit_price) AS revenue,
               p.stock_quantity,
               p.low_stock_threshold
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        JOIN orders o ON o.id = oi.order_id
        WHERE o.status != 'iptal' AND o.tenant_id = ?
        GROUP BY p.id
        ORDER BY sold_qty DESC
        LIMIT 8
    """, (tenant_id,)).fetchall()

    repeat_customers = cursor.execute("""
        SELECT customer_name, customer_phone, COUNT(*) AS order_count,
               SUM(CASE WHEN status != 'iptal' THEN total_price ELSE 0 END) AS revenue
        FROM orders
        WHERE tenant_id = ?
        GROUP BY customer_phone
        HAVING COUNT(*) >= 2
        ORDER BY order_count DESC, revenue DESC
        LIMIT 6
    """, (tenant_id,)).fetchall()

    large_orders = cursor.execute("""
        SELECT o.id, o.customer_name, o.total_price, COUNT(oi.id) AS item_lines,
               SUM(oi.quantity) AS total_items, o.status
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        WHERE o.status NOT IN ('iptal', 'teslim_edildi') AND o.tenant_id = ?
        GROUP BY o.id
        HAVING total_items >= 5 OR o.total_price >= 500
        ORDER BY o.total_price DESC
        LIMIT 6
    """, (tenant_id,)).fetchall()

    conn.close()
    risks = []
    for p in top_products:
        d = dict(p)
        if d["stock_quantity"] <= d["low_stock_threshold"] and d["sold_qty"] > 0:
            risks.append({
                "type": "stock_demand_conflict",
                "title": f"{d['name']} hem satiliyor hem kritik stokta",
                "body": f"Stok {d['stock_quantity']}, esik {d['low_stock_threshold']}. Yenileme oncelikli.",
                "priority": "high",
            })
    for o in large_orders:
        d = dict(o)
        risks.append({
            "type": "large_order_review",
            "title": f"Siparis #{d['id']} insan onayi gerektirebilir",
            "body": f"{d['customer_name']} icin {d['total_items']} adet / {d['total_price']} TL siparis.",
            "priority": "normal",
        })

    return {
        "top_products": [dict(r) for r in top_products],
        "repeat_customers": [dict(r) for r in repeat_customers],
        "large_orders": [dict(r) for r in large_orders],
        "risk_signals": risks[:8],
    }


@router.get("/cargo", summary="Kargo yönetim özeti")
def get_cargo_dashboard(current_user: CurrentUser = Depends(get_current_user)):
    """
    Kargodaki tüm siparişler + takip bilgisi.
    Gecikme tespiti ve durum bilgisi ile.
    """
    conn = get_connection()
    cursor = conn.cursor()
    tenant_id = current_user.tenant_id

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
        WHERE o.status = 'kargoda' AND o.tenant_id = ?
        ORDER BY o.updated_at DESC
    """, (tenant_id,)).fetchall()

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
def get_sales_chart(current_user: CurrentUser = Depends(get_current_user)):
    """Son 7 günün günlük sipariş sayısı ve gelir verisi."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            date(created_at) AS day,
            COUNT(*)         AS order_count,
            COALESCE(SUM(CASE WHEN status != 'iptal' THEN total_price ELSE 0 END), 0) AS revenue
        FROM orders
        WHERE created_at >= date('now', '-6 days', 'localtime') AND tenant_id = ?
        GROUP BY day
        ORDER BY day ASC
    """, (current_user.tenant_id,)).fetchall()
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


@router.post("/ai-tasks", summary="LLM destekli gunluk gorev listesi uret")
async def generate_ai_tasks(background_tasks: BackgroundTasks, current_user: CurrentUser = Depends(get_current_user)):
    """Tenant-aware proactive task list. Cached for 15 minutes per tenant."""
    global _ai_tasks_cache, _ai_tasks_ts

    now = time.time()
    cache_key = f"tenant:{current_user.tenant_id}"
    if _ai_tasks_cache and _ai_tasks_cache.get("key") == cache_key and (now - _ai_tasks_ts) < _AI_TASKS_TTL:
        return _ai_tasks_cache

    conn = get_connection()
    low_stock = conn.execute("""
        SELECT name, stock_quantity, low_stock_threshold FROM products
        WHERE stock_quantity <= low_stock_threshold AND is_active = 1 AND tenant_id = ?
        ORDER BY stock_quantity ASC LIMIT 5
    """, (current_user.tenant_id,)).fetchall()
    open_tickets = conn.execute(
        "SELECT COUNT(*) AS c FROM tickets WHERE status IN ('open','in_progress') AND tenant_id = ?",
        (current_user.tenant_id,),
    ).fetchone()["c"]
    pending_orders = conn.execute(
        "SELECT COUNT(*) AS c FROM orders WHERE status = 'hazırlanıyor' AND tenant_id = ?",
        (current_user.tenant_id,),
    ).fetchone()["c"]
    delayed_cargo = conn.execute("""
        SELECT COUNT(*) AS c FROM orders o
        LEFT JOIN cargo_tracking ct ON ct.tracking_code = o.cargo_tracking_code
        WHERE o.status = 'kargoda' AND o.tenant_id = ?
          AND ct.current_status IN ('Şubede Bekliyor','Gecikti','İade Sürecinde')
    """, (current_user.tenant_id,)).fetchone()["c"]
    conn.close()

    try:
        from agent.llm_service import agenerate_ai_tasks
        result = await asyncio.wait_for(
            agenerate_ai_tasks({
                "low_stock": [dict(r) for r in low_stock],
                "open_tickets": open_tickets,
                "pending_orders": pending_orders,
                "delayed_cargo": delayed_cargo,
            }),
            timeout=3.0,
        )
    except Exception:
        result = _build_template_tasks(low_stock, open_tickets, pending_orders, delayed_cargo)

    result["key"] = cache_key
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
