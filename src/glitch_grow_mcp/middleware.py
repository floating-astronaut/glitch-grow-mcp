"""Starlette middleware: extract Bearer token, resolve tenant, set contextvars."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .auth import resolve_token
from .context import current_tenant, current_token_hash
from .tenants import TenantConfig, TenantNotFound, load_tenant

_PUBLIC_PATHS = {"/healthz"}

# Paths that some MCP clients probe for OAuth discovery. We don't implement
# OAuth — we return a clean 404 so they recognize "no OAuth here" and fall
# back to static bearer (when the client supports both).
_OAUTH_DISCOVERY_PREFIXES = (
    "/.well-known/oauth-",
    "/.well-known/openid-",
    "/register",
)

# WWW-Authenticate header on 401s so clients know bearer is the auth scheme.
_WWW_AUTH = 'Bearer realm="glitch-grow-mcp", error="invalid_token"'


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in _PUBLIC_PATHS:
            return await call_next(request)
        if any(path.startswith(p) for p in _OAUTH_DISCOVERY_PREFIXES):
            return JSONResponse(
                {"error": "this MCP uses static bearer auth, not OAuth"},
                status_code=404,
            )

        authz = request.headers.get("authorization", "")
        if not authz.lower().startswith("bearer "):
            return JSONResponse(
                {"error": "missing bearer token"},
                status_code=401,
                headers={"WWW-Authenticate": _WWW_AUTH},
            )
        token = authz.split(None, 1)[1].strip()

        resolved = resolve_token(token)
        if resolved is None:
            return JSONResponse(
                {"error": "invalid or revoked token"},
                status_code=401,
                headers={"WWW-Authenticate": _WWW_AUTH},
            )
        tenant_id, token_hash = resolved

        try:
            tenant: TenantConfig = load_tenant(tenant_id)
        except TenantNotFound:
            return JSONResponse(
                {"error": f"tenant '{tenant_id}' config missing"}, status_code=500
            )
        if not tenant.enabled:
            return JSONResponse({"error": "tenant disabled"}, status_code=403)

        # Hot-reloaded per request — adding accounts to the JSON file
        # takes effect immediately on the next call.
        token_t = current_tenant.set(tenant)
        token_h = current_token_hash.set(token_hash)
        try:
            return await call_next(request)
        finally:
            current_tenant.reset(token_t)
            current_token_hash.reset(token_h)
