from __future__ import annotations

from collections import defaultdict

from database.db import get_connection

COMPLETION_STATUSES = {"kargoda", "teslim_edildi", "tamamlandi", "tamamlandı"}

NON_EDITABLE_STATUSES = {"iptal", "teslim_edildi", "tamamlandi", "tamamlandı"}

# ---------------------------------------------------------------------------
# Okuma fonksiyonları
# ---------------------------------------------------------------------------

def _orders_where(
    tenant_id: int,
    status: str | None,
    search: str | None,
    today: bool,
) -> tuple[str, list]:
    q = "FROM orders WHERE tenant_id = ?"
    params: list = [tenant_id]
    if status:
        q += " AND status = ?"
        params.append(status)
    if today:
        q += " AND DATE(created_at) = DATE('now', 'localtime')"
    if search and search.strip():
        term = f"%{search.strip()}%"
        q += """ AND (
            customer_name LIKE ? OR IFNULL(customer_phone, '') LIKE ?
            OR IFNULL(tracking_code, '') LIKE ? OR CAST(id AS TEXT) LIKE ?
        )"""
        params.extend([term, term, term, term])
    return q, params


def count_orders(
    tenant_id: int = 1,
    status: str | None = None,
    search: str | None = None,
    today: bool = False,
) -> int:
    conn = get_connection()
    where, params = _orders_where(tenant_id, status, search, today)
    row = conn.execute(f"SELECT COUNT(*) AS c {where}", params).fetchone()
    conn.close()
    return int(row["c"] if row else 0)


def list_orders(
    tenant_id: int = 1,
    status: str | None = None,
    search: str | None = None,
    today: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    conn = get_connection()
    where, params = _orders_where(tenant_id, status, search, today)
    q = f"SELECT * {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params = [*params, limit, offset]
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_order(order_id: int, tenant_id: int = 1) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM orders WHERE id = ? AND tenant_id = ?", (order_id, tenant_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_order_enriched(order_id: int, tenant_id: int = 1) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM orders WHERE id = ? AND tenant_id = ?",
            (order_id, tenant_id),
        ).fetchone()
        if not row:
            return None
        return _enrich_order_row(conn, row)
    finally:
        conn.close()


def get_order_items(order_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT oi.*, p.name AS product_name FROM order_items oi
           JOIN products p ON p.id = oi.product_id
           WHERE oi.order_id = ?""",
        (order_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _enrich_order_row(conn, row) -> dict:
    order = dict(row)
    items_rows = conn.execute(
        """
        SELECT oi.product_id, p.name AS product_name,
               oi.quantity, oi.unit_price,
               (oi.quantity * oi.unit_price) AS subtotal
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ?
        """,
        (order["id"],),
    ).fetchall()
    order["items"] = [dict(i) for i in items_rows]
    return order


def fetch_orders_page_enriched(
    tenant_id: int = 1,
    status: str | None = None,
    search: str | None = None,
    today: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    conn = get_connection()
    try:
        where, params = _orders_where(tenant_id, status, search, today)
        total = int(conn.execute(f"SELECT COUNT(*) AS c {where}", params).fetchone()["c"])
        q = f"SELECT * {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        rows = conn.execute(q, [*params, limit, offset]).fetchall()
        items = [_enrich_order_row(conn, r) for r in rows]
        return items, total
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Yazma fonksiyonları
# ---------------------------------------------------------------------------

# update_order_status: kargo/not alanları gönderilmediyse SQL'de dokunulmaz
UNSET = object()


def _stock_already_deducted(conn, order_id: int, tenant_id: int) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM stock_movements
        WHERE tenant_id = ?
          AND reason LIKE ?
        LIMIT 1
        """,
        (tenant_id, f"%Siparis #{order_id}%"),
    ).fetchone()
    return bool(row)


