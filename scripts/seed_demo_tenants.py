from __future__ import annotations

import json
import random
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import bcrypt
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from database.daily_metrics import backfill_tenant_metrics
from database.db import get_connection, init_db
from services.visual_stock_ingestion import _encode_image

STATIC_ROOT = ROOT / "static" / "uploads" / "demo-tenants"
POLYVORE = ROOT / "demo_assets" / "polyvore"
TENANTS = ROOT / "tenants"

ACCOUNTS = [
    {
        "tenant_id": 2,
        "slug": "mina-butik",
        "business_name": "Mina Butik",
        "business_type": "giyim",
        "username": "mina_butik",
        "password": "demo1234",
        "full_name": "Mina Yılmaz",
        "notes": "Minimal, şehirli ve rahat kadın giyim butiği. Beden konusunda net, sakin ve güven veren cevaplar ister.",
        "rules": ["Müşteriye nazik hitap et.", "Emoji kullanma.", "Beden konusunda emin değilsen ölçü iste.", "Stok yoksa alternatif ürün öner."],
    },
    {
        "tenant_id": 3,
        "slug": "dogal-lezzetler",
        "business_name": "Doğal Lezzetler",
        "business_type": "gida",
        "username": "dogal_lezzetler",
        "password": "demo1234",
        "full_name": "Elif Kaya",
        "notes": "Paketli yöresel gıda ürünleri satan güven odaklı bir işletme. Alerjen sorularında dikkatli ve şeffaf yanıt verir.",
        "rules": ["Alerjen konusunda kesin tıbbi tavsiye verme.", "İçerikten emin değilsen insan kontrolü öner.", "Saklama koşullarını kısa ve net söyle."],
    },
    {
        "tenant_id": 4,
        "slug": "laluna-cicek",
        "business_name": "Laluna Çiçek",
        "business_type": "cicek",
        "username": "laluna_cicek",
        "password": "demo1234",
        "full_name": "Deniz Arslan",
        "notes": "Hediye ve çiçek tasarımları satan butik mağaza. Müşteriye özel gün, renk ve duyguya göre öneri verir.",
        "rules": ["Özel gün amacını sor.", "Renk tercihi varsa stoktaki benzer buketleri öner.", "Teslimat zamanı kritikse net teyit iste."],
    },
]

FASHION_FILES = [
    "pieces-leather-boot-100364440_5.jpg",
    "topshop-moto-vintage-boyfriend-jeans-100077218_8.jpg",
    "givenchy-leather-medium-antigona-duffel-black-100002074_3.jpg",
    "vintage-pearl-feather-earrings-100774542_6.jpg",
    "long-sleeve-simple-blouse-100445477_1.jpg",
    "red-tartan-check-skater-skirt-100167523_2.jpg",
    "classic-flat-shoes-100566397_3.jpg",
    "beige-crystal-sandals-100050716_2.jpg",
    "givenchy-skinny-jean-100010727_2.jpg",
    "diane-von-furstenberg-metallic-mesh-sandals-100111991_3.jpg",
    "tailored-blazer-scalloped-100346741_2.jpg",
    "theory-tube-crop-top-101635841_1.jpg",
    "topshop-black-heavy-leggings-101204936_3.jpg",
    "tory-burch-super-skinny-jean-100963093_4.jpg",
    "miu-miu-pleated-leather-mini-skirt-102004691_3.jpg",
    "ct-leather-low-converse-white-100099673_6.jpg",
    "flat-blue-100740998_4.jpg",
    "alexis-bittar-medium-bracelet-100728995_5.jpg",
]

