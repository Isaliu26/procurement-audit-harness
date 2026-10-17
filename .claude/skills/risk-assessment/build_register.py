#!/usr/bin/env python3
"""Build outputs/risk-register.md and outputs/auditor-comments.md from the agent's
judgments in outputs/risk-ratings.json.

The agent supplies judgments only: scores, justifications, citations and
{{$.path}} placeholders. This script resolves every citation, fills every figure
from analytics.json, computes score / matrix label / band from the council's
method in history.json, drops risks it cannot evidence, and, after the auditor
gate, checks that the auditor's decisions were applied and nothing else changed.

Exit codes: 0 built (drops and warnings are listed), 1 refused (revision check or
rating-file error: nothing written), 2 an input is missing or unusable.
"""
import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

CITE_RE = re.compile(r"\[(rule|metric|history):([^\]\s]+)\]")
PH_RE = re.compile(r"\{\{\s*(\$[^}|\s]*)\s*(?:\|\s*(\w+)\s*)?\}\}")
ID_RE = re.compile(r"\b[A-Z]{2,5}-\d+\b")
LEVEL_RE = re.compile(r"\bL[1-5]\b")
NUM_RE = re.compile(r"£?\d[\d,]*(?:\.\d+)?%?")
ACCUSE_RE = re.compile(
    r"\b(fraud\w*|corrupt\w*|misconduct|wrongdoing|illegal\w*|unlawful\w*|embezzl\w*|theft|"
    r"collu\w+|breached|misappropriat\w*)\b", re.I)
ADVERSE = {"limited assurance", "no assurance", "weak", "unsatisfactory", "limited", "poor"}
DECISIONS = {"APPROVE", "REJECT", "REVISE", "OVERRIDE"}
FIG4_CRR_MIN = 9  # Figure 4 (strategy p21) puts risks scoring 9 or above on the Corporate Risk Register

# Conflicts inside the council's scoring method. For each: which reading the builder
# (or the rubric) uses, and which is only marked. Printed in every register header.
CONFLICTS = [
    ("DIS-01", "Impact 'Medium' is numbered (2) in para 4.3 but 3 in Table 1.",
     "Used: 3 (Table 1 and matrix row '3 Medium'). Marked, not used: the (2) in para 4.3."),
    ("DIS-02", "Table 1 percentage ranges overlap between impact 3 and 4; the printed £ ranges abut at £500k.",
     "Used: the printed £ ranges; an exposure of exactly £500k is placed at the higher level (4). "
     "Marked, not used: the percentage-of-budget ranges."),
    ("DIS-03", "Table 2 probability bands leave gaps (99-100%, 29-30%, below 2%).",
     "Used: the five likelihood labels and scores only, set by the rubric in SKILL.md. "
     "Marked, not used: the probability percentages."),
    ("DIS-04", "The matrix names scores 8-12 'High'; Table 4 names that band 'Medium - High (Amber)'.",
     "Used: the Table 4 band name. Marked: the matrix label is shown beside it on every risk where they differ."),
    ("DIS-05", "Table 4 puts risks on the Corporate Risk Register at Extreme (15-25); Figure 4 says a score of 9 or above.",
     f"Used: Table 4 (15-25). Marked: a risk scoring {FIG4_CRR_MIN}-14 carries a note that the Figure 4 reading "
     "would also place it on the Corporate Risk Register."),
    ("DIS-07", "Para 6.3 sends an Extreme risk to Directorate level to decide the register; Table 4 adds it to the Corporate Risk Register.",
     "Used: Table 4. Marked, not used: the para 6.3 routing."),
]


class Fatal(Exception):
    def __init__(self, msg, code=2):
        super().__init__(msg)
        self.code = code


# ----------------------------------------------------------------- loading
def load_json(path, what):
    p = Path(path)
    if not p.exists():
        raise Fatal(f"missing input: {what} ({p})")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise Fatal(f"{what} is not valid JSON ({p}): {e}")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def index_ids(obj, out=None):
    """id -> item for every dict in history.json carrying a string 'id'."""
    out = {} if out is None else out
    if isinstance(obj, dict):
        if isinstance(obj.get("id"), str):
            out[obj["id"]] = obj
        for v in obj.values():
            index_ids(v, out)
    elif isinstance(obj, list):
        for v in obj:
            index_ids(v, out)
    return out


