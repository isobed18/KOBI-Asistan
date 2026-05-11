"""
Varsayılan admin kullanıcısını oluşturur.
Sadece ilk kurulumda çalıştırın: python database/seed_users.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import bcrypt as _bcrypt
from database.db import get_connection, init_db


def _hash(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")

DEFAULT_USERS = [
    {
        "username":  "admin",
        "password":  "admin123",
        "role":      "admin",
        "full_name": "Sistem Yöneticisi",
        "tenant_id": 1,
    },
]


def seed():
    init_db()
    conn = get_connection()
    created = 0
    for u in DEFAULT_USERS:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (u["username"],)
        ).fetchone()
        if existing:
            print(f"  [SKIP] '{u['username']}' already exists, skipping.")
            continue
        conn.execute(
            "INSERT INTO users (username, password_hash, role, full_name, tenant_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (u["username"], _hash(u["password"]), u["role"], u["full_name"], u["tenant_id"]),
        )
        created += 1
        print(f"  [OK] '{u['username']}' olusturuldu (sifre: {u['password']})")

    conn.commit()
    conn.close()
    print(f"\n[OK] {created} kullanici eklendi.")


if __name__ == "__main__":
    seed()
