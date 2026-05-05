"""MCP-federation bridge to the local meta-ads-mcp on :3103.

The upstream MCP exposes Meta Marketing API tools across all ad accounts
the operator has access to. We forward tool calls but reject any whose
account_id argument is not in this tenant's allowlist.
"""

from typing import Any

import httpx

from ..config import get_settings
from ..tenants import TenantConfig

# Argument names that carry an ad-account ID across the upstream MCP's tool surface.
_ACCOUNT_ARG_KEYS = ("account_id", "ad_account_id", "act_id", "account")


class MetaAdsBridge:
    def __init__(self, tenant: TenantConfig):
        self.tenant = tenant
        self.base_url = get_settings().meta_ads_mcp_url
        self.allowed = set(tenant.meta_ad_accounts)

    def _enforce_account_scope(self, args: dict[str, Any]) -> None:
        for key in _ACCOUNT_ARG_KEYS:
            if key in args and args[key] not in self.allowed:
                raise PermissionError(
                    f"meta_ads: account '{args[key]}' not in tenant '{self.tenant.id}' allowlist"
                )

    async def list_accounts(self) -> list[str]:
        """Tenants only ever see THEIR accounts via this bridge."""
        return sorted(self.allowed)

    async def call_tool(self, tool_name: str, args: dict[str, Any]) -> Any:
        """Forward a single tool call, after scope check.

        The upstream MCP speaks streamable-HTTP; we use a minimal JSON-RPC
        shape that matches the MCP `tools/call` envelope. Adjust if the
        upstream protocol revs.
        """
        self._enforce_account_scope(args)
        # If no explicit account scope but the tenant only has one, inject it.
        if not any(k in args for k in _ACCOUNT_ARG_KEYS) and len(self.allowed) == 1:
            args = {**args, "account_id": next(iter(self.allowed))}

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
