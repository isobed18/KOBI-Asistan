"""
Musteri Yetkilendirme & Session Scope
======================================
Telefon veya takip kodu ile musteri kimlik dogrulama.
Agent tool'lari bu scope dahilinde kisitlanir.
"""

import contextvars
import string
import random
from database.db import get_connection

# ── ContextVar: async-safe, per-request scope ──
_current_scope = contextvars.ContextVar("customer_scope", default=None)

# ── Session scope deposu ──
_session_scopes: dict[str, dict] = {}


def generate_tracking_code() -> str:
    """SIP-XXXXXX formatta unique takip kodu uretir."""
    chars = string.ascii_uppercase + string.digits
    code = "".join(random.choices(chars, k=6))
    return f"SIP-{code}"


# ── Scope Yonetimi ──

def set_session_scope(session_id: str, telefon: str = None, takip_kodu: str = None):
    """
    Session'a musteri scope'u atar.
    telefon: musteri telefon numarasi -> tum siparislere erisim
    takip_kodu: siparis takip kodu -> sadece o siparise erisim
    """
    scope = {"telefon": telefon, "takip_kodu": takip_kodu}
    _session_scopes[session_id] = scope
    return scope


def get_session_scope(session_id: str) -> dict:
    """Session'in scope'unu dondurur."""
    return _session_scopes.get(session_id, {})


def clear_session_scope(session_id: str):
    """Session scope'unu temizler."""
    _session_scopes.pop(session_id, None)


# ── ContextVar (per-request) ──

def activate_scope(session_id: str):
    """Mevcut async context icin scope'u aktif eder."""
    scope = get_session_scope(session_id)
    _current_scope.set(scope)


def get_active_scope() -> dict:
    """Aktif request'in scope'unu dondurur. Scope yoksa bos dict."""
    return _current_scope.get() or {}


# ── Yetki Kontrol Fonksiyonlari ──

def check_order_access(order_row: dict) -> tuple:
    """
    Siparis satirina erisim izni kontrol eder.
    Returns: (is_allowed: bool, reason: str)
    """
    scope = get_active_scope()

    # Scope yoksa admin/unrestricted
    if not scope or (not scope.get("telefon") and not scope.get("takip_kodu")):
        return True, ""

    # Telefon ile scope
    if scope.get("telefon"):
        if order_row.get("customer_phone") != scope["telefon"]:
            return False, "Bu siparise erisim yetkiniz yok. Sadece kendi siparislerinizi sorgulayabilirsiniz."

    # Takip kodu ile scope
    if scope.get("takip_kodu"):
        if order_row.get("tracking_code") != scope["takip_kodu"]:
            return False, "Bu siparise erisim yetkiniz yok. Sadece takip kodunuzla baglantili siparisi sorgulayabilirsiniz."

    return True, ""


def get_customer_orders_filter() -> dict:
    """
    Aktif scope'a gore SQL WHERE kosulu uretir.
    Returns: {"where": str, "params": list}
    """
    scope = get_active_scope()

    if not scope:
        return {"where": "1=1", "params": []}

    if scope.get("telefon"):
        return {"where": "customer_phone = ?", "params": [scope["telefon"]]}

    if scope.get("takip_kodu"):
        return {"where": "tracking_code = ?", "params": [scope["takip_kodu"]]}

    return {"where": "1=1", "params": []}


# ── Telefon / Takip Kodu Dogrulama ──

def validate_phone(telefon: str) -> bool:
    """Telefon numarasinin DB'de kayitli olup olmadigini kontrol eder."""
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT COUNT(*) as c FROM orders WHERE customer_phone = ?", (telefon,)
    ).fetchone()
    conn.close()
    return row["c"] > 0


def validate_tracking_code(takip_kodu: str) -> bool:
    """Takip kodunun DB'de kayitli olup olmadigini kontrol eder."""
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT COUNT(*) as c FROM orders WHERE tracking_code = ?", (takip_kodu,)
    ).fetchone()
    conn.close()
    return row["c"] > 0
