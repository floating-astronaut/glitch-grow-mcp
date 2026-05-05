"""HTTP bridge to the running glitch-grow-ads-agent FastAPI service.

The agent is already a long-running per-brand service. We POST to its
`/agent/run` endpoint and inject the tenant's `ads_agent_brand`. When
the agent ships an update we pick it up automatically — no MCP redeploy.
"""

from typing import Any

import httpx

from ..config import get_settings
from ..tenants import TenantConfig


class AdsAgentBridge:
    def __init__(self, tenant: TenantConfig):
        self.tenant = tenant
        self.base_url = get_settings().ads_agent_base_url
        if not tenant.ads_agent_brand:
            raise PermissionError(
                f"tenant '{tenant.id}' has no ads_agent_brand configured"
            )

    async def run(self, instruction: str, context: dict[str, Any] | None = None) -> dict:
        """Send a natural-language instruction to the agent for this brand."""
        payload = {
            "brand": self.tenant.ads_agent_brand,
            "instruction": instruction,
            "context": context or {},
            "allowed_meta_ad_accounts": self.tenant.meta_ad_accounts,
            "allowed_amazon_profiles": self.tenant.amazon_profile_ids,
            "allowed_tiktok_advertisers": self.tenant.tiktok_advertiser_ids,
            "allowed_google_customers": self.tenant.google_ads_customer_ids,
            "allowed_shopify_shops": self.tenant.shopify_shops,
        }
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(f"{self.base_url}/agent/run", json=payload)
            r.raise_for_status()
            return r.json()

    async def healthz(self) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{self.base_url}/healthz")
            r.raise_for_status()
            return r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text}