FASHION_PRODUCTS = [
    ("Black Leather Ankle Boot - 38", "Shoes", 1890, 2, "Black leather ankle boot with low heel. City, smart casual, winter outfit.", "37: 23.5 cm, 38: 24.2 cm, 39: 24.8 cm. Regular fit."),
    ("Vintage Boyfriend Jeans - M", "Bottoms", 1290, 16, "Light blue vintage boyfriend jeans. Relaxed denim fit, casual street style.", "XS: 32-34, S: 34-36, M: 38-40, L: 42-44. Relaxed fit."),
    ("Black Medium Antigona Handbag", "Bags", 2490, 5, "Structured black medium handbag, top handle and shoulder carry.", "One size. Medium bag; fits wallet, phone, small notebook."),
    ("Pearl Feather Drop Earrings", "Accessories", 690, 20, "Vintage inspired pearl and feather drop earrings. Lightweight statement accessory.", "One size. Pierced earrings."),
    ("Ivory Long Sleeve Simple Blouse - M", "Tops", 990, 3, "Ivory long sleeve simple blouse. Minimal office and everyday outfit top.", "XS: 32-34, S: 34-36, M: 38-40, L: 42-44, XL: 46-48. Regular fit."),
    ("Red Tartan Check Skater Skirt - S", "Bottoms", 860, 4, "Red tartan check skater skirt with high waist. Preppy mini skirt.", "S: waist 66-70 cm, M: 71-76 cm, L: 77-82 cm. High waist."),
    ("Navy Classic Flat Shoes - 38", "Shoes", 790, 15, "Navy classic flat shoes. Comfortable ballet flats for daily outfits.", "37: 23.5 cm, 38: 24.2 cm, 39: 24.8 cm. Regular fit."),
    ("Beige Crystal Sandals - 38", "Shoes", 899, 12, "Beige crystal embellished sandals. Summer occasion sandals with delicate straps.", "37: 23.5 cm, 38: 24.2 cm, 39: 24.8 cm. Regular fit."),
    ("Dark Blue Skinny Jeans - M", "Bottoms", 1190, 10, "Dark blue skinny jeans with stretch denim. Slim fit everyday denim.", "XS: 32-34, S: 34-36, M: 38-40, L: 42-44. Stretch fabric."),
    ("Gold Metallic Mesh Sandals - 39", "Shoes", 1199, 6, "Gold metallic mesh sandals for evening outfits and special occasions.", "38: 24.2 cm, 39: 24.8 cm, 40: 25.5 cm. Narrow straps."),
    ("Scalloped Tailored Blazer - M", "Outerwear", 2190, 4, "Tailored blazer with scalloped edge. Smart office jacket, clean silhouette.", "S: 34-36, M: 38-40, L: 42-44. Structured fit."),
    ("Black Tube Crop Top - M", "Tops", 690, 18, "Black tube crop top. Minimal fitted summer top, layering piece.", "XS: 32-34, S: 34-36, M: 38-40, L: 42. Fitted."),
    ("Black Heavy Leggings - M", "Bottoms", 740, 22, "Black heavy leggings with opaque stretch fabric. Everyday active casual bottom.", "S: 34-36, M: 38-40, L: 42-44, XL: 46-48. High stretch."),
    ("Super Skinny Blue Jeans - S", "Bottoms", 1290, 7, "Blue super skinny jeans. Polished denim, slim ankle silhouette.", "XS: 32-34, S: 34-36, M: 38-40. Very slim fit."),
    ("Black Pleated Leather Mini Skirt - S", "Bottoms", 1690, 3, "Black pleated leather mini skirt. Statement evening skirt with structured pleats.", "XS: waist 62-66 cm, S: 66-70 cm, M: 71-76 cm."),
    ("White Low Converse Sneakers - 38", "Shoes", 950, 11, "White low top canvas sneakers. Casual street style everyday shoes.", "37: 23.5 cm, 38: 24.2 cm, 39: 24.8 cm, 40: 25.5 cm."),
    ("Blue Pointed Flat Shoes - 38", "Shoes", 820, 13, "Blue pointed flat shoes. Polished flat shoe for office and denim outfits.", "37: 23.5 cm, 38: 24.2 cm, 39: 24.8 cm. Regular fit."),
    ("Silver Medium Bracelet", "Accessories", 560, 24, "Silver medium bracelet. Minimal jewelry accessory for daily outfits.", "One size. Medium wrist fit."),
]

FOOD_PRODUCTS = [
    ("Glutensiz Granola 300g", "Gıda", 210, 34, "Yulaf, fındık, kuru üzüm ve bal ile hazırlanmış granola.", "Yulaf, fındık, bal, kuru üzüm", "Fındık içerir. Gluten bulaş riski düşüktür fakat üretim hattı doğrulanmalıdır."),
    ("Soğuk Sıkım Zeytinyağı 500ml", "Gıda", 360, 22, "Erken hasat, düşük asitli zeytinyağı.", "Zeytinyağı", "Bilinen majör alerjen içermez."),
    ("Çiçek Balı 450g", "Gıda", 280, 18, "Yayla çiçeklerinden süzme bal.", "Bal", "1 yaş altı bebekler için uygun değildir. Polen hassasiyeti olanlar dikkatli olmalıdır."),
    ("Ceviz İçi 500g", "Gıda", 310, 9, "Yeni mahsul kelebek ceviz içi.", "Ceviz", "Ceviz/ağaç yemişi içerir."),
    ("Domates Salçası 660g", "Gıda", 190, 16, "Ev yapımı yoğun kıvamlı domates salçası.", "Domates, tuz", "Bilinen majör alerjen içermez."),
]