def resolve_path(doc, path):
    """'$.a.b.0.c' -> value. Raises KeyError with the segment that failed."""
    cur = doc
    for seg in [s for s in path[1:].split(".") if s != ""]:
        if isinstance(cur, dict):
            if seg not in cur:
                raise KeyError(seg)
            cur = cur[seg]
        elif isinstance(cur, list):
            try:
                cur = cur[int(seg)]
            except (ValueError, IndexError):
                raise KeyError(seg)
        else:
            raise KeyError(seg)
    return cur


def strip_label(s):
    return re.sub(r"\s*\(.*?\)\s*", "", s).strip().lower()


def parse_range(text):
    m = re.search(r"(\d+)\s*-\s*(\d+)", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"up to\s*(\d+)", text, re.I)
    if m:
        return 0, int(m.group(1))
    raise Fatal(f"cannot parse band range {text!r}")


def load_method(hist):
    sm = hist.get("scoring_method") or {}
    if not sm.get("usable"):
        lik = {1: "Very low", 2: "Low", 3: "Medium", 4: "High", 5: "Very high"}
        matrix = {(l, i): ("", l * i) for l in lik for i in lik}
        bands = [("Low", 0, 4, None), ("Medium", 5, 9, None), ("High", 10, 15, None), ("Very high", 16, 25, None)]
        return {"fallback": True, "lik": lik, "imp": dict(lik), "matrix": matrix, "bands": bands,
                "escalation": {}}
    lik = {int(x["score"]): x["label"] for x in sm["likelihood_scale"]}
    imp = {int(x["score"]): x["label"] for x in sm["impact_scale"]}
    matrix = {}
    for m in sm["matrix"]:
        if "impact_row" in m and "cells" in m:
            i = int(m["impact_row"].split()[0])
            cells = re.findall(r"([A-Za-z]+)\((\d+)\)", m["cells"])
            if len(cells) != 5:
                raise Fatal(f"matrix row {m.get('id')} does not have 5 cells")
            for l, (label, score) in enumerate(cells, 1):
                if int(score) != l * i:
                    raise Fatal(f"matrix {m.get('id')}: cell {label}({score}) is not likelihood {l} x impact {i}")
                matrix[(l, i)] = (label, int(score))
    if len(matrix) != 25 or sorted(lik) != [1, 2, 3, 4, 5] or sorted(imp) != [1, 2, 3, 4, 5]:
        raise Fatal("history.json scoring_method is incomplete (need 5 likelihood, 5 impact, 25 matrix cells)")
    bands = []
    for b in sm["bands"]:
        lo, hi = parse_range(b["score_range"])
        bands.append((b["label"], lo, hi, b["id"]))
    for (_, s) in matrix.values():
        if not any(lo <= s <= hi for _, lo, hi, _ in bands):
            raise Fatal(f"score {s} falls in no band of the council's Table 4")
    esc = {}
    for e in sm.get("escalation", []):
        if not e.get("band"):  # register-membership items (ESC-05..) carry no band
            continue
        txt = e["quote"].replace(" | ", " ")
        txt = re.sub(r"^(?:(?:\d+\s*-\s*\d+|Up to \d+)\s*)+", "", txt).strip()
        esc[strip_label(e["band"].rsplit(" ", 1)[0] if re.search(r"\d$", e["band"]) else e["band"])] = (e["id"], txt)
    return {"fallback": False, "lik": lik, "imp": imp, "matrix": matrix, "bands": bands, "escalation": esc}


def band_for(method, score):
    for label, lo, hi, bid in method["bands"]:
        if lo <= score <= hi:
            return label, bid
    raise Fatal(f"no band for score {score}")


# --------------------------------------------------------------- resolving
class Ctx:
    def __init__(self, analytics, rules, hist):
        self.analytics = analytics
        self.rules = {r["rule_id"]: r for r in rules.get("rules", [])}
        self.hist_ids = index_ids(hist)

    def describe_history(self, hid):
        it = self.hist_ids[hid]
        if "audit_title" in it:
            op = it.get("opinion") or it.get("opinion_report") or ""
            return f"{it['audit_title']}: {op}"
        return (it.get("theme") or it.get("description") or it.get("quote") or "")[:70]


