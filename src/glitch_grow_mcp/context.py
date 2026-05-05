"""Per-request context — set by auth middleware, read by tool handlers."""

from contextvars import ContextVar

from .tenants import TenantConfig

current_tenant: ContextVar[TenantConfig | None] = ContextVar("current_tenant", default=None)
current_token_hash: ContextVar[str | None] = ContextVar("current_token_hash", default=None)


def require_tenant() -> TenantConfig:
    t = current_tenant.get()
    if t is None:
        raise PermissionError("no authenticated tenant on this request")
    return t
