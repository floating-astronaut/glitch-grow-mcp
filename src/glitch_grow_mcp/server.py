"""FastMCP server — exposes Glitch Grow agent capabilities, scoped per tenant."""

import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .auth import record_call
from .bridges import (
    AdsAgentBridge,
    AmazonAdsBridge,
    MetaAdsBridge,
    SocialAgentBridge,
)
from .config import get_settings
from .context import current_token_hash, require_tenant
from .middleware import BearerAuthMiddleware

log = logging.getLogger("glitch_grow_mcp")

# DNS rebinding protection: allow the public hostname through nginx in
# addition to the default localhost entries. Extend this list when adding
# more public hostnames.
mcp = FastMCP(
    "glitch-grow-mcp",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "127.0.0.1:*", "localhost:*", "[::1]:*",
            "mcp.glitchexecutor.com",
        ],
        allowed_origins=[
            "http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*",
            "https://mcp.glitchexecutor.com",
        ],
    ),
)


# ---- helpers ---------------------------------------------------------------


def _audit(tool: str, args: dict[str, Any], status: str, detail: str | None = None) -> None:
    tenant = require_tenant()
    tok = current_token_hash.get() or "?"
    try:
        record_call(tenant.id, tok, tool, json.dumps(args)[:8000], status, detail)
    except Exception:
        log.exception("audit write failed")


# ---- tenant introspection --------------------------------------------------


@mcp.tool()
def whoami() -> dict:
    """Return the calling tenant's id, display name, and resource scope."""
    t = require_tenant()
    out = {
        "id": t.id,
        "display_name": t.display_name,
        "shopify_shops": t.shopify_shops,
        "meta_ad_accounts": t.meta_ad_accounts,
        "amazon_profile_ids": t.amazon_profile_ids,
        "tiktok_advertiser_ids": t.tiktok_advertiser_ids,
        "google_ads_customer_ids": t.google_ads_customer_ids,
        "linkedin_ad_accounts": t.linkedin_ad_accounts,
        "ads_agent_brand": t.ads_agent_brand,
        "social_agent_brand": t.social_agent_brand,
        "ads_agent_store_slugs": t.ads_agent_store_slugs,
    }
    _audit("whoami", {}, "ok")
    return out


# ---- ads agent (HTTP bridge) ----------------------------------------------


@mcp.tool()
async def ads_agent_run(command: str, store_slug: str, kwargs: dict | None = None) -> dict:
    """Run a typed command on the Glitch Grow ads agent for one of your storefronts.

    Args:
      command: one of the agent's commands — e.g. `insights`, `roas`,
        `ads`, `creative`, `meta_audit`, `tiktok_campaigns`, `amazon`,
        `port_meta_to_tiktok`, etc. Use `ads_agent_list_commands` to see
        the canonical list.
      store_slug: which of your storefronts to act on (e.g. `ayurpet-ind`,
        `ayurpet`). Must be in your tenant's allowlist — see `whoami`.
      kwargs: per-command fields. Common ones: `days` (lookback window),
        `limit` (top-N), `ad_id`, `campaign_id`, `campaign_status`,
        `budget`. Unknown fields are passed through.

    Returns the agent's `{reply, state}` dict.
    """
    t = require_tenant()
    args = {"command": command, "store_slug": store_slug, "kwargs": kwargs}
    try:
        result = await AdsAgentBridge(t).run(command, store_slug, kwargs)
        _audit("ads_agent_run", args, "ok")
        return result
    except Exception as e:
        _audit("ads_agent_run", args, "error", repr(e))
        raise


@mcp.tool()
def ads_agent_list_commands() -> dict:
    """List the canonical commands accepted by `ads_agent_run`.

    The agent is a typed dispatcher (LangGraph router), not a natural-
    language interface. Use this list to pick a `command`. New commands
    the agent ships work automatically without a MCP redeploy — this
    list is just a snapshot for discoverability.
    """
    from .bridges.ads_agent import KNOWN_COMMANDS
    t = require_tenant()
    out = {
        "commands": list(KNOWN_COMMANDS),
        "your_store_slugs": t.ads_agent_store_slugs,
        "common_kwargs": {
            "days": "int — lookback window (most read commands)",
            "limit": "int — top-N (ads_leaderboard, etc.)",
            "ad_id": "str — for ad-level commands",
            "campaign_id": "str — for campaign-level commands",
            "campaign_status": "str — ACTIVE / PAUSED",
            "budget": "float — for budget updates",
        },
        "examples": [
            {"command": "insights", "store_slug": "<your-slug>", "kwargs": {"days": 7}},
            {"command": "roas", "store_slug": "<your-slug>", "kwargs": {"days": 14}},
            {"command": "ads", "store_slug": "<your-slug>", "kwargs": {"days": 7, "limit": 10}},
            {"command": "meta_audit", "store_slug": "<your-slug>"},
        ],
    }
    _audit("ads_agent_list_commands", {}, "ok")
    return out