def fmt_value(v, fmt):
    if isinstance(v, (dict, list)):
        raise ValueError("placeholder points at a container, not a value")
    if fmt == "gbp":
        return f"£{float(v):,.0f}"
    if fmt == "gbp2":
        return f"£{float(v):,.2f}"
    if fmt == "pct":
        return f"{float(v) * 100:.1f}%"
    if fmt == "int":
        return f"{int(round(float(v))):,}"
    if fmt == "ratio":
        return f"{float(v):.2f}"
    if fmt == "raw" or isinstance(v, (str, bool)):
        return str(v)
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def render_text(text, ctx):
    """Return (rendered, problems, n_resolved_citations).
    problems: list of (kind, message); kind in placeholder | cite | typed | tone."""
    problems = []
    if not isinstance(text, str):
        return "", [("placeholder", f"expected text, got {type(text).__name__}")], 0

    # typed-figure and tone checks run on the agent's own words
    bare = ID_RE.sub("", LEVEL_RE.sub("", PH_RE.sub("", CITE_RE.sub("", text))))
    for m in NUM_RE.finditer(bare):
        problems.append(("typed", f"figure typed in prose: {m.group(0)!r}: use a {{{{$.path}}}} placeholder"))
    for m in ACCUSE_RE.finditer(bare):
        problems.append(("tone", f"accusatory wording {m.group(0)!r}: use indicator language"))

    def ph(m):
        path, fmt = m.group(1), m.group(2)
        try:
            return fmt_value(resolve_path(ctx.analytics, path), fmt)
        except KeyError as e:
            problems.append(("placeholder", f"placeholder {path}: no such key {e.args[0]!r} in analytics.json"))
        except (ValueError, TypeError) as e:
            problems.append(("placeholder", f"placeholder {path}: {e}"))
        return m.group(0)

    out = PH_RE.sub(ph, text)
    n_ok = 0

    def cite(m):
        nonlocal n_ok
        kind, ref = m.group(1), m.group(2)
        if kind == "rule":
            r = ctx.rules.get(ref)
            if r is None:
                problems.append(("cite", f"[rule:{ref}] not found in rules.json"))
                return f"[rule:{ref} ⚠ UNRESOLVED]"
            n_ok += 1
            return f"[rule:{ref} (cl. {r['clause']})]"
        if kind == "metric":
            if not ref.startswith("$"):
                problems.append(("cite", f"[metric:{ref}] is not a $.path"))
                return f"[metric:{ref} ⚠ UNRESOLVED]"
            try:
                resolve_path(ctx.analytics, ref)
            except KeyError as e:
                problems.append(("cite", f"[metric:{ref}] no such key {e.args[0]!r} in analytics.json"))
                return f"[metric:{ref} ⚠ UNRESOLVED]"
            n_ok += 1
            return f"[metric:{ref}]"
        if ref not in ctx.hist_ids:
            problems.append(("cite", f"[history:{ref}] no item with that id in history.json"))
            return f"[history:{ref} ⚠ UNRESOLVED]"
        n_ok += 1
        return f"[history:{ref} ({ctx.describe_history(ref)})]"

    out = CITE_RE.sub(cite, out)
    return out, problems, n_ok


# ------------------------------------------------------------- risk checks
def int_in(v, lo, hi):
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def is_adverse(item):
    for k in ("opinion", "opinion_report", "opinion_implementation"):
        if str(item.get(k, "")).strip().lower() in ADVERSE:
            return True
    return False


