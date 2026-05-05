# glitch-grow-mcp

Multi-tenant MCP server that exposes Glitch Grow's ads + social agent capabilities to client Claude Code installs, scoped per tenant.

One MCP service. Per-client tokens. Each client adds one URL to their local Claude Code and gets the full agent suite — Meta, Amazon, TikTok, Google, LinkedIn ads + Shopify + social publishing — bound to their brand.

## Architecture

```
┌──────────────────────┐        bearer token         ┌────────────────────────────┐
│ Client's Claude Code │ ────────────────────────────▶│ glitch-grow-mcp (this repo)│
│  (local Mac)         │ ◀─── tools, scoped to tenant │ /home/support/glitch-grow- │
└──────────────────────┘                              │  mcp on :3104              │
                                                      └────────┬───────────────────┘
                                                               │
                              ┌────────────────────────────────┼────────────────────────────────┐
                              ▼                                ▼                                ▼
                  glitch-grow-ads-agent            glitch-social-media-agent         meta-ads-mcp / amazon-ads-mcp
                  (FastAPI, :3110, /agent/run)     (per-brand CLI scripts)           (federated MCPs on :3103, :3105)
```

- **Tenant config** is one JSON per tenant under `tenants/`. Hot-reloaded on every request — adding an ad account is `edit + save`, no restart.
- **Agent updates** are picked up automatically. Bridges call existing services / scripts; the MCP only needs a redeploy when new tool surfaces are added, not when underlying agents change.

## Quick start

```bash
cd /home/support/glitch-grow-mcp
python3 -m venv .venv && .venv/bin/pip install -e .

# issue a token for the Ayurpet tenant
.venv/bin/glitch-grow-mcp tokens issue --tenant ayurpet --label "client-mac-1"

# run the server (dev)
.venv/bin/glitch-grow-mcp serve
```

Production runs under `glitch-grow-mcp.service` (see `ops/glitch-grow-mcp.service`), behind nginx at `mcp.glitchexecutor.com`.

## Onboarding a new client

1. Drop a tenant config at `tenants/<id>.json` (copy `_template.json.example`).
2. `glitch-grow-mcp tokens issue --tenant <id> --label "<who>"` — copy the printed token to the client.
3. Client adds the MCP to their Claude Code:
   ```bash
   claude mcp add --transport http glitchgrow https://mcp.glitchexecutor.com \
     -H "Authorization: Bearer <token>"
   ```

## Forward-compat guarantees

| Change                                            | Action needed on MCP                          |
|---------------------------------------------------|-----------------------------------------------|
| Add a Meta ad account for an existing tenant      | edit `tenants/<id>.json`, save. **None.**     |
| Update the ads agent or social agent code         | restart the agent service. **None on MCP.**   |
| Add a NEW tool (e.g. wrap a new social script)    | edit `server.py`, restart `glitch-grow-mcp`.  |
| Onboard a new tenant                              | drop a JSON file + issue a token.             |

## CLI

```
glitch-grow-mcp serve                                  # run the MCP server
glitch-grow-mcp tenants list                           # list configured tenants
glitch-grow-mcp tenants show <id>                      # show one tenant's scope
glitch-grow-mcp tokens issue --tenant <id> --label X   # mint a new bearer token
glitch-grow-mcp tokens list                            # list issued tokens (hashes only)
glitch-grow-mcp tokens revoke <hash-prefix>            # revoke by prefix
```

## Audit

Every tool call is logged to `data/tokens.sqlite` (`audit` table) with tenant id, token hash prefix, tool name, redacted args, status, and timestamp. Query with any sqlite client.
