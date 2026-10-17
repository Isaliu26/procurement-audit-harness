"""Live jobs: one at a time, in a throwaway working copy of the project.

The committed outputs/ folder is never written. A live run works in live/work/,
seeded from the project (CLAUDE.md, .claude, scripts, outputs) with data/ and
.venv linked in, so the SDK loads the same skills and agents as Claude Code does.
"""
import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import guard

log = logging.getLogger("harness")
ROOT = guard.ROOT
LIVE = guard.LIVE
WORK = LIVE / "work"
STATE = LIVE / "state.json"
TOOLS = ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]
MODEL = os.environ.get("MODEL", "claude-sonnet-5-5")

# Per-stage caps (USD, turns, wall-clock seconds). Budget is the real limit.
STAGES = {
    3: {"agent": "risk-assessor", "skill": "risk-assessment", "usd": float(os.environ.get("BUDGET_STAGE3", "0.35")), "turns": 40, "secs": 900},
    4: {"agent": "risk-assessor", "skill": "risk-assessment", "usd": float(os.environ.get("BUDGET_STAGE4", "0.25")), "turns": 30, "secs": 900},
}

PROMPTS = {
    3: ("Rebuild the risk register from scratch for this run, following the risk-assessment skill. "
        "outputs/rules.json, analytics.json and history.json exist; risk-ratings.json, the register and "
        "auditor-comments.md were removed for a fresh build. Run build_register.py until clean, then report."),
    4: ("The auditor has completed outputs/auditor-comments.md through the web decision form. Follow "
        "skill section 6 exactly: change only what a decision asks, add the revision block, and re-run "
        "build_register.py until there are no drops or warnings. The previous register may already be a revision: "
        "replace its revision block with one for the new round that lists only THIS round's changes, and do not "
        "list a REJECT for a risk that is already removed (its Rating reads 'removed'); that was applied earlier. "
        "An OVERRIDE needs no entry in revision.changes (the builder applies it), so a round whose only new "
        "decisions are OVERRIDEs uses an empty changes list; the round is the register's current version plus one. "
        "Then report under 200 words."),
}

_DOWNSTREAM_OF_3 = ["risk-register.md", "risk-ratings.json", "auditor-comments.md", ".register-state.json",
                    "audit-plan.json", "planning-memo.md", "risk-control-matrix.md", "audit-program.md",
                    "challenges.md", "review.md", "pack-figures.json"]


# Failures of the CLI's subprocess isolation (CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1): bubblewrap, socat, namespaces.
SANDBOX_ERR = re.compile(r"bubblewrap|bwrap|namespace|unshare|CLONE_NEW|socat|sandbox", re.I)
# Scrub on = the CLI isolates and scrubs agent shell commands. Off = only the guard hook protects the key.
isolation = {"scrub": True, "probe": "not run"}
# Estimated charge for an attempt we abort on a sandbox tool error (no cost is reported for it).
ABORT_CHARGE_USD = 0.05


class SandboxToolError(RuntimeError):
    """A tool call failed because the CLI's sandbox could not initialise."""


def sandbox_error(text: str) -> bool:
    return bool(SANDBOX_ERR.search(text or ""))


def probe_sandbox() -> dict:
    """Does the CLI's isolation work here? Linux needs bwrap (able to make namespaces) and socat."""
    if not sys.platform.startswith("linux"):
        return {"ok": True, "detail": f"{sys.platform}: the CLI uses its own isolation; probe skipped"}
    missing = [t for t in ("bwrap", "socat") if not shutil.which(t)]
    if missing:
        return {"ok": False, "detail": "not installed: " + ", ".join(missing)}
    try:
        r = subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"], capture_output=True, text=True, timeout=5)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"bwrap probe error: {type(e).__name__}: {e}"[:200]}
    if r.returncode != 0:
        return {"ok": False, "detail": f"bwrap exited {r.returncode}: {guard.redact(r.stderr.strip())}"[:200]}
    return {"ok": True, "detail": "bwrap and socat available; bwrap created its sandbox"}


def apply_probe() -> dict:
    res = probe_sandbox()
    isolation["scrub"] = res["ok"]
    isolation["probe"] = ("ok: " if res["ok"] else "FAILED, isolation off: ") + res["detail"]
    log.warning("sandbox probe: %s", isolation["probe"])
    return res


# ---------- working copy ----------
def seed(fresh: bool = False) -> Path:
    if fresh and WORK.exists():
        shutil.rmtree(WORK)
    if WORK.exists():
        return WORK
    WORK.mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
    for name in ("CLAUDE.md",):
        shutil.copy2(ROOT / name, WORK / name)
    for name in (".claude", "scripts", "outputs"):
        shutil.copytree(ROOT / name, WORK / name, ignore=ignore)
    for link in ("data", ".venv"):
        if (ROOT / link).exists():
            (WORK / link).symlink_to(ROOT / link)
    return WORK


def get_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def set_state(**kw):
    LIVE.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({**get_state(), **kw}))


