"""Stage 4 decision form and stage 6 sign-off: pure text transforms, no model call."""
import re
from datetime import date

DECISIONS = ("APPROVE", "REJECT", "REVISE", "OVERRIDE")
_ROW = re.compile(r"^\|\s*(R-\d+)\s*\|(.*)\|\s*$")
_VERSION = re.compile(r"Register version:\s*(v\d+)")


def parse_comments(text: str) -> dict:
    m = _VERSION.search(text)
    rows = []
    for line in text.splitlines():
        r = _ROW.match(line)
        if not r:
            continue
        cells = [c.strip() for c in line.strip()[1:-1].split("|")]
        if len(cells) != 5:
            continue
        rows.append(dict(zip(("risk", "title", "rating", "decision", "comment"), cells)))
    return {"version": m.group(1) if m else None, "rows": rows}


def validate(decisions: list[dict], existing_ids: set[str]) -> list[str]:
    errs = []
    seen = set()
    for d in decisions:
        rid, dec, com = d.get("risk", ""), str(d.get("decision", "")).upper(), str(d.get("comment", "")).strip()
        seen.add(rid)
        if rid not in existing_ids:
            errs.append(f"{rid or '?'}: unknown risk")
            continue
        if dec not in DECISIONS:
            errs.append(f"{rid}: choose one of {', '.join(DECISIONS)}")
        if "|" in com or "\n" in com or len(com) > 600:
            errs.append(f"{rid}: comment must be one line, under 600 characters, without the | character")
        if dec == "REVISE" and not com:
            errs.append(f"{rid}: REVISE needs a comment saying what to change")
        if dec == "OVERRIDE" and not re.search(r"\b(likelihood|impact)\s*=\s*[1-5]\b", com):
            errs.append(f"{rid}: OVERRIDE needs likelihood=N and/or impact=N (1 to 5) in the comment")
    for rid in existing_ids - seen:
        errs.append(f"{rid}: no decision given")
    return errs


def apply_decisions(text: str, decisions: list[dict]) -> str:
    by_id = {d["risk"]: d for d in decisions}
    out = []
    for line in text.splitlines():
        r = _ROW.match(line)
        if r and r.group(1) in by_id:
            c = [x.strip() for x in line.strip()[1:-1].split("|")]
            d = by_id[r.group(1)]
            line = f"| {c[0]} | {c[1]} | {c[2]} | {d['decision'].upper()} | {str(d.get('comment', '')).strip()} |"
        out.append(line)
    return "\n".join(out) + "\n"


def decisions_changed(text: str, decisions: list[dict]) -> bool:
    cur = {r["risk"]: (r["decision"].upper(), r["comment"].strip()) for r in parse_comments(text)["rows"]}
    return any(cur.get(d["risk"]) != (d["decision"].upper(), str(d.get("comment", "")).strip()) for d in decisions)


# ---------- stage 6 ----------
def review_info(text: str) -> dict:
    v = re.search(r"Pack version reviewed:\s*(v\d+)", text)
    verdict = re.search(r"^VERDICT:\s*(.+)$", text, re.M)
    signed = re.search(r"\|\s*Decision \(SIGNED OFF / RETURNED TO TEAM\)\s*\|\s*([^|]*)\|", text)
    return {"pack_version": v.group(1) if v else None,
            "verdict": verdict.group(1).strip() if verdict else None,
            "signed": (signed.group(1).strip() if signed else "")}


def validate_signoff(info: dict, decision: str, name: str, comments: str, stale: bool) -> list[str]:
    errs = []
    if decision not in ("SIGNED OFF", "RETURNED TO TEAM"):
        errs.append("Decision must be SIGNED OFF or RETURNED TO TEAM")
    if not name.strip() or len(name) > 80 or re.search(r"[|\n]", name):
        errs.append("Enter the auditor name (under 80 characters, no | character)")
    if len(comments) > 500 or re.search(r"[|\n]", comments):
        errs.append("Comments must be one line, under 500 characters, without the | character")
    if decision == "SIGNED OFF":
        if info["verdict"] != "READY FOR SIGN-OFF":
            errs.append(f"Sign-off is only valid when the QA verdict is READY FOR SIGN-OFF (it is: {info['verdict']})")
        if stale:
            errs.append("The register changed after this pack was built. Rerun stage 5 (or choose RETURNED TO TEAM).")
    return errs


def apply_signoff(text: str, decision: str, name: str, comments: str, pack_version: str, today: date | None = None) -> str:
    today = today or date.today()
    entries = {
        "Pack version signed off": pack_version,
        "Decision (SIGNED OFF / RETURNED TO TEAM)": decision,
        "Auditor name": name.strip(),
        "Date": today.isoformat(),
        "Comments": comments.strip(),
    }
    out = []
    for line in text.splitlines():
        for item, val in entries.items():
            if re.match(r"^\|\s*" + re.escape(item) + r"\s*\|", line):
                line = f"| {item} | {val} |"
        out.append(line)
    return "\n".join(out) + "\n"