FLOWER_PRODUCTS = [
    ("Beyaz Lilyum Buketi", "Çiçek", 1250, 7, "Zarif beyaz lilyum ve yeşilliklerle hazırlanır.", "Düğün, teşekkür, geçmiş olsun"),
    ("Kırmızı Gül Kutusu", "Çiçek", 1490, 5, "Premium kırmızı güllerden kutu aranjmanı.", "Romantik, yıl dönümü, doğum günü"),
    ("Pastel Bahar Buketi", "Çiçek", 890, 14, "Pembe, lila ve beyaz tonlarında mevsim buketi.", "Doğum günü, kutlama, yeni iş"),
    ("Orkide Saksı", "Çiçek", 980, 8, "Çift dallı beyaz orkide.", "Ofis, ev hediyesi, uzun ömürlü"),
    ("Günebakan Buketi", "Çiçek", 760, 10, "Canlı sarı tonlarda enerjik buket.", "Tebrik, moral, yaz teması"),
]


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _write_config(account: dict):
    preset_rules = account["rules"]
    payload = {
        "tenant_id": account["tenant_id"],
        "slug": account["slug"],
        "business_name": account["business_name"],
        "business_type": account["business_type"],
        "language": "tr",
        "agent": {
            "name": f"{account['business_name']} Asistanı",
            "role": "Müşteri iletişimi ve operasyon asistanı",
            "personality": f"{account['business_name']} için çalışan asistan. KOBİ notları: {account['notes']}",
            "rules": preset_rules,
        },
        "llm": {"provider": "ollama", "model": "qwen3.6:27b", "temperature": 0.2},
        "features": {
            "dashboard_theme": "elegant",
            "whatsapp_business": False,
            "telegram_admin_notifications": True,
            "image_search": account["business_type"] in ("giyim", "cicek"),
            "product_advisory": True,
            "faq_rag": False,
            "report_export": False,
        },
        "branding": {"primary_color": "#2563eb", "accent_color": "#16a34a"},
    }
    target = TENANTS / account["slug"]
    target.mkdir(parents=True, exist_ok=True)
    (target / "config.yaml").write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _make_card_image(path: Path, title: str, color: tuple[int, int, int]):
    from PIL import Image, ImageDraw

    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (720, 900), color)
    draw = ImageDraw.Draw(img)
    draw.rectangle((36, 36, 684, 864), outline=(255, 255, 255), width=8)
    draw.text((70, 410), title[:34], fill=(255, 255, 255))
    img.save(path, "JPEG", quality=92)


def _copy_or_make_fashion(idx: int, tenant_id: int) -> Path:
    target = STATIC_ROOT / str(tenant_id) / FASHION_FILES[idx]
    target.parent.mkdir(parents=True, exist_ok=True)
    src = POLYVORE / FASHION_FILES[idx]
    if src.exists():
        shutil.copyfile(src, target)
    else:
        _make_card_image(target, FASHION_PRODUCTS[idx][0], (40 + idx * 12, 70, 105))
    return target


def _insert_product(conn, tenant_id: int, item: tuple, image_path: Path, business_type: str):
    name, category, price, stock, description, extra, *rest = item
    image_url = "/" + image_path.relative_to(ROOT).as_posix()
    threshold = 4 if stock < 10 else 6
    if business_type == "gida":
        ingredients, allergens = extra, rest[0]
        size_guide = None
        advisory = "Alerjen sorularında etiketi kontrol ederek cevap ver; emin değilsen insan kontrolü öner."
        keywords = f"{name} {category} {ingredients} {allergens}"
    elif business_type == "cicek":
        ingredients = allergens = size_guide = None
        advisory = extra
        keywords = f"{name} {category} {extra}"
    else:
        ingredients = allergens = None
        size_guide = extra
        advisory = "Beden sorularında beden rehberine dayan; iki beden arasında kalırsa ölçü iste."
        keywords = f"{name} {category} {description} {size_guide}"
    row = conn.execute(
        "SELECT id FROM products WHERE tenant_id = ? AND name = ?",
        (tenant_id, name),
    ).fetchone()
    if row:
        pid = int(row["id"])
        conn.execute(
            """
            UPDATE products SET category=?, price=?, stock_quantity=?, low_stock_threshold=?,
                description=?, ingredients=?, allergens=?, size_guide=?, advisory_notes=?,
                image_url=?, visual_keywords=?, is_active=1
            WHERE id=? AND tenant_id=?
            """,
            (category, price, stock, threshold, description, ingredients, allergens, size_guide, advisory, image_url, keywords, pid, tenant_id),
        )
    else:
        cur = conn.execute(
            """
            INSERT INTO products (
                tenant_id, name, category, price, stock_quantity, low_stock_threshold,
                description, ingredients, allergens, size_guide, advisory_notes, image_url, visual_keywords
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tenant_id, name, category, price, stock, threshold, description, ingredients, allergens, size_guide, advisory, image_url, keywords),
        )
        pid = int(cur.lastrowid)
    model_name = settings.FASHION_CLIP_MODEL if business_type == "giyim" else settings.GENERAL_CLIP_MODEL
    emb = _encode_image(str(image_path), model_name)
    conn.execute("DELETE FROM product_image_embeddings WHERE tenant_id=? AND product_id=?", (tenant_id, pid))
    conn.execute(
        """
        INSERT INTO product_image_embeddings (tenant_id, product_id, image_path, image_url, model_name, embedding_json, keywords)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (tenant_id, pid, str(image_path), image_url, model_name, json.dumps(emb) if emb else None, keywords),
    )
    return pid


