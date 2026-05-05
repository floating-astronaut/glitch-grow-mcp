"""Subprocess bridge to glitch-social-media-agent.

The social agent is a collection of per-brand CLI scripts. We invoke
them with the tenant's `social_agent_brand` and capture stdout/stderr.
When new scripts are added, expose new MCP tools that wrap them.
"""

import asyncio
import json
import shlex
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..tenants import TenantConfig


class SocialAgentError(RuntimeError):
    def __init__(self, returncode: int, stdout: str, stderr: str):
        super().__init__(f"social-agent exited {returncode}: {stderr.strip()[:400]}")
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class SocialAgentBridge:
    def __init__(self, tenant: TenantConfig):
        self.tenant = tenant
        self.repo: Path = get_settings().social_agent_repo
        if not tenant.social_agent_brand:
            raise PermissionError(
                f"tenant '{tenant.id}' has no social_agent_brand configured"
            )
        if not (self.repo / "brand" / "configs" / f"{tenant.social_agent_brand}.json").is_file():
            raise PermissionError(
                f"social-agent has no brand config for '{tenant.social_agent_brand}'"
            )

    @property
    def python(self) -> str:
        # Prefer the agent's own venv if present; fall back to system python.
        venv = self.repo / ".venv" / "bin" / "python"
        return str(venv) if venv.is_file() else "python3"

    async def run_script(self, script: str, args: list[str] | None = None) -> dict[str, Any]:
        """Run a script under scripts/ with --brand <tenant.social_agent_brand>.

        Only allow scripts that physically exist under scripts/ — no path traversal.
        """
        scripts_dir = self.repo / "scripts"
        target = (scripts_dir / script).resolve()
        if not str(target).startswith(str(scripts_dir.resolve()) + "/"):
            raise PermissionError(f"refusing to run script outside scripts/: {script}")
        if not target.is_file():
            raise FileNotFoundError(f"script not found: {script}")

        cmd = [self.python, str(target), "--brand", self.tenant.social_agent_brand or ""]
        if args:
            cmd.extend(args)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self.repo),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out_b, err_b = await proc.communicate()
        out = out_b.decode("utf-8", errors="replace")
        err = err_b.decode("utf-8", errors="replace")

        if proc.returncode != 0:
            raise SocialAgentError(proc.returncode or -1, out, err)

        # Try to parse stdout as JSON; if not, return raw.
        parsed: Any
        try:
            parsed = json.loads(out)
        except json.JSONDecodeError:
            parsed = {"stdout": out}
        return {"command": " ".join(shlex.quote(c) for c in cmd), "result": parsed, "stderr": err}
