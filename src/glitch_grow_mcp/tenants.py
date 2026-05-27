"""Tenant config loader.

Tenant configs live as JSON files in `tenants/<tenant_id>.json`. They are
re-read from disk on every request, so adding/removing accounts for a
tenant is just an edit-and-save — no restart, no redeploy.
"""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .config import get_settings


class TenantConfig(BaseModel):
    """One client's allowlist of resources.

    Add/remove fields as new surfaces are introduced. Anything missing
    from a tenant's file means that surface is not enabled for them.
    """

    id: str
    display_name: str
    enabled: bool = True

    # Per-surface scope. Each list defines what the tenant is allowed to touch.
    shopify_shops: list[str] = Field(default_factory=list)
    meta_ad_accounts: list[str] = Field(default_factory=list)
    amazon_profile_ids: list[str] = Field(default_factory=list)
    tiktok_advertiser_ids: list[str] = Field(default_factory=list)
    google_ads_customer_ids: list[str] = Field(default_factory=list)
    linkedin_ad_accounts: list[str] = Field(default_factory=list)

    # Brand keys passed to existing per-brand agents.
    ads_agent_brand: str | None = None
    social_agent_brand: str | None = None

    # MCP-5 (2026-05-27): cockpit-proxy identity.
    #
    # `actor_email` is the cockpit user whose `core.user_brands` row
    # authorizes any control-plane action this tenant stages through
    # the MCP gateway. The cockpit's POST /v1/control/actions (and
    # /automation-rules) requires `actor_email` in the body and
    # verifies it has operator role on the target brand. By stamping
    # it from the tenant config rather than letting the MCP client
    # supply it, we prevent an external client from impersonating
    # other operators.
    actor_email: str | None = None

    # `cockpit_brand_ids` is a defense-in-depth allowlist of brand_ids
    # this tenant may target through control-plane tools. The cockpit
    # re-verifies against `core.user_brands`, so this is NOT the auth
    # boundary — it's just an early reject so an MCP client targeting
    # the wrong brand gets a clearer error.
    cockpit_brand_ids: list[str] = Field(default_factory=list)

    # The ads agent dispatches per `store_slug` (one slug = one storefront).
    # List the slugs this tenant is allowed to drive; the bridge rejects
    # any call whose store_slug isn't in this set.
    ads_agent_store_slugs: list[str] = Field(default_factory=list)

    # Free-form metadata (notes, contacts, etc.). Not used by code.
    meta: dict[str, Any] = Field(default_factory=dict)


class TenantNotFound(Exception):
    pass


def _path_for(tenant_id: str) -> Path:
    return get_settings().tenants_dir / f"{tenant_id}.json"


def load_tenant(tenant_id: str) -> TenantConfig:
    """Load a tenant's config from disk. Re-read every call (hot reload)."""
    path = _path_for(tenant_id)
    if not path.is_file():
        raise TenantNotFound(f"tenant '{tenant_id}' not found at {path}")
    raw = json.loads(path.read_text())
    return TenantConfig(**raw)


def list_tenants() -> list[str]:
    return sorted(p.stem for p in get_settings().tenants_dir.glob("*.json"))


def write_tenant(cfg: TenantConfig) -> Path:
    path = _path_for(cfg.id)
    path.write_text(json.dumps(cfg.model_dump(), indent=2, sort_keys=True) + "\n")
    return path
