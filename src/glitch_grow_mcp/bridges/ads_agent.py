"""HTTP bridge to the running glitch-grow-ads-agent FastAPI service.

The agent is a long-running per-store-slug LangGraph service. /agent/run
takes a typed payload `{command, store_slug, ...kwargs}` and dispatches
through one of ~20 nodes. We forward the call after enforcing that the
store_slug is in the tenant's allowlist, and after injecting auth.

When the agent ships an update we pick it up automatically — no MCP
redeploy. When the agent adds a new command, this bridge already
supports it (we don't enumerate the list — it's `command` passthrough).
"""

from typing import Any

import httpx

from ..config import get_settings
from ..tenants import TenantConfig

# Canonical list as of 2026-05 (kept here for the help tool — does NOT
# constrain the bridge; new commands work without code changes).
KNOWN_COMMANDS: tuple[str, ...] = (
    "insights",
    "roas",
    "tracking_audit",
    "ads",
    "creative",
    "ideas",
    "alerts",
    "amazon",
    "amazon_recs",
    "meta_audit",
    "google_ads",
    "linkedin_ads",
    "attribution",
    "tiktok",
    "tiktok_campaigns",
    "tiktok_campaign_status",
    "tiktok_campaign_budget",
    "tiktok_pixels",
    "port_meta_to_tiktok",
    "enable_tiktok_launch",
)


class AdsAgentBridge:
    def __init__(self, tenant: TenantConfig):
        self.tenant = tenant
        s = get_settings()
        self.base_url = s.ads_agent_base_url
        self.run_token = s.ads_agent_run_token
        self.allowed_slugs = set(tenant.ads_agent_store_slugs)

    def _auth_headers(self) -> dict[str, str]:
        if not self.run_token:
            raise RuntimeError(
                "AGENT_RUN_TOKEN is not set in glitch-grow-mcp's .env — "
                "the ads-agent /agent/run endpoint is bearer-gated"
            )
        return {"Authorization": f"Bearer {self.run_token}"}

    def _enforce_slug(self, store_slug: str) -> None:
        if not self.allowed_slugs:
            raise PermissionError(
                f"tenant '{self.tenant.id}' has no ads_agent_store_slugs configured"
            )
        if store_slug not in self.allowed_slugs:
            raise PermissionError(
                f"store_slug '{store_slug}' not in tenant '{self.tenant.id}' "
                f"allowlist: {sorted(self.allowed_slugs)}"
            )

    async def run(
        self,
        command: str,
        store_slug: str,
        kwargs: dict[str, Any] | None = None,
    ) -> dict:
        """Invoke a typed agent command for one of the tenant's storefronts.

        `command` is one of KNOWN_COMMANDS (or any new one the agent ships).
        `store_slug` must be in this tenant's allowlist.
        `kwargs` is merged into the body — pass per-command fields like
        `days`, `limit`, `ad_id`, `campaign_id`, etc.
        """
        self._enforce_slug(store_slug)
        body: dict[str, Any] = {"command": command, "store_slug": store_slug}
        if kwargs:
            body.update(kwargs)
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(
                f"{self.base_url}/agent/run",
                json=body,
                headers=self._auth_headers(),
            )
            r.raise_for_status()
            return r.json()

    async def healthz(self) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{self.base_url}/healthz")
            r.raise_for_status()
            ct = r.headers.get("content-type", "")
            return r.json() if ct.startswith("application/json") else {"raw": r.text}
