from __future__ import annotations

from database.db import get_connection


COMPLETION_STATUSES = {"kargoda", "teslim_edildi", "tamamlandi", "tamamlandı"}


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
    cargo_tracking_code: str | None = None,
    cargo_company: str | None = None,
    notes: str | None = None,
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
    if cargo_tracking_code:
        fields.append("cargo_tracking_code = ?")
        params.append(cargo_tracking_code)
    if cargo_company:
        fields.append("cargo_company = ?")
        params.append(cargo_company)
    if notes:
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
        "kargo_kodu": cargo_tracking_code,
        "kargo_firmasi": cargo_company,
    }
    if stock_warnings:
        result["stok_uyarilari"] = stock_warnings
    return result