@mcp.tool()
async def ads_agent_health() -> dict:
    """Ping the underlying ads agent service."""
    t = require_tenant()
    try:
        result = await AdsAgentBridge(t).healthz()
        _audit("ads_agent_health", {}, "ok")
        return result
    except Exception as e:
        _audit("ads_agent_health", {}, "error", repr(e))
        raise


# ---- social agent (subprocess bridge) -------------------------------------


@mcp.tool()
async def social_agent_run_script(script: str, args: list[str] | None = None) -> dict:
    """Run a script under glitch-social-media-agent/scripts/ for this tenant's brand.

    `script` is the filename (e.g. `post_foundation.py`). The brand flag is
    injected automatically; the tenant cannot pass `--brand` for another tenant.
    """
    t = require_tenant()
    call_args = {"script": script, "args": args}
    try:
        result = await SocialAgentBridge(t).run_script(script, args)
        _audit("social_agent_run_script", call_args, "ok")
        return result
    except Exception as e:
        _audit("social_agent_run_script", call_args, "error", repr(e))
        raise


# ---- meta ads (mcp federation) --------------------------------------------


@mcp.tool()
async def meta_ads_list_accounts() -> list[str]:
    """List Meta ad accounts this tenant is allowed to operate on."""
    t = require_tenant()
    result = await MetaAdsBridge(t).list_accounts()
    _audit("meta_ads_list_accounts", {}, "ok")
    return result


@mcp.tool()
async def meta_ads_call(tool: str, args: dict | None = None) -> Any:
    """Call any tool on the upstream meta-ads-mcp, scoped to this tenant's accounts.

    Use `meta_ads_list_accounts` first to see what you can target.
    """
    t = require_tenant()
    args = args or {}
    call_args = {"tool": tool, "args": args}
    try:
        result = await MetaAdsBridge(t).call_tool(tool, args)
        _audit("meta_ads_call", call_args, "ok")
        return result
    except Exception as e:
        _audit("meta_ads_call", call_args, "error", repr(e))
        raise


# ---- amazon ads (mcp federation) ------------------------------------------


@mcp.tool()
async def amazon_ads_list_profiles() -> list[str]:
    """List Amazon Ads profiles this tenant is allowed to operate on."""
    t = require_tenant()
    result = await AmazonAdsBridge(t).list_profiles()
    _audit("amazon_ads_list_profiles", {}, "ok")
    return result


@mcp.tool()
async def amazon_ads_call(tool: str, args: dict | None = None) -> Any:
    """Call any tool on the upstream amazon-ads-mcp, scoped to this tenant's profiles."""
    t = require_tenant()
    args = args or {}
    call_args = {"tool": tool, "args": args}
    try:
        result = await AmazonAdsBridge(t).call_tool(tool, args)
        _audit("amazon_ads_call", call_args, "ok")
        return result
    except Exception as e:
        _audit("amazon_ads_call", call_args, "error", repr(e))
        raise


# ---- ASGI app --------------------------------------------------------------


def _healthz(_request) -> JSONResponse:
    return JSONResponse({"ok": True, "service": "glitch-grow-mcp"})


def build_app() -> Starlette:
    """Build the Starlette app: bearer-auth middleware in front of FastMCP.

    The inner FastMCP app owns a session manager that must be started in a
    lifespan context. Mounting it under another Starlette doesn't propagate
    that lifespan automatically — we forward it explicitly.
    """
    mcp_app = mcp.streamable_http_app()
    app = Starlette(
        routes=[
            Route("/healthz", _healthz),
            Mount("/", app=mcp_app),
        ],
        lifespan=mcp_app.router.lifespan_context,
    )
    app.add_middleware(BearerAuthMiddleware)
    return app


app = build_app()


def main() -> None:
    import uvicorn

    s = get_settings()
    logging.basicConfig(level=getattr(logging, s.log_level.upper(), logging.INFO))
    uvicorn.run(app, host=s.host, port=s.port, log_level=s.log_level.lower())


if __name__ == "__main__":
    main()
