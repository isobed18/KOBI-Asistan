from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta

from database.db import get_connection
from agent.tenant_context import get_tenant_id


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def create_otp_challenge(
    order_id: int,
    action: str,
    channel: str | None = None,
    channel_user_id: str | None = None,
    tenant_id: int | None = None,
) -> dict:
    tenant = int(tenant_id or get_tenant_id() or 1)
    code = f"{random.randint(100000, 999999)}"
    expires_at = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO otp_challenges (
            tenant_id, order_id, action, channel, channel_user_id, code_hash, expires_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (tenant, order_id, action, channel, channel_user_id, _hash_code(code), expires_at),
    )
    challenge_id = int(cursor.lastrowid)
    conn.commit()
    conn.close()
    return {
        "challenge_id": challenge_id,
        "order_id": order_id,
        "action": action,
        "code": code,
        "expires_at": expires_at,
    }


def verify_otp_challenge(
    order_id: int,
    action: str,
    code: str,
    tenant_id: int | None = None,
) -> dict:
    tenant = int(tenant_id or get_tenant_id() or 1)
    conn = get_connection()
    cursor = conn.cursor()
    challenge = cursor.execute(
        """
        SELECT *
        FROM otp_challenges
        WHERE tenant_id = ?
          AND order_id = ?
          AND action = ?
          AND verified_at IS NULL
          AND datetime(expires_at) >= datetime('now', 'localtime')
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (tenant, order_id, action),
    ).fetchone()

    if not challenge:
        conn.close()
        return {"ok": False, "hata": "Gecerli OTP bulunamadi veya suresi doldu."}

    attempts = int(challenge["attempts"])
    max_attempts = int(challenge["max_attempts"])
    if attempts >= max_attempts:
        conn.close()
        return {"ok": False, "hata": "OTP deneme hakki doldu."}

    if _hash_code(str(code).strip()) != challenge["code_hash"]:
        cursor.execute(
            "UPDATE otp_challenges SET attempts = attempts + 1 WHERE id = ?",
            (challenge["id"],),
        )
        conn.commit()
        conn.close()
        return {"ok": False, "hata": "OTP kodu hatali."}

    cursor.execute(
        "UPDATE otp_challenges SET verified_at = datetime('now', 'localtime') WHERE id = ?",
        (challenge["id"],),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "challenge_id": int(challenge["id"])}

