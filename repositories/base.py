from __future__ import annotations

from typing import Protocol


class ProductRepository(Protocol):
    def search(self, query: str, tenant_id: int = 1) -> list[dict]:
        ...

    def update_stock(self, product_id: int, delta: int, reason: str, tenant_id: int = 1) -> dict:
        ...


class OrderRepository(Protocol):
    def update_status(
        self,
        order_id: int,
        status: str,
        tenant_id: int = 1,
        cargo_tracking_code: str | None = None,
        cargo_company: str | None = None,
        notes: str | None = None,
    ) -> dict:
        ...


class TicketRepository(Protocol):
    def create(self, payload: dict, tenant_id: int = 1, dedupe_key: dict | None = None) -> int:
        ...