def _deduct_stock_for_order(conn, order_id: int, tenant_id: int, reason_status: str) -> list[str]:
    if _stock_already_deducted(conn, order_id, tenant_id):
        return ["Bu siparis icin stok daha once dusulmus; tekrar dusulmedi."]

    items = conn.execute(
        """
        SELECT oi.product_id, oi.quantity, p.name, p.stock_quantity
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ? AND p.tenant_id = ?
        """,
        (order_id, tenant_id),
    ).fetchall()

    warnings: list[str] = []
    for item in items:
        before = int(item["stock_quantity"])
        qty = int(item["quantity"])
        after = before - qty
        if after < 0:
            warnings.append(f"{item['name']}: stok yetersiz (mevcut {before}, gereken {qty})")
            after = 0

        conn.execute(
            "UPDATE products SET stock_quantity = ? WHERE id = ? AND tenant_id = ?",
            (after, item["product_id"], tenant_id),
        )
        conn.execute(
            """
            INSERT INTO stock_movements (tenant_id, product_id, delta, reason, before_qty, after_qty)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                item["product_id"],
                -qty,
                f"Siparis #{order_id} {reason_status} event",
                before,
                after,
            ),
        )
    return warnings


def update_order_status(
    order_id: int,
    status: str,
    tenant_id: int = 1,
    cargo_tracking_code: str | None | object = UNSET,
    cargo_company: str | None | object = UNSET,
    notes: str | None | object = UNSET,
) -> dict:
    conn = get_connection()
    order = conn.execute(
        "SELECT id, status, customer_name FROM orders WHERE id = ? AND tenant_id = ?",
        (order_id, tenant_id),
    ).fetchone()
    if not order:
        conn.close()
        return {"hata": f"Siparis #{order_id} bulunamadi."}

    fields = ["status = ?", "updated_at = datetime('now', 'localtime')"]
    params: list = [status]
    if cargo_tracking_code is not UNSET:
        fields.append("cargo_tracking_code = ?")
        params.append(cargo_tracking_code if cargo_tracking_code else None)
    if cargo_company is not UNSET:
        fields.append("cargo_company = ?")
        params.append(cargo_company if cargo_company else None)
    if notes is not UNSET:
        fields.append("notes = ?")
        params.append(notes)
    params.extend([order_id, tenant_id])

    conn.execute(
        f"UPDATE orders SET {', '.join(fields)} WHERE id = ? AND tenant_id = ?",
        params,
    )

    stock_warnings: list[str] = []
    if status in COMPLETION_STATUSES:
        stock_warnings = _deduct_stock_for_order(conn, order_id, tenant_id, status)

    conn.commit()
    conn.close()
    result = {
        "basari": True,
        "siparis_no": order_id,
        "musteri": order["customer_name"],
        "eski_durum": order["status"],
        "yeni_durum": status,
        "kargo_kodu": None if cargo_tracking_code is UNSET else (cargo_tracking_code or None),
        "kargo_firmasi": None if cargo_company is UNSET else (cargo_company or None),
    }
    if stock_warnings:
        result["stok_uyarilari"] = stock_warnings
    return result


def _apply_stock_delta(
    conn,
    tenant_id: int,
    product_id: int,
    delta: int,
    reason: str,
) -> None:
    """delta negative = çıkış, pozitif = giriş."""
    row = conn.execute(
        "SELECT stock_quantity FROM products WHERE id = ? AND tenant_id = ?",
        (product_id, tenant_id),
    ).fetchone()
    if not row:
        raise ValueError(f"Urun #{product_id} bulunamadi.")
    before = int(row["stock_quantity"])
    after = before + delta
    if after < 0:
        after = 0
    conn.execute(
        "UPDATE products SET stock_quantity = ? WHERE id = ? AND tenant_id = ?",
        (after, product_id, tenant_id),
    )
    conn.execute(
        """
        INSERT INTO stock_movements (tenant_id, product_id, delta, reason, before_qty, after_qty)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (tenant_id, product_id, delta, reason, before, after),
    )


def deduct_stock_on_order_created(conn, order_id: int, tenant_id: int) -> None:
    """Sipariş satırlarına göre stok düşer; hareket nedeni olusturma (durum güncellemesinde çift düşümü engeller)."""
    items = conn.execute(
        """
        SELECT oi.product_id, SUM(oi.quantity) AS quantity, MAX(p.stock_quantity) AS stock_quantity
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id AND p.tenant_id = ?
        WHERE oi.order_id = ?
        GROUP BY oi.product_id
        """,
        (tenant_id, order_id),
    ).fetchall()
    for item in items:
        qty = int(item["quantity"])
        cur = int(item["stock_quantity"])
        if cur < qty:
            raise ValueError(
                f"Urun #{item['product_id']} icin yeterli stok yok. Mevcut: {cur}"
            )
        _apply_stock_delta(
            conn,
            tenant_id,
            int(item["product_id"]),
            -qty,
            f"Siparis #{order_id} olusturma",
        )


