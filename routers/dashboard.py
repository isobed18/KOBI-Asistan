"""
Dashboard Router — Yönetici Paneli için Toplu KPI Verisi
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from datetime import date, datetime, timedelta
import asyncio
import json
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import get_connection
from database.schemas import CargoShipmentCreate, CargoShipmentPatch
from agent.tenant_config import tenant_public_payload
from repositories.orders import deduct_stock_on_order_created, delete_order_and_restore_stock
from routers.auth_router import CurrentUser, get_current_user
from services.cargo_intervention import CARGO_DELAY_STATUSES, create_cargo_delay_ticket_for_order

# ---------------------------------------------------------------------------
# AI Tasks cache (15 dakika TTL)
# ---------------------------------------------------------------------------
_ai_tasks_cache: dict | None = None
_ai_tasks_ts: float = 0
_AI_TASKS_TTL = 900  # 15 dakika

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _parse_estimated_delivery_date(val) -> date | None:
    """SQLite cargo_tracking.estimated_delivery: date veya datetime string."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            y, m, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
            return date(y, m, d)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _is_delayed_by_eta(estimated_delivery) -> bool:
    d = _parse_estimated_delivery_date(estimated_delivery)
    if d is None:
        return False
    return d < date.today()


class CargoDelayBildirRequest(BaseModel):
    order_id: int


