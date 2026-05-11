"""
Varsayılan admin kullanıcısını oluşturur.
Sadece ilk kurulumda çalıştırın: python database/seed_users.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from passlib.context import CryptContext
from database.db import get_connection, init_db

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
            print(f"  ⚠  '{u['username']}' zaten var, atlanıyor.")
            continue
        conn.execute(
            "INSERT INTO users (username, password_hash, role, full_name, tenant_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (u["username"], pwd_ctx.hash(u["password"]), u["role"], u["full_name"], u["tenant_id"]),
        )
        created += 1
        print(f"  ✓  '{u['username']}' oluşturuldu (şifre: {u['password']})")

    conn.commit()
    conn.close()
    print(f"\n[OK] {created} kullanıcı eklendi.")


if __name__ == "__main__":
    seed()
