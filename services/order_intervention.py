"""Sipariş iptalinde müdahale kaydı — panel durum güncellemesi ve OTP akışı ile uyumlu dedupe."""

from __future__ import annotations

from repositories.tickets import create_ticket as repo_create_ticket


def create_order_cancelled_intervention_ticket(
    *,
    order_id: int,
    customer_name: str,
    tenant_id: int,
    previous_status: str,
) -> int:
    """
    Sipariş 'iptal' olduğunda bilet açar.
    cancellation_request + related_order_id dedupe OTP/müşteri talebi ile aynıdır.
    """
    prev = (previous_status or "").strip()
    desc = (
        f"Sipariş #{order_id} 'iptal' durumuna alındı. Müşteri: {customer_name}."
        f" Önceki durum: {prev or '—'}."
    )
    return repo_create_ticket(
        payload={
            "type": "cancellation_request",
            "title": f"Sipariş iptal — #{order_id} ({customer_name})",
            "description": desc,
            "priority": "high",
            "related_order_id": order_id,
        },
        tenant_id=tenant_id,
        dedupe_key={"type": "cancellation_request", "related_order_id": order_id},
    )
