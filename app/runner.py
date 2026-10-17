"""Live jobs: one at a time, in a throwaway working copy of the project.

The committed outputs/ folder is never written. A live run works in live/work/,
seeded from the project (CLAUDE.md, .claude, scripts, outputs) with data/ and
.venv linked in, so the SDK loads the same skills and agents as Claude Code does.
"""
import asyncio
import json
import os
import shutil
import time
from pathlib import Path

from . import guard

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
        "Then report under 200 words."),
}

_DOWNSTREAM_OF_3 = ["risk-register.md", "risk-ratings.json", "auditor-comments.md", ".register-state.json",
                    "audit-plan.json", "planning-memo.md", "risk-control-matrix.md", "audit-program.md",
                    "challenges.md", "review.md", "pack-figures.json"]


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


# ---------- job ----------
class Job:
    def __init__(self, stage: int, label: str):
        self.id = str(int(time.time() * 1000))
        self.stage, self.label = stage, label
        self.status = "running"      # running | done | failed
        self.events: list[dict] = []
        self.cost = 0.0
        self.error: str | None = None
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
                "cost_usd": round(self.cost, 4), "error": self.error, "events": len(self.events)}


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
        from claude_agent_sdk import (AssistantMessage, ResultMessage, TextBlock, ToolResultBlock,
                                      ToolUseBlock, UserMessage, query)
        opts = build_options(work, cfg)
        try:
            async for m in query(prompt=PROMPTS[job.stage], options=opts):
                if isinstance(m, AssistantMessage):
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
                            await job.emit("tool", "tool error: " + str(b.content)[:300])
                elif isinstance(m, ResultMessage):
                    job.cost = float(m.total_cost_usd or 0)
                    self.ledger.add(job.cost)
                    await job.emit("status", f"Cost of this run: ${job.cost:.3f} · turns: {m.num_turns}")
                    if m.is_error:
                        raise RuntimeError(f"{m.subtype}: {m.result or ''}")
        except Exception:
            if not job.cost:  # run died before reporting a cost: assume the cap was used
                self.ledger.add(cfg["usd"])
            raise


def build_options(work: Path, cfg: dict):
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
             "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "1"},
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
