from __future__ import annotations

from difflib import SequenceMatcher

from database.db import get_connection


TR_MAP = str.maketrans({
    "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
})


def normalize_name(value: str) -> str:
    return " ".join((value or "").translate(TR_MAP).lower().split())


def fuzzy_score(query: str, name: str) -> float:
    q = normalize_name(query)
    n = normalize_name(name)
    if not q or not n:
        return 0.0
    if q == n:
        return 1.0
    if q in n or n in q:
        return 0.95

    q_words = q.split()
    n_words = n.split()
    hits = 0.0
    for qw in q_words:
        best = 0.0
        for nw in n_words:
            if qw == nw:
                best = max(best, 1.0)
            elif len(qw) >= 4 and (nw.startswith(qw[:4]) or qw.startswith(nw[:4])):
                best = max(best, 0.86)
            elif len(qw) >= 3 and (qw in nw or nw in qw):
                best = max(best, 0.72)
            else:
                best = max(best, SequenceMatcher(None, qw, nw).ratio() * 0.65)
        hits += best

    word_score = hits / max(len(q_words), 1)
    seq_score = SequenceMatcher(None, q, n).ratio()
    return max(word_score, seq_score * 0.78)


def list_products(
    tenant_id: int = 1,
    category: str | None = None,
    critical_only: bool = False,
    search: str | None = None,
    limit: int = 100,
    in_stock_only: bool = False,
    order_by: str = "name",
) -> list[dict]:
    conn = get_connection()
    q = "SELECT * FROM products WHERE is_active = 1 AND tenant_id = ?"
    params: list = [tenant_id]
    if category:
        q += " AND category = ?"
        params.append(category)
    if critical_only:
        q += " AND stock_quantity <= low_stock_threshold"
    if in_stock_only:
        q += " AND stock_quantity > 0"
    if search and str(search).strip():
        q += " AND name LIKE ?"
        params.append(f"%{str(search).strip()}%")
    ob = "id ASC" if order_by == "id" else "name ASC"
    q += f" ORDER BY {ob} LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_product(product_id: int, tenant_id: int = 1) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM products WHERE id = ? AND tenant_id = ? AND is_active = 1",
        (product_id, tenant_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def search_products(query: str, tenant_id: int = 1, threshold: float = 0.38, limit: int = 5) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, name, category, price, stock_quantity, low_stock_threshold,
               description, ingredients, allergens, size_guide, advisory_notes
        FROM products
        WHERE is_active = 1 AND tenant_id = ?
        """,
        (tenant_id,),
    ).fetchall()
    conn.close()

    scored: list[tuple[float, dict]] = []
    for row in rows:
        score = fuzzy_score(query, row["name"])
        if score >= threshold:
            item = dict(row)
            item["match_score"] = round(score, 3)
            scored.append((score, item))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in scored[:limit]]


def update_stock(product_id: int, delta: int, reason: str, tenant_id: int = 1) -> dict:
    conn = get_connection()
    row = conn.execute(
        "SELECT id, name, stock_quantity FROM products WHERE id = ? AND tenant_id = ? AND is_active = 1",
        (product_id, tenant_id),
    ).fetchone()
    if not row:
        conn.close()
        return {"hata": f"Urun #{product_id} bulunamadi."}

    before = int(row["stock_quantity"])
    after = before + int(delta)
    if after < 0:
        conn.close()
        return {"hata": f"Stok sifirin altina dusmez. Mevcut: {before}, delta: {delta}"}

    conn.execute(
        "UPDATE products SET stock_quantity = ? WHERE id = ? AND tenant_id = ?",
        (after, product_id, tenant_id),
    )
    conn.execute(
        """
        INSERT INTO stock_movements (tenant_id, product_id, delta, reason, before_qty, after_qty)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (tenant_id, product_id, int(delta), reason, before, after),
    )
    conn.commit()
    conn.close()
    return {
        "basari": True,
        "urun_id": product_id,
        "urun": row["name"],
        "onceki_stok": before,
        "yeni_stok": after,
        "delta": int(delta),
        "neden": reason,
    }


def patch_product(product_id: int, tenant_id: int, fields: dict) -> dict:
    """Kısmi ürün güncellemesi; yalnızca `fields` içindeki anahtarlar güncellenir."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM products WHERE id = ? AND is_active = 1 AND tenant_id = ?",
        (product_id, tenant_id),
    ).fetchone()
    if not row:
        conn.close()
        return {"hata": f"Urun #{product_id} bulunamadi."}

    current = dict(row)
    old_stock = int(current["stock_quantity"])

    if "name" in fields and not (fields.get("name") or "").strip():
        conn.close()
        return {"hata": "Urun adi bos olamaz."}
    if "stock_quantity" in fields and int(fields["stock_quantity"]) < 0:
        conn.close()
        return {"hata": "Stok miktari 0'in altina dusemez."}
    if "low_stock_threshold" in fields and int(fields["low_stock_threshold"]) < 0:
        conn.close()
        return {"hata": "Esik degeri negatif olamaz."}
    if "price" in fields and float(fields["price"]) < 0:
        conn.close()
        return {"hata": "Fiyat negatif olamaz."}

    sets: list[str] = []
    params: list = []
    if "name" in fields:
        sets.append("name = ?")
        params.append((fields["name"] or "").strip())
    if "category" in fields:
        sets.append("category = ?")
        v = fields["category"]
        params.append(v if v is not None else None)
    if "price" in fields:
        sets.append("price = ?")
        params.append(float(fields["price"]))
    if "stock_quantity" in fields:
        sets.append("stock_quantity = ?")
        params.append(int(fields["stock_quantity"]))
    if "low_stock_threshold" in fields:
        sets.append("low_stock_threshold = ?")
        params.append(int(fields["low_stock_threshold"]))
    for text_field in ("description", "ingredients", "allergens", "size_guide", "advisory_notes"):
        if text_field in fields:
            sets.append(f"{text_field} = ?")
            params.append(fields[text_field])

    if not sets:
        conn.close()
        return {"hata": "Guncellenecek alan yok."}

    params.extend([product_id, tenant_id])
    conn.execute(
        f"UPDATE products SET {', '.join(sets)} WHERE id = ? AND tenant_id = ?",
        params,
    )

    if "stock_quantity" in fields:
        new_stock = int(fields["stock_quantity"])
        delta = new_stock - old_stock
        if delta != 0:
            conn.execute(
                """
                INSERT INTO stock_movements (tenant_id, product_id, delta, reason, before_qty, after_qty)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    product_id,
                    delta,
                    "tablo duzenleme",
                    old_stock,
                    new_stock,
                ),
            )

    conn.commit()
    updated = conn.execute(
        "SELECT * FROM products WHERE id = ? AND tenant_id = ?",
        (product_id, tenant_id),
    ).fetchone()
    conn.close()
    return {"basari": True, "urun": dict(updated)}


def deactivate_product(product_id: int, tenant_id: int) -> dict:
    """Soft delete (is_active = 0)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, name FROM products WHERE id = ? AND is_active = 1 AND tenant_id = ?",
        (product_id, tenant_id),
    ).fetchone()
    if not row:
        conn.close()
        return {"hata": f"Urun #{product_id} bulunamadi."}
    conn.execute(
        "UPDATE products SET is_active = 0 WHERE id = ? AND tenant_id = ?",
        (product_id, tenant_id),
    )
    conn.commit()
    conn.close()
    return {"basari": True, "urun_id": product_id, "isim": row["name"]}

