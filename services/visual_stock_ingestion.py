from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from database.db import get_connection
from repositories.products import normalize_name, search_products_by_visual_description

ROOT = Path(__file__).resolve().parents[1]
UPLOAD_ROOT = ROOT / "static" / "uploads" / "visual-stock"

BUSINESS_MODEL_HINTS = {
    "giyim": {
        "clip_model": "sentence-transformers/clip-ViT-B-32",
        "label": "fashion_clip_fallback",
        "category": "Giyim",
        "keywords": {
            "gomlek": "gomlek dugmeli yakali keten pamuk uzun kollu",
            "shirt": "gomlek dugmeli yakali keten pamuk uzun kollu",
            "tshirt": "tshirt basic pamuklu oversize kisa kollu",
            "t-shirt": "tshirt basic pamuklu oversize kisa kollu",
            "elbise": "elbise kadin yazlik rahat",
            "pantolon": "pantolon denim kumaş rahat kesim",
            "ceket": "ceket dis giyim blazer",
        },
    },
    "cicek": {
        "clip_model": "sentence-transformers/clip-ViT-B-32",
        "label": "general_clip_fallback",
        "category": "Cicek",
        "keywords": {
            "rose": "kirmizi gul buket romantik",
            "gül": "kirmizi gul buket romantik",
            "lale": "lale renkli buket bahar",
            "buket": "buket cicek hediye",
            "orkide": "orkide saksı premium hediye",
        },
    },
    "gida": {
        "clip_model": "sentence-transformers/clip-ViT-B-32",
        "label": "packaged_food_fallback",
        "category": "Gida",
        "keywords": {
            "bal": "bal kavanoz kahvalti doğal",
            "zeytinyagi": "zeytinyagi sise gida",
            "ceviz": "ceviz kuruyemis paket",
            "recel": "recel kavanoz kahvalti",
        },
    },
}


def _safe_name(name: str) -> str:
    stem = Path(name).stem
    stem = normalize_name(stem).replace(" ", "-")
    stem = re.sub(r"[^a-z0-9._-]+", "-", stem).strip("-")
    return stem or "urun"


def _tokens_from_filename(filename: str) -> list[str]:
    raw = Path(filename).stem
    cleaned = normalize_name(raw.replace("_", " ").replace("-", " "))
    return [t for t in cleaned.split() if len(t) > 1]


def _title_from_tokens(tokens: Iterable[str], fallback: str = "Yeni Urun") -> str:
    words = [t for t in tokens if not t.isdigit()]
    if not words:
        return fallback
    return " ".join(w.capitalize() for w in words[:4])


def _business_hint(business_type: str | None) -> dict:
    return BUSINESS_MODEL_HINTS.get((business_type or "").lower(), BUSINESS_MODEL_HINTS["giyim"])


