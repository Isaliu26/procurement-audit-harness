"""Secrets, access code, cost ledger, output redaction and the tool-use hook.

The API key and access code are taken OUT of os.environ at import time, so the
Claude CLI and the agents' shell commands do not inherit them; the key is passed
to the CLI explicitly (runner.py) and nowhere else. Nothing here logs a secret.
"""
import hmac
import json
import os
import re
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "live"
_dotenv = dotenv_values(ROOT / ".env") if (ROOT / ".env").is_file() else {}


def _take(name: str) -> str:
    return os.environ.pop(name, None) or _dotenv.get(name) or ""


API_KEY = _take("ANTHROPIC_API_KEY")
ACCESS_CODE = _take("ACCESS_CODE")
del _dotenv

LEDGER_CAP_USD = float(os.environ.get("LEDGER_CAP_USD", "4.00"))

# ---------- redaction ----------
_KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9_\-]{6,}")


def redact(text: str) -> str:
    text = _KEY_RE.sub("[REDACTED]", str(text))
    for secret in (API_KEY, ACCESS_CODE):
        if len(secret) >= 4:
            text = text.replace(secret, "[REDACTED]")
    return text


# ---------- access code ----------
_fails: dict[str, deque] = defaultdict(deque)
MAX_FAILS, WINDOW_S = 5, 600


def check_access(code: str | None, client: str) -> tuple[bool, int, str]:
    """(ok, http_status, message)."""
    if not ACCESS_CODE:
        return False, 503, "Live runs are not configured on this server (no access code set)."
    now = time.time()
    q = _fails[client]
    while q and now - q[0] > WINDOW_S:
        q.popleft()
    if len(q) >= MAX_FAILS:
        return False, 429, "Too many wrong access codes. Try again in about 10 minutes."
    if code and hmac.compare_digest(code.encode(), ACCESS_CODE.encode()):
        return True, 200, ""
    q.append(now)
    return False, 401, "Access code missing or wrong."


# ---------- cost ledger ----------
class Ledger:
    """Total model spend since the server's disk was created. Ephemeral on Render."""

    def __init__(self, path: Path | None = None):
        self.path = path or LIVE / "ledger.json"

    def spent(self) -> float:
        try:
            return float(json.loads(self.path.read_text())["spent_usd"])
        except Exception:
            return 0.0

    def add(self, usd: float) -> float:
        total = round(self.spent() + max(usd, 0.0), 4)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"spent_usd": total}))
        return total

    def can_afford(self, stage_cap: float) -> bool:
        return self.spent() + stage_cap <= LEDGER_CAP_USD


# ---------- tool-use hook (mitigation, not a guarantee) ----------
_BASH_DENY = re.compile(
    r"(\bprintenv\b|\benv\b|\bexport\b|\.env\b|environ|getenv|ANTHROPIC|API_KEY|ACCESS_CODE|/proc/"
    r"|\bcurl\b|\bwget\b|\bssh\b|\bscp\b|\bnc\b|\bncat\b|\.\./|~/|/Users/|/home/|/etc/)",
    re.I,
)


def tool_denial(tool: str, tool_input: dict, workdir: Path) -> str | None:
    """Return a reason to deny this tool call, or None to allow it."""
    if tool == "Bash":
        cmd = str(tool_input.get("command", ""))
        if _BASH_DENY.search(cmd):
            return "This command touches the environment, network or paths outside the run folder."
        return None
    for key in ("file_path", "path", "notebook_path"):
        p = tool_input.get(key)
        if p:
            full = os.path.normpath(os.path.join(workdir, p))
            if not (full == str(workdir) or full.startswith(str(workdir) + os.sep)):
                return "Path is outside the run folder."
            if re.search(r"(^|/)\.env", full):
                return "Environment files are not readable."
    return None


def make_pretool_hook(workdir: Path):
    async def hook(input_data, tool_use_id, context):
        why = tool_denial(input_data.get("tool_name", ""), input_data.get("tool_input", {}) or {}, workdir)
        if why:
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                           "permissionDecision": "deny",
                                           "permissionDecisionReason": why}}
        return {}
    return hook
