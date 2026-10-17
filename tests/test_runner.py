"""Runner behaviour with a fake Agent SDK `query` (no model call, no cost).
Run: .venv/bin/python tests/test_runner.py"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import claude_agent_sdk  # noqa: E402
from claude_agent_sdk import AssistantMessage, TextBlock  # noqa: E402
from app import guard, runner as rn  # noqa: E402

CFG = {"agent": "risk-assessor", "skill": "risk-assessment", "usd": 0.35, "turns": 5, "secs": 60}
WORK = Path(tempfile.mkdtemp())
BWRAP = "error: bubblewrap is required for subprocess env scrubbing and isolation. Install with: sudo apt-get install -y bubblewrap"


def msg():
    return AssistantMessage(content=[TextBlock(text="working")], model="x")


def setup(fake):
    claude_agent_sdk.query = fake
    rn.isolation["scrub"] = True
    r = rn.Runner()
    r.ledger = guard.Ledger(Path(tempfile.mkdtemp()) / "ledger.json")
    rn.STAGES[3]["usd"] = CFG["usd"]
    return r, rn.Job(3, "test")


def run(coro):
    return asyncio.run(coro)


def test_options_flags():
    seen = []
    o1 = rn.build_options(WORK, CFG, scrub=True, stderr=seen.append)
    o0 = rn.build_options(WORK, CFG, scrub=False)
    assert o1.env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] == "1" and o0.env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] == "0"
    assert o1.stderr is not None and o1.allowed_tools == rn.TOOLS and o1.hooks


def test_sandbox_error_detection():
    assert rn.sandbox_error(BWRAP) and rn.sandbox_error("bwrap: No permissions to create new namespace")
    assert not rn.sandbox_error("rate limit exceeded")


def test_bubblewrap_failure_retries_once_without_scrub_and_costs_nothing():
    calls = []

    async def fake(prompt, options):
        calls.append(options.env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"])
        if options.env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] == "1":
            options.stderr(BWRAP + " sk-ant-LEAKYKEY123456")
            raise RuntimeError("Command failed with exit code 1")
        yield msg()

    r, job = setup(fake)
    run(r._agent(job, WORK, CFG))
    assert calls == ["1", "0"], calls
    assert rn.isolation["scrub"] is False and job.public()["isolation"] == "hook-only"
    assert r.ledger.spent() == 0.0
    kinds = [e["kind"] for e in job.events]
    assert "notice" in kinds and "stderr" in kinds
    assert all("LEAKYKEY" not in e["text"] for e in job.events)
    # later jobs in this process start with the scrub off
    calls.clear()
    run(r._agent(rn.Job(3, "again"), WORK, CFG))
    assert calls == ["0"]


def test_sandbox_failure_twice_gives_up_after_one_retry():
    calls = []

    async def fake(prompt, options):
        calls.append(1)
        options.stderr(BWRAP)
        raise RuntimeError("Command failed with exit code 1")
        yield

    r, job = setup(fake)
    try:
        run(r._agent(job, WORK, CFG))
        raise AssertionError("should have raised")
    except RuntimeError:
        pass
    assert len(calls) == 2 and r.ledger.spent() == 0.0
    assert "sandbox" in rn.friendly_error(RuntimeError(BWRAP)).lower()


def test_other_failure_before_any_response_is_free_and_not_retried():
    calls = []

    async def fake(prompt, options):
        calls.append(1)
        raise RuntimeError("something else broke")
        yield

    r, job = setup(fake)
    try:
        run(r._agent(job, WORK, CFG))
    except RuntimeError:
        pass
    assert len(calls) == 1 and r.ledger.spent() == 0.0 and rn.isolation["scrub"] is True


def test_failure_after_model_response_without_cost_charges_the_cap():
    async def fake(prompt, options):
        yield msg()
        raise RuntimeError("Reached maximum budget ($0.35)")

    r, job = setup(fake)
    try:
        run(r._agent(job, WORK, CFG))
    except RuntimeError:
        pass
    assert r.ledger.spent() == CFG["usd"]


def test_sandbox_error_after_a_response_is_not_retried():
    calls = []

    async def fake(prompt, options):
        calls.append(1)
        yield msg()
        options.stderr(BWRAP)
        raise RuntimeError("Command failed")

    r, job = setup(fake)
    try:
        run(r._agent(job, WORK, CFG))
    except RuntimeError:
        pass
    assert len(calls) == 1


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