def evaluate_risk(raw, ctx, method):
    """-> dict(result fields, drops, warnings). drops non-empty means excluded."""
    drops, warns = [], []
    rid = raw.get("id", "?")

    def take(label, text, need_cite=False):
        out, probs, n_ok = render_text(text, ctx)
        for kind, msg in probs:
            if kind == "placeholder":
                drops.append(f"{label}: {msg}")
            elif kind == "cite":
                warns.append(f"{rid} {label}: {msg}")
            else:
                warns.append(f"{rid} {label}: {msg}")
        if need_cite and n_ok == 0:
            drops.append(f"{label}: no resolvable citation ([rule:], [metric:] or [history:])")
        return out

    res = {"id": rid, "title": raw.get("title", ""), "theme": raw.get("theme", "")}
    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(rid)):
        drops.append("id missing or not a simple identifier")
    res["title"] = take("title", raw.get("title", ""))
    if not raw.get("title"):
        drops.append("title missing")
    res["statement"] = take("statement", raw.get("statement", ""))
    res["focus"] = take("focus", raw.get("focus", ""))
    res["evidence"] = [take(f"evidence[{i}]", e) for i, e in enumerate(raw.get("evidence", []))]
    if not res["evidence"]:
        drops.append("evidence: at least one evidence line is required")

    lk, im = raw.get("likelihood") or {}, raw.get("impact") or {}
    res["lik_just"] = take("likelihood.justification", lk.get("justification", ""), need_cite=True)
    res["imp_just"] = take("impact.justification", im.get("justification", ""), need_cite=True)

    base = lk.get("base_score")
    if not int_in(base, 1, 5):
        drops.append("likelihood.base_score must be an integer 1-5")
        base = None
    if base is not None and lk.get("rubric") != f"L{base}":
        drops.append(f"likelihood.rubric must be 'L{base}' to match base_score (got {lk.get('rubric')!r})")
    imp = im.get("score")
    if not int_in(imp, 1, 5):
        drops.append("impact.score must be an integer 1-5")
        imp = None

    uplift = lk.get("uplift") or {}
    final = base
    res["uplift"] = None
    if uplift.get("applied"):
        ids = uplift.get("audit_ids") or []
        if not ids:
            drops.append("likelihood.uplift: applied without audit_ids")
        for aid in ids:
            it = ctx.hist_ids.get(aid)
            if it is None or ("audit_title" not in it):
                drops.append(f"likelihood.uplift: {aid} is not an audit or follow-up in history.json")
            elif not is_adverse(it):
                drops.append(f"likelihood.uplift: {aid} ({ctx.describe_history(aid)}) is not an adverse opinion")
        reason = take("likelihood.uplift.reason", uplift.get("reason", ""))
        if not uplift.get("reason"):
            drops.append("likelihood.uplift: reason required")
        if base is not None:
            final = min(5, base + 1)
        res["uplift"] = {"audit_ids": ids, "reason": reason,
                         "described": [f"{a}: {ctx.describe_history(a)}" for a in ids if a in ctx.hist_ids]}
    res["base"] = base

    if base is not None and imp is not None and not drops:
        pass
    res["lik"], res["imp"] = final, imp
    return res, drops, warns


def score_risk(res, method, override):
    """Fill score, labels and band. override = {'likelihood': n, 'impact': n} or {}."""
    l = override.get("likelihood", res["lik"])
    i = override.get("impact", res["imp"])
    mlabel, score = method["matrix"][(l, i)]
    band, bid = band_for(method, score)
    res.update(lik_final=l, imp_final=i, score=score, matrix_label=mlabel, band=band, band_id=bid,
               lik_label=method["lik"][l], imp_label=method["imp"][i], override=override or None)
    esc = method["escalation"].get(strip_label(band))
    res["escalation"] = esc
    res["matrix_mismatch"] = bool(mlabel) and strip_label(band) != mlabel.lower()
    res["fig4_note"] = (not method["fallback"]) and FIG4_CRR_MIN <= score < 15
    return res


# ------------------------------------------------------- auditor comments
ROW_SPLIT = re.compile(r"(?<!\\)\|")


def parse_comments(path):
    p = Path(path)
    out = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in ROW_SPLIT.split(line.strip())[1:-1]]
        if len(cells) < 5 or cells[0].lower() == "risk" or set(cells[0]) <= set("-: "):
            continue
        out[cells[0]] = {"decision": cells[3].upper(), "comment": "|".join(cells[4:]).strip()}
    return out


def validate_decisions(dec):
    errs, overrides = [], {}
    for rid, d in dec.items():
        v = d["decision"]
        if v == "":
            continue
        if v not in DECISIONS:
            errs.append(f"{rid}: Decision {v!r} is not one of {', '.join(sorted(DECISIONS))}")
        elif v == "REVISE" and not d["comment"]:
            errs.append(f"{rid}: REVISE needs a Comment saying what to change")
        elif v == "OVERRIDE":
            ov = {k.lower(): int(n) for k, n in
                  re.findall(r"\b(likelihood|impact)\s*=\s*([1-5])\b", d["comment"], re.I)}
            if not ov:
                errs.append(f"{rid}: OVERRIDE needs 'likelihood=N' and/or 'impact=N' (N 1-5) in the Comment")
            overrides[rid] = ov
    return errs, overrides


