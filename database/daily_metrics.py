"""
Günlük operasyon metrikleri (rollup) ve basit tahmin satırları.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from database.db import get_connection


def _orders_day_stats(cursor, tenant_id: int, metric_date: str) -> dict[str, Any]:
    rows = cursor.execute(
        """
        SELECT status,
               COUNT(*) AS c,
               COALESCE(SUM(CASE WHEN status != 'iptal' THEN total_price ELSE 0 END), 0) AS rev
        FROM orders
        WHERE tenant_id = ? AND date(created_at) = ?
        GROUP BY status
        """,
        (tenant_id, metric_date),
    ).fetchall()
    by_status: dict[str, dict[str, float]] = {}
    order_count = 0
    revenue = 0.0
    cancelled = 0
    for r in rows:
        s = r["status"]
        c = int(r["c"] or 0)
        rev = float(r["rev"] or 0)
        by_status[s] = {"count": c, "revenue": rev}
        order_count += c
        revenue += rev
        if s == "iptal":
            cancelled = c
    non_cancel = order_count - cancelled
    avg_order = (revenue / non_cancel) if non_cancel > 0 else None
    return {
        "order_count": order_count,
        "revenue": round(revenue, 2),
        "cancelled_count": cancelled,
        "avg_order_value": round(avg_order, 2) if avg_order is not None else None,
        "by_status": by_status,
    }


def _tickets_day_stats(cursor, tenant_id: int, metric_date: str) -> dict[str, int]:
    opened = cursor.execute(
        """
        SELECT COUNT(*) AS c FROM tickets
        WHERE tenant_id = ? AND date(created_at) = ?
        """,
        (tenant_id, metric_date),
    ).fetchone()["c"]
    resolved = cursor.execute(
        """
        SELECT COUNT(*) AS c FROM tickets
        WHERE tenant_id = ? AND resolved_at IS NOT NULL AND date(resolved_at) = ?
        """,
        (tenant_id, metric_date),
    ).fetchone()["c"]
    return {"tickets_opened": int(opened or 0), "tickets_resolved": int(resolved or 0)}


def _stock_movements_day(cursor, tenant_id: int, metric_date: str) -> dict[str, int]:
    row = cursor.execute(
        """
        SELECT COUNT(*) AS n, COALESCE(SUM(ABS(delta)), 0) AS units
        FROM stock_movements
        WHERE tenant_id = ? AND date(created_at) = ?
        """,
        (tenant_id, metric_date),
    ).fetchone()
    return {"stock_movement_lines": int(row["n"] or 0), "stock_units_moved": int(row["units"] or 0)}


def _top_products_day(cursor, tenant_id: int, metric_date: str, limit: int = 5) -> list[dict[str, Any]]:
    rows = cursor.execute(
        """
        SELECT p.id, p.name,
               SUM(oi.quantity) AS qty,
               SUM(oi.quantity * oi.unit_price) AS rev
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id AND p.tenant_id = o.tenant_id
        WHERE o.tenant_id = ? AND date(o.created_at) = ? AND o.status != 'iptal'
        GROUP BY p.id
        ORDER BY rev DESC
        LIMIT ?
        """,
        (tenant_id, metric_date, limit),
    ).fetchall()
    return [
        {"product_id": r["id"], "name": r["name"], "qty": int(r["qty"] or 0), "revenue": round(float(r["rev"] or 0), 2)}
        for r in rows
    ]


def upsert_metrics_for_date(tenant_id: int, metric_date: str) -> None:
    """Belirli bir gün için tenant_daily_metrics satırını hesaplar ve yazar."""
    conn = get_connection()
    cursor = conn.cursor()
    o = _orders_day_stats(cursor, tenant_id, metric_date)
    t = _tickets_day_stats(cursor, tenant_id, metric_date)
    sm = _stock_movements_day(cursor, tenant_id, metric_date)
    top = _top_products_day(cursor, tenant_id, metric_date)

    metrics_json = {
        "by_status": o["by_status"],
        "tickets": t,
        "stock_movements": sm,
        "top_products": top,
    }
    cursor.execute(
        """
        INSERT INTO tenant_daily_metrics (
            tenant_id, metric_date, order_count, revenue, cancelled_count,
            avg_order_value, metrics_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tenant_id, metric_date) DO UPDATE SET
            order_count = excluded.order_count,
            revenue = excluded.revenue,
            cancelled_count = excluded.cancelled_count,
            avg_order_value = excluded.avg_order_value,
            metrics_json = excluded.metrics_json,
            computed_at = datetime('now', 'localtime')
        """,
        (
            tenant_id,
            metric_date,
            o["order_count"],
            o["revenue"],
            o["cancelled_count"],
            o["avg_order_value"],
            json.dumps(metrics_json, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()


def rollup_yesterday_for_tenant(tenant_id: int, day: date | None = None) -> str:
    """Dün (veya verilen gün) için rollup; ISO tarih döner."""
    d = day or (date.today() - timedelta(days=1))
    s = d.isoformat()
    upsert_metrics_for_date(tenant_id, s)
    return s


def active_tenant_ids() -> list[int]:
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT DISTINCT tenant_id FROM users WHERE is_active = 1"
        ).fetchall()
        conn.close()
        ids = [int(r["tenant_id"]) for r in rows] if rows else []
        return ids if ids else [1]
    except Exception:
        return [1]


def rollup_yesterday_all_tenants() -> None:
    y = date.today() - timedelta(days=1)
    for tid in active_tenant_ids():
        try:
            upsert_metrics_for_date(tid, y.isoformat())
        except Exception as e:
            print(f"[rollup] tenant={tid} date={y}: {e}")


def backfill_tenant_metrics(tenant_id: int | None = None) -> int:
    """orders tablosundaki tarihler için eksik metrik satırlarını doldurur; işlenen gün sayısı."""
    conn = get_connection()
    cursor = conn.cursor()
    q = """
        SELECT DISTINCT o.tenant_id AS tid, date(o.created_at) AS d
        FROM orders o
    """
    params: tuple[Any, ...] = ()
    if tenant_id is not None:
        q += " WHERE o.tenant_id = ?"
        params = (tenant_id,)
    q += " ORDER BY tid, d"
    pairs = cursor.execute(q, params).fetchall()
    conn.close()

    seen: set[tuple[int, str]] = set()
    n = 0
    for r in pairs:
        tid, d = int(r["tid"]), str(r["d"])
        key = (tid, d)
        if key in seen:
            continue
        seen.add(key)
        try:
            upsert_metrics_for_date(tid, d)
            n += 1
        except Exception as e:
            print(f"[backfill] skip {tid} {d}: {e}")
    return n


def write_naive_forecasts_for_tenant(tenant_id: int, horizon_days: int = 7) -> None:
    """Son metriklerden basit ortalama ile ileri tarih tahmini yazar (payload_json)."""
    conn = get_connection()
    cursor = conn.cursor()
    end_d = date.today() - timedelta(days=1)
    start_d = end_d - timedelta(days=13)
    rows = cursor.execute(
        """
        SELECT metric_date, revenue, order_count
        FROM tenant_daily_metrics
        WHERE tenant_id = ? AND metric_date >= ? AND metric_date <= ?
        ORDER BY metric_date ASC
        """,
        (tenant_id, start_d.isoformat(), end_d.isoformat()),
    ).fetchall()
    if not rows:
        conn.close()
        return
    revs = [float(r["revenue"] or 0) for r in rows]
    ords = [int(r["order_count"] or 0) for r in rows]
    avg_rev = sum(revs) / len(revs) if revs else 0.0
    avg_ord = sum(ords) / len(ords) if ords else 0.0

    cursor.execute(
        """
        DELETE FROM tenant_daily_forecasts
        WHERE tenant_id = ? AND forecast_for_date > date('now', 'localtime')
        """,
        (tenant_id,),
    )

    today = date.today()
    for i in range(1, horizon_days + 1):
        target = (today + timedelta(days=i)).isoformat()
        payload = {
            "predicted_revenue": round(avg_rev, 2),
            "predicted_orders": round(avg_ord, 1),
            "method": "rolling_mean",
            "basis_days": len(rows),
        }
        cursor.execute(
            """
            INSERT INTO tenant_daily_forecasts (
                tenant_id, forecast_for_date, horizon_days, payload_json
            ) VALUES (?, ?, ?, ?)
            """,
            (tenant_id, target, horizon_days, json.dumps(payload, ensure_ascii=False)),
        )
    conn.commit()
    conn.close()


def refresh_forecasts_all_tenants(horizon_days: int = 7) -> None:
    for tid in active_tenant_ids():
        try:
            write_naive_forecasts_for_tenant(tid, horizon_days=horizon_days)
        except Exception as e:
            print(f"[forecast] tenant={tid}: {e}")
