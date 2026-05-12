"""Kargo gecikmesi / iade durumunda müdahale (bilet) oluşturma — scheduler ve API ortak."""

from __future__ import annotations

import json

from repositories.tickets import create_ticket as repo_create_ticket

# Dashboard kargo özeti ve bilet tetikleme ile aynı küme
CARGO_DELAY_STATUSES = frozenset({"Şubede Bekliyor", "Gecikti", "İade Sürecinde"})


def cargo_delay_template(order_info: dict) -> dict:
    name = order_info.get("customer_name", "Müşteri")
    code = order_info.get("cargo_tracking_code", "")
    status = order_info.get("cargo_status", "Gecikti")
    delivery = order_info.get("estimated_delivery") or "yakın zamanda"
    musteri_mesaji = (
        f"Sayın {name},\n\n"
        f"{code} takip numaralı siparişinizde kargo sürecinde gecikme yaşanmaktadır. "
        f"Güncel durum: {status}. Tahmini teslimat: {delivery}.\n\n"
        f"Gecikmeden dolayı özür dileriz. Kargo durumunuzu {code} koduyla takip edebilirsiniz. "
        f"Herhangi bir sorunuz için müşteri hizmetlerimize ulaşabilirsiniz.\n\n"
        f"Saygılarımızla,\nMüşteri Hizmetleri"
    )
    ic_not = (
        f"Sipariş #{order_info.get('id')} — Kargo: {code} — "
        f"Durum: {status} — Müşteri: {name} ({order_info.get('customer_phone', '-')})"
    )
    return {"musteri_mesaji": musteri_mesaji, "ic_not": ic_not}


def create_cargo_delay_ticket_for_order(
    *,
    order_id: int,
    customer_name: str,
    customer_phone: str | None,
    cargo_tracking_code: str,
    cargo_status: str,
    estimated_delivery: str | None,
    tenant_id: int,
) -> int:
    """Açık müdahale varsa dedupe ile mevcut id döner."""
    order_info = {
        "id": order_id,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "cargo_tracking_code": cargo_tracking_code,
        "cargo_status": cargo_status,
        "estimated_delivery": estimated_delivery,
    }
    llm_json = json.dumps(cargo_delay_template(order_info), ensure_ascii=False)
    return repo_create_ticket(
        payload={
            "type": "cargo_delay",
            "title": f"Kargo Gecikmesi — Siparis #{order_id} ({customer_name})",
            "description": (
                f"Siparis #{order_id} ({customer_name}) kargo durumu: '{cargo_status}'. "
                f"Kargo kodu: {cargo_tracking_code}."
            ),
            "llm_content": llm_json,
            "priority": "high",
            "related_order_id": order_id,
        },
        tenant_id=tenant_id,
        dedupe_key={"type": "cargo_delay", "related_order_id": order_id},
    )