def esc_cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def write_comments(path, version, rows, dec, removed):
    L = ["# Auditor comments: risk register decisions", "",
         f"Register version: v{version}. Complete the **Decision** and **Comment** columns, then ask for the "
         "risk-assessor to be re-run. Do not edit the Risk ids or the header row. Avoid the `|` character in comments.",
         "",
         "| Decision | Meaning | Comment needed |", "|---|---|---|",
         "| APPROVE | Keep this risk as rated, in scope | no |",
         "| REJECT | Remove this risk from the register | optional |",
         "| REVISE | Agent must change this risk as the Comment asks | yes: what to change |",
         "| OVERRIDE | Auditor sets the rating; the register marks it | yes: `likelihood=N` and/or `impact=N` |",
         "", "| Risk | Title | Rating | Decision | Comment |", "|---|---|---|---|---|"]
    for r in rows:
        d = dec.get(r["id"], {"decision": "", "comment": ""})
        L.append(f"| {r['id']} | {esc_cell(r['title'])} | {r['score']} {esc_cell(r['band'])}"
                 f"{' ⚑' if r['override'] else ''} | {d['decision']} | {esc_cell(d['comment'])} |")
    for rid, info in removed.items():
        d = dec.get(rid, {"decision": "REJECT", "comment": ""})
        L.append(f"| {rid} | {esc_cell(info.get('title', ''))} | removed | {d['decision']} | {esc_cell(d['comment'])} |")
    Path(path).write_text("\n".join(L) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- diffing
def flatten(o, prefix=""):
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else k))
        return out
    return {prefix: o}


def diff_risk(old, new):
    a, b = flatten(old), flatten(new)
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def short(v):
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= 40 else "(text changed)"


# ------------------------------------------------------------- revision gate
def revision_checks(raw_risks, kept_ids, dropped, snap, dec, pending, rev_block, new_version):
    """Return (errors, warnings, change_lines)."""
    errs, warns, lines = [], [], []
    old = snap["risks"]
    prev_rejected = set(snap.get("rejected", {}))
    changes = {}
    for c in (rev_block or {}).get("changes", []):
        changes.setdefault(c.get("risk_id"), []).append(c)

    if not rev_block:
        errs.append("auditor decisions are pending but risk-ratings.json has no 'revision' block "
                    "(write one even if nothing changed: {\"round\": N, \"changes\": []})")
    elif rev_block.get("round") != new_version:
        errs.append(f"revision.round is {rev_block.get('round')!r}; this register will be v{new_version}")

    now = {r["id"]: r for r in raw_risks}
    for rid, r in now.items():
        if rid in prev_rejected:
            errs.append(f"{rid} was rejected by the auditor earlier and must not reappear")

    for rid, d in sorted(pending.items()):
        v = d["decision"]
        if v == "REJECT":
            if rid in kept_ids or rid in now:
                errs.append(f"{rid}: auditor REJECT left unapplied (risk still in risk-ratings.json)")
            else:
                lines.append(f"- **{rid}** REJECT: removed from scope. Auditor comment: {d['comment'] or '(none)'}")
        elif v == "REVISE":
            if rid not in now:
                errs.append(f"{rid}: auditor REVISE but the risk is missing from risk-ratings.json")
                continue
            fields = diff_risk(old.get(rid, {}), now[rid]) if rid in old else []
            if not fields:
                errs.append(f"{rid}: auditor REVISE left unapplied (risk is identical to the previous version)")
            elif rid not in changes:
                errs.append(f"{rid}: revised but no entry in revision.changes naming the reason")
            else:
                declared = {f for c in changes[rid] for f in c.get("fields", [])}
                undeclared = [f for f in fields if f not in declared]
                if undeclared:
                    warns.append(f"{rid}: changed fields not named in revision.changes: {', '.join(undeclared)}")
                why = "; ".join(c.get("reason", "") for c in changes[rid])
                lines.append(f"- **{rid}** REVISE (auditor: {d['comment']}). Changed: "
                             + ", ".join(f"`{f}` {short(flatten(old[rid]).get(f))} → {short(flatten(now[rid]).get(f))}"
                                         for f in fields) + f". Reason: {why or '(none given)'}")
        elif v == "APPROVE":
            lines.append(f"- **{rid}** APPROVE: unchanged")
        elif v == "OVERRIDE":
            lines.append(f"- **{rid}** OVERRIDE ⚑: auditor set the rating ({d['comment']})")

    for rid in old:
        if rid in now and rid not in dropped:
            fields = diff_risk(old[rid], now[rid])
            p = pending.get(rid, {}).get("decision")
            if fields and p != "REVISE":
                errs.append(f"{rid}: changed ({', '.join(fields)}) but the auditor did not ask for a revision "
                            f"(decision: {p or dec.get(rid, {}).get('decision') or 'none'})")
        elif rid not in prev_rejected and pending.get(rid, {}).get("decision") != "REJECT":
            why = dropped.get(rid)
            errs.append(f"{rid}: removed from the register but the auditor did not reject it"
                        + (f" (dropped by the builder: {'; '.join(why)})" if why else ""))
    for rid in now:
        if rid not in old and rid not in prev_rejected:
            ref = [c.get("auditor_ref") for c in changes.get(rid, []) if c.get("action") == "added"]
            if not ref or not any(pending.get(x, {}).get("comment") for x in ref):
                errs.append(f"{rid}: new risk added without an 'added' entry in revision.changes whose "
                            "auditor_ref names an auditor comment asking for it")
            else:
                lines.append(f"- **{rid}** ADDED at the auditor's request (see comment on {', '.join(ref)})")
    declared_ids = {c.get("risk_id") for cs in changes.values() for c in cs}
    for rid in declared_ids - set(old) - set(now) - set(pending):
        warns.append(f"revision.changes names {rid}, which is not a known risk")
    return errs, warns, lines