def _clear_tenant_demo(conn, tenant_id: int):
    order_ids = [
        int(r["id"])
        for r in conn.execute("SELECT id FROM orders WHERE tenant_id = ?", (tenant_id,)).fetchall()
    ]
    cargo_codes = [
        r["cargo_tracking_code"]
        for r in conn.execute(
            "SELECT cargo_tracking_code FROM orders WHERE tenant_id = ? AND cargo_tracking_code IS NOT NULL",
            (tenant_id,),
        ).fetchall()
        if r["cargo_tracking_code"]
    ]
    if order_ids:
        marks = ",".join("?" for _ in order_ids)
        conn.execute(f"DELETE FROM order_items WHERE order_id IN ({marks})", order_ids)
    if cargo_codes:
        marks = ",".join("?" for _ in cargo_codes)
        conn.execute(f"DELETE FROM cargo_tracking WHERE tracking_code IN ({marks})", cargo_codes)
    for table in (
        "orders",
        "tickets",
        "daily_reports",
        "tenant_daily_metrics",
        "tenant_daily_forecasts",
        "stock_movements",
        "product_image_embeddings",
        "visual_stock_candidates",
        "visual_stock_batches",
        "products",
    ):
        conn.execute(f"DELETE FROM {table} WHERE tenant_id = ?", (tenant_id,))
    conn.commit()


