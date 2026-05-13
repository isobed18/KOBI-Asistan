from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

from datasets import load_dataset

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.db import init_db
from services.visual_stock_ingestion import approve_candidate, create_batch, save_upload_to_batch

DEFAULT_OUT = ROOT / "demo_assets" / "polyvore"

FASHION_CATEGORY_HINTS = {
    "accessories",
    "bags",
    "belts",
    "blazers",
    "blouses",
    "boots",
    "bracelets",
    "clothing",
    "coats",
    "dresses",
    "earrings",
    "flats",
    "handbags",
    "hats",
    "jackets",
    "jeans",
    "jewelry",
    "necklaces",
    "pants",
    "sandals",
    "shirts",
    "shoes",
    "shorts",
    "skirts",
    "sneakers",
    "sunglasses",
    "sweaters",
    "tops",
}


def _safe_file_part(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-")
    return cleaned[:80] or "polyvore-item"


def _is_fashion_row(row: dict) -> bool:
    category = str(row.get("category") or "").lower()
    text = str(row.get("text") or "").lower()
    joined = f"{category} {text}"
    return any(hint in joined for hint in FASHION_CATEGORY_HINTS)


def _reservoir_sample(
    dataset_name: str,
    split: str,
    count: int,
    scan_limit: int,
    seed: int,
    fashion_only: bool,
) -> list[dict]:
    rng = random.Random(seed)
    sample: list[dict] = []
    ds = load_dataset(dataset_name, split=split, streaming=True)
    for idx, row in enumerate(ds):
        if idx >= scan_limit:
            break
        if row.get("image") is None:
            continue
        if fashion_only and not _is_fashion_row(row):
            continue
        if len(sample) < count:
            sample.append(row)
            continue
        replace_at = rng.randint(0, idx)
        if replace_at < count:
            sample[replace_at] = row
    return sample


def _save_row_image(row: dict, out_dir: Path) -> Path:
    item_id = str(row.get("item_ID") or random.randint(100000, 999999))
    text = str(row.get("text") or row.get("category") or "polyvore item")
    path = out_dir / f"{_safe_file_part(text)}-{_safe_file_part(item_id)}.jpg"
    image = row["image"].convert("RGB")
    image.save(path, "JPEG", quality=92)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download 15 Polyvore demo products and create FashionCLIP visual-stock candidates."
    )
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--business-type", default="giyim")
    parser.add_argument("--count", type=int, default=15)
    parser.add_argument("--scan-limit", type=int, default=400)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    parser.add_argument("--dataset", default="Marqo/polyvore")
    parser.add_argument("--split", default="data")
    parser.add_argument("--no-fashion-filter", action="store_true")
    parser.add_argument("--approve", action="store_true", help="Also insert approved products after candidate creation.")
    parser.add_argument("--price", type=float, default=899.0)
    parser.add_argument("--stock", type=int, default=12)
    args = parser.parse_args()

    init_db()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = _reservoir_sample(
        args.dataset,
        args.split,
        args.count,
        args.scan_limit,
        args.seed,
        fashion_only=args.business_type.lower() == "giyim" and not args.no_fashion_filter,
    )
    if not rows:
        raise RuntimeError("No usable Polyvore rows found.")

    batch_id = create_batch(args.tenant_id, args.business_type, created_by=None)
    candidates = []
    products = []

    for row in rows:
        image_path = _save_row_image(row, out_dir)
        display_name = str(row.get("text") or image_path.name)
        with image_path.open("rb") as fileobj:
            candidate = save_upload_to_batch(
                batch_id=batch_id,
                tenant_id=args.tenant_id,
                filename=f"{display_name}.jpg",
                fileobj=fileobj,
                business_type=args.business_type,
            )
        candidate["polyvore_category"] = row.get("category")
        candidate["polyvore_item_ID"] = row.get("item_ID")
        candidates.append(candidate)
        if args.approve:
            products.append(
                approve_candidate(
                    candidate["id"],
                    args.tenant_id,
                    {
                        "name": candidate["suggested_name"],
                        "category": candidate["suggested_category"] or row.get("category"),
                        "price": args.price,
                        "stock_quantity": args.stock,
                        "visual_keywords": candidate["visual_keywords"],
                        "description": candidate["description"],
                    },
                )
            )

    result = {
        "batch_id": batch_id,
        "tenant_id": args.tenant_id,
        "business_type": args.business_type,
        "download_dir": str(out_dir),
        "candidate_count": len(candidates),
        "approved_count": len(products),
        "candidates": [
            {
                "id": c["id"],
                "name": c["suggested_name"],
                "category": c["suggested_category"],
                "classifier": c["classifier"],
                "confidence": c["confidence"],
                "image_url": c["image_url"],
                "polyvore_category": c.get("polyvore_category"),
            }
            for c in candidates
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