# ------------------------------------------------------------------ rendering
def render_register(version, rows, dropped, titles, method, meta, dec, rev_lines, rev_warn, prev_rejected):
    L = ["# Risk Register: West Berkshire Council procurement audit planning", ""]
    L.append(f"**Version:** v{version}" + (" (revision after auditor gate)" if version > 1 else " (initial, awaiting auditor decisions)"))
    L.append(f"**Built from:** analytics.json (generated {meta['analytics_generated']}, sha256 {meta['analytics_sha'][:12]}), "
             f"history.json (sha256 {meta['history_sha'][:12]}), rules.json (sha256 {meta['rules_sha'][:12]}), "
             f"risk-ratings.json (sha256 {meta['ratings_sha'][:12]}).")
    L.append("")
    L.append("These are risk indicators to investigate, drawn from published data. They are not findings of "
             "wrongdoing by the council, any department or any supplier.")
    L.append("")
    L.append("## Scoring method")
    L.append("")
    if method["fallback"]:
        L.append("**FALLBACK SCALE IN USE:** history.json reports no usable council scoring method, so risks are rated "
                 "1-5 Very low to Very high. Score = likelihood × impact; bands Low 1-4, Medium 5-9, High 10-15, "
                 "Very high 16-25.")
    else:
        L.append("The council's own method, extracted into history.json from the Risk Management Strategy 2024-2027: "
                 "5-point likelihood × 5-point impact, matrix cell for the label, Table 4 for the band and escalation. "
                 "Score, label and band are computed by `build_register.py`, never by the agent.")
        L.append("")
        L.append("**Conflicts inside the council's method.** One reading is used and the other is marked. Neither is "
                 "resolved silently. The auditor confirmed these six choices on 2026-10-10.")
        L.append("")
        for did, what, choice in CONFLICTS:
            L.append(f"- **{did}** {what} {choice}" + ("" if did in meta["hist_ids"] else " (id not found in this history.json)"))
    L.append("")
    if rev_lines is not None:
        L.append(f"## Revision v{version}: what changed")
        L.append("")
        L += rev_lines or ["- No decisions pending this round."]
        for w in rev_warn:
            L.append(f"- ⚠ {w}")
        L.append("")
    L.append("## Summary")
    L.append("")
    L.append("| Risk | Title | Likelihood | Impact | Score | Band |")
    L.append("|---|---|---|---|---|---|")
    for r in rows:
        flag = " ⚑" if r["override"] else ""
        L.append(f"| {r['id']} | {esc_cell(r['title'])} | {r['lik_final']} {r['lik_label']} | "
                 f"{r['imp_final']} {r['imp_label']} | {r['score']}{flag} | {esc_cell(r['band'])} |")
    L.append("")
    L.append("## Risks")
    L.append("")
    for r in rows:
        L.append(f"### {r['id']}: {r['title']}")
        L.append("")
        L.append(f"- **Risk:** {r['statement']}")
        if r["uplift"]:
            L.append(f"- **Likelihood:** {r['lik_final']} ({r['lik_label']}). {r['lik_just']} "
                     f"Base {r['base']} + 1 repeat-finding uplift = {min(5, r['base'] + 1)} "
                     f"({'; '.join(r['uplift']['described'])}). {r['uplift']['reason']}")
        else:
            L.append(f"- **Likelihood:** {r['lik_final']} ({r['lik_label']}). {r['lik_just']}")
        L.append(f"- **Impact:** {r['imp_final']} ({r['imp_label']}). {r['imp_just']}")
        line = (f"- **Rating:** {r['lik_final']} × {r['imp_final']} = **{r['score']}**, band "
                f"**{r['band']}**" + (f" [history:{r['band_id']}]" if r["band_id"] else ""))
        if r["matrix_mismatch"]:
            line += f". Matrix label: {r['matrix_label']} (differs from the Table 4 band name; DIS-04)"
        L.append(line)
        if r["escalation"]:
            L.append(f"- **Escalation (Table 4):** {r['escalation'][1]} [history:{r['escalation'][0]}]")
        if r["fig4_note"]:
            L.append(f"- **Marked, not applied:** the Figure 4 reading (score {FIG4_CRR_MIN} or above) would also place "
                     "this on the Corporate Risk Register (DIS-05).")
        if r["override"]:
            o = r["override"]
            what = ", ".join(f"{k} {r['agent_' + k]} → {v}" for k, v in o.items())
            L.append(f"- ⚑ **AUDITOR OVERRIDE:** {what}. The agent proposed score {r['agent_score']}. "
                     f"Auditor comment: {dec[r['id']]['comment']}")
        L.append("- **Evidence:**")
        for e in r["evidence"]:
            L.append(f"  - {e}")
        L.append(f"- **Proposed focus:** {r['focus']}")
        L.append("")
    L.append("## Excluded risks (not rated)")
    L.append("")
    if dropped:
        L.append("Excluded because a justification had no resolvable citation, a figure could not be sourced, or a "
                 "rating input was invalid. Fix `risk-ratings.json` and re-run.")
        L.append("")
        for rid, reasons in dropped.items():
            L.append(f"- **{rid}** {esc_cell(titles.get(rid, ''))}: " + "; ".join(reasons))
    else:
        L.append("None.")
    if prev_rejected:
        L.append("")
        L.append("Removed at the auditor's request: " + ", ".join(sorted(prev_rejected)) + ".")
    L.append("")
    L.append("## Auditor decisions")
    L.append("")
    L.append("Recorded in `outputs/auditor-comments.md` (APPROVE, REJECT, REVISE or OVERRIDE per risk). "
             "The table below mirrors that file as at this build.")
    L.append("")
    L.append("| Risk | Rating | Decision | Comment |")
    L.append("|---|---|---|---|")
    for r in rows:
        d = dec.get(r["id"], {"decision": "", "comment": ""})
        L.append(f"| {r['id']} | {r['score']} {esc_cell(r['band'])}{' ⚑' if r['override'] else ''} | "
                 f"{d['decision'] or '(undecided)'} | {esc_cell(d['comment'])} |")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--analytics", default="outputs/analytics.json")
    ap.add_argument("--history", default="outputs/history.json")
    ap.add_argument("--rules", default="outputs/rules.json")
    ap.add_argument("--ratings", default="outputs/risk-ratings.json")
    ap.add_argument("--register", default="outputs/risk-register.md")
    ap.add_argument("--comments", default="outputs/auditor-comments.md")
    ap.add_argument("--state", default="outputs/.register-state.json")
    a = ap.parse_args(argv)

    try:
        return run(a)
    except Fatal as e:
        print(f"{'REFUSED' if e.code == 1 else 'ERROR'}: {e}", file=sys.stderr)
        return e.code


