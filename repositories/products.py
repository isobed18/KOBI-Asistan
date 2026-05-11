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


def search_products(query: str, tenant_id: int = 1, threshold: float = 0.38, limit: int = 5) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, name, category, price, stock_quantity, low_stock_threshold
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

