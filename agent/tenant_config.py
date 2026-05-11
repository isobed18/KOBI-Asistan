"""
Tenant Config Loader
====================
Selective adaptation inspired by yerdaulet-damir/langgraph-sales-agent:
each business can have a YAML config that controls branding, assistant
personality, rules, LLM preferences and feature flags without code changes.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
import json

ROOT = Path(__file__).resolve().parents[1]
TENANTS_DIR = ROOT / "tenants"


def _simple_yaml(text: str) -> dict[str, Any]:
    """
    Tiny YAML subset parser used as fallback when PyYAML is unavailable.
    Supports the config shape used in tenants/*/config.yaml:
    nested maps, booleans, numbers, quoted/unquoted strings and block lists.
    """
    result: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, result)]
    current_list_key: tuple[int, dict[str, Any], str] | None = None

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if line.startswith("- "):
            if current_list_key and current_list_key[0] == indent:
                _, list_parent, key = current_list_key
                list_parent.setdefault(key, []).append(line[2:].strip())
            continue

        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if value in ("", "|"):
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
            current_list_key = (indent + 2, parent, key) if value == "" else None
            continue

        if value.lower() in ("true", "false"):
            parsed: Any = value.lower() == "true"
        else:
            try:
                parsed = int(value)
            except ValueError:
                parsed = value.strip('"').strip("'")
        parent[key] = parsed
        current_list_key = None
    return result


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except Exception:
        return _simple_yaml(text)


@lru_cache(maxsize=64)
def get_tenant_config(slug: str = "default") -> dict[str, Any]:
    path = TENANTS_DIR / slug / "config.yaml"
    if not path.exists():
        path = TENANTS_DIR / "default" / "config.yaml"
    data = _load_yaml(path)
    data.setdefault("tenant_id", 1)
    data.setdefault("slug", slug)
    data.setdefault("business_name", "KOBI Asistan")
    data.setdefault("agent", {})
    data.setdefault("features", {})
    data.setdefault("branding", {})
    return data


def get_tenant_by_id(tenant_id: int | None) -> dict[str, Any]:
    tid = int(tenant_id or 1)
    for path in TENANTS_DIR.glob("*/config.yaml"):
        data = _load_yaml(path)
        if int(data.get("tenant_id", 1)) == tid:
            data.setdefault("slug", path.parent.name)
            return get_tenant_config(data["slug"])
    return get_tenant_config("default")


def tenant_public_payload(tenant_id: int | None = 1) -> dict[str, Any]:
    cfg = get_tenant_by_id(tenant_id)
    return {
        "tenant_id": cfg.get("tenant_id", 1),
        "slug": cfg.get("slug", "default"),
        "business_name": cfg.get("business_name", "KOBI Asistan"),
        "business_type": cfg.get("business_type", "kobi"),
        "language": cfg.get("language", "tr"),
        "agent_name": cfg.get("agent", {}).get("name", "Kobi"),
        "features": cfg.get("features", {}),
        "branding": cfg.get("branding", {}),
    }


def tenant_prompt_block(tenant_id: int | None = 1) -> str:
    cfg = get_tenant_by_id(tenant_id)
    agent = cfg.get("agent", {})
    rules = agent.get("rules", [])
    rules_text = "\n".join(f"- {r}" for r in rules) if isinstance(rules, list) else str(rules)
    return (
        f"Isletme: {cfg.get('business_name')}\n"
        f"Isletme tipi: {cfg.get('business_type')}\n"
        f"Asistan adi: {agent.get('name', 'Kobi')}\n"
        f"Asistan rolu: {agent.get('role', 'Operasyon Asistani')}\n"
        f"Kisilik:\n{agent.get('personality', '')}\n"
        f"Isletme kurallari:\n{rules_text}"
    )


def dump_config_debug(tenant_id: int | None = 1) -> str:
    return json.dumps(get_tenant_by_id(tenant_id), ensure_ascii=False, indent=2)
