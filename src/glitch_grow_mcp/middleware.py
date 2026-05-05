"""Starlette middleware: extract Bearer token, resolve tenant, set contextvars."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .auth import resolve_token
from .context import current_tenant, current_token_hash
from .tenants import TenantConfig, TenantNotFound, load_tenant

_PUBLIC_PATHS = {"/healthz"}


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        authz = request.headers.get("authorization", "")
        if not authz.lower().startswith("bearer "):
            return JSONResponse({"error": "missing bearer token"}, status_code=401)
        token = authz.split(None, 1)[1].strip()

        resolved = resolve_token(token)
        if resolved is None:
            return JSONResponse({"error": "invalid or revoked token"}, status_code=401)
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