_SNAP = ["risk-ratings.json", "risk-register.md", "auditor-comments.md", ".register-state.json"]


def snapshot(work: Path) -> dict:
    return {n: ((work / "outputs" / n).read_bytes() if (work / "outputs" / n).is_file() else None) for n in _SNAP}


def restore(work: Path, snap: dict):
    for n, data in snap.items():
        f = work / "outputs" / n
        if data is None:
            f.unlink(missing_ok=True)
        else:
            f.write_bytes(data)


# ---------- job ----------
class Job:
    def __init__(self, stage: int, label: str):
        self.id = str(int(time.time() * 1000))
        self.stage, self.label = stage, label
        self.status = "running"      # running | done | failed
        self.events: list[dict] = []
        self.cost = 0.0
        self.error: str | None = None
        self.stderr_lines: list[str] = []
        self.responded = False
        self.started = time.time()
        self.changed = asyncio.Condition()

    async def emit(self, kind: str, text: str = ""):
        async with self.changed:
            self.events.append({"i": len(self.events), "t": round(time.time() - self.started, 1),
                                "kind": kind, "text": guard.redact(text)[:1200]})
            self.events = self.events[-400:]
            self.changed.notify_all()

    def public(self) -> dict:
        return {"id": self.id, "stage": self.stage, "label": self.label, "status": self.status,
                "cost_usd": round(self.cost, 4), "error": self.error, "events": len(self.events),
                "isolation": "env-scrub" if isolation["scrub"] else "hook-only"}


class Runner:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.current: Job | None = None
        self.ledger = guard.Ledger()

    def busy(self) -> bool:
        return self.lock.locked()

    async def start(self, stage: int, label: str, prepare):
        """prepare() -> Path workdir; runs inside the lock so only one job exists."""
        await self.lock.acquire()
        job = self.current = Job(stage, label)
        asyncio.create_task(self._run(job, prepare))
        return job

    async def _run(self, job: Job, prepare):
        cfg = STAGES[job.stage]
        try:
            work = prepare()
            await job.emit("status", f"Working copy ready. Starting {cfg['agent']} on {MODEL}.")
            before = (work / "outputs" / "risk-register.md").stat().st_mtime if (work / "outputs" / "risk-register.md").exists() else 0
            await asyncio.wait_for(self._agent(job, work, cfg), timeout=cfg["secs"])
            problem = check_outcome(job.stage, work, before)
            if problem:
                raise RuntimeError(problem)
            job.status = "done"
            await job.emit("status", "Finished.")
        except asyncio.TimeoutError:
            await self._fail(job, "The run took too long and was stopped (this server has very little CPU).")
        except Exception as e:  # noqa: BLE001 - mapped to a friendly message below
            await self._fail(job, friendly_error(e))
        finally:
            self.lock.release()
            async with job.changed:
                job.changed.notify_all()

    async def _fail(self, job: Job, msg: str):
        job.status, job.error = "failed", msg
        await job.emit("error", msg)

    async def _agent(self, job: Job, work: Path, cfg: dict):
        """Run the agent; if the CLI's sandbox is unusable, retry once with the scrub off."""
        snap = snapshot(work)
        try:
            await self._attempt(job, work, cfg, scrub=isolation["scrub"])
        except Exception as e:  # noqa: BLE001
            await asyncio.sleep(0.5)  # let the stderr reader deliver its last lines
            start_failure = not job.responded and sandbox_error("\n".join(job.stderr_lines) + "\n" + str(e))
            if isolation["scrub"] and (isinstance(e, SandboxToolError) or start_failure):
                isolation["scrub"] = False
                isolation["probe"] = "FAILED at run time, isolation off: " + guard.redact(str(e))[:160]
                log.warning("sandbox failure at run time; retrying once with CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=0: %s", guard.redact(str(e))[:200])
                await job.emit("notice", "The CLI's sandbox (bubblewrap/socat) does not work on this server. "
                                         "Retrying once with isolation off: the API key is then protected only by the "
                                         "guard hook that blocks commands touching the environment.")
                restore(work, snap)
                job.stderr_lines.clear()
                await self._attempt(job, work, cfg, scrub=False)
            else:
                raise

    async def _attempt(self, job: Job, work: Path, cfg: dict, scrub: bool):
        from claude_agent_sdk import (AssistantMessage, ResultMessage, TextBlock, ToolResultBlock,
                                      ToolUseBlock, UserMessage, query)
        loop = asyncio.get_running_loop()

        def on_stderr(line: str):
            line = guard.redact(line.rstrip())[:400]
            if not line:
                return
            log.info("cli stderr: %s", line)
            if len(job.stderr_lines) < 200:
                job.stderr_lines.append(line)
                loop.call_soon_threadsafe(lambda: asyncio.ensure_future(job.emit("stderr", line)))

        opts = build_options(work, cfg, scrub=scrub, stderr=on_stderr)
        job.responded = False
        try:
            async with contextlib.aclosing(query(prompt=PROMPTS[job.stage], options=opts)) as stream:
                async for m in stream:
                    if isinstance(m, AssistantMessage):
                        job.responded = True
                        for b in m.content:
                            if isinstance(b, TextBlock) and b.text.strip():
                                await job.emit("text", b.text.strip())
                            elif isinstance(b, ToolUseBlock):
                                inp = b.input or {}
                                detail = inp.get("command") or inp.get("file_path") or inp.get("pattern") or ""
                                await job.emit("tool", f"{b.name}: {str(detail)[:200]}")
                    elif isinstance(m, UserMessage) and isinstance(m.content, list):
                        for b in m.content:
                            if isinstance(b, ToolResultBlock) and b.is_error:
                                text = str(b.content)
                                await job.emit("tool", "tool error: " + text[:300])
                                if scrub and sandbox_error(text):
                                    raise SandboxToolError(text[:300])
                    elif isinstance(m, ResultMessage):
                        job.responded = True
                        job.cost = float(m.total_cost_usd or 0)
                        self.ledger.add(job.cost)
                        await job.emit("status", f"Cost of this run: ${job.cost:.3f} · turns: {m.num_turns}")
                        if m.is_error:
                            raise RuntimeError(f"{m.subtype}: {m.result or ''}")
        except SandboxToolError:
            self.ledger.add(ABORT_CHARGE_USD)  # estimate: the aborted attempt reports no cost
            raise
        except Exception:
            # Charge the cap only if the model had started work but no cost was reported.
            # A run that died before any model response (e.g. the CLI failed to start) costs nothing.
            if job.responded and not job.cost:
                self.ledger.add(cfg["usd"])
            raise