def _build_live_briefing(
    *,
    as_of_date: str,
    today_new_orders: int,
    by_status: dict,
    critical_stock_count: int,
    delayed_cargo_count: int,
) -> dict:
    """LLM gerektirmeden Genel Bakış AI brifingi için anlık Türkçe özet."""
    haz = int(by_status.get("hazırlanıyor", 0) or 0)
    karg = int(by_status.get("kargoda", 0) or 0)
    s = int(critical_stock_count)
    d = int(delayed_cargo_count)
    tnew = int(today_new_orders)

    p1 = (
        f"Bugün {tnew} yeni sipariş kaydı. {haz} sipariş hazırlanıyor "
        f"(kargoya verilmeyi bekliyor), {karg} sipariş kargoda."
    )
    p2 = f"{s} ürün stok eşiği veya altında."
    if d:
        p2 += f" {d} kargo sevkiyatında gecikme veya risk uyarısı."

    return {
        "as_of_date": as_of_date,
        "source": "live_db",
        "counts": {
            "today_new_orders": tnew,
            "hazirlaniyor": haz,
            "kargoya_verilebilir": haz,
            "kargoda": karg,
            "kritik_stok_urun": s,
            "kargo_gecikme": d,
        },
        "paragraphs": [p1, p2],
        "lead": f"{p1} {p2}",
    }


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

    delayed = [
        r for r in cargo_rows
        if r["current_status"] in ("Şubede Bekliyor", "Gecikti", "İade Sürecinde")
        or _is_delayed_by_eta(r["estimated_delivery"])
    ]

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

    today_orders_row = cursor.execute(
        """
        SELECT COUNT(*) AS c FROM orders
        WHERE tenant_id = ? AND date(created_at) = date('now', 'localtime')
        """,
        (tenant_id,),
    ).fetchone()
    today_new_orders = int(today_orders_row["c"] if today_orders_row else 0)

    cancelled_today_count_row = cursor.execute(
        """
        SELECT COUNT(*) AS c FROM orders
        WHERE tenant_id = ? AND status = 'iptal'
          AND date(updated_at) = date('now', 'localtime')
        """,
        (tenant_id,),
    ).fetchone()
    cancelled_today_count = int(cancelled_today_count_row["c"] if cancelled_today_count_row else 0)

    cancelled_today_rows = cursor.execute(
        """
        SELECT id, customer_name, customer_phone, total_price, tracking_code, updated_at, notes
        FROM orders
        WHERE tenant_id = ? AND status = 'iptal'
          AND date(updated_at) = date('now', 'localtime')
        ORDER BY updated_at DESC
        LIMIT 50
        """,
        (tenant_id,),
    ).fetchall()

    preparing_rows = cursor.execute(
        """
        SELECT id, customer_name, customer_phone, total_price, tracking_code, created_at, updated_at, notes
        FROM orders
        WHERE tenant_id = ? AND status = 'hazırlanıyor'
        ORDER BY datetime(created_at) ASC
        LIMIT 50
        """,
        (tenant_id,),
    ).fetchall()

    # Son rapor (kiracıya özel; bugün veya en son)
    latest_report = cursor.execute("""
        SELECT id, tenant_id, date, report_text, briefing_json, raw_data, model_version, source, created_at
        FROM daily_reports
        WHERE tenant_id = ?
        ORDER BY created_at DESC
        LIMIT 1
    """, (tenant_id,)).fetchone()

    lr_out = None
    if latest_report:
        lr_out = dict(latest_report)
        bj = lr_out.get("briefing_json")
        if bj:
            try:
                lr_out["briefing"] = json.loads(bj)
            except Exception:
                lr_out["briefing"] = None

    yday = (date.today() - timedelta(days=1)).isoformat()
    yesterday_metrics = cursor.execute(
        """
        SELECT metric_date, order_count, revenue, cancelled_count, avg_order_value, metrics_json, computed_at
        FROM tenant_daily_metrics
        WHERE tenant_id = ? AND metric_date = ?
        """,
        (tenant_id, yday),
    ).fetchone()

    forecast_rows = cursor.execute(
        """
        SELECT forecast_for_date, payload_json, generated_at
        FROM tenant_daily_forecasts
        WHERE tenant_id = ? AND forecast_for_date > date('now', 'localtime')
        ORDER BY forecast_for_date ASC, generated_at DESC
        """,
        (tenant_id,),
    ).fetchall()
    forecast_by_date: dict = {}
    for r in forecast_rows:
        fd = r["forecast_for_date"]
        if fd in forecast_by_date:
            continue
        try:
            payload = json.loads(r["payload_json"])
        except Exception:
            payload = {}
        forecast_by_date[fd] = {
            "forecast_for_date": fd,
            "payload": payload,
            "generated_at": r["generated_at"],
        }
    forecast_week = sorted(forecast_by_date.values(), key=lambda x: x["forecast_for_date"])[:7]

    live_briefing = _build_live_briefing(
        as_of_date=date.today().isoformat(),
        today_new_orders=today_new_orders,
        by_status=by_status,
        critical_stock_count=len(low_stock),
        delayed_cargo_count=len(delayed),
    )

    conn.close()

    return {
        "tenant": tenant_public_payload(tenant_id),
        "live_briefing": live_briefing,
        "orders": {
            "total": len(orders),
            "by_status": by_status,
            "total_revenue": round(total_revenue, 2),
            "pending": by_status.get("hazırlanıyor", 0),
            "in_cargo": by_status.get("kargoda", 0),
            "delivered": by_status.get("teslim_edildi", 0),
            "cancelled": by_status.get("iptal", 0),
            "cancelled_today": [dict(r) for r in cancelled_today_rows],
            "cancelled_today_count": cancelled_today_count,
            "preparing_orders": [dict(r) for r in preparing_rows],
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
        "latest_report": lr_out,
        "yesterday_metrics": dict(yesterday_metrics) if yesterday_metrics else None,
        "forecast_week": forecast_week,
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
                "title": f"{d['name']} hem satılıyor hem kritik stokta",
                "body": f"Stok {d['stock_quantity']}, eşik {d['low_stock_threshold']}. Yenileme öncelikli.",
                "priority": "high",
            })
    for o in large_orders:
        d = dict(o)
        risks.append({
            "type": "large_order_review",
            "title": f"Sipariş #{d['id']} insan onayı gerektirebilir",
            "body": f"{d['customer_name']} için {d['total_items']} adet / {d['total_price']} TL sipariş.",
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
            o.cargo_delay_bildirildi_at AS delay_bildirildi_at,
            ct.current_status AS cargo_status,
            ct.estimated_delivery,
            ct.last_update    AS cargo_last_update
        FROM orders o
        LEFT JOIN cargo_tracking ct ON ct.tracking_code = o.cargo_tracking_code
        WHERE o.status = 'kargoda' AND o.tenant_id = ?
        ORDER BY o.updated_at DESC
    """, (tenant_id,)).fetchall()

    result = []
    for r in rows:
        d = dict(r)
        d["is_delayed"] = _is_delayed_by_eta(d.get("estimated_delivery"))
        result.append(d)

    conn.close()
    return {
        "total": len(result),
        "delayed_count": sum(1 for r in result if r["is_delayed"]),
        "shipments": result,
    }


@router.post("/cargo/bildir", summary="Kargo gecikmesi bildirildi olarak kaydet")
def post_cargo_delay_bildir(
    body: CargoDelayBildirRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Siparis satirinda kalici isaret; Kargolar tablosunda 'Bildirildi' olarak kalir."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE orders
        SET cargo_delay_bildirildi_at = datetime('now', 'localtime'),
            updated_at = datetime('now', 'localtime')
        WHERE id = ? AND tenant_id = ? AND status = 'kargoda'
        """,
        (body.order_id, current_user.tenant_id),
    )
    if cursor.rowcount == 0:
        conn.rollback()
        conn.close()
        raise HTTPException(
            status_code=404,
            detail="Sipariş bulunamadı veya artık kargoda değil.",
        )
    conn.commit()
    conn.close()
    return {"ok": True}


def _normalize_sqlite_datetime(s: str | None) -> str | None:
    if s is None:
        return None
    t = (s or "").strip().replace("T", " ")
    if not t:
        return None
    if len(t) == 16 and t.count(":") == 1:
        t += ":00"
    return t


def _ensure_cargo_tracking_row(cursor, tracking_code: str, company: str | None) -> None:
    code = (tracking_code or "").strip()
    if not code:
        return
    row = cursor.execute("SELECT 1 FROM cargo_tracking WHERE tracking_code = ?", (code,)).fetchone()
    if row:
        return
    comp = (company or "").strip() or "Kargo"
    cursor.execute(
        """
        INSERT INTO cargo_tracking (tracking_code, company, current_status, estimated_delivery, last_update)
        VALUES (?, ?, 'Dağıtıma Çıktı', NULL, datetime('now', 'localtime'))
        """,
        (code, comp),
    )


@router.post("/cargo/shipment", summary="Kargoda yeni siparis olustur", status_code=201)
def create_cargo_shipment(
    body: CargoShipmentCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id
    code = (body.cargo_tracking_code or "").strip()
    comp = (body.cargo_company or "").strip()
    if not code or not comp:
        raise HTTPException(status_code=400, detail="Kargo kodu ve firma zorunludur.")
    name = (body.customer_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Musteri adi zorunludur.")

    items_list = list(body.items) if body.items else []

    conn = get_connection()
    cursor = conn.cursor()
    try:
        conn.execute("BEGIN")
        total = 0.0
        item_rows: list[tuple[int, int, float]] = []
        for item in items_list:
            pid = int(item.product_id)
            qty = int(item.quantity)
            if qty < 1:
                raise HTTPException(status_code=400, detail="Adet 1 veya daha buyuk olmalidir.")
            product = cursor.execute(
                """
                SELECT id, price, stock_quantity
                FROM products
                WHERE id = ? AND is_active = 1 AND tenant_id = ?
                """,
                (pid, tenant_id),
            ).fetchone()
            if not product:
                raise HTTPException(status_code=404, detail=f"Urun #{pid} bulunamadi.")
            if int(product["stock_quantity"]) < qty:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Urun #{pid} icin yeterli stok yok. Mevcut: {product['stock_quantity']}"
                    ),
                )
            subtotal = float(product["price"]) * qty
            total += subtotal
            item_rows.append((pid, qty, float(product["price"])))

        notes = body.notes
        if notes is not None:
            notes = (notes or "").strip() or None

        cursor.execute(
            """
            INSERT INTO orders (tenant_id, customer_name, customer_phone, notes, total_price)
            VALUES (?, ?, ?, ?, ?)
            """,
            (tenant_id, name, (body.customer_phone or "").strip() or None, notes, total),
        )
        order_id = int(cursor.lastrowid)

        for product_id, quantity, unit_price in item_rows:
            cursor.execute(
                """
                INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                VALUES (?, ?, ?, ?)
                """,
                (order_id, product_id, quantity, unit_price),
            )

        if item_rows:
            deduct_stock_on_order_created(conn, order_id, tenant_id)

        cursor.execute(
            """
            UPDATE orders
            SET status = 'kargoda',
                cargo_tracking_code = ?,
                cargo_company = ?,
                updated_at = datetime('now', 'localtime')
            WHERE id = ? AND tenant_id = ?
            """,
            (code, comp, order_id, tenant_id),
        )

        est = (body.estimated_delivery or "").strip() or None
        lu = _normalize_sqlite_datetime(body.last_update)
        if not lu:
            lu = cursor.execute("SELECT datetime('now', 'localtime') AS t").fetchone()["t"]

        ex = cursor.execute(
            "SELECT 1 FROM cargo_tracking WHERE tracking_code = ?",
            (code,),
        ).fetchone()
        if ex:
            cursor.execute(
                """
                UPDATE cargo_tracking
                SET company = ?, estimated_delivery = ?, last_update = ?
                WHERE tracking_code = ?
                """,
                (comp, est, lu, code),
            )
        else:
            cursor.execute(
                """
                INSERT INTO cargo_tracking (tracking_code, company, current_status, estimated_delivery, last_update)
                VALUES (?, ?, 'Dağıtıma Çıktı', ?, ?)
                """,
                (code, comp, est, lu),
            )

        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except ValueError as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        conn.close()

    return {"message": "Kargo kaydi olusturuldu.", "order_id": order_id, "total_price": total}


@router.patch("/cargo/shipment/{order_id}", summary="Kargodaki siparisi ve takip bilgisini guncelle")
def patch_cargo_shipment(
    order_id: int,
    body: CargoShipmentPatch,
    current_user: CurrentUser = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id
    if not body.model_dump(exclude_unset=True):
        raise HTTPException(status_code=400, detail="Guncellenecek alan yok.")

    new_delay_status: str | None = None
    conn = get_connection()
    cursor = conn.cursor()
    try:
        conn.execute("BEGIN")
        order = cursor.execute(
            """
            SELECT id, status, customer_name, customer_phone, cargo_tracking_code, cargo_company
            FROM orders WHERE id = ? AND tenant_id = ?
            """,
            (order_id, tenant_id),
        ).fetchone()
        if not order:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Siparis bulunamadi.")
        if order["status"] != "kargoda":
            conn.rollback()
            raise HTTPException(status_code=400, detail="Yalnizca kargodaki siparisler duzenlenebilir.")

        osets: list[str] = []
        oparams: list = []

        if body.customer_name is not None:
            osets.append("customer_name = ?")
            oparams.append((body.customer_name or "").strip())
        if body.customer_phone is not None:
            osets.append("customer_phone = ?")
            v = (body.customer_phone or "").strip()
            oparams.append(v or None)
        if body.cargo_tracking_code is not None:
            osets.append("cargo_tracking_code = ?")
            oparams.append((body.cargo_tracking_code or "").strip() or None)
        if body.cargo_company is not None:
            osets.append("cargo_company = ?")
            oparams.append((body.cargo_company or "").strip() or None)

        if osets:
            osets.append("updated_at = datetime('now', 'localtime')")
            oparams.extend([order_id, tenant_id])
            cursor.execute(
                f"UPDATE orders SET {', '.join(osets)} WHERE id = ? AND tenant_id = ?",
                oparams,
            )

        order2 = cursor.execute(
            """
            SELECT cargo_tracking_code, cargo_company
            FROM orders WHERE id = ? AND tenant_id = ?
            """,
            (order_id, tenant_id),
        ).fetchone()
        tcode = (order2["cargo_tracking_code"] or "").strip() if order2 else ""
        tcomp = (order2["cargo_company"] or "").strip() if order2 else ""

        if any(getattr(body, k) is not None for k in ("cargo_status", "estimated_delivery", "last_update")) or (
            body.cargo_company is not None and tcode
        ):
            if not tcode:
                conn.rollback()
                raise HTTPException(status_code=400, detail="Takip alanlari icin once kargo kodu girin.")

            _ensure_cargo_tracking_row(cursor, tcode, tcomp or None)

            tsets: list[str] = []
            tparams: list = []
            if body.cargo_status is not None:
                tsets.append("current_status = ?")
                tparams.append((body.cargo_status or "").strip() or "—")
            if body.estimated_delivery is not None:
                tsets.append("estimated_delivery = ?")
                ev = (body.estimated_delivery or "").strip() or None
                tparams.append(ev)
            if body.last_update is not None:
                lu = _normalize_sqlite_datetime(body.last_update)
                if lu:
                    tsets.append("last_update = ?")
                    tparams.append(lu)
            if body.cargo_company is not None and tcode:
                tsets.append("company = ?")
                tparams.append((body.cargo_company or "").strip() or "Kargo")
            if tsets:
                tparams.append(tcode)
                cursor.execute(
                    f"UPDATE cargo_tracking SET {', '.join(tsets)} WHERE tracking_code = ?",
                    tparams,
                )

        conn.commit()
        if body.cargo_status is not None:
            st = (body.cargo_status or "").strip() or "—"
            if st in CARGO_DELAY_STATUSES:
                new_delay_status = st
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()

    if new_delay_status is not None:
        c2 = get_connection()
        try:
            o = c2.execute(
                """
                SELECT id, customer_name, customer_phone, cargo_tracking_code
                FROM orders
                WHERE id = ? AND tenant_id = ? AND status = 'kargoda'
                """,
                (order_id, tenant_id),
            ).fetchone()
            if o and (o["cargo_tracking_code"] or "").strip():
                code = (o["cargo_tracking_code"] or "").strip()
                est_row = c2.execute(
                    "SELECT estimated_delivery FROM cargo_tracking WHERE tracking_code = ?",
                    (code,),
                ).fetchone()
                est = est_row["estimated_delivery"] if est_row else None
                create_cargo_delay_ticket_for_order(
                    order_id=int(o["id"]),
                    customer_name=o["customer_name"],
                    customer_phone=o["customer_phone"],
                    cargo_tracking_code=code,
                    cargo_status=new_delay_status,
                    estimated_delivery=est,
                    tenant_id=tenant_id,
                )
        finally:
            c2.close()

    return {"ok": True}


@router.delete("/cargo/shipment/{order_id}", summary="Kargodaki siparisi sil (stok iade)")
def delete_cargo_shipment(
    order_id: int,
    current_user: CurrentUser = Depends(get_current_user),
):
    result = delete_order_and_restore_stock(order_id, tenant_id=current_user.tenant_id)
    if result.get("hata"):
        raise HTTPException(status_code=404, detail=result["hata"])
    return {"ok": True}


@router.get("/sales-chart", summary="Gunluk satis grafigi (canli siparisler)")
def get_sales_chart(
    days: int = 14,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Gunluk siparis sayisi ve gelir — dogrudan `orders` tablosundan (grafik ile KPI tutarli).
    `days`: 7–30 arasi (varsayilan 14).
    """
    from datetime import date, timedelta

    tenant_id = current_user.tenant_id
    span = min(max(int(days), 7), 30)
    lookback = span - 1
    today = date.today()

    conn = get_connection()
    rows = conn.execute(
        f"""
        SELECT
            date(created_at) AS day,
            COUNT(*) AS order_count,
            COALESCE(SUM(CASE WHEN status != 'iptal' THEN total_price ELSE 0 END), 0) AS revenue
        FROM orders
        WHERE created_at >= date('now', '-{lookback} days', 'localtime')
          AND tenant_id = ?
        GROUP BY day
        ORDER BY day ASC
        """,
        (tenant_id,),
    ).fetchall()
    conn.close()

    data_map = {r["day"]: dict(r) for r in rows}
    result = []
    for i in range(lookback, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        result.append(
            {
                "day": d,
                "order_count": int(data_map.get(d, {}).get("order_count", 0) or 0),
                "revenue": round(float(data_map.get(d, {}).get("revenue", 0.0) or 0), 2),
            }
        )
    return {"days": result, "days_span": span}


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
