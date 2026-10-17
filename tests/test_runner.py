"""Runner behaviour with a fake Agent SDK `query` (no model call, no cost).
Run: .venv/bin/python tests/test_runner.py"""
import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import claude_agent_sdk  # noqa: E402
from claude_agent_sdk import AssistantMessage, TextBlock, ToolResultBlock, UserMessage  # noqa: E402
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


SOCAT = ("Sandbox is required but failed to initialize: Sandbox dependencies not available: "
         "socat not installed. Restart to retry.")


def tool_error(text):
    return UserMessage(content=[ToolResultBlock(tool_use_id="t1", content=text, is_error=True)])


def test_sandbox_tool_error_aborts_restores_files_retries_without_scrub():
    work = Path(tempfile.mkdtemp())
    (work / "outputs").mkdir()
    f = work / "outputs" / "risk-ratings.json"
    f.write_text("original")
    calls, seen_on_retry, continued = [], [], []

    async def fake(prompt, options):
        calls.append(options.env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"])
        if calls[-1] == "1":
            f.write_text("half-edited by the aborted attempt")
            yield msg()
            yield tool_error(SOCAT)
            continued.append(1)          # must never be reached: the attempt is aborted
            yield msg()
        else:
            seen_on_retry.append(f.read_text())
            yield msg()

    r, job = setup(fake)
    run(r._agent(job, work, CFG))
    assert calls == ["1", "0"] and not continued
    assert seen_on_retry == ["original"], seen_on_retry
    assert r.ledger.spent() == rn.ABORT_CHARGE_USD
    assert any(e["kind"] == "notice" for e in job.events) and rn.isolation["scrub"] is False
    assert "socat" in rn.isolation["probe"]


def test_each_trigger_word_counts_and_ordinary_tool_errors_do_not():
    for w in ("Sandbox is required", "bwrap: no permission", "bubblewrap missing", "cannot create namespace", "socat not installed"):
        assert rn.sandbox_error(w), w
    calls = []

    async def fake(prompt, options):
        calls.append(1)
        yield msg()
        yield tool_error("<tool_use_error>String to replace not found in file.</tool_use_error>")
        yield msg()

    r, job = setup(fake)
    run(r._agent(job, WORK, CFG))
    assert len(calls) == 1 and rn.isolation["scrub"] is True and r.ledger.spent() == 0.0


def test_probe_cases():
    ok_run = subprocess.CompletedProcess([], 0, "", "")
    bad_run = subprocess.CompletedProcess([], 1, "", "bwrap: No permissions to create new namespace: Operation not permitted")
    with mock.patch.object(rn.sys, "platform", "linux"):
        with mock.patch.object(rn.shutil, "which", lambda t: None if t == "socat" else "/usr/bin/" + t):
            res = rn.probe_sandbox()
            assert not res["ok"] and "socat" in res["detail"]
        with mock.patch.object(rn.shutil, "which", lambda t: "/usr/bin/" + t):
            with mock.patch.object(rn.subprocess, "run", lambda *a, **k: ok_run):
                assert rn.probe_sandbox()["ok"]
            with mock.patch.object(rn.subprocess, "run", lambda *a, **k: bad_run):
                res = rn.probe_sandbox()
                assert not res["ok"] and "namespace" in res["detail"]
            def boom(*a, **k): raise subprocess.TimeoutExpired("bwrap", 5)
            with mock.patch.object(rn.subprocess, "run", boom):
                assert not rn.probe_sandbox()["ok"]
            rn.isolation["scrub"] = True
            with mock.patch.object(rn.subprocess, "run", lambda *a, **k: bad_run):
                rn.apply_probe()
            assert rn.isolation["scrub"] is False and rn.isolation["probe"].startswith("FAILED")
    with mock.patch.object(rn.sys, "platform", "darwin"):
        assert rn.probe_sandbox()["ok"]
    rn.isolation["scrub"] = True


def test_status_reports_isolation_and_probe():
    from fastapi.testclient import TestClient
    from app import main
    with mock.patch.object(rn, "probe_sandbox", lambda: {"ok": False, "detail": "bwrap exited 1: denied"}):
        with TestClient(main.app) as c:        # runs the start-up probe
            st = c.get("/api/status").json()
    assert st["isolation"] == "hook-only" and "bwrap exited 1" in st["isolation_probe"]
    rn.isolation["scrub"] = True


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