def build_options(work: Path, cfg: dict, scrub: bool = True, stderr=None):
    from claude_agent_sdk import ClaudeAgentOptions, HookMatcher
    cfgdir = LIVE / "cc-config"
    cfgdir.mkdir(parents=True, exist_ok=True)
    return ClaudeAgentOptions(
        cwd=str(work), setting_sources=["project"], model=MODEL,
        tools=TOOLS, allowed_tools=TOOLS,  # explicit: ENV_SCRUB forces default permission mode otherwise
        skills=[cfg["skill"]],
        extra_args={"agent": cfg["agent"]},
        max_turns=cfg["turns"], max_budget_usd=cfg["usd"],
        hooks={"PreToolUse": [HookMatcher(matcher="Bash|Read|Write|Edit|Glob|Grep",
                                          hooks=[guard.make_pretool_hook(work)])]},
        env={"ANTHROPIC_API_KEY": guard.API_KEY, "CLAUDE_CONFIG_DIR": str(cfgdir),
             "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "1" if scrub else "0"},
        stderr=stderr,
    )


def check_outcome(stage: int, work: Path, before_mtime: float) -> str | None:
    reg = work / "outputs" / "risk-register.md"
    if not reg.is_file() or reg.stat().st_mtime <= before_mtime:
        return "The agent stopped without producing a new risk register. See the log above for why."
    if stage == 4 and "Revision v" not in reg.read_text("utf-8")[:3000]:
        return "The agent rebuilt the register but did not record a revision, so the decisions were not applied."
    return None


def friendly_error(e: Exception) -> str:
    if str(e).startswith("The agent "):
        return str(e)
    s = str(e).lower()
    if "credit balance" in s or "billing" in s or "insufficient" in s or "payment" in s:
        return "The API credit has run out. Ask the owner to top up the account; no further live runs are possible until then."
    if "maximum budget" in s or "error_max_budget" in s:
        return "This run hit its cost cap and was stopped before finishing. The committed run is unaffected."
    if "max_turns" in s or "maximum number of turns" in s or "error_max_turns" in s:
        return "The agent used its turn limit before finishing. Try again, or use the committed run."
    if "rate limit" in s or "429" in s or "overloaded" in s:
        return "The model service is rate-limited or busy. Wait a minute and try again."
    if "authentication" in s or "invalid x-api-key" in s or "401" in s:
        return "The server's API key was rejected. The owner needs to check the key."
    if sandbox_error(s):
        return "The agent could not start its sandbox on this server, even after retrying without it. See the log above."
    if "killed" in s or "-9" in s or "memory" in s:
        return "The agent process was killed, probably out of memory on this small server."
    return "The run failed: " + guard.redact(str(e))[:300]


# ---------- stage preparation ----------
def prepare_stage3() -> Path:
    work = seed(fresh=True)
    for name in _DOWNSTREAM_OF_3:
        p = work / "outputs" / name
        if p.exists():
            p.unlink()
    shutil.rmtree(work / "outputs" / "samples", ignore_errors=True)
    set_state(stale_from=None, rebuilt_from_scratch=True)
    return work


def prepare_stage4() -> Path:
    work = seed()
    if not (work / "outputs" / "risk-register.md").is_file():  # an earlier stage-3 run failed midway
        work = seed(fresh=True)
    set_state(stale_from=5)
    return work


runner = Runner()
