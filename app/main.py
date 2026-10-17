"""Read-only viewer for the procurement audit pack (Part B, step 1).

No model calls and no write routes. The `committed` source is the outputs/ folder
shipped with the project; `live` is live/outputs/, filled only by live runs
(added in a later step) and absent on a fresh start.
"""
import asyncio
import json
from collections import Counter
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import gate_form, guard, runner as rn

ROOT = guard.ROOT  # secrets were already taken out of os.environ by guard

SOURCES = {"committed": ROOT / "outputs", "live": rn.WORK / "outputs"}

# Only these files can be fetched. Anything else is a 404.
DOCS = {
    "rules": "rules.json", "analytics": "analytics.json", "history": "history.json",
    "register": "risk-register.md", "auditor-comments": "auditor-comments.md",
    "planning-memo": "planning-memo.md", "risk-control-matrix": "risk-control-matrix.md",
    "audit-program": "audit-program.md", "challenges": "challenges.md", "review": "review.md",
}

STAGES = [
    {"n": 1, "key": "extract", "title": "Extract rules", "agent": "extract-rules skill",
     "needs": ["rules"]},
    {"n": 2, "key": "analysis", "title": "Analysis", "agent": "spend-analyst + findings-analyst",
     "needs": ["analytics", "history"]},
    {"n": 3, "key": "register", "title": "Risk register", "agent": "risk-assessor",
     "needs": ["register"]},
    {"n": 4, "key": "gate", "title": "Auditor gate", "agent": "human (form)",
     "needs": ["auditor-comments"]},
    {"n": 5, "key": "team", "title": "Agent team", "agent": "planner, challenger, qa-reviewer",
     "needs": ["planning-memo", "risk-control-matrix", "audit-program", "challenges", "review"]},
    {"n": 6, "key": "signoff", "title": "Sign-off", "agent": "human (form)", "needs": ["review"]},
]

app = FastAPI(title="Procurement audit harness", docs_url=None, redoc_url=None)


def _dir(source: str) -> Path:
    if source not in SOURCES:
        raise HTTPException(404, "unknown source")
    return SOURCES[source]


def _path(source: str, doc: str) -> Path:
    name = DOCS.get(doc)
    p = _dir(source) / name if name else None
    if not p or not p.is_file():
        raise HTTPException(404, f"{doc} not available in the {source} run")
    return p


def _signed(review_text: str) -> bool:
    return gate_form.review_info(review_text)["signed"] == "SIGNED OFF"


def _undecided(d: Path) -> bool:
    f = d / "auditor-comments.md"
    rows = gate_form.parse_comments(f.read_text("utf-8"))["rows"] if f.is_file() else []
    return not rows or any(not r["decision"] for r in rows)


def _stale_from() -> int | None:
    return rn.get_state().get("stale_from")


@app.get("/api/status")
def status():
    out = {"sources": {}}
    for src, d in SOURCES.items():
        have = {k: (d / v).is_file() for k, v in DOCS.items()}
        stages = []
        for s in STAGES:
            state = "done" if all(have[k] for k in s["needs"]) else "missing"
            if s["key"] == "gate" and have["auditor-comments"] and _undecided(d):
                state = "pending"
            if s["key"] == "signoff" and have["review"]:
                state = "done" if _signed((d / "review.md").read_text("utf-8")) else "pending"
            sf = _stale_from()
            if src == "live" and sf and s["n"] >= sf and state == "done":
                state = "stale"
            stages.append({**s, "state": state})
        out["sources"][src] = {"available": (d / "risk-register.md").is_file(), "stages": stages}
    out["live_runs_enabled"] = bool(guard.API_KEY and guard.ACCESS_CODE)
    out["isolation"] = "env-scrub" if rn.isolation["scrub"] else "hook-only"
    out["busy"] = rn.runner.busy()
    out["job"] = rn.runner.current.public() if rn.runner.current else None
    out["spent_usd"] = round(rn.runner.ledger.spent(), 3)
    out["ledger_cap_usd"] = guard.LEDGER_CAP_USD
    out["live_stage_caps_usd"] = {str(k): v["usd"] for k, v in rn.STAGES.items()}
    return out



# ---------------- live jobs (access code required) ----------------
def _client(request: Request) -> str:
    return (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "?"))


def _authorize(request: Request, code: str | None, stage_cap: float | None = None):
    ok, status, msg = guard.check_access(code, _client(request))
    if not ok:
        raise HTTPException(status, msg)
    if not guard.API_KEY:
        raise HTTPException(503, "The server has no API key configured, so live runs are unavailable.")
    if rn.runner.busy():
        raise HTTPException(409, "Another live run is in progress. Only one runs at a time.")
    if stage_cap is not None and not rn.runner.ledger.can_afford(stage_cap):
        raise HTTPException(402, "The demo's cost budget is used up, so no more live runs are possible. "
                                 "The committed run is still fully browsable.")


@app.post("/api/jobs/{stage}")
async def start_job(stage: int, request: Request, x_access_code: str | None = Header(None)):
    if stage != 3:
        raise HTTPException(501, "Live reruns of this stage are not built yet. Stage 3 reruns from the 'Rerun stage' button; stage 4 uses its decision form.")
    _authorize(request, x_access_code, rn.STAGES[3]["usd"])
    job = await rn.runner.start(3, "Rebuild risk register", rn.prepare_stage3)
    return JSONResponse(job.public(), status_code=202)