@lru_cache(maxsize=4)
def _load_clip_model(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(model_name)
    except Exception:
        return None


def _encode_image(image_path: str, model_name: str) -> list[float] | None:
    model = _load_clip_model(model_name)
    if model is None:
        return None
    try:
        from PIL import Image

        image = Image.open(image_path).convert("RGB")
        emb = model.encode([image], normalize_embeddings=True)[0]
        return [float(x) for x in emb.tolist()]
    except Exception:
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


@dataclass
class CandidateDraft:
    suggested_name: str
    suggested_category: str
    suggested_price: float | None
    suggested_stock: int
    visual_keywords: str
    description: str
    classifier: str
    confidence: float
    embedding: list[float] | None
    model_name: str


def classify_image_draft(filename: str, image_path: str, business_type: str | None) -> CandidateDraft:
    hint = _business_hint(business_type)
    tokens = _tokens_from_filename(filename)
    token_text = " ".join(tokens)
    matched_keywords: list[str] = []
    for key, value in hint["keywords"].items():
        if key in token_text:
            matched_keywords.extend(value.split())

    keywords = " ".join(dict.fromkeys([*tokens, *matched_keywords]))
    suggested_name = _title_from_tokens(tokens, fallback="Yeni Gorsel Urun")
    category = hint["category"]
    confidence = 0.56 if matched_keywords else 0.35
    model_name = hint["clip_model"]
    embedding = _encode_image(image_path, model_name)
    classifier = hint["label"]
    if embedding is not None:
        classifier = f"clip:{model_name}"
        confidence = max(confidence, 0.72)
    return CandidateDraft(
        suggested_name=suggested_name,
        suggested_category=category,
        suggested_price=None,
        suggested_stock=1,
        visual_keywords=keywords or token_text or suggested_name.lower(),
        description=f"Gorselden otomatik taslak: {suggested_name}. Onaydan once isim, fiyat ve stok kontrol edilmeli.",
        classifier=classifier,
        confidence=confidence,
        embedding=embedding,
        model_name=model_name if embedding is not None else classifier,
    )


def create_batch(tenant_id: int, business_type: str | None, created_by: int | None = None) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO visual_stock_batches (tenant_id, business_type, created_by)
        VALUES (?, ?, ?)
        """,
        (tenant_id, business_type, created_by),
    )
    batch_id = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return batch_id


def save_upload_to_batch(batch_id: int, tenant_id: int, filename: str, fileobj, business_type: str | None) -> dict:
    ext = Path(filename).suffix.lower() or ".jpg"
    digest = hashlib.sha1(f"{tenant_id}:{batch_id}:{filename}:{os.urandom(8).hex()}".encode()).hexdigest()[:12]
    safe = f"{_safe_name(filename)}-{digest}{ext}"
    target_dir = UPLOAD_ROOT / str(tenant_id) / str(batch_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe
    with target.open("wb") as out:
        shutil.copyfileobj(fileobj, out)

    image_url = f"/static/uploads/visual-stock/{tenant_id}/{batch_id}/{safe}"
    draft = classify_image_draft(filename, str(target), business_type)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO visual_stock_candidates (
            tenant_id, batch_id, image_path, image_url, original_filename,
            suggested_name, suggested_category, suggested_price, suggested_stock,
            visual_keywords, description, classifier, confidence
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tenant_id,
            batch_id,
            str(target),
            image_url,
            filename,
            draft.suggested_name,
            draft.suggested_category,
            draft.suggested_price,
            draft.suggested_stock,
            draft.visual_keywords,
            draft.description,
            draft.classifier,
            draft.confidence,
        ),
    )
    candidate_id = int(cur.lastrowid)
    if draft.embedding is not None:
        cur.execute(
            """
            INSERT INTO product_image_embeddings (
                tenant_id, candidate_id, image_path, image_url, model_name, embedding_json, keywords
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                candidate_id,
                str(target),
                image_url,
                draft.model_name,
                json.dumps(draft.embedding),
                draft.visual_keywords,
            ),
        )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM visual_stock_candidates WHERE id = ? AND tenant_id = ?",
        (candidate_id, tenant_id),
    ).fetchone()
    conn.close()
    return dict(row)


