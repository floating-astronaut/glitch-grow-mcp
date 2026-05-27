"""MCP-5 (2026-05-27): cockpit control-plane bridge.

The retired `apps/mcp/glitch-grow/` server (R4, MCP-RETIRE-2) used to
hold per-platform bridges (ads_agent, social_agent, meta_ads, amazon_ads)
that talked directly to back-end services and APIs. Post-pivot, the
MCP gateway's job is ONE thing: forward external AI client tool-calls
into the cockpit's canonical `/v1/control/*` substrate.

This module is that forwarder. It has no DB access, no per-platform
credentials, no business logic — just one thin httpx client that
authenticates to the cockpit with `X-Internal-Token` and stamps the
tenant's `actor_email` so the cockpit knows whose `core.user_brands`
binding to authorize against.

Why a separate bridge module: keeps the auth secret + URL constant
loading in one place, lets the server.py tool definitions stay
declarative.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import get_settings
from ..tenants import TenantConfig

log = logging.getLogger("glitch_grow_mcp.bridges.control_plane")


class ControlPlaneError(Exception):
    """Raised when the cockpit returns a non-2xx response or the bridge
    is misconfigured (missing token, missing actor_email, etc.). The
    server.py tool handler turns this into a structured MCP tool
    error so the calling AI client can adapt."""

    def __init__(self, message: str, *, status_code: int | None = None,
                 detail: Any | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


def _require_actor_email(tenant: TenantConfig) -> str:
    if not tenant.actor_email:
        raise ControlPlaneError(
            f"tenant {tenant.id!r} has no actor_email — "
            "set `actor_email` in the tenant JSON before using "
            "control-plane tools."
        )
    return tenant.actor_email


def _require_brand_allowed(tenant: TenantConfig, brand_id: str) -> None:
    """Defense-in-depth allowlist check. Cockpit still verifies via
    core.user_brands — this is just an earlier reject with a clearer
    error message."""
    if tenant.cockpit_brand_ids and brand_id not in tenant.cockpit_brand_ids:
        raise ControlPlaneError(
            f"brand_id {brand_id!r} is not in tenant {tenant.id!r}'s "
            f"cockpit_brand_ids allowlist {tenant.cockpit_brand_ids}",
        )


async def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    s = get_settings()
    if not s.cockpit_internal_token:
        raise ControlPlaneError(
            "GGM_COCKPIT_INTERNAL_TOKEN is not configured — the MCP "
            "server has no credential to call the cockpit. Set it in "
            "the MCP server's .env before enabling control-plane tools."
        )
    url = f"{s.cockpit_base_url.rstrip('/')}{path}"
    headers = {
        "X-Internal-Token": s.cockpit_internal_token,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, headers=headers, json=body)
    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:  # noqa: BLE001
            detail = resp.text
        raise ControlPlaneError(
            f"cockpit POST {path} failed ({resp.status_code})",
            status_code=resp.status_code,
            detail=detail,
        )
    return resp.json()


async def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    s = get_settings()
    if not s.cockpit_internal_token:
        raise ControlPlaneError(
            "GGM_COCKPIT_INTERNAL_TOKEN is not configured — the MCP "
            "server has no credential to call the cockpit."
        )
    url = f"{s.cockpit_base_url.rstrip('/')}{path}"
    headers = {"X-Internal-Token": s.cockpit_internal_token}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=headers, params=params)
    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:  # noqa: BLE001
            detail = resp.text
        raise ControlPlaneError(
            f"cockpit GET {path} failed ({resp.status_code})",
            status_code=resp.status_code,
            detail=detail,
        )
    return resp.json()


class ControlPlaneBridge:
    """One instance per request. Holds the resolved tenant; reads
    settings lazily through `_post` / `_get` so a config rotation
    picks up on the next call."""

    def __init__(self, tenant: TenantConfig) -> None:
        self.tenant = tenant

    async def stage_action(
        self,
        *,
        brand_id: str,
        action_type: str,
        title: str,
        summary: str | None = None,
        agent_sku: str | None = None,
        idempotency_key: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _require_brand_allowed(self.tenant, brand_id)
        body: dict[str, Any] = {
            "brand_id": brand_id,
            "action_type": action_type,
            "title": title,
            "actor_email": _require_actor_email(self.tenant),
        }
        if summary is not None:
            body["summary"] = summary
        if agent_sku is not None:
            body["agent_sku"] = agent_sku
        if idempotency_key is not None:
            body["idempotency_key"] = idempotency_key
        if payload is not None:
            body["payload"] = payload
        return await _post("/v1/control/actions", body)

    async def list_actions(
        self,
        *,
        brand_id: str,
        action_status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        _require_brand_allowed(self.tenant, brand_id)
        params: dict[str, Any] = {
            "brand_id": brand_id,
            "source": "mcp",  # only show this tenant-class's own staged work
            "limit": limit,
        }
        if action_status:
            params["status"] = action_status
        return await _get("/v1/control/actions", params)

    async def stage_automation_rule(
        self,
        *,
        brand_id: str,
        title: str,
        action_kind: str,
        schedule_expression: str,
        config: dict[str, Any] | None = None,
        next_run_at: str | None = None,
    ) -> dict[str, Any]:
        _require_brand_allowed(self.tenant, brand_id)
        body: dict[str, Any] = {
            "brand_id": brand_id,
            "title": title,
            "action_kind": action_kind,
            "schedule_expression": schedule_expression,
            "actor_email": _require_actor_email(self.tenant),
        }
        if config is not None:
            body["config"] = config
        if next_run_at is not None:
            body["next_run_at"] = next_run_at
        return await _post("/v1/control/automation-rules", body)

    async def list_automation_rules(
        self,
        *,
        brand_id: str,
        rule_status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        _require_brand_allowed(self.tenant, brand_id)
        params: dict[str, Any] = {
            "brand_id": brand_id,
            "source": "mcp",
            "limit": limit,
        }
        if rule_status:
            params["status"] = rule_status
        return await _get("/v1/control/automation-rules", params)
