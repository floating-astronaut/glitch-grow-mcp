# Changelog — `glitch-grow-mcp`

Auto-regenerated from `git log` by `/home/support/bin/changelog-regen`,
called before every push by `/home/support/bin/git-sync-all` (cron `*/15 * * * *`).

**Purpose:** traceability. If a push broke something, scan dates + short SHAs
here; then `git show <sha>` to see the diff, `git revert <sha>` to undo.

**Format:** UTC dates, newest first. Each entry: `time — subject (sha) — N files`.
Body text (if present) shown as indented sub-bullets.

---

## 2026-05-16

- **02:46 UTC** — Allow browser MCP clients (claude.ai) — Origin allowlist, OAuth-discovery 404, WWW-Authenticate (`89c9196`) — 3 files
    When a teammate tried to connect this MCP from the Claude.ai web client,
    the access log showed three signals the server wasn't presenting itself
    the way browser-based MCP clients expect:
    1. Origin: https://claude.ai was rejected by FastMCP's
       DNS-rebinding TransportSecurity → 403 'Invalid Origin header'.
       Added claude.ai (and *.claude.ai) to allowed_origins.
    2. The client probed /.well-known/oauth-protected-resource,
       /.well-known/oauth-authorization-server, and /register before falling
       back to bearer. Our auth middleware was returning 401 on all of
       those, which read as 'OAuth required, you're unauthorized' rather

## 2026-05-06

- **21:04 UTC** — Wire ads_agent_run to the agent's real typed-command surface (`b231a5e`) — 6 files
    The previous payload (brand + free-form instruction + allowlist hints)
    mismatched the agent's actual /agent/run signature, which expects
    {command, store_slug, ...kwargs} — see AgentState in the agent's
    graph.py. Real calls were 500-ing with KeyError: 'store_slug'.
    Now:
    - ads_agent_run takes (command, store_slug, kwargs) and forwards the
      body verbatim. The agent's command set is enumerated only for
      discovery — the bridge passes through whatever command name is
      given, so new commands the agent ships work without an MCP redeploy.
    - New ads_agent_list_commands tool returns the canonical command list,
- **20:46 UTC** — Restart=always for glitch-grow-mcp.service (`f82f89f`) — 1 file
    Service was caught down on 2026-05-06 because a system-wide SIGTERM event
    on 2026-05-05 23:26:27 cleanly stopped it (along with several siblings).
    Restart=on-failure does not cover clean exits, so it stayed dead and
    nginx returned 502 to clients. Restart=always ensures it always comes
    back up regardless of how it exited.

## 2026-05-05

- **07:43 UTC** — Allow mcp.glitchexecutor.com in DNS-rebinding protection + nginx wildcard cert (`d7711e0`) — 2 files
    FastMCP defaults its allowed_hosts to localhost only when binding to 127.0.0.1,
    which made requests through nginx (Host: mcp.glitchexecutor.com) return 421.
    Added the public hostname to TransportSecuritySettings.
    Also pointed the nginx config at the existing *.glitchexecutor.com wildcard
    cert (no separate certbot run needed).
- **07:33 UTC** — Initial scaffold of glitch-grow-mcp — multi-tenant MCP product (`7278784`) — 22 files
    Productizes the Glitch Grow ads + social agents as a single MCP server
    that clients add to their local Claude Code via one bearer token. Each
    client's calls are scoped server-side to their brand's resources.
    What's here:
    - FastMCP streamable-HTTP server on :3106 with bearer-auth middleware
    - Per-tenant config = JSON file (hot-reload per request — adding an ad
      account is edit-and-save, no restart, no redeploy)
    - Bridges: ads-agent (HTTP to localhost:3110), social-agent (subprocess
      to scripts/), meta-ads-mcp (federated, scope-enforced),
      amazon-ads-mcp (federated, scope-enforced)
