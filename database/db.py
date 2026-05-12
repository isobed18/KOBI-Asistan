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
            tenant_id       INTEGER NOT NULL DEFAULT 1,
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
            tenant_id            INTEGER NOT NULL DEFAULT 1,
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

    # İNSAN İNCELEME BİLETLERİ
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id           INTEGER NOT NULL DEFAULT 1,
            type                TEXT NOT NULL,
            priority            TEXT NOT NULL DEFAULT 'normal',
            status              TEXT NOT NULL DEFAULT 'open',
            title               TEXT NOT NULL,
            description         TEXT,
            llm_content         TEXT,
            related_order_id    INTEGER,
            related_product_id  INTEGER,
            created_at          TEXT DEFAULT (datetime('now', 'localtime')),
            resolved_at         TEXT
        )
    """)

    # GÜNLÜK AI RAPORLARI (kiracı bazlı + yapılandırılmış brifing)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_reports (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id      INTEGER NOT NULL DEFAULT 1,
            date           TEXT NOT NULL,
            report_text    TEXT NOT NULL,
            raw_data       TEXT,
            briefing_json  TEXT,
            model_version  TEXT,
            source           TEXT,
            supersedes_id    INTEGER,
            created_at     TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # STOK HAREKETLERİ
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_movements (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id   INTEGER NOT NULL DEFAULT 1,
            product_id  INTEGER NOT NULL,
            delta       INTEGER NOT NULL,
            reason      TEXT NOT NULL DEFAULT 'manuel',
            note        TEXT,
            before_qty  INTEGER,
            after_qty   INTEGER,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    # KULLANICILAR (admin / kobi)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id    INTEGER NOT NULL DEFAULT 1,
            username     TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role         TEXT NOT NULL DEFAULT 'admin',
            full_name    TEXT,
            is_active    INTEGER NOT NULL DEFAULT 1,
            created_at   TEXT DEFAULT (datetime('now', 'localtime')),
            last_login   TEXT
        )
    """)

    # OTP CHALLENGES (kritik musteri aksiyonlari)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS otp_challenges (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id       INTEGER NOT NULL DEFAULT 1,
            order_id        INTEGER NOT NULL,
            action          TEXT NOT NULL,
            channel         TEXT,
            channel_user_id TEXT,
            code_hash       TEXT NOT NULL,
            attempts        INTEGER NOT NULL DEFAULT 0,
            max_attempts    INTEGER NOT NULL DEFAULT 5,
            expires_at      TEXT NOT NULL,
            verified_at     TEXT,
            created_at      TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # Günlük özet metrikleri (grafik / kıyas)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tenant_daily_metrics (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id        INTEGER NOT NULL,
            metric_date      TEXT NOT NULL,
            order_count      INTEGER NOT NULL DEFAULT 0,
            revenue          REAL NOT NULL DEFAULT 0,
            cancelled_count  INTEGER NOT NULL DEFAULT 0,
            avg_order_value  REAL,
            metrics_json     TEXT,
            computed_at      TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(tenant_id, metric_date)
        )
    """)

    # Basit AI / istatistik tahmin satırları
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tenant_daily_forecasts (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id          INTEGER NOT NULL,
            forecast_for_date  TEXT NOT NULL,
            generated_at       TEXT DEFAULT (datetime('now', 'localtime')),
            horizon_days       INTEGER NOT NULL DEFAULT 7,
            payload_json       TEXT NOT NULL
        )
    """)

    # İnsan girilen günlük hedefler
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tenant_daily_targets (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id       INTEGER NOT NULL,
            target_date     TEXT NOT NULL,
            revenue_target  REAL,
            order_target    INTEGER,
            notes           TEXT,
            created_at      TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(tenant_id, target_date)
        )
    """)

    # Hafif migration: eski SQLite dosyalarinda yeni kolonlar eksikse ekle.
    def ensure_column(table: str, column: str, ddl: str):
        cols = [r["name"] for r in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
        if column not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    for table in ("products", "orders", "tickets", "users", "stock_movements", "otp_challenges"):
        ensure_column(table, "tenant_id", "INTEGER NOT NULL DEFAULT 1")

    # Eski daily_reports şeması (tenant yok): kolon migrasyonu
    dr_cols = [r["name"] for r in cursor.execute("PRAGMA table_info(daily_reports)").fetchall()]
    if dr_cols:
        ensure_column("daily_reports", "tenant_id", "INTEGER NOT NULL DEFAULT 1")
        ensure_column("daily_reports", "briefing_json", "TEXT")
        ensure_column("daily_reports", "model_version", "TEXT")
        ensure_column("daily_reports", "source", "TEXT")
        ensure_column("daily_reports", "supersedes_id", "INTEGER")

    # Kargo paneli: manuel "Bildir" ile isaretlenen gecikmeler (kalici)
    ensure_column("orders", "cargo_delay_bildirildi_at", "TEXT")

    # Telegram siparis talebi: acik talep dedupe ve sorgu
    ensure_column("tickets", "source_channel_user_id", "TEXT")

    def ensure_index(name: str, ddl: str):
        cursor.execute(ddl)

    ensure_index(
        "idx_orders_tenant_created",
        "CREATE INDEX IF NOT EXISTS idx_orders_tenant_created ON orders(tenant_id, created_at)",
    )
    ensure_index(
        "idx_tickets_tenant_created",
        "CREATE INDEX IF NOT EXISTS idx_tickets_tenant_created ON tickets(tenant_id, created_at)",
    )
    ensure_index(
        "idx_daily_reports_tenant_date",
        "CREATE INDEX IF NOT EXISTS idx_daily_reports_tenant_date ON daily_reports(tenant_id, date, created_at DESC)",
    )
    ensure_index(
        "idx_tdm_tenant_date",
        "CREATE INDEX IF NOT EXISTS idx_tdm_tenant_date ON tenant_daily_metrics(tenant_id, metric_date)",
    )
    ensure_index(
        "idx_tdf_tenant_forecast",
        "CREATE INDEX IF NOT EXISTS idx_tdf_tenant_forecast ON tenant_daily_forecasts(tenant_id, forecast_for_date, generated_at DESC)",
    )
    ensure_index(
        "idx_stock_mov_tenant_created",
        "CREATE INDEX IF NOT EXISTS idx_stock_mov_tenant_created ON stock_movements(tenant_id, created_at)",
    )

    conn.commit()
    conn.close()
    print("[OK] Veritabani hazir.")
