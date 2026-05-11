"""
Demo grafikleri ve Bugun / AI brifingi icin tarihsel veri zenginlestirme.

- Son ~45 gune yayilmis siparisler + kalemler
- Bilet ve stok hareketleri (hafif)
- Ornek daily_reports + briefing_json (kiracı 1)
- tenant_daily_metrics backfill

Tekrar calistirmada idempotent: SIP-DEMO- ile baslayan siparis sayisi yeterliyse atlanir.
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import date, timedelta

from database.db import get_connection
from database.daily_metrics import backfill_tenant_metrics

DEMO_PREFIX = "SIP-DEMO-"
# Takvimde 'bos gun' kalanlari doldurur (220 limiti eski gunlere takilinca Mayis 1-11 bos kalmasin)
GAP_PREFIX = "SIP-DEMOGAP-"
DEMO_REPORT_SOURCE = "demo_seed"
TENANT_DEFAULT = 1
TARGET_DEMO_ORDERS = 220
DAYS_SPAN = 46


def _has_column(cursor, table: str, column: str) -> bool:
    rows = cursor.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def _demo_order_count(cursor, tenant_id: int) -> int:
    return cursor.execute(
        f"SELECT COUNT(*) AS c FROM orders WHERE tenant_id = ? AND tracking_code LIKE '{DEMO_PREFIX}%'",
        (tenant_id,),
    ).fetchone()["c"]


def _customer_pool():
    names = [
        ("Ayse Kaya", "05321110001"),
        ("Mehmet Demir", "05321110002"),
        ("Fatma Celik", "05321110003"),
        ("Ali Yildiz", "05321110004"),
        ("Zeynep Arslan", "05321110005"),
        ("Can Ozturk", "05321110006"),
        ("Elif Sahin", "05321110007"),
        ("Burak Koc", "05321110008"),
        ("Selin Aydin", "05321110009"),
        ("Emre Polat", "05321110010"),
    ]
    return names


def _pick_status(days_ago: int, rnd: random.Random) -> str:
    if days_ago > 21:
        return rnd.choices(
            ["teslim_edildi", "iptal", "teslim_edildi", "teslim_edildi"],
            weights=[1, 1, 1, 1],
        )[0]
    if days_ago > 10:
        return rnd.choices(
            ["teslim_edildi", "kargoda", "hazırlanıyor", "iptal"],
            weights=[5, 2, 2, 1],
        )[0]
    return rnd.choices(
        ["hazırlanıyor", "kargoda", "teslim_edildi", "iptal"],
        weights=[3, 3, 2, 1],
    )[0]


def _cargo_for_status(status: str, rnd: random.Random):
    if status != "kargoda":
        return None, None
    carriers = [
        ("MNG-9" + "".join(str(rnd.randint(0, 9)) for _ in range(4)), "MNG"),
        ("YK-7" + "".join(str(rnd.randint(0, 9)) for _ in range(4)), "Yurtici"),
        ("PTT-3" + "".join(str(rnd.randint(0, 9)) for _ in range(4)), "PTT"),
    ]
    return carriers[rnd.randint(0, len(carriers) - 1)]


def _fill_sparse_calendar_days(
    cursor,
    tenant_id: int,
    pid_list: list[tuple[int, float, str]],
    customers: list[tuple[str, str]],
    today: date,
    ensure_cargo_row,
    *,
    days_back: int = 45,
    min_per_day: int = 2,
) -> int:
    """
    Son N takvim gununde siparis sayisi min_per_day altindaysa SIP-DEMOGAP- siparisi ekler.
    220 demo limiti yuzunden son gunler bos kaldiginda grafik / Bugun guncellenir.
    """
    added = 0
    for off in range(days_back):
        d = today - timedelta(days=off)
        ds = d.isoformat()
        have = int(
            cursor.execute(
                """
                SELECT COUNT(*) AS c FROM orders
                WHERE tenant_id = ? AND date(created_at) = ?
                """,
                (tenant_id, ds),
            ).fetchone()["c"]
            or 0
        )
        if have >= min_per_day:
            continue
        rnd_gap = random.Random(88000 + off * 31 + tenant_id)
        for j in range(min_per_day - have):
            status = rnd_gap.choices(
                ["teslim_edildi", "kargoda", "hazırlanıyor"],
                weights=[6, 2, 2],
            )[0]
            cargo_code, cargo_company = None, None
            if status == "kargoda":
                cargo_code, cargo_company = _cargo_for_status(status, rnd_gap)
                if cargo_code:
                    ensure_cargo_row(
                        cargo_code,
                        cargo_company or "MNG",
                        rnd_gap.choice(["Dagitima Cikti", "Teslim Edildi", "Subede Bekliyor"]),
                    )
            cust = customers[rnd_gap.randint(0, len(customers) - 1)]
            hour = min(18, 9 + j * 3 + rnd_gap.randint(0, 2))
            minute = rnd_gap.randint(0, 59)
            ts = f"{ds} {hour:02d}:{minute:02d}:00"
            code = f"{GAP_PREFIX}{tenant_id}-{d.strftime('%Y%m%d')}-{uuid.uuid4().hex[:12]}"

            lines = rnd_gap.randint(1, 3)
            subtotal = 0.0
            items: list[tuple[int, int, float]] = []
            for _ in range(lines):
                pid, price, _ = pid_list[rnd_gap.randint(0, len(pid_list) - 1)]
                qty = rnd_gap.randint(1, 4)
                items.append((pid, qty, price))
                subtotal += qty * price
            total = round(subtotal * (0.9 + rnd_gap.random() * 0.18), 2)

            cursor.execute(
                """
                INSERT INTO orders (
                    tenant_id, tracking_code, customer_name, customer_phone, status,
                    cargo_tracking_code, cargo_company, total_price, notes,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    code,
                    cust[0],
                    cust[1],
                    status,
                    cargo_code,
                    cargo_company,
                    total,
                    None,
                    ts,
                    ts,
                ),
            )
            oid = cursor.lastrowid
            for pid, qty, up in items:
                cursor.execute(
                    """
                    INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                    VALUES (?, ?, ?, ?)
                    """,
                    (oid, pid, qty, up),
                )
            added += 1
    return added


