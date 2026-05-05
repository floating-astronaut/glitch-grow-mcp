# Client setup — connecting your Mac's Claude Code to glitch-grow-mcp

You'll get **one bearer token** from us. That token is bound to your brand and grants the same agent capabilities we use internally — Meta / Amazon / TikTok / Google / LinkedIn ads, Shopify, social publishing — but scoped only to your accounts.

## One-time setup

```bash
claude mcp add --transport http glitchgrow https://mcp.glitchexecutor.com \
  -H "Authorization: Bearer <YOUR_TOKEN>"
```

Verify:

```bash
claude mcp list
# should show:  glitchgrow  https://mcp.glitchexecutor.com  ✓
```

## Verify access from inside Claude Code

Open Claude Code and ask:

> Use the `whoami` tool from `glitchgrow` and show me what I have access to.

You should see your brand name, your Shopify shop domains, and your ad account IDs.

## What you can do

The MCP exposes these tools (prefix `glitchgrow__` in Claude Code):

| Tool                          | Purpose                                                                |
|-------------------------------|------------------------------------------------------------------------|
| `whoami`                      | Show your brand, shops, ad accounts, scope                             |
| `ads_agent_run`               | Send a natural-language instruction to the AI ads agent for your brand |
| `ads_agent_health`            | Health-check the underlying agent                                      |
| `social_agent_run_script`     | Run a per-brand script in the social media agent                       |
| `meta_ads_list_accounts`      | List your Meta ad accounts                                             |
| `meta_ads_call`               | Call any Meta Ads tool (campaigns, ads, insights — full surface)       |
| `amazon_ads_list_profiles`    | List your Amazon Ads profiles                                          |
| `amazon_ads_call`             | Call any Amazon Ads tool                                               |

Example prompts:

- "Pull last 7 days Meta spend + ROAS for my brand and tell me the worst-performing ad set."
- "Run the foundation post script for today."
- "Pause every Meta ad with ROAS < 1.5 over the last 14 days."

## Security

- Your token cannot see other clients' data — every tool call is scoped server-side.
- We log every call (tool name, timestamp, scope) for audit. We never log the contents of your shop data.
- If your token is exposed, message us and we'll revoke it instantly.

## Troubleshooting

- **`401 invalid or revoked token`** — token mistyped, or revoked. Ask us for a new one.
- **`401 missing bearer token`** — the `-H "Authorization: Bearer …"` flag wasn't passed when you added the MCP. Re-run `claude mcp remove glitchgrow` and re-add with the header.
- **Tool returns "not in tenant allowlist"** — you're trying to operate on an account that isn't in your config. Ask us to add it (it's one JSON edit on our end, no restart needed).