class GateBody(BaseModel):
    decisions: list[dict]


@app.get("/api/{source}/gate")
def gate(source: str):
    p = _path(source, "auditor-comments")
    return gate_form.parse_comments(p.read_text("utf-8"))


@app.post("/api/gate")
async def submit_gate(body: GateBody, request: Request, x_access_code: str | None = Header(None)):
    _authorize(request, x_access_code, rn.STAGES[4]["usd"])
    live_f = rn.WORK / "outputs" / "auditor-comments.md"
    cur_f = live_f if live_f.is_file() else SOURCES["committed"] / "auditor-comments.md"
    cur = cur_f.read_text("utf-8")
    ids = {r["risk"] for r in gate_form.parse_comments(cur)["rows"]}
    errs = gate_form.validate(body.decisions, ids)
    if errs:
        raise HTTPException(422, "; ".join(errs))
    if not gate_form.decisions_changed(cur, body.decisions):
        raise HTTPException(422, "No decision was changed, so there is nothing for the risk-assessor to revise.")

    def prepare():
        work = rn.prepare_stage4()
        f = work / "outputs" / "auditor-comments.md"
        f.write_text(gate_form.apply_decisions(f.read_text("utf-8"), body.decisions), "utf-8")
        return work

    job = await rn.runner.start(4, "Revise register after auditor decisions", prepare)
    return JSONResponse(job.public(), status_code=202)


class SignoffBody(BaseModel):
    decision: str
    name: str
    comments: str = ""


@app.get("/api/{source}/signoff")
def signoff_info(source: str):
    p = _path(source, "review")
    info = gate_form.review_info(p.read_text("utf-8"))
    sf = _stale_from()
    return {**info, "stale": bool(source == "live" and sf and sf <= 5)}


@app.post("/api/signoff")
async def signoff(body: SignoffBody, request: Request, x_access_code: str | None = Header(None)):
    _authorize(request, x_access_code)
    work = rn.seed()  # the sign-off is written to the live copy; committed review.md is never touched
    f = work / "outputs" / "review.md"
    if not f.is_file():
        raise HTTPException(404, "There is no review.md in the live run (rerun stage 5 first).")
    text = f.read_text("utf-8")
    info = gate_form.review_info(text)
    sf = _stale_from()
    errs = gate_form.validate_signoff(info, body.decision, body.name, body.comments, bool(sf and sf <= 5))
    if errs:
        raise HTTPException(422, "; ".join(errs))
    f.write_text(gate_form.apply_signoff(text, body.decision, body.name, body.comments, info["pack_version"] or ""), "utf-8")
    return {"ok": True}


@app.get("/api/jobs/current")
def current_job():
    j = rn.runner.current
    return j.public() if j else JSONResponse({"status": "none"})


@app.get("/api/jobs/current/stream")
async def stream(start: int = 0):
    job = rn.runner.current
    if not job:
        raise HTTPException(404, "no job")

    async def gen():
        i = start
        while True:
            while i < len(job.events):
                yield f"data: {json.dumps(job.events[i])}\n\n"
                i += 1
            if job.status != "running":
                yield f"event: end\ndata: {json.dumps(job.public())}\n\n"
                return
            async with job.changed:
                try:
                    await asyncio.wait_for(job.changed.wait(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/api/{source}/doc/{doc}")
def doc(source: str, doc: str):
    p = _path(source, doc)
    text = p.read_text("utf-8")
    if p.suffix == ".json":
        return JSONResponse(json.loads(text))
    return JSONResponse({"markdown": text})


@app.get("/api/{source}/digest/{stage}")
def digest(source: str, stage: str):
    """Small JSON summaries so the browser never receives the 184 KB analytics file."""
    if stage == "rules":
        r = json.loads(_path(source, "rules").read_text("utf-8"))
        return {
            "source": r["source"],
            "rule_count": len(r["rules"]),
            "by_type": dict(Counter(x["type"] for x in r["rules"]).most_common()),
            "parameters": r["parameters"],
            "excluded_count": len(r["excluded"]),
            "notes": r["notes"],
            "rules": [{k: x.get(k) for k in ("rule_id", "clause", "page", "type", "scope",
                                              "required_action", "verbatim_quote")}
                      for x in r["rules"]],
        }
    if stage == "analytics":
        a = json.loads(_path(source, "analytics").read_text("utf-8"))
        tests = {k: {"counts": t.get("counts"), "totals_gbp": t.get("totals_gbp"),
                     "interpretation": t.get("interpretation"), "top20": t.get("top20", [])[:20]}
                 for k, t in a["tests"].items()}
        return {"window": a["window"], "limitations": a["limitations"], "tests": tests}
    if stage == "history":
        h = json.loads(_path(source, "history").read_text("utf-8"))
        return {"counts": {k: len(v) for k, v in h.items() if hasattr(v, "__len__")},
                "audits": h.get("audits", []), "risk_themes": h.get("risk_themes", []),
                "gaps": h.get("gaps", [])}
    raise HTTPException(404, "unknown digest")


app.mount("/", StaticFiles(directory=ROOT / "app" / "static", html=True), name="static")
