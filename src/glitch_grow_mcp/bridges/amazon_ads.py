"""MCP-federation bridge to the local amazon-ads-mcp on :3105.

Same pattern as the Meta bridge: forward tool calls, but reject any
whose profile_id is not in the tenant's amazon_profile_ids allowlist.
"""

from typing import Any

import httpx

from ..config import get_settings
from ..tenants import TenantConfig

_PROFILE_ARG_KEYS = ("profile_id", "amazon_profile_id", "profile")


class AmazonAdsBridge:
    def __init__(self, tenant: TenantConfig):
        self.tenant = tenant
        self.base_url = get_settings().amazon_ads_mcp_url
        self.allowed = set(tenant.amazon_profile_ids)

    def _enforce_profile_scope(self, args: dict[str, Any]) -> None:
        for key in _PROFILE_ARG_KEYS:
            if key in args and args[key] not in self.allowed:
                raise PermissionError(
                    f"amazon_ads: profile '{args[key]}' not in tenant '{self.tenant.id}' allowlist"
                )

    async def list_profiles(self) -> list[str]:
        return sorted(self.allowed)

    async def call_tool(self, tool_name: str, args: dict[str, Any]) -> Any:
        self._enforce_profile_scope(args)
        if not any(k in args for k in _PROFILE_ARG_KEYS) and len(self.allowed) == 1:
            args = {**args, "profile_id": next(iter(self.allowed))}
        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args},
        }
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(self.base_url, json=payload)
            r.raise_for_status()
            return r.json()