def _seed_ops(conn, tenant_id: int, product_ids: list[int], account: dict):
    rnd = random.Random(6000 + tenant_id)
    customers = [
        ("Ayşe Demir", "05321112233"),
        ("Mehmet Yıldız", "05324445566"),
        ("Zeynep Aydın", "05327778899"),
        ("Can Ergin", "05320001122"),
        ("Ece Şahin", "05323334455"),
        ("Burak Kılıç", "05326667788"),
    ]
    statuses = ["hazırlanıyor", "kargoda", "teslim_edildi", "iptal"]
    fixed_statuses = ["hazırlanıyor", "hazırlanıyor", "kargoda", "kargoda", "teslim_edildi", "iptal"]
    total_orders = 34 if tenant_id == 2 else 24
    for i in range(total_orders):
        if i < len(fixed_statuses):
            day = datetime.now() - timedelta(hours=i + 1)
            status = fixed_statuses[i]
        else:
            day = datetime.now() - timedelta(days=rnd.randint(1, 18), hours=rnd.randint(0, 8))
            status = rnd.choices(statuses, weights=[5, 5, 10, 1])[0]
        pid = product_ids[i % len(product_ids)] if i < len(product_ids) else rnd.choice(product_ids)
        p = conn.execute("SELECT price FROM products WHERE id=?", (pid,)).fetchone()
        qty = 4 if (tenant_id == 2 and i in (0, 2)) else rnd.randint(1, 3)
        total = round(float(p["price"]) * qty, 2)
        code = f"SIP-D{tenant_id}-{i:03d}"
        cargo = f"TRK{tenant_id}{i:04d}" if status == "kargoda" else None
        customer_name, customer_phone = customers[i % len(customers)]
        cur = conn.execute(
            """
            INSERT INTO orders (tenant_id, tracking_code, customer_name, customer_phone, status, cargo_tracking_code, cargo_company, total_price, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tenant_id, code, customer_name, customer_phone, status, cargo, "Yurtiçi Kargo" if cargo else None, total, "Demo sipariş", day.strftime("%Y-%m-%d %H:%M:%S"), day.strftime("%Y-%m-%d %H:%M:%S")),
        )
        oid = int(cur.lastrowid)
        conn.execute("INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)", (oid, pid, qty, float(p["price"])))
        if cargo:
            if tenant_id == 2 and i == 2:
                cargo_status = "Gecikti"
                estimated = (date.today() - timedelta(days=1)).isoformat()
            elif tenant_id == 2 and i == 3:
                cargo_status = "Şubede Bekliyor"
                estimated = (date.today() - timedelta(days=2)).isoformat()
            else:
                cargo_status = rnd.choice(["Dağıtımda", "Transfer merkezinde"])
                estimated = (day + timedelta(days=2)).date().isoformat()
            conn.execute(
                "INSERT OR REPLACE INTO cargo_tracking (tracking_code, company, current_status, estimated_delivery, last_update) VALUES (?, ?, ?, ?, ?)",
                (cargo, "Yurtiçi Kargo", cargo_status, estimated, day.strftime("%Y-%m-%d %H:%M:%S")),
            )
    ticket_rows = [
        ("stock_alert", "Kritik stok kontrolü", "Black Leather Ankle Boot, Ivory Blouse ve Pleated Mini Skirt kritik stokta.", "high"),
        ("cargo_delay", "Kargo gecikme riski", "Bir gönderi tahmini teslim tarihini geçti; bir gönderi şubede bekliyor.", "high"),
        ("cancellation_request", "Müşteri iptal talebi", "Müşteri iptal için doğrulama sonrası inceleme istedi.", "high"),
    ]
    for typ, title, desc, pr in ticket_rows:
        conn.execute(
            "INSERT INTO tickets (tenant_id, type, priority, status, title, description, created_at) VALUES (?, ?, ?, 'open', ?, ?, datetime('now','localtime'))",
            (tenant_id, typ, pr, title, desc),
        )
    today = date.today().isoformat()
    briefing = {
        "summary": f"{account['business_name']} için gün özeti hazır. Kritik stok, geciken kargo ve açık müdahale kayıtları var.",
        "tasks": [
            {"type": "tickets", "title": "Açık müdahale kayıtlarını incele", "priority": "high"},
            {"type": "inventory", "title": "Kritik stok ürünlerini yenile", "priority": "high"},
            {"type": "cargo", "title": "Geciken kargoları müşteriye bildir", "priority": "high"},
        ],
    }
    conn.execute(
        "INSERT INTO daily_reports (tenant_id, date, report_text, raw_data, briefing_json, model_version, source) VALUES (?, ?, ?, ?, ?, 'demo', 'demo_seed')",
        (tenant_id, today, briefing["summary"], json.dumps({"demo": True}, ensure_ascii=False), json.dumps(briefing, ensure_ascii=False)),
    )
    conn.commit()
    backfill_tenant_metrics(tenant_id)


def seed():
    init_db()
    STATIC_ROOT.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    try:
        for acc in ACCOUNTS:
            _write_config(acc)
            tenant_id = acc["tenant_id"]
            _clear_tenant_demo(conn, tenant_id)
            if not conn.execute("SELECT 1 FROM users WHERE username=?", (acc["username"],)).fetchone():
                conn.execute(
                    "INSERT INTO users (tenant_id, username, password_hash, role, full_name) VALUES (?, ?, ?, 'admin', ?)",
                    (acc["tenant_id"], acc["username"], _hash(acc["password"]), acc["full_name"]),
                )
            if acc["business_type"] == "giyim":
                products = FASHION_PRODUCTS
                paths = [_copy_or_make_fashion(i, tenant_id) for i in range(len(products))]
            elif acc["business_type"] == "gida":
                products = FOOD_PRODUCTS
                paths = []
                for i, item in enumerate(products):
                    p = STATIC_ROOT / str(tenant_id) / f"gida-{i+1}.jpg"
                    _make_card_image(p, item[0], (70, 120 + i * 16, 70))
                    paths.append(p)
            else:
                products = FLOWER_PRODUCTS
                paths = []
                for i, item in enumerate(products):
                    p = STATIC_ROOT / str(tenant_id) / f"cicek-{i+1}.jpg"
                    _make_card_image(p, item[0], (140 + i * 12, 80, 130))
                    paths.append(p)
            pids = [_insert_product(conn, tenant_id, item, paths[i], acc["business_type"]) for i, item in enumerate(products)]
            conn.commit()
            _seed_ops(conn, tenant_id, pids, acc)
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
    print("[OK] Demo tenant hesapları ve verileri hazır.")
