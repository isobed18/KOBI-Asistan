"""
Demo icin sahte veri olusturur.
python -m database.seed komutuyla calistir.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import get_connection, init_db


def seed():
    init_db()
    conn = get_connection()
    cursor = conn.cursor()

    if cursor.execute("SELECT COUNT(*) FROM products").fetchone()[0] > 0:
        print("[SKIP] Veri zaten mevcut, seed atlandi.")
        conn.close()
        from database.enrich_demo_history import maybe_enrich_demo_chart_data

        print(maybe_enrich_demo_chart_data())
        return

    # URUNLER
    products = [
        ("Organik Domates",      "Sebze",    45.00,  8,  15),
        ("Koy Yumurtasi (30lu)", "Gida",     85.00,  25, 10),
        ("Zeytinyagi 1L",        "Gida",     220.00, 5,  10),
        ("Cicek Bali 500g",      "Gida",     180.00, 40, 10),
        ("Nohut 1kg",            "Bakliyat", 55.00,  60, 15),
        ("Mercimek 1kg",         "Bakliyat", 48.00,  3,  10),
        ("El Yapimi Recel",      "Gida",     95.00,  18, 10),
        ("Ceviz Ici 500g",       "Kuruyemis", 340.00, 12, 10),
    ]
    cursor.executemany("""
        INSERT INTO products (name, category, price, stock_quantity, low_stock_threshold)
        VALUES (?,?,?,?,?)
    """, products)

    # SIPARISLER (tracking_code eklendi)
    orders = [
        # (tracking_code, musteri, telefon, durum, kargo_kodu, kargo_firma, toplam, not)
        ("SIP-AY7K21", "Ayse Kaya",     "05321234567", "teslim_edildi", "YK-88291",  "Yurtici",  310.00, None),
        ("SIP-MD3R45", "Mehmet Demir",   "05334567890", "kargoda",       "MNG-44512", "MNG",      625.00, None),
        ("SIP-FC9B67", "Fatma Celik",    "05359876543", "kargoda",       "PTT-20011", "PTT",      180.00, "Kapida odeme"),
        ("SIP-AY8X12", "Ali Yildiz",     "05361112233", "hazırlanıyor",  None,        None,       503.00, None),
        ("SIP-ZA4N89", "Zeynep Arslan",  "05389998877", "hazırlanıyor",  None,        None,       265.00, "Fatura kesilsin"),
        ("SIP-CO1T56", "Can Ozturk",     "05301234000", "iptal",         None,        None,       95.00,  "Musteri vazgecti"),
    ]
    cursor.executemany("""
        INSERT INTO orders (tracking_code, customer_name, customer_phone, status,
                            cargo_tracking_code, cargo_company, total_price, notes)
        VALUES (?,?,?,?,?,?,?,?)
    """, orders)

    # SIPARIS KALEMLERI
    order_items = [
        (1, 1, 2, 45.00), (1, 5, 2, 55.00), (1, 2, 1, 85.00),
        (2, 3, 1, 220.00), (2, 4, 1, 180.00), (2, 8, 1, 340.00),
        (3, 4, 1, 180.00),
        (4, 2, 2, 85.00), (4, 7, 2, 95.00), (4, 1, 3, 45.00),
        (5, 5, 3, 55.00), (5, 6, 2, 48.00), (5, 7, 1, 95.00),
        (6, 7, 1, 95.00),
    ]
    cursor.executemany("""
        INSERT INTO order_items (order_id, product_id, quantity, unit_price)
        VALUES (?,?,?,?)
    """, order_items)

    # KARGO TAKIP
    cargo = [
        ("MNG-44512",  "MNG Kargo",     "Dagitima Cikti",   "2026-05-12", "2026-05-11 08:30:00"),
        ("YK-88291",   "Yurtici Kargo", "Teslim Edildi",    "2026-05-07", "2026-05-07 14:20:00"),
        ("PTT-20011",  "PTT Kargo",     "Subede Bekliyor",  "2026-05-13", "2026-05-10 16:00:00"),
    ]
    cursor.executemany("""
        INSERT INTO cargo_tracking (tracking_code, company, current_status,
                                     estimated_delivery, last_update)
        VALUES (?,?,?,?,?)
    """, cargo)

    conn.commit()
    conn.close()
    print("[OK] Demo verisi eklendi!")
    print("   - 8 urun, 6 siparis (tracking code'lu), 3 kargo kaydi")

    from database.enrich_demo_history import maybe_enrich_demo_chart_data

    print(maybe_enrich_demo_chart_data())


if __name__ == "__main__":
    seed()