def list_batch_candidates(batch_id: int, tenant_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT * FROM visual_stock_candidates
        WHERE batch_id = ? AND tenant_id = ?
        ORDER BY id ASC
        """,
        (batch_id, tenant_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def approve_candidate(candidate_id: int, tenant_id: int, payload: dict) -> dict:
    conn = get_connection()
    cur = conn.cursor()
    cand = cur.execute(
        "SELECT * FROM visual_stock_candidates WHERE id = ? AND tenant_id = ?",
        (candidate_id, tenant_id),
    ).fetchone()
    if not cand:
        conn.close()
        return {"hata": f"Aday #{candidate_id} bulunamadi."}
    if cand["status"] == "approved" and cand["approved_product_id"]:
        conn.close()
        return {"basari": True, "product_id": cand["approved_product_id"], "mesaj": "Aday zaten onaylanmis."}

    name = (payload.get("name") or cand["suggested_name"] or "Yeni Urun").strip()
    category = payload.get("category") or cand["suggested_category"]
    price = float(payload.get("price") if payload.get("price") is not None else cand["suggested_price"] or 0)
    stock = int(payload.get("stock_quantity") if payload.get("stock_quantity") is not None else cand["suggested_stock"] or 1)
    threshold = int(payload.get("low_stock_threshold") or 5)
    visual_keywords = payload.get("visual_keywords") or cand["visual_keywords"]
    description = payload.get("description") or cand["description"]

    cur.execute(
        """
        INSERT INTO products (
            tenant_id, name, category, price, stock_quantity, low_stock_threshold,
            description, image_url, visual_keywords, advisory_notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tenant_id,
            name,
            category,
            price,
            stock,
            threshold,
            description,
            cand["image_url"],
            visual_keywords,
            payload.get("advisory_notes"),
        ),
    )
    product_id = int(cur.lastrowid)
    cur.execute(
        """
        UPDATE visual_stock_candidates
        SET status = 'approved',
            approved_product_id = ?,
            reviewed_at = datetime('now', 'localtime')
        WHERE id = ? AND tenant_id = ?
        """,
        (product_id, candidate_id, tenant_id),
    )
    cur.execute(
        """
        UPDATE product_image_embeddings
        SET product_id = ?
        WHERE tenant_id = ? AND candidate_id = ?
        """,
        (product_id, tenant_id, candidate_id),
    )
    if not cur.execute(
        "SELECT 1 FROM product_image_embeddings WHERE tenant_id = ? AND product_id = ? LIMIT 1",
        (tenant_id, product_id),
    ).fetchone():
        cur.execute(
            """
            INSERT INTO product_image_embeddings (
                tenant_id, product_id, image_path, image_url, model_name, keywords
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (tenant_id, product_id, cand["image_path"], cand["image_url"], cand["classifier"], visual_keywords),
        )
    conn.commit()
    conn.close()
    return {"basari": True, "product_id": product_id, "candidate_id": candidate_id}


def reject_candidate(candidate_id: int, tenant_id: int, reason: str | None = None) -> dict:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE visual_stock_candidates
        SET status = 'rejected',
            reviewed_at = datetime('now', 'localtime'),
            description = COALESCE(description, '') || ?
        WHERE id = ? AND tenant_id = ?
        """,
        (f"\nRed nedeni: {reason}" if reason else "", candidate_id, tenant_id),
    )
    changed = cur.rowcount
    conn.commit()
    conn.close()
    if not changed:
        return {"hata": f"Aday #{candidate_id} bulunamadi."}
    return {"basari": True, "candidate_id": candidate_id}


def search_by_uploaded_image(tenant_id: int, filename: str, fileobj, business_type: str | None) -> dict:
    temp_batch = create_batch(tenant_id, business_type, None)
    cand = save_upload_to_batch(temp_batch, tenant_id, filename, fileobj, business_type)
    query_embedding = None
    conn = get_connection()
    emb_row = conn.execute(
        "SELECT embedding_json FROM product_image_embeddings WHERE tenant_id = ? AND candidate_id = ?",
        (tenant_id, cand["id"]),
    ).fetchone()
    if emb_row and emb_row["embedding_json"]:
        query_embedding = json.loads(emb_row["embedding_json"])

    results: list[dict] = []
    if query_embedding:
        rows = conn.execute(
            """
            SELECT pie.*, p.name, p.category, p.price, p.stock_quantity
            FROM product_image_embeddings pie
            JOIN products p ON p.id = pie.product_id
            WHERE pie.tenant_id = ? AND pie.product_id IS NOT NULL AND pie.embedding_json IS NOT NULL
            """,
            (tenant_id,),
        ).fetchall()
        for row in rows:
            score = _cosine(query_embedding, json.loads(row["embedding_json"]))
            if score > 0.2:
                d = dict(row)
                d["score"] = round(score, 4)
                results.append(d)
        results.sort(key=lambda r: r["score"], reverse=True)
        results = results[:5]

    if not results:
        conn.close()
        results = search_products_by_visual_description(
            cand.get("visual_keywords") or cand.get("suggested_name") or filename,
            tenant_id=tenant_id,
            category=cand.get("suggested_category"),
            limit=5,
        )
        return {"candidate": cand, "results": results, "mode": "keyword_fallback"}
    conn.close()
    return {"candidate": cand, "results": results, "mode": "clip_embedding"}
