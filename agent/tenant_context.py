"""
Tenant Context
==============
Small contextvars helper for tenant-aware tools and graph prompts.
"""

import contextvars

_tenant_id = contextvars.ContextVar("tenant_id", default=1)


def set_tenant_id(tenant_id: int | None):
    _tenant_id.set(int(tenant_id or 1))


def get_tenant_id() -> int:
    return int(_tenant_id.get() or 1)
