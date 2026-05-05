"""Bearer-token auth + per-call audit log.

Tokens are stored in sqlite. We never persist the raw token — only its
sha256 hash. The plaintext is shown to the operator exactly once at
issue-time (and ends up pasted into the client's Claude Code config).
"""

import hashlib
import secrets
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .config import get_settings


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- schema ----------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tokens (
  token_hash TEXT PRIMARY KEY,
  tenant_id  TEXT NOT NULL,
  label      TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tokens_tenant ON tokens(tenant_id);

CREATE TABLE IF NOT EXISTS audit (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ts         TEXT NOT NULL,
  tenant_id  TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  tool       TEXT NOT NULL,
  args_json  TEXT,
  status     TEXT NOT NULL,
  detail     TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_ts ON audit(tenant_id, ts);
"""


@contextmanager
def _conn(path: Path) -> Iterator[sqlite3.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _ensure_schema() -> None:
    with _conn(get_settings().tokens_db_path) as con:
        con.executescript(_SCHEMA)


# ---- token operations ------------------------------------------------------


def issue_token(tenant_id: str, label: str) -> str:
    """Mint a new token. Returns the plaintext — show to operator exactly once."""
    _ensure_schema()
    plaintext = "ggm_" + secrets.token_urlsafe(32)
    with _conn(get_settings().tokens_db_path) as con:
        con.execute(
            "INSERT INTO tokens (token_hash, tenant_id, label, created_at) VALUES (?,?,?,?)",
            (_hash(plaintext), tenant_id, label, _now()),
        )
    return plaintext


def revoke_token(token_hash_prefix: str) -> int:
    """Revoke by hash-prefix (operator never has the plaintext anymore)."""
    _ensure_schema()
    with _conn(get_settings().tokens_db_path) as con:
        cur = con.execute(
            "UPDATE tokens SET revoked_at=? WHERE token_hash LIKE ? AND revoked_at IS NULL",
            (_now(), token_hash_prefix + "%"),
        )
        return cur.rowcount


def list_tokens() -> list[dict]:
    _ensure_schema()
    with _conn(get_settings().tokens_db_path) as con:
        return [dict(r) for r in con.execute(
            "SELECT substr(token_hash,1,12) AS hash_prefix, tenant_id, label, "
            "created_at, revoked_at FROM tokens ORDER BY created_at DESC"
        )]


def resolve_token(plaintext: str | None) -> tuple[str, str] | None:
    """Look up a presented token. Returns (tenant_id, token_hash) or None."""
    if not plaintext:
        return None
    _ensure_schema()
    h = _hash(plaintext)
    with closing(sqlite3.connect(get_settings().tokens_db_path)) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT tenant_id, revoked_at FROM tokens WHERE token_hash = ?",
            (h,),
        ).fetchone()
    if row is None or row["revoked_at"] is not None:
        return None
    return row["tenant_id"], h


# ---- audit -----------------------------------------------------------------


def record_call(
    tenant_id: str,
    token_hash: str,
    tool: str,
    args_json: str,
    status: str,
    detail: str | None = None,
) -> None:
    _ensure_schema()
    with _conn(get_settings().tokens_db_path) as con:
        con.execute(
            "INSERT INTO audit (ts, tenant_id, token_hash, tool, args_json, status, detail) "
            "VALUES (?,?,?,?,?,?,?)",
            (_now(), tenant_id, token_hash, tool, args_json, status, detail),
        )
