import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "kobi.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # URUNLER
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            category        TEXT,
            price           REAL NOT NULL,
            stock_quantity  INTEGER NOT NULL DEFAULT 0,
            low_stock_threshold INTEGER NOT NULL DEFAULT 10,
            is_active       INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # SIPARISLER
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_code        TEXT UNIQUE,
            customer_name        TEXT NOT NULL,
            customer_phone       TEXT,
            status               TEXT NOT NULL DEFAULT 'hazırlanıyor',
            cargo_tracking_code  TEXT,
            cargo_company        TEXT,
            total_price          REAL,
            notes                TEXT,
            created_at           TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at           TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # SIPARIS KALEMLERI
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id    INTEGER NOT NULL,
            product_id  INTEGER NOT NULL,
            quantity    INTEGER NOT NULL,
            unit_price  REAL NOT NULL,
            FOREIGN KEY (order_id)   REFERENCES orders(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    # KARGO TAKIP
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cargo_tracking (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_code      TEXT NOT NULL UNIQUE,
            company            TEXT NOT NULL,
            current_status     TEXT NOT NULL,
            estimated_delivery TEXT,
            last_update        TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    conn.commit()
    conn.close()
    print("[OK] Veritabani hazir.")
