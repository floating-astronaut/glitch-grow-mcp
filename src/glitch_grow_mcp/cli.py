"""Admin CLI: tenants + tokens.

Usage:
  glitch-grow-mcp serve
  glitch-grow-mcp tenants list
  glitch-grow-mcp tenants show <id>
  glitch-grow-mcp tokens issue --tenant <id> --label <label>
  glitch-grow-mcp tokens list
  glitch-grow-mcp tokens revoke <hash-prefix>
"""

import argparse
import json
import sys

from .auth import issue_token, list_tokens, revoke_token
from .tenants import TenantNotFound, list_tenants, load_tenant


def _cmd_serve(_args) -> int:
    from . import server  # local import — server is heavyweight
    server.main()
    return 0


def _cmd_tenants_list(_args) -> int:
    for tid in list_tenants():
        try:
            t = load_tenant(tid)
            print(f"{tid}\t{t.display_name}\tenabled={t.enabled}")
        except Exception as e:
            print(f"{tid}\t<error: {e}>", file=sys.stderr)
    return 0


def _cmd_tenants_show(args) -> int:
    try:
        t = load_tenant(args.id)
    except TenantNotFound as e:
        print(str(e), file=sys.stderr)
        return 2
    print(json.dumps(t.model_dump(), indent=2, sort_keys=True))
    return 0


def _cmd_tokens_issue(args) -> int:
    try:
        load_tenant(args.tenant)
    except TenantNotFound as e:
        print(f"refusing to issue: {e}", file=sys.stderr)
        return 2
    plaintext = issue_token(args.tenant, args.label)
    print("Token issued. Show this to the client ONCE — it is not stored anywhere recoverable:\n")
    print(f"    {plaintext}\n")
    print("Mac side, in their Claude Code:")
    print(
        "    claude mcp add --transport http glitchgrow https://mcp.glitchexecutor.com "
        f'-H "Authorization: Bearer {plaintext}"'
    )
    return 0


def _cmd_tokens_list(_args) -> int:
    rows = list_tokens()
    if not rows:
        print("(no tokens)")
        return 0
    print(f"{'HASH_PFX':<14}{'TENANT':<16}{'LABEL':<28}{'CREATED':<28}REVOKED")
    for r in rows:
        print(
            f"{r['hash_prefix']:<14}{r['tenant_id']:<16}{(r['label'] or '')[:27]:<28}"
            f"{(r['created_at'] or '')[:26]:<28}{r['revoked_at'] or ''}"
        )
    return 0


def _cmd_tokens_revoke(args) -> int:
    n = revoke_token(args.hash_prefix)
    print(f"revoked {n} token(s) matching prefix {args.hash_prefix}")
    return 0 if n else 1


def main() -> None:
    p = argparse.ArgumentParser(prog="glitch-grow-mcp")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("serve", help="run the MCP server").set_defaults(fn=_cmd_serve)

    tenants = sub.add_parser("tenants", help="tenant management").add_subparsers(
        dest="tenants_cmd", required=True
    )
    tenants.add_parser("list").set_defaults(fn=_cmd_tenants_list)
    show = tenants.add_parser("show")
    show.add_argument("id")
    show.set_defaults(fn=_cmd_tenants_show)

    tokens = sub.add_parser("tokens", help="bearer-token management").add_subparsers(
        dest="tokens_cmd", required=True
    )
    issue = tokens.add_parser("issue")
    issue.add_argument("--tenant", required=True)
    issue.add_argument("--label", required=True)
    issue.set_defaults(fn=_cmd_tokens_issue)
    tokens.add_parser("list").set_defaults(fn=_cmd_tokens_list)
    revoke = tokens.add_parser("revoke")
    revoke.add_argument("hash_prefix")
    revoke.set_defaults(fn=_cmd_tokens_revoke)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