def maybe_enrich_demo_chart_data(tenant_id: int = TENANT_DEFAULT) -> str:
    conn = get_connection()
    cursor = conn.cursor()

    existing_demo = _demo_order_count(cursor, tenant_id)

    products = cursor.execute(
        "SELECT id, price, name FROM products WHERE tenant_id = ? AND is_active = 1",
        (tenant_id,),
    ).fetchall()
    if not products:
        conn.close()
        return "[SKIP] Urun yok; once database.seed calistirin."

    pid_list = [(int(r["id"]), float(r["price"]), r["name"]) for r in products]
    customers = _customer_pool()
    today = date.today()
    rnd = random.Random(42 + tenant_id)

    cargo_codes_seen: set[str] = set()

    def ensure_cargo_row(code: str, company: str, status: str):
        if code in cargo_codes_seen:
            return
        cursor.execute(
            "SELECT 1 FROM cargo_tracking WHERE tracking_code = ?", (code,)
        )
        if cursor.fetchone():
            cargo_codes_seen.add(code)
            return
        cursor.execute(
            """
            INSERT INTO cargo_tracking (tracking_code, company, current_status, estimated_delivery, last_update)
            VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
            """,
            (code, company, status, (today + timedelta(days=3)).isoformat()),
        )
        cargo_codes_seen.add(code)

    n_insert = 0
    # Once bugunden geriye SIP-DEMO doldur (limit dolunca en az son gunler dolu olur)
    if existing_demo < TARGET_DEMO_ORDERS:
        for day_i in range(DAYS_SPAN + 1):
            d = today - timedelta(days=day_i)
            days_ago = day_i
            rnd_day = random.Random(10007 + day_i * 997 + tenant_id)
            n_today = 3 + ((DAYS_SPAN - day_i) % 6) + rnd_day.randint(0, 3)
            for k in range(n_today):
                if existing_demo + n_insert >= TARGET_DEMO_ORDERS:
                    break
                status = _pick_status(days_ago, rnd_day)
                cargo_code, cargo_company = _cargo_for_status(status, rnd_day)
                if cargo_code:
                    st = rnd_day.choice(
                        ["Dagitima Cikti", "Subede Bekliyor", "Teslim Edildi", "Gecikti"]
                    )
                    ensure_cargo_row(cargo_code, cargo_company or "Kargo", st)

                cust = customers[rnd_day.randint(0, len(customers) - 1)]
                hour = 9 + rnd_day.randint(0, 9)
                minute = rnd_day.randint(0, 59)
                ts = f"{d.isoformat()} {hour:02d}:{minute:02d}:00"
                code = f"{DEMO_PREFIX}{tenant_id}-{d.strftime('%Y%m%d')}-{k:02d}-{rnd_day.randint(100,999)}"

                lines = rnd_day.randint(1, 4)
                subtotal = 0.0
                items: list[tuple[int, int, float]] = []
                for _ in range(lines):
                    pid, price, _ = pid_list[rnd_day.randint(0, len(pid_list) - 1)]
                    qty = rnd_day.randint(1, 5)
                    items.append((pid, qty, price))
                    subtotal += qty * price
                total = round(subtotal * (0.95 + rnd_day.random() * 0.1), 2)

                cursor.execute(
                    """
                    INSERT INTO orders (
                        tenant_id, tracking_code, customer_name, customer_phone, status,
                        cargo_tracking_code, cargo_company, total_price, notes,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tenant_id,
                        code,
                        cust[0],
                        cust[1],
                        status,
                        cargo_code,
                        cargo_company,
                        total,
                        None,
                        ts,
                        ts,
                    ),
                )
                oid = cursor.lastrowid
                for pid, qty, up in items:
                    cursor.execute(
                        """
                        INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                        VALUES (?, ?, ?, ?)
                        """,
                        (oid, pid, qty, up),
                    )
                n_insert += 1
            if existing_demo + n_insert >= TARGET_DEMO_ORDERS:
                break

    # Bos kalan takvim gunlerini doldur (1-11 Mayis gibi; SKIP olsa bile calisir)
    sparse_filled = _fill_sparse_calendar_days(
        cursor, tenant_id, pid_list, customers, today, ensure_cargo_row
    )

    # Biletler (son 30 gun, hafif)
    demo_tickets = cursor.execute(
        "SELECT COUNT(*) AS c FROM tickets WHERE tenant_id = ? AND title LIKE 'Demo:%'",
        (tenant_id,),
    ).fetchone()["c"]
    if demo_tickets < 18:
        types = ["stock_alert", "cargo_delay", "anomaly", "other"]
        prios = ["low", "normal", "high"]
        for i in range(18 - int(demo_tickets)):
            dd = today - timedelta(days=i % 28)
            ts = f"{dd.isoformat()} 11:00:00"
            is_resolved = i % 3 == 0
            res_at = f"{dd.isoformat()} 16:00:00" if is_resolved else None
            cursor.execute(
                """
                INSERT INTO tickets (tenant_id, type, priority, status, title, description, created_at, resolved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    types[i % len(types)],
                    prios[i % len(prios)],
                    "resolved" if is_resolved else "open",
                    f"Demo: Operasyon notu #{i+1}",
                    "Otomatik demo bileti — grafik ve ozet ekranlari icin.",
                    ts,
                    res_at,
                ),
            )

    # Stok hareketleri (bir kisim urun)
    demo_mov = cursor.execute(
        "SELECT COUNT(*) AS c FROM stock_movements WHERE tenant_id = ? AND reason = 'demo_seed'",
        (tenant_id,),
    ).fetchone()["c"]
    if demo_mov < 40:
        for i in range(40 - int(demo_mov)):
            pid = pid_list[i % len(pid_list)][0]
            dd = today - timedelta(days=i % 35)
            ts = f"{dd.isoformat()} 10:15:00"
            delta = (-2 if i % 4 == 0 else 5) if i % 2 == 0 else -1
            cursor.execute(
                """
                INSERT INTO stock_movements (tenant_id, product_id, delta, reason, note, created_at)
                VALUES (?, ?, ?, 'demo_seed', ?, ?)
                """,
                (tenant_id, pid, delta, "Demo hareket", ts),
            )

    # Ornek gunluk raporlar + briefing_json (AI brifingi karti)
    has_source = _has_column(cursor, "daily_reports", "source")
    if has_source:
        n_rep = cursor.execute(
            "SELECT COUNT(*) AS c FROM daily_reports WHERE tenant_id = ? AND source = ?",
            (tenant_id, DEMO_REPORT_SOURCE),
        ).fetchone()["c"]
        if int(n_rep) < 8:
            for j in range(8 - int(n_rep)):
                rd = today - timedelta(days=j + 1)
                date_s = rd.isoformat()
                briefing = {
                    "headlines": [
                        f"{rd.strftime('%d.%m')} — {1200 + j * 180} TL ciro, siparisler duzgun akti.",
                        f"Stok: {2 + j % 3} urun dikkat; kargo gecikmesi {j % 2} adet.",
                    ],
                    "kpis": {
                        "toplam_siparis": 12 + j * 2,
                        "toplam_gelir": 1200.0 + j * 200,
                        "kritik_stok_sayisi": j % 4,
                    },
                    "risks": [
                        {"type": "info", "title": "Demo risk sinyali", "detail": "Gercek veri degil; UI testi."}
                    ],
                }
                text = (
                    f"## Gunluk ozet ({date_s})\n\n"
                    f"Satis ivmesi iyi; hazirlanan paket sayisi onceki gune gore stabil.\n\n"
                    f"## Oneri\n\n"
                    f"Kritik stoktaki urunlere kisa vadeli siparis plani."
                )
                cursor.execute(
                    """
                    INSERT INTO daily_reports (
                        tenant_id, date, report_text, raw_data, briefing_json,
                        model_version, source, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tenant_id,
                        date_s,
                        text,
                        json.dumps({"demo": True, "date": date_s}, ensure_ascii=False),
                        json.dumps(briefing, ensure_ascii=False),
                        "demo_v1",
                        DEMO_REPORT_SOURCE,
                        f"{date_s} 07:30:00",
                    ),
                )

    conn.commit()
    conn.close()

    bf = backfill_tenant_metrics(tenant_id)
    parts = [
        f"SIP-DEMO +{n_insert}",
        f"bos gun doldurma +{sparse_filled}",
        f"metrics backfill {bf} gun",
    ]
    if existing_demo >= TARGET_DEMO_ORDERS and n_insert == 0:
        head = "[SKIP] SIP-DEMO kotasi dolu;"
    else:
        head = "[OK] Demo zenginlestirme:"
    return f"{head} " + ", ".join(parts) + "."


if __name__ == "__main__":
    from database.db import init_db

    init_db()
    print(maybe_enrich_demo_chart_data())
