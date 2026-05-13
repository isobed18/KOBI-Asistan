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
    "pieces-leather-boot-102049118_4.jpg",
    "topshop-moto-vintage-boyfriend-jeans-100014086_2.jpg",
    "givenchy-leather-medium-antigona-duffel-black-100002074_3.jpg",
    "vintage-pearl-feather-earrings-100560058_7.jpg",
    "long-sleeve-simple-blouse-100445477_1.jpg",
    "red-tartan-check-skater-skirt-100361260_2.jpg",
    "classic-flat-shoes-100566397_3.jpg",
    "beige-crystal-sandals-100050716_2.jpg",
    "givenchy-skinny-jean-100010727_2.jpg",
    "diane-von-furstenberg-metallic-mesh-sandals-100111991_3.jpg",
]

FASHION_PRODUCTS = [
    ("Deri Bot - Siyah 38", "Ayakkabı", 1890, 9, "Siyah deri görünümlü şehir botu.", "37: 23.5 cm, 38: 24.2 cm, 39: 24.8 cm. Kalıp normal."),
    ("Vintage Boyfriend Jean - M", "Alt Giyim", 1290, 14, "Rahat kesim açık mavi boyfriend jean.", "S: 34-36, M: 38-40, L: 42. Rahat kalıp."),
    ("Antigona Model Çanta", "Çanta", 2490, 6, "Siyah, orta boy, elde ve omuzda taşınabilir çanta.", ""),
    ("İnci Detaylı Küpe", "Aksesuar", 690, 18, "Hafif, vintage esintili inci detaylı küpe.", ""),
    ("Uzun Kollu Bluz - Ekru M", "Üst Giyim", 990, 11, "Sade, uzun kollu, günlük kullanıma uygun bluz.", "S: 34-36, M: 38-40, L: 42-44. Kalıp normal."),
    ("Tartan Mini Etek - S", "Alt Giyim", 860, 8, "Kırmızı tartan desenli mini etek.", "S: bel 66-70 cm, M: 71-76 cm, L: 77-82 cm."),
    ("Klasik Babet - Lacivert 38", "Ayakkabı", 790, 15, "Lacivert klasik düz taban babet.", "37: 23.5 cm, 38: 24.2 cm, 39: 24.8 cm."),
    ("Kristal Sandalet - Bej 38", "Ayakkabı", 899, 12, "Bej taş detaylı yazlık sandalet.", "37: 23.5 cm, 38: 24.2 cm, 39: 24.8 cm. Kalıp normal."),
    ("Skinny Jean - Koyu Mavi", "Alt Giyim", 1190, 10, "Koyu mavi dar paça jean.", "S: 34-36, M: 38-40, L: 42. Esnek kumaş."),
    ("Metallic Sandalet - Gold 39", "Ayakkabı", 1199, 7, "Gold metalik bantlı özel gün sandaleti.", "38: 24.2 cm, 39: 24.8 cm, 40: 25.5 cm."),
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


def _seed_ops(conn, tenant_id: int, product_ids: list[int], account: dict):
    rnd = random.Random(6000 + tenant_id)
    customers = ["Ayşe Demir", "Mehmet Yıldız", "Zeynep Aydın", "Can Ergin", "Ece Şahin", "Burak Kılıç"]
    statuses = ["hazırlanıyor", "kargoda", "teslim_edildi", "iptal"]
    for i in range(28):
        day = datetime.now() - timedelta(days=rnd.randint(0, 18), hours=rnd.randint(0, 8))
        status = rnd.choices(statuses, weights=[4, 4, 9, 1])[0]
        pid = rnd.choice(product_ids)
        p = conn.execute("SELECT price FROM products WHERE id=?", (pid,)).fetchone()
        qty = rnd.randint(1, 3)
        total = round(float(p["price"]) * qty, 2)
        code = f"SIP-D{tenant_id}-{i:03d}"
        if conn.execute("SELECT 1 FROM orders WHERE tracking_code=?", (code,)).fetchone():
            continue
        cargo = f"TRK{tenant_id}{i:04d}" if status == "kargoda" else None
        cur = conn.execute(
            """
            INSERT INTO orders (tenant_id, tracking_code, customer_name, customer_phone, status, cargo_tracking_code, cargo_company, total_price, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tenant_id, code, rnd.choice(customers), f"05{rnd.randint(100000000, 999999999)}", status, cargo, "Yurtiçi Kargo" if cargo else None, total, "Demo sipariş", day.strftime("%Y-%m-%d %H:%M:%S"), day.strftime("%Y-%m-%d %H:%M:%S")),
        )
        oid = int(cur.lastrowid)
        conn.execute("INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)", (oid, pid, qty, float(p["price"])))
        if cargo:
            conn.execute(
                "INSERT OR REPLACE INTO cargo_tracking (tracking_code, company, current_status, estimated_delivery, last_update) VALUES (?, ?, ?, ?, ?)",
                (cargo, "Yurtiçi Kargo", rnd.choice(["Dağıtımda", "Transfer merkezinde", "Gecikme riski"]), (day + timedelta(days=2)).date().isoformat(), day.strftime("%Y-%m-%d %H:%M:%S")),
            )
    ticket_rows = [
        ("stock_alert", "Kritik stok kontrolü", "Bazı ürünlerde stok eşiğe yaklaştı.", "high"),
        ("cargo_delay", "Kargo gecikme riski", "Bir kargo son güncellemeden beri bekliyor.", "normal"),
        ("cancellation_request", "Müşteri iptal talebi", "Müşteri iptal için doğrulama sonrası inceleme istedi.", "high"),
    ]
    for typ, title, desc, pr in ticket_rows:
        if not conn.execute("SELECT 1 FROM tickets WHERE tenant_id=? AND type=? AND title=?", (tenant_id, typ, title)).fetchone():
            conn.execute(
                "INSERT INTO tickets (tenant_id, type, priority, status, title, description, created_at) VALUES (?, ?, ?, 'open', ?, ?, datetime('now','localtime'))",
                (tenant_id, typ, pr, title, desc),
            )
    today = date.today().isoformat()
    if not conn.execute("SELECT 1 FROM daily_reports WHERE tenant_id=? AND date=? AND source='demo_seed'", (tenant_id, today)).fetchone():
        briefing = {
            "summary": f"{account['business_name']} için demo günü hazır. Açık biletler, kargolar ve stoklar kontrol altında.",
            "tasks": [
                {"type": "tickets", "title": "Açık müdahale kayıtlarını incele", "priority": "high"},
                {"type": "inventory", "title": "Kritik stok ürünlerini gözden geçir", "priority": "normal"},
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
            if not conn.execute("SELECT 1 FROM users WHERE username=?", (acc["username"],)).fetchone():
                conn.execute(
                    "INSERT INTO users (tenant_id, username, password_hash, role, full_name) VALUES (?, ?, ?, 'admin', ?)",
                    (acc["tenant_id"], acc["username"], _hash(acc["password"]), acc["full_name"]),
                )
            tenant_id = acc["tenant_id"]
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
