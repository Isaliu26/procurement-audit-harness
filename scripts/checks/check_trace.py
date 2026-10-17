#!/usr/bin/env python3
"""Traceability check.
 1. every rule in rules.json is cited by a rated risk (risk-register.md), a control or a test
    (audit-plan.json), or listed as not tested with a reason; the matrix agrees;
 2. every approved in-scope risk has a control with a test and appears in the matrix and the program;
 3. every High (Extreme or High band) register risk is in scope, and every risk not in scope has its
    exclusion recorded with a reason (auditor-comments.md) and named in the memo;
 4. challenges.md exists, every row cites evidence and none is open. Without --final, an absent
    or unfinished challenges.md is reported as PENDING, not as a failure (the challenger may still be working).
Usage: check_trace.py [--root DIR] [--final]"""
import re
import sys

from _util import CITE_RULE, IN_SCOPE, cli, load_json, need, parse_md_table, result

CITE_ANY = re.compile(r"\[(rule|metric|history):([^\]\s]+)")
STATUSES = {"resolved", "declined", "for the auditor"}


def strings_in(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from strings_in(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings_in(v)


def hist_ids(o, out=None):
    out = set() if out is None else out
    if isinstance(o, dict):
        if isinstance(o.get("id"), str):
            out.add(o["id"])
        for v in o.values():
            hist_ids(v, out)
    elif isinstance(o, list):
        for v in o:
            hist_ids(v, out)
    return out


def metric_ok(analytics, path):
    cur = analytics
    for seg in [s for s in path[1:].split(".") if s]:
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        elif isinstance(cur, list) and seg.isdigit() and int(seg) < len(cur):
            cur = cur[int(seg)]
        else:
            return False
    return True


def parse_comments(text):
    out = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        c = [x.strip() for x in re.split(r"(?<!\\)\|", line.strip())[1:-1]]
        if len(c) >= 5 and re.fullmatch(r"R-\d+", c[0]):
            out[c[0]] = {"decision": c[3].upper(), "comment": "|".join(c[4:]).strip()}
    return out


def run(root, final=False):
    r = result("trace")
    out = root / "outputs"
    rules = {x["rule_id"]: x for x in load_json(out / "rules.json")["rules"]}
    analytics, hist = load_json(out / "analytics.json"), load_json(out / "history.json")
    hids = hist_ids(hist)
    plan = load_json(out / "audit-plan.json", "audit-plan.json")
    register = need(out / "risk-register.md").read_text(encoding="utf-8")
    dec = parse_comments(need(out / "auditor-comments.md").read_text(encoding="utf-8"))
    matrix = need(out / "risk-control-matrix.md").read_text(encoding="utf-8")
    program = need(out / "audit-program.md").read_text(encoding="utf-8")
    memo = need(out / "planning-memo.md").read_text(encoding="utf-8")

    # ---- 1. rules
    cited = {}
    for m in CITE_RULE.finditer(register):
        cited.setdefault(m.group(1), set()).add("register")
    controls = {c.get("id"): (pr.get("risk_id"), c) for pr in plan.get("risks", []) for c in pr.get("controls", [])}
    tests = {t.get("id"): (pr.get("risk_id"), t) for pr in plan.get("risks", []) for t in pr.get("tests", [])}
    for cid, (_, c) in controls.items():
        for m in CITE_RULE.finditer(c.get("description", "")):
            cited.setdefault(m.group(1), set()).add(cid)
    for tid, (_, t) in tests.items():
        for s in (t.get("step", ""), t.get("objective", "")):
            for m in CITE_RULE.finditer(s):
                cited.setdefault(m.group(1), set()).add(tid)
    not_tested = {}
    for nt in plan.get("not_tested", []):
        for rid in nt.get("rule_ids", []):
            if not str(nt.get("reason", "")).strip():
                r["failures"].append(f"rule {rid}: listed as not tested with no reason")
            not_tested[rid] = nt.get("reason", "")
    rows = parse_md_table(matrix, ["rule", "status"]) or []
    status_of = {x["rule"]: x["status"].lower() for x in rows}
    for rid in rules:
        r["checked"] += 1
        if rid not in cited and rid not in not_tested:
            r["failures"].append(f"rule {rid}: not cited by a rated risk, control or test and not listed as not tested")
        want = "tested" if rid in cited else "not tested"
        if status_of.get(rid) != want:
            r["failures"].append(f"rule {rid}: risk-control-matrix.md shows {status_of.get(rid)!r}, expected {want!r}")
    for rid in not_tested:
        if rid not in rules:
            r["failures"].append(f"not_tested names {rid}, which is not in rules.json")
    for rid in set(cited) - set(rules):
        r["failures"].append(f"{rid} is cited but is not in rules.json")

    # ---- 2. approved risks
    approved = sorted(k for k, v in dec.items() if v["decision"] in IN_SCOPE)
    plan_ids = {pr.get("risk_id") for pr in plan.get("risks", [])}
    for extra in sorted(plan_ids - set(approved)):
        r["failures"].append(f"{extra}: planned but not an approved in-scope risk")
    for rid in approved:
        r["checked"] += 1
        pr = next((p for p in plan.get("risks", []) if p.get("risk_id") == rid), None)
        if pr is None:
            r["failures"].append(f"{rid}: approved but not in audit-plan.json")
            continue
        cs = [(cid, c) for cid, (rr, c) in controls.items() if rr == rid]
        if not cs:
            r["failures"].append(f"{rid}: no control")
        for cid, c in cs:
            if not any(m.group(1) in rules for m in CITE_RULE.finditer(c.get("description", ""))):
                r["failures"].append(f"{cid} ({rid}): control cites no rule in rules.json")
            if not any(cid in (t.get("control_ids") or []) for _, (rr, t) in tests.items() if rr == rid):
                r["failures"].append(f"{cid} ({rid}): control has no test")
        for tid, (rr, t) in tests.items():
            if rr != rid:
                continue
            txt = t.get("step", "") + " " + t.get("objective", "")
            ok = any((k == "rule" and v.split("(")[0] in rules) or (k == "metric" and metric_ok(analytics, v))
                     for k, v in CITE_ANY.findall(txt))
            if not ok:
                r["failures"].append(f"{tid} ({rid}): test cites no resolvable rule or metric")
        if not re.search(rf"^\|\s*{rid}\b", matrix, re.M):
            r["failures"].append(f"{rid}: not in risk-control-matrix.md")
        if not re.search(rf"^##\s+{rid}\b", program, re.M):
            r["failures"].append(f"{rid}: not in audit-program.md")

    # ---- 3. High risks and exclusions
    summary = parse_md_table(register, ["risk", "band"]) or []
    for row in summary:
        r["checked"] += 1
        rid, band = row["risk"], row["band"]
        if re.search(r"extreme|high", band, re.I) and dec.get(rid, {}).get("decision") not in IN_SCOPE:
            r["failures"].append(f"{rid}: {band} risk is not in scope (decision {dec.get(rid, {}).get('decision') or 'none'})")
    for rid, d in dec.items():
        if d["decision"] in IN_SCOPE:
            continue
        r["checked"] += 1
        if d["decision"] != "REJECT":
            r["failures"].append(f"{rid}: decision {d['decision'] or 'none'} is neither in scope nor a recorded exclusion")
        elif not d["comment"]:
            r["failures"].append(f"{rid}: rejected with no reason recorded in auditor-comments.md")
        if not re.search(rf"\b{rid}\b", memo.split("## Out of scope")[-1].split("\n## ")[0]):
            r["failures"].append(f"{rid}: exclusion is not recorded in planning-memo.md (Out of scope)")

    # ---- 4. challenges
    ch = out / "challenges.md"
    sink = r["failures"] if final else r["pending"]
    if not ch.exists():
        sink.append("challenges.md does not exist")
    else:
        table = parse_md_table(ch.read_text(encoding="utf-8"), ["#", "status", "citation"])
        if table is None:
            sink.append("challenges.md has no table with # / Citation / Status columns")
        else:
            r["notes"].append(f"challenges.md: {len(table)} row(s)")
            for row in table:
                r["checked"] += 1
                n, st, cite = row["#"], row["status"].strip().lower(), row["citation"]
                if st == "open" or st not in STATUSES:
                    sink.append(f"challenge #{n}: status {row['status']!r} is not closed (resolved / declined / for the auditor)")
                hits = CITE_ANY.findall(cite)
                if not hits:
                    r["failures"].append(f"challenge #{n}: cites no evidence ([rule:], [metric:] or [history:])")
                for k, v in hits:
                    v = v.split("(")[0]
                    if (k == "rule" and v not in rules) or (k == "history" and v not in hids) \
                            or (k == "metric" and not metric_ok(analytics, v)):
                        r["failures"].append(f"challenge #{n}: [{k}:{v}] does not resolve")
    return r


if __name__ == "__main__":
    sys.exit(cli("trace", run))