def run(a):
    analytics = load_json(a.analytics, "analytics.json")
    hist = load_json(a.history, "history.json")
    rules = load_json(a.rules, "rules.json")
    ratings = load_json(a.ratings, "risk-ratings.json (the agent's judgments)")
    method = load_method(hist)
    ctx = Ctx(analytics, rules, hist)

    raw_risks = ratings.get("risks")
    if not isinstance(raw_risks, list) or not raw_risks:
        raise Fatal("risk-ratings.json has no 'risks' list", 1)
    ids = [r.get("id") for r in raw_risks]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise Fatal(f"duplicate risk ids in risk-ratings.json: {sorted(dup)}", 1)

    dec = parse_comments(a.comments)
    derrs, overrides = validate_decisions(dec)
    if derrs:
        raise Fatal("auditor-comments.md: " + "; ".join(derrs), 1)

    snap = None
    if Path(a.state).exists():
        snap = json.loads(Path(a.state).read_text(encoding="utf-8"))

    # evaluate every risk
    evaluated, dropped, warnings, titles = [], {}, [], {}
    for raw in raw_risks:
        res, drops, warns = evaluate_risk(raw, ctx, method)
        titles[res["id"]] = raw.get("title", "")
        warnings += warns
        if drops:
            dropped[res["id"]] = drops
        else:
            evaluated.append((raw, res))

    # decide mode and pending decisions
    decided = {k: v for k, v in dec.items() if v["decision"]}
    seen = (snap or {}).get("decisions_seen", {})
    pending = {k: v for k, v in decided.items() if seen.get(k) != v}
    gated = bool(snap) and (snap["version"] > 1 or bool(decided))
    rev_block = ratings.get("revision")
    version = (snap or {}).get("version", 1)

    rev_lines, rev_warn = None, []
    if pending:
        if not snap:
            raise Fatal("auditor decisions exist but there is no previous register state "
                        f"({a.state}); build the initial register before the gate", 1)
        version = snap["version"] + 1
        errs, rev_warn, rev_lines = revision_checks(
            raw_risks, {r["id"] for _, r in evaluated}, dropped, snap, dec, pending, rev_block, version)
        if errs:
            raise Fatal("revision check failed, nothing written:\n  - " + "\n  - ".join(errs), 1)
    elif gated:
        # already past the gate and nothing new decided: only a rebuild, no change allowed
        errs, _, _ = revision_checks(raw_risks, {r["id"] for _, r in evaluated}, dropped, snap, dec, {},
                                     {"round": version, "changes": []}, version)
        if errs:
            raise Fatal("register is past the auditor gate and risk-ratings.json no longer matches it, "
                        "nothing written:\n  - " + "\n  - ".join(errs), 1)
        rev_lines, rev_warn = snap.get("rev_lines", []), snap.get("rev_warn", [])
    elif rev_block:
        raise Fatal("risk-ratings.json has a 'revision' block but there are no new auditor decisions "
                    "to apply: remove the block", 1)

    # score
    rows = []
    for raw, res in evaluated:
        ov = overrides.get(res["id"], {}) if dec.get(res["id"], {}).get("decision") == "OVERRIDE" else {}
        res["agent_likelihood"], res["agent_impact"] = res["lik"], res["imp"]
        res = score_risk(res, method, ov)
        res["agent_score"] = res["agent_likelihood"] * res["agent_impact"]
        rows.append(res)
    rows.sort(key=lambda r: (-r["score"], r["id"]))

    prev_rejected = dict((snap or {}).get("rejected", {}))
    for rid, d in pending.items():
        if d["decision"] == "REJECT" and snap and rid in snap["risks"]:
            prev_rejected[rid] = {"title": snap["risks"][rid].get("title", ""), "comment": d["comment"]}
    meta = {"analytics_generated": analytics.get("generated_at", "?"), "analytics_sha": sha(a.analytics),
            "history_sha": sha(a.history), "rules_sha": sha(a.rules), "ratings_sha": sha(a.ratings),
            "hist_ids": ctx.hist_ids}

    register = render_register(version, rows, dropped, titles, method, meta, dec, rev_lines, rev_warn, prev_rejected)
    Path(a.register).write_text(register, encoding="utf-8")
    write_comments(a.comments, version, rows, dec, prev_rejected)
    Path(a.state).write_text(json.dumps({
        "version": version,
        "decisions_seen": decided,
        "risks": {raw["id"]: raw for raw in raw_risks if raw["id"] not in dropped},
        "rejected": prev_rejected,
        "rev_lines": rev_lines, "rev_warn": rev_warn,
    }, indent=1, ensure_ascii=False), encoding="utf-8")

    for rid, reasons in dropped.items():
        print(f"DROPPED {rid}: " + "; ".join(reasons))
    for w in warnings + rev_warn:
        print(f"WARN {w}")
    print(f"OK: register v{version}: {len(rows)} risk(s) kept, {len(dropped)} dropped, "
          f"{len(warnings) + len(rev_warn)} warning(s) -> {a.register}, {a.comments}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
