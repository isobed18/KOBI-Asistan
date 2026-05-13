from __future__ import annotations

import re
from pathlib import Path

import bcrypt as _bcrypt
import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.tenant_config import TENANTS_DIR, business_type_presets, get_tenant_config
from database.db import get_connection

router = APIRouter(prefix="/tenant-setup", tags=["tenant-setup"])


class BusinessSetupPreviewRequest(BaseModel):
    business_name: str
    business_type: str
    owner_notes: str | None = None


class TenantRegisterRequest(BaseModel):
    business_name: str
    business_type: str
    owner_name: str
    username: str
    password: str
    owner_notes: str | None = None
    communication_rules: str | None = None


def _hash(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def _slugify(value: str) -> str:
    value = value.lower()
    value = value.replace("ı", "i").replace("ğ", "g").replace("ü", "u").replace("ş", "s").replace("ö", "o").replace("ç", "c")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "tenant"


def _next_tenant_id() -> int:
    conn = get_connection()
    row = conn.execute("SELECT COALESCE(MAX(tenant_id), 0) AS m FROM users").fetchone()
    conn.close()
    return int(row["m"] or 0) + 1


def _rules_from_text(text: str | None) -> list[str]:
    lines = []
    for raw in (text or "").splitlines():
        item = raw.strip(" -\t")
        if item:
            lines.append(item)
    return lines


def _write_tenant_config(payload: dict):
    slug = payload["slug"]
    target = TENANTS_DIR / slug
    target.mkdir(parents=True, exist_ok=True)
    (target / "config.yaml").write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    get_tenant_config.cache_clear()


@router.get("/business-types")
def list_business_types():
    """Onboarding ekraninin gosterecegi isletme tipi presetleri."""
    return business_type_presets()


@router.post("/preview")
def preview_business_setup(body: BusinessSetupPreviewRequest):
    """Ilk kayit ekraninda LLM'e gitmeden config taslagi uretir.

    Demo icin dusuk maliyetli deterministic preview. Sonraki adimda bu taslak
    admin onayi ile tenant config dosyasina veya DB tenant ayarlarina yazilabilir.
    """
    presets = business_type_presets()
    preset = presets.get(body.business_type) or presets["genel"]
    return {
        "business_name": body.business_name,
        "business_type": body.business_type,
        "preset": preset,
        "config_preview": {
            "agent": {
                "personality": (
                    f"{body.business_name} icin sakin, satis odakli ve proaktif bir musteri asistanisin. "
                    "Sadece katalog ve isletme kurallarina dayanarak cevap ver."
                ),
                "rules": preset["agent_rules"],
            },
            "features": preset["features"],
            "recommended_metadata": preset["recommended_metadata"],
            "owner_notes": body.owner_notes,
        },
    }


@router.post("/register", status_code=201)
def register_tenant(body: TenantRegisterRequest):
    """Demo/MVP kayıt akışı: tenant YAML config + admin kullanıcısı oluşturur."""
    business_name = body.business_name.strip()
    username = body.username.strip().lower()
    owner_name = body.owner_name.strip()
    password = body.password
    if len(business_name) < 2:
        raise HTTPException(status_code=400, detail="İşletme adı gerekli.")
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Kullanıcı adı en az 3 karakter olmalı.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Şifre en az 6 karakter olmalı.")

    presets = business_type_presets()
    preset = presets.get(body.business_type) or presets["genel"]
    tenant_id = _next_tenant_id()
    slug_base = _slugify(business_name)
    slug = slug_base
    i = 2
    while (TENANTS_DIR / slug / "config.yaml").exists():
        slug = f"{slug_base}-{i}"
        i += 1

    extra_rules = _rules_from_text(body.communication_rules)
    owner_notes = (body.owner_notes or "").strip()
    personality = (
        f"{business_name} için çalışan müşteri asistanısın. "
        "Cevaplarında işletmenin katalog bilgisini, stok durumunu ve aşağıdaki KOBİ notlarını esas al. "
        "Emin olmadığın konularda müşteriyi yanıltma; insan incelemesi gerektiren durumlarda bilet oluştur."
    )
    if owner_notes:
        personality += f"\n\nKOBİ notları:\n{owner_notes}"

    config_payload = {
        "tenant_id": tenant_id,
        "slug": slug,
        "business_name": business_name,
        "business_type": body.business_type,
        "language": "tr",
        "agent": {
            "name": f"{business_name} Asistanı",
            "role": "Müşteri iletişimi ve operasyon asistanı",
            "personality": personality,
            "rules": [*preset["agent_rules"], *extra_rules],
        },
        "llm": {
            "provider": "ollama",
            "model": "qwen3.6:27b",
            "temperature": 0.2,
        },
        "features": {
            **preset["features"],
            "dashboard_theme": "elegant",
            "whatsapp_business": False,
            "telegram_admin_notifications": True,
            "faq_rag": False,
            "report_export": False,
        },
        "branding": {
            "primary_color": "#2563eb",
            "accent_color": "#16a34a",
        },
    }

    conn = get_connection()
    try:
        if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            raise HTTPException(status_code=409, detail="Bu kullanıcı adı zaten kullanılıyor.")
        _write_tenant_config(config_payload)
        conn.execute(
            "INSERT INTO users (tenant_id, username, password_hash, role, full_name) VALUES (?, ?, ?, ?, ?)",
            (tenant_id, username, _hash(password), "admin", owner_name),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "tenant_id": tenant_id,
        "slug": slug,
        "username": username,
        "business_name": business_name,
        "business_type": body.business_type,
        "message": "KOBİ hesabı oluşturuldu. Giriş yaparak kuruluma devam edebilirsiniz.",
    }