def delete_order_and_restore_stock(order_id: int, tenant_id: int = 1) -> dict:
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        order = conn.execute(
            "SELECT id FROM orders WHERE id = ? AND tenant_id = ?",
            (order_id, tenant_id),
        ).fetchone()
        if not order:
            conn.rollback()
            return {"hata": f"Siparis #{order_id} bulunamadi."}

        rows = conn.execute(
            """
            SELECT oi.product_id, oi.quantity
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id AND p.tenant_id = ?
            WHERE oi.order_id = ?
            """,
            (tenant_id, order_id),
        ).fetchall()

        for r in rows:
            pid = int(r["product_id"])
            qty = int(r["quantity"])
            _apply_stock_delta(
                conn,
                tenant_id,
                pid,
                qty,
                f"Siparis #{order_id} silme",
            )

        conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        conn.execute(
            "DELETE FROM orders WHERE id = ? AND tenant_id = ?",
            (order_id, tenant_id),
        )
        conn.commit()
        return {"basari": True, "siparis_no": order_id}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def patch_order(
    order_id: int,
    tenant_id: int = 1,
    customer_name: str | None = None,
    customer_phone: str | None = None,
    notes: str | None = None,
    created_at: str | None = None,
    items: list[dict] | None = None,
) -> dict:
    """
    items: [{"product_id": int, "quantity": int}] — verilirse kalemler tamamen yenilenir.
    Tamamlanmış / iptal durumunda kalem güncellemesi reddedilir; müşteri, not ve created_at güncellenebilir.
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        order = conn.execute(
            "SELECT id, status FROM orders WHERE id = ? AND tenant_id = ?",
            (order_id, tenant_id),
        ).fetchone()
        if not order:
            conn.rollback()
            return {"hata": f"Siparis #{order_id} bulunamadi."}
        if order["status"] in NON_EDITABLE_STATUSES and items is not None:
            conn.rollback()
            return {
                "hata": "Bu durumdaki siparis kalemleri guncellenemez.",
            }

        fields: list[str] = []
        params: list = []
        if customer_name is not None:
            fields.append("customer_name = ?")
            params.append(customer_name)
        if customer_phone is not None:
            fields.append("customer_phone = ?")
            params.append(customer_phone)
        if notes is not None:
            fields.append("notes = ?")
            params.append(notes)
        if created_at is not None:
            ca = (created_at or "").strip().replace("T", " ")
            if len(ca) == 16 and ca.count(":") == 1:
                ca += ":00"
            fields.append("created_at = ?")
            params.append(ca)

        if items is not None:
            if not items:
                conn.rollback()
                return {"hata": "Siparis en az bir kalem icermelidir."}

            new_lines: dict[int, int] = defaultdict(int)
            for it in items:
                pid = int(it["product_id"])
                q = int(it["quantity"])
                if q < 1:
                    conn.rollback()
                    return {"hata": "Adet 1 veya daha buyuk olmalidir."}
                new_lines[pid] += q

            old_rows = conn.execute(
                """
                SELECT oi.product_id, oi.quantity
                FROM order_items oi
                JOIN products p ON p.id = oi.product_id AND p.tenant_id = ?
                WHERE oi.order_id = ?
                """,
                (tenant_id, order_id),
            ).fetchall()
            old_lines: dict[int, int] = defaultdict(int)
            for r in old_rows:
                old_lines[int(r["product_id"])] += int(r["quantity"])

            all_pids = set(old_lines) | set(new_lines)
            for pid in all_pids:
                old_q = int(old_lines.get(pid, 0))
                new_q = int(new_lines.get(pid, 0))
                need_extra = new_q - old_q
                if need_extra <= 0:
                    continue
                pr = conn.execute(
                    """
                    SELECT id, price, stock_quantity, name FROM products
                    WHERE id = ? AND tenant_id = ? AND is_active = 1
                    """,
                    (pid, tenant_id),
                ).fetchone()
                if not pr:
                    conn.rollback()
                    return {"hata": f"Urun #{pid} bulunamadi veya pasif."}
                if int(pr["stock_quantity"]) < need_extra:
                    conn.rollback()
                    return {
                        "hata": (
                            f"Urun #{pid} ({pr['name']}) icin yeterli stok yok. "
                            f"Mevcut: {pr['stock_quantity']}, ek gereken: {need_extra}"
                        ),
                    }

            total = 0.0
            for pid, new_q in new_lines.items():
                pr = conn.execute(
                    "SELECT price FROM products WHERE id = ? AND tenant_id = ? AND is_active = 1",
                    (pid, tenant_id),
                ).fetchone()
                if not pr:
                    conn.rollback()
                    return {"hata": f"Urun #{pid} bulunamadi veya pasif."}
                price = float(pr["price"])
                total += price * new_q

            for pid in all_pids:
                old_q = int(old_lines.get(pid, 0))
                new_q = int(new_lines.get(pid, 0))
                diff = new_q - old_q
                if diff == 0:
                    continue
                _apply_stock_delta(
                    conn,
                    tenant_id,
                    pid,
                    -diff,
                    f"Siparis #{order_id} kalem guncelleme",
                )

            conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
            for pid, new_q in new_lines.items():
                pr = conn.execute(
                    "SELECT price FROM products WHERE id = ? AND tenant_id = ?",
                    (pid, tenant_id),
                ).fetchone()
                unit = float(pr["price"])
                conn.execute(
                    """
                    INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                    VALUES (?, ?, ?, ?)
                    """,
                    (order_id, pid, new_q, unit),
                )

            fields.append("total_price = ?")
            params.append(total)

        if not fields:
            conn.rollback()
            return {"hata": "Guncellenecek alan yok."}

        fields.append("updated_at = datetime('now', 'localtime')")
        params.extend([order_id, tenant_id])
        conn.execute(
            f"UPDATE orders SET {', '.join(fields)} WHERE id = ? AND tenant_id = ?",
            params,
        )
        conn.commit()
        return {"basari": True, "siparis_no": order_id}
    except ValueError as e:
        conn.rollback()
        return {"hata": str(e)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

