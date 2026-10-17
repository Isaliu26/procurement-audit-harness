#!/usr/bin/env python3
"""Build the audit planning pack from the planner's judgments in outputs/audit-plan.json.

  --gate   run only the auditor-gate check (every register risk decided, register is a
           revision) and print the approved scope.

Otherwise: compute the approved scope, resolve every citation and placeholder, draw every
sample deterministically from outputs/analytics-full/, verify each sampled transaction in
the cleaned spend file, check control -> test and rule -> risk/control/test coverage, then
write outputs/samples/<test>.csv, planning-memo.md, risk-control-matrix.md, audit-program.md
and pack-figures.json. Nothing is written unless every check passes.

Exit codes: 0 ok, 1 refused (gate or plan failure; nothing written), 2 an input is missing.
"""
import argparse
import hashlib
import importlib.util
import json
import random
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("build_register", HERE.parent / "risk-assessment" / "build_register.py")
br = importlib.util.module_from_spec(_spec)
sys.modules["build_register"] = br
_spec.loader.exec_module(br)

# Sample size by the risk's final score (auditor override applied). First row whose floor is met.
SIZE_BY_SCORE = [(20, 25), (15, 15), (10, 10), (1, 5)]
DEFAULT_MAX_ROWS_PER_ITEM = 50
DEFAULT_SEED = "audit-pack-v1"
IN_SCOPE = {"APPROVE", "OVERRIDE"}
OPS = {"==", "!=", ">", ">=", "<", "<=", "in", "notin", "contains", "isnull", "notnull"}
ID_C, ID_T = re.compile(r"C-\d+"), re.compile(r"T-\d+")
SPEND_COLS = ["row_id", "service", "category", "narrative", "date", "amount", "supplier", "tag"]


class Refused(Exception):
    def __init__(self, errors, code=1):
        self.errors = errors if isinstance(errors, list) else [errors]
        self.code = code
        super().__init__("; ".join(self.errors))


def size_for(score):
    for floor, n in SIZE_BY_SCORE:
        if score >= floor:
            return n
    return SIZE_BY_SCORE[-1][1]


def load(path, what):
    try:
        return br.load_json(path, what)
    except br.Fatal as e:
        raise Refused(str(e), 2)


def strings_in(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from strings_in(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings_in(v)


def esc(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


# =================================================================== gate
def compute_scope(P):
    """-> (scope dict, errors). scope: version, risks (scored rows, sorted), rejected, dec, method, ctx."""
    errs = []
    analytics = load(P["analytics"], "analytics.json")
    hist = load(P["history"], "history.json")
    rules = load(P["rules"], "rules.json")
    ratings = load(P["ratings"], "risk-ratings.json")
    for k, what in (("state", ".register-state.json"), ("comments", "auditor-comments.md"),
                    ("register", "risk-register.md")):
        if not Path(P[k]).exists():
            raise Refused(f"missing input: {what} ({P[k]}): run the risk-assessor first", 2)
    state = json.loads(Path(P["state"]).read_text(encoding="utf-8"))
    version = state["version"]

    m = re.search(r"\*\*Version:\*\*\s*v(\d+)", Path(P["register"]).read_text(encoding="utf-8"))
    if not m or int(m.group(1)) != version:
        errs.append(f"risk-register.md version ({m.group(0) if m else 'none'}) does not match the register "
                    f"state (v{version}): re-run the risk-assessor")
    if version < 2:
        errs.append("the register is not a revision (v1): the auditor has not yet decided the risks and the "
                    "risk-assessor has not applied the decisions")

    dec = br.parse_comments(P["comments"])
    derrs, overrides = br.validate_decisions(dec)
    errs += [f"auditor-comments.md: {e}" for e in derrs]

    decided = {k: v for k, v in dec.items() if v["decision"]}
    if decided != state.get("decisions_seen", {}):
        errs.append("auditor-comments.md was changed after the register was built: ask for the risk-assessor "
                    "to be re-run so the register reflects the decisions")

    reg_ids = list(state["risks"])
    for rid in reg_ids:
        d = dec.get(rid, {}).get("decision", "")
        if not d:
            errs.append(f"{rid}: undecided (no Decision in auditor-comments.md)")
        elif d == "REVISE":
            errs.append(f"{rid}: decision is REVISE: the revised risk needs the auditor's APPROVE before planning")
        elif d == "REJECT":
            errs.append(f"{rid}: rejected but still in the register: re-run the risk-assessor")
    for rid, d in dec.items():
        if d["decision"] in IN_SCOPE and rid not in state["risks"]:
            errs.append(f"{rid}: {d['decision']} but the risk is not in the register (dropped by the builder?)")

    approved = [rid for rid in reg_ids if dec.get(rid, {}).get("decision") in IN_SCOPE]
    if not approved and not errs:
        errs.append("no risk is approved: nothing to plan")

    by_id = {r.get("id"): r for r in ratings.get("risks", [])}
    method = br.load_method(hist)
    ctx = br.Ctx(analytics, rules, hist)
    rows = []
    for rid in approved:
        raw = by_id.get(rid)
        if raw is None or raw != state["risks"][rid]:
            errs.append(f"{rid}: risk-ratings.json no longer matches the register state: re-run the risk-assessor")
            continue
        res, drops, _ = br.evaluate_risk(raw, ctx, method)
        if drops:
            errs.append(f"{rid}: cannot be scored: " + "; ".join(drops))
            continue
        ov = overrides.get(rid, {}) if dec[rid]["decision"] == "OVERRIDE" else {}
        res["agent_likelihood"], res["agent_impact"] = res["lik"], res["imp"]
        res = br.score_risk(res, method, ov)
        res.update(decision=dec[rid]["decision"], comment=dec[rid]["comment"], raw=raw)
        rows.append(res)
    rows.sort(key=lambda r: (-r["score"], r["id"]))
    rejected = {rid: {"title": v.get("title", ""), "comment": v.get("comment", "")}
                for rid, v in state.get("rejected", {}).items()}
    return {"version": version, "risks": rows, "rejected": rejected, "dec": dec, "method": method,
            "ctx": ctx, "analytics": analytics, "rules": rules, "hist": hist}, errs


# ================================================================ samples
def apply_filter(df, flt, where, errs):
    for i, f in enumerate(flt or []):
        col, op = f.get("col"), f.get("op")
        if col not in df.columns:
            errs.append(f"{where}: filter[{i}] column {col!r} not in the file (columns: {', '.join(df.columns)})")
            continue
        if op not in OPS:
            errs.append(f"{where}: filter[{i}] op {op!r} not one of {sorted(OPS)}")
            continue
        s, v = df[col], f.get("value")
        if op in ("in", "notin") and not isinstance(v, list):
            errs.append(f"{where}: filter[{i}] op {op} needs a list value")
            continue
        if op not in ("isnull", "notnull") and "value" not in f:
            errs.append(f"{where}: filter[{i}] needs a value")
            continue
        mask = {"==": lambda: s == v, "!=": lambda: s != v, ">": lambda: s > v, ">=": lambda: s >= v,
                "<": lambda: s < v, "<=": lambda: s <= v, "in": lambda: s.isin(v), "notin": lambda: ~s.isin(v),
                "contains": lambda: s.astype(str).str.contains(str(v), regex=False, na=False),
                "isnull": lambda: s.isna() | (s.astype(str) == ""),
                "notnull": lambda: s.notna() & (s.astype(str) != "")}[op]()
        try:
            df = df[mask.fillna(False)]
        except Exception as e:  # type mismatch such as str > int
            errs.append(f"{where}: filter[{i}] {col} {op} {v!r} failed: {e}")
    return df


def recipe_text(sample):
    parts = [f"`{sample['file']}`"]
    for f in sample.get("filter") or []:
        v = f.get("value")
        parts.append(f"filter {f['col']} {f['op']}" + ("" if f["op"] in ("isnull", "notnull") else f" {json.dumps(v)}"))
    if sample.get("sort"):
        parts.append("sort " + ", ".join(f"{s['col']} {'descending' if s.get('desc') else 'ascending'}"
                                         for s in sample["sort"]))
    parts.append("take the first N in that order" if sample.get("method", "top") == "top"
                 else f"seeded random draw (seed {sample.get('seed', DEFAULT_SEED)!r})")
    return "; ".join(parts)


def draw_sample(test, rid, score, P, spend, errs):
    """-> (rows list for the CSV, stats dict) or (None, None) for a no-sample test."""
    tid = test["id"]
    where = f"{tid} sample"
    s = test.get("sample")
    if s is None:
        if not str(test.get("no_sample_reason", "")).strip():
            errs.append(f"{tid}: sample is null so no_sample_reason is required")
        return None, {"sampled": False}
    f = Path(P["full"]) / str(s.get("file", ""))
    if not s.get("file") or not f.exists():
        errs.append(f"{where}: file {s.get('file')!r} not found in analytics-full")
        return None, None
    df = pd.read_csv(f)
    if "row_ids" not in df.columns and "row_id" not in df.columns:
        errs.append(f"{where}: {f.name} has neither row_ids nor row_id, so its items cannot be traced to "
                    "spend transactions")
        return None, None
    n_before = len(df)
    df = apply_filter(df, s.get("filter"), where, errs)
    sort = s.get("sort") or []
    bad = [x.get("col") for x in sort if x.get("col") not in df.columns]
    if bad:
        errs.append(f"{where}: sort column(s) {bad} not in the file")
        return None, None
    if sort:
        df = df.sort_values(by=[x["col"] for x in sort], ascending=[not x.get("desc") for x in sort],
                            kind="mergesort")
    pop = len(df)
    if pop == 0:
        errs.append(f"{where}: the filter leaves no items (of {n_before}) in {f.name}")
        return None, None

    allowed = size_for(score)
    n = s.get("n", "by_score")
    if n == "by_score":
        n = allowed
    elif not (isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= allowed):
        errs.append(f"{where}: n must be 'by_score' or an integer 1-{allowed} (score {score} allows {allowed})")
        return None, None
    elif not str(s.get("n_reason", "")).strip():
        errs.append(f"{where}: a smaller n than the score allows needs n_reason")
    n = min(n, pop)

    method = s.get("method", "top")
    if method == "top":
        picked = df.head(n)
    elif method == "random":
        rng = random.Random(f"{tid}:{s.get('seed', DEFAULT_SEED)}")
        picked = df.iloc[sorted(rng.sample(range(pop), n))]
    else:
        errs.append(f"{where}: method must be 'top' or 'random'")
        return None, None

    cap = s.get("max_rows_per_item", DEFAULT_MAX_ROWS_PER_ITEM)
    rows, missing, mism, truncated, total_rows = [], [], [], 0, 0
    for rank, (_, it) in enumerate(picked.iterrows(), 1):
        label = next((str(it[c]) for c in ("supplier", "supplier_norm", "row_id") if c in it and pd.notna(it[c])), "")
        ids = [x for x in str(it["row_ids"]).split(";") if x] if "row_ids" in picked.columns \
            and pd.notna(it.get("row_ids")) else [str(it["row_id"])]
        recs = []
        for i in ids:
            if i not in spend.index:
                missing.append(i)
                continue
            r = spend.loc[i]
            if "row_id" in picked.columns and "amount" in picked.columns and pd.notna(it.get("amount")) \
                    and abs(float(it["amount"]) - float(r["amount"])) > 0.005:
                mism.append(i)
            recs.append(r)
        recs.sort(key=lambda r: (str(r["date"]), r.name))
        total_rows += len(recs)
        if len(recs) > cap:
            truncated += 1
        for r in recs[:cap]:
            rows.append({"test_id": tid, "risk_id": rid, "item_rank": rank, "item": label,
                         "item_transactions": len(recs), **{c: r[c] for c in SPEND_COLS if c != "row_id"},
                         "row_id": r.name})
    if missing:
        errs.append(f"{where}: {len(missing)} sampled transaction(s) not in the cleaned spend file, e.g. "
                    + ", ".join(missing[:3]))
    if mism:
        errs.append(f"{where}: amount differs from the spend file for {len(mism)} transaction(s), e.g. {mism[0]}")
    rows.sort(key=lambda r: (r["item_rank"], str(r["date"]), r["row_id"]))
    stats = {"sampled": True, "file": f.name, "items_in_file": n_before, "population_items": pop,
             "allowed_n": allowed, "n_items": len(picked), "transactions_in_items": total_rows,
             "transactions_listed": len(rows), "items_truncated": truncated,
             "value_gbp": round(float(sum(r["amount"] for r in rows)), 2), "recipe": recipe_text(s),
             "items": [{"rank": k, "item": next((r["item"] for r in rows if r["item_rank"] == k), ""),
                        "transactions": next((r["item_transactions"] for r in rows if r["item_rank"] == k), 0),
                        "value_gbp": round(float(sum(r["amount"] for r in rows if r["item_rank"] == k)), 2)}
                       for k in range(1, len(picked) + 1)]}
    return rows, stats


# ================================================================== plan
def resolvable(text, ctx, kinds):
    for m in br.CITE_RE.finditer(text if isinstance(text, str) else ""):
        kind, ref = m.groups()
        if kind not in kinds:
            continue
        if kind == "rule" and ref in ctx.rules:
            return True
        if kind == "metric" and ref.startswith("$"):
            try:
                br.resolve_path(ctx.analytics, ref)
                return True
            except KeyError:
                pass
        if kind == "history" and ref in ctx.hist_ids:
            return True
    return False


def check_plan(plan, scope, P):
    """-> (errs, model). model carries validated tests/controls/pbc/not_tested/coverage and drawn samples."""
    errs = []
    ctx = scope["ctx"]
    in_scope = {r["id"]: r for r in scope["risks"]}
    if not isinstance(plan, dict):
        return ["audit-plan.json must be an object"], None
    if plan.get("register_version") != scope["version"]:
        errs.append(f"audit-plan.json register_version {plan.get('register_version')!r} is not the current "
                    f"register version {scope['version']}: the plan was written against another register")
    if not isinstance(plan.get("memo"), dict) or not all(
            isinstance(plan["memo"].get(k), str) and plan["memo"][k].strip() for k in ("objective", "approach")):
        errs.append("memo needs non-empty 'objective' and 'approach' text")

    spend_path = Path(P["spend"])
    if not spend_path.exists():
        raise Refused(f"missing input: cleaned spend file ({spend_path})", 2)
    spend = pd.read_csv(spend_path, dtype={"row_id": str}).set_index("row_id")

    plan_risks = {}
    for pr in plan.get("risks", []):
        rid = pr.get("risk_id")
        if rid in plan_risks:
            errs.append(f"{rid}: planned twice")
        plan_risks[rid] = pr
        if rid not in in_scope:
            errs.append(f"{rid}: planned but not an approved risk (the planner works only on approved risks)")
    for rid in in_scope:
        if rid not in plan_risks:
            errs.append(f"{rid}: approved but missing from audit-plan.json")

    controls, tests, samples = {}, {}, {}
    for rid, pr in plan_risks.items():
        if rid not in in_scope:
            continue
        score = in_scope[rid]["score"]
        for c in pr.get("controls") or []:
            cid = c.get("id", "?")
            if not ID_C.fullmatch(str(cid)) or cid in controls:
                errs.append(f"{rid}: control id {cid!r} must look like C-01 and be unique")
                continue
            if not str(c.get("description", "")).strip():
                errs.append(f"{cid}: description missing")
            elif not resolvable(c["description"], ctx, {"rule"}):
                errs.append(f"{cid}: uncited control: the description needs at least one [rule:ID] that exists "
                            "in rules.json")
            controls[cid] = {"risk": rid, "tests": [], **c}
        if not pr.get("controls"):
            errs.append(f"{rid}: no expected controls")
        if not pr.get("tests"):
            errs.append(f"{rid}: no tests")
        for t in pr.get("tests") or []:
            tid = t.get("id", "?")
            if not ID_T.fullmatch(str(tid)) or tid in tests:
                errs.append(f"{rid}: test id {tid!r} must look like T-01 and be unique")
                continue
            tests[tid] = {"risk": rid, **t}
            if not str(t.get("objective", "")).strip() or not str(t.get("step", "")).strip():
                errs.append(f"{tid}: objective and step are required")
            if not (resolvable(t.get("step", ""), ctx, {"rule", "metric"})
                    or resolvable(t.get("objective", ""), ctx, {"rule", "metric"})):
                errs.append(f"{tid}: uncited test: the step needs at least one [rule:ID] or [metric:$.path] "
                            "that resolves")
            cids = t.get("control_ids")
            if not cids or not isinstance(cids, list):
                errs.append(f"{tid}: control_ids required (the controls this test exercises)")
            for cid in cids or []:
                if cid not in controls or controls[cid]["risk"] != rid:
                    errs.append(f"{tid}: control {cid} is not a control of {rid}")
                else:
                    controls[cid]["tests"].append(tid)
            if not t.get("pbc") or not all(isinstance(x, str) and x.strip() for x in t.get("pbc", [])):
                errs.append(f"{tid}: pbc must list at least one request item (text)")
            rows, stats = draw_sample(t, rid, score, P, spend, errs)
            if stats is not None:
                samples[tid] = (rows, stats)
    for cid, c in controls.items():
        if not c["tests"]:
            errs.append(f"{cid}: control has no test (no test lists it in control_ids)")

    # rule coverage: cited by an approved risk, a control or a test, or listed as not tested
    cited = {}
    def note(text_src, who):
        for m in br.CITE_RE.finditer(text_src):
            if m.group(1) == "rule" and m.group(2) in ctx.rules:
                cited.setdefault(m.group(2), set()).add(who)
    for r in scope["risks"]:
        for s in strings_in(r["raw"]):
            note(s, r["id"])
    for cid, c in controls.items():
        for s in strings_in(c):
            note(s, cid)
    for tid, t in tests.items():
        for s in strings_in({k: v for k, v in t.items() if k != "sample"}):
            note(s, tid)
    not_tested, seen_nt = {}, set()
    for i, nt in enumerate(plan.get("not_tested") or []):
        ids, reason = nt.get("rule_ids"), str(nt.get("reason", "")).strip()
        if not isinstance(ids, list) or not ids:
            errs.append(f"not_tested[{i}]: rule_ids must be a non-empty list")
            continue
        if not reason:
            errs.append(f"not_tested[{i}]: a reason is required")
        for rid_ in ids:
            if rid_ not in ctx.rules:
                errs.append(f"not_tested[{i}]: {rid_} is not in rules.json")
            elif rid_ in seen_nt:
                errs.append(f"not_tested: {rid_} listed twice")
            else:
                seen_nt.add(rid_)
                not_tested[rid_] = reason
    unaccounted = [r for r in ctx.rules if r not in cited and r not in not_tested]
    if unaccounted:
        errs.append(f"{len(unaccounted)} rule(s) in rules.json are not cited by any approved risk, control or "
                    f"test and not listed as not tested: {', '.join(unaccounted[:12])}"
                    + (" ..." if len(unaccounted) > 12 else ""))
    both = sorted(r for r in not_tested if r in cited)
    if both:
        errs.append(f"rule(s) both cited and listed as not tested: {', '.join(both)}")

    return errs, {"controls": controls, "tests": tests, "samples": samples, "cited": cited,
                  "not_tested": not_tested, "plan_risks": plan_risks}


# ============================================================== rendering
def flatten(o, prefix=""):
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
        return out
    if isinstance(o, list):
        return {prefix: o}
    return {prefix: o}


def build_pack_values(scope, model):
    pack = {"register_version": scope["version"], "risks_in_scope": len(scope["risks"]),
            "risks_rejected": len(scope["rejected"]), "risks": {}, "tests": {},
            "controls_total": len(model["controls"]), "tests_total": len(model["tests"]),
            "rules_total": len(scope["ctx"].rules), "rules_cited": len(model["cited"]),
            "rules_not_tested": len(model["not_tested"]),
            "size_by_score": {f"from_{fl}": n for fl, n in SIZE_BY_SCORE}}
    for r in scope["risks"]:
        pack["risks"][r["id"]] = {"likelihood": r["lik_final"], "impact": r["imp_final"], "score": r["score"],
                                  "sample_size_allowed": size_for(r["score"])}
    tot_tx = tot_val = tot_items = 0
    for tid, (rows, st) in model["samples"].items():
        if st.get("sampled"):
            pack["tests"][tid] = {k: v for k, v in st.items() if k not in ("items", "recipe", "file")}
            pack["tests"][tid]["items"] = {str(i["rank"]): {"transactions": i["transactions"],
                                                            "value_gbp": i["value_gbp"]} for i in st["items"]}
            tot_tx += st["transactions_listed"]
            tot_val += st["value_gbp"]
            tot_items += st["n_items"]
    pack["samples_files"] = sum(1 for _, st in model["samples"].values() if st.get("sampled"))
    pack["samples_items"], pack["samples_transactions"] = tot_items, tot_tx
    pack["samples_value_gbp"] = round(tot_val, 2)
    return pack


def make_renderer(scope, pack):
    ctx = br.Ctx({**scope["analytics"], "pack": pack}, scope["rules"], scope["hist"])
    seen = {}
    errs = []

    def R(text, where):
        out, probs, _ = br.render_text(text, ctx)
        for kind, msg in probs:
            errs.append(f"{where}: {msg}")
        for m in br.PH_RE.finditer(text if isinstance(text, str) else ""):
            if m.group(1).startswith("$pack"):
                continue
            try:
                seen[m.group(1)] = br.fmt_value(br.resolve_path(ctx.analytics, m.group(1)), m.group(2))
            except (KeyError, ValueError, TypeError):
                pass
        return out
    return R, errs, seen


def n(v):
    return f"{v:,}"


def gbp(v):
    return f"£{v:,.0f}"


def header(title, scope, P, extra=""):
    shas = " ".join(f"{k} (sha256 {br.sha(P[k])[:12]})" for k in ("analytics", "history", "rules", "ratings", "plan"))
    return [f"# {title}", "", f"**Pack version:** built from register v{scope['version']}. **Built from:** {shas}.", "",
            "These are risk indicators to investigate, drawn from published data. They are not findings of "
            "wrongdoing by the council, any department or any supplier.", ""] + ([extra, ""] if extra else [])


def rule_ref(rid, ctx):
    return f"{rid} (cl. {ctx.rules[rid]['clause']})"


def render_docs(scope, model, pack, plan, P):
    R, errs, seen = make_renderer(scope, pack)
    ctx = scope["ctx"]
    risks, controls, tests = scope["risks"], model["controls"], model["tests"]
    samples = model["samples"]
    pbc_map, pbc_order = {}, []
    for tid, t in tests.items():
        for item in t["pbc"]:
            txt = R(item, f"{tid} pbc")
            if txt not in pbc_map:
                pbc_map[txt] = []
                pbc_order.append(txt)
            pbc_map[txt].append(tid)
    pbc_ids = {txt: f"PBC-{i:02d}" for i, txt in enumerate(pbc_order, 1)}
    pack["pbc_total"] = len(pbc_order)

    def band(r):
        return f"{r['score']} {r['band']}" + (" ⚑" if r["override"] else "")

    def smp(tid):
        st = samples[tid][1]
        if not st.get("sampled"):
            return "no transaction sample"
        return f"{st['n_items']} items, {n(st['transactions_listed'])} transactions"

    # ------------------------------------------------------------ memo
    memo = plan["memo"]
    L = header("Planning memo: procurement audit, West Berkshire Council", scope, P)
    L += ["## Objective", "", R(memo["objective"], "memo.objective"), "",
          "## Scope: risks approved by the auditor", "",
          f"{n(pack['risks_in_scope'])} risks are in scope. Ratings use the council's own scoring method as "
          f"recorded in the register (register v{pack['register_version']}); a ⚑ marks an auditor override.", "",
          "| Risk | Title | Rating | Auditor decision | Tests | Sample |", "|---|---|---|---|---|---|"]
    for r in risks:
        ts = [t for t, v in tests.items() if v["risk"] == r["id"]]
        smp_txt = "; ".join(f"{t}: {smp(t)}" for t in ts)
        L.append(f"| {r['id']} | {esc(r['title'])} | {esc(band(r))} | {r['decision']} | {', '.join(ts)} | {esc(smp_txt)} |")
    L += [""]
    for r in risks:
        if r["decision"] == "OVERRIDE":
            L += [f"- ⚑ **{r['id']}** auditor override: likelihood {r['agent_likelihood']} → {r['lik_final']}, "
                  f"impact {r['agent_impact']} → {r['imp_final']}. Auditor comment: {r['comment']}"]
        elif r["comment"]:
            L += [f"- **{r['id']}** auditor comment: {r['comment']}"]
    L += ["", "## Out of scope", ""]
    if scope["rejected"]:
        L += [f"- **{rid}** {v['title']}: rejected by the auditor. {v['comment']}".rstrip()
              for rid, v in sorted(scope["rejected"].items())]
    else:
        L += ["No risk was rejected."]
    for i, t in enumerate(memo.get("exclusions") or []):
        L += [f"- {R(t, f'memo.exclusions[{i}]')}"]
    L += ["", "## Approach", "", R(memo["approach"], "memo.approach"), ""]
    if memo.get("points"):
        L += ["## Points for the auditor", ""] + [f"- {R(t, f'memo.points[{i}]')}" for i, t in enumerate(memo["points"])] + [""]
    sz = ", ".join(f"score {fl} or more: {n(sz_)}" if fl > 1 else f"below {SIZE_BY_SCORE[-2][0]}: {n(sz_)}"
                   for fl, sz_ in SIZE_BY_SCORE)
    L += ["## Sampling", "",
          "Samples are targeted at the flagged items in `outputs/analytics-full/`, drawn by `build_pack.py` "
          "(the same inputs always give the same sample), and every sampled transaction is checked against the "
          "cleaned spend data. The number of items drawn scales with the risk's final score (" + sz + "), "
          "so the highest-rated risks are examined most.", "",
          f"In total {n(pack['samples_items'])} items are drawn across {n(pack['samples_files'])} sampled tests, "
          f"covering {n(pack['samples_transactions'])} transactions worth {gbp(pack['samples_value_gbp'])} "
          "as published. Samples are chosen to target risk indicators, not to estimate error rates, and cannot be "
          "extrapolated to the whole population.", "",
          "## Limitations", ""]
    L += [f"- {x}" for x in scope["analytics"].get("limitations", [])]
    L += [f"- {R(t, f'memo.limitations[{i}]')}" for i, t in enumerate(memo.get("limitations") or [])]
    L += ["", "## Rule coverage", "",
          f"{n(pack['rules_total'])} rules are in `rules.json`: {n(pack['rules_cited'])} are cited by an approved "
          f"risk, control or test and {n(pack['rules_not_tested'])} are listed as not tested, each with a reason "
          "(see the risk-control matrix).", "",
          "## Next step", "", "The pack goes to the challenger and the QA review, then to the auditor for sign-off "
          "(`outputs/review.md`).", ""]
    docs = {"planning-memo.md": "\n".join(L)}

    # ---------------------------------------------------------- matrix
    L = header("Risk-control matrix", scope, P)
    L += ["## Risks, controls and tests", "",
          "| Risk | Rating | Rule | Expected control | Test | Sample |", "|---|---|---|---|---|---|"]
    for r in risks:
        first = True
        for cid, c in controls.items():
            if c["risk"] != r["id"]:
                continue
            crules = sorted({m.group(2) for m in br.CITE_RE.finditer(c["description"]) if m.group(1) == "rule"
                             and m.group(2) in ctx.rules})
            ts = c["tests"]
            L.append(f"| {r['id'] + ' ' + esc(r['title']) if first else ''} | {esc(band(r)) if first else ''} | "
                     f"{esc(', '.join(rule_ref(x, ctx) for x in crules))} | "
                     f"{cid}: {esc(R(c['description'], cid))} | {', '.join(ts)} | "
                     f"{esc('; '.join(f'{t}: {smp(t)}' for t in ts))} |")
            first = False
    L += ["", "## Rule coverage", "",
          "Every rule in `rules.json` is cited by an approved risk, control or test, or listed as not tested with a "
          "reason.", "", "| Rule | Clause | Status | Cited by / reason |", "|---|---|---|---|"]
    for rid, rule in ctx.rules.items():
        if rid in model["cited"]:
            L.append(f"| {rid} | {rule['clause']} | tested | {', '.join(sorted(model['cited'][rid]))} |")
        else:
            L.append(f"| {rid} | {rule['clause']} | not tested | {esc(R(model['not_tested'][rid], f'not_tested {rid}'))} |")
    docs["risk-control-matrix.md"] = "\n".join(L) + "\n"

    # --------------------------------------------------------- program
    L = header("Audit program", scope, P)
    for r in risks:
        L += [f"## {r['id']}: {r['title']}", "", f"**Rating:** {band(r)} (likelihood {r['lik_final']} {r['lik_label']}, "
              f"impact {r['imp_final']} {r['imp_label']}). **Sample allowance for this score:** "
              f"{n(size_for(r['score']))} items per sampled test.", "",
              f"**Risk indicator:** {R(r['raw']['statement'], r['id'] + ' statement')}", ""]
        for cid, c in controls.items():
            if c["risk"] != r["id"]:
                continue
            L += [f"### Expected control {cid}", "", R(c["description"], cid), ""]
            for tid in c["tests"]:
                t = tests[tid]
                _, st = samples[tid]
                L += [f"#### Test {tid}", "", f"**Objective:** {R(t['objective'], tid + ' objective')}", "",
                      f"**Test step:** {R(t['step'], tid + ' step')}", ""]
                if st.get("sampled"):
                    L += [f"**Sample:** {recipe_text(t['sample'])}. {n(st['population_items'])} items qualify; "
                          f"{n(st['n_items'])} drawn ({'score-based size' if t['sample'].get('n', 'by_score') == 'by_score' else 'reduced: ' + t['sample'].get('n_reason', '')}). "
                          f"{n(st['transactions_listed'])} transactions worth {gbp(st['value_gbp'])} are listed in "
                          f"`outputs/samples/{tid}.csv`.", ""]
                    if st["items_truncated"]:
                        L += [f"{n(st['items_truncated'])} item(s) hold more transactions than the listing cap; the "
                              "CSV shows the earliest ones and the `item_transactions` column gives the full count.", ""]
                    L += ["| # | Item | Transactions | Value listed |", "|---|---|---|---|"]
                    L += [f"| {i['rank']} | {esc(i['item'])} | {n(i['transactions'])} | {gbp(i['value_gbp'])} |"
                          for i in st["items"]]
                    L += [""]
                else:
                    L += [f"**Sample:** none. {R(t['no_sample_reason'], tid + ' no_sample_reason')}", ""]
                L += ["**Needs (PBC):** " + ", ".join(pbc_ids[R(x, tid)] for x in t["pbc"]), ""]
    L += ["## Prepared-by-client (PBC) request list", "",
          "| Ref | Request | Needed for |", "|---|---|---|"]
    for txt in pbc_order:
        L.append(f"| {pbc_ids[txt]} | {esc(txt)} | {', '.join(pbc_map[txt])} |")
    docs["audit-program.md"] = "\n".join(L) + "\n"
    return docs, errs, seen


# ==================================================================== main
def paths(a):
    o = Path(a.outputs)
    full = Path(a.analytics_full) if a.analytics_full else o / "analytics-full"
    return {"analytics": o / "analytics.json", "history": o / "history.json", "rules": o / "rules.json",
            "ratings": o / "risk-ratings.json", "comments": o / "auditor-comments.md",
            "state": o / ".register-state.json", "register": o / "risk-register.md",
            "plan": o / "audit-plan.json", "full": full,
            "spend": Path(a.spend) if a.spend else full / "cleaned_spend.csv",
            "samples": o / "samples", "out": o}


def run(a):
    P = paths(a)
    scope, errs = compute_scope(P)
    if errs:
        raise Refused(errs)
    if a.gate:
        print(f"GATE OK: register v{scope['version']}, {len(scope['risks'])} risk(s) in scope:")
        for r in scope["risks"]:
            print(f"  {r['id']}  {r['score']} {r['band']}{' (override)' if r['override'] else ''}  {r['title']}")
        for rid, v in sorted(scope["rejected"].items()):
            print(f"  {rid}  out of scope (rejected)  {v['title']}")
        return 0

    plan = load(P["plan"], "audit-plan.json (the planner's judgments)")
    errs, model = check_plan(plan, scope, P)
    if model is None:
        raise Refused(errs)
    pack = build_pack_values(scope, model)
    docs, rerrs, seen = render_docs(scope, model, pack, plan, P) if not errs else ({}, [], {})
    errs += rerrs
    if errs:
        raise Refused(errs)

    out = P["out"]
    sdir = P["samples"]
    sdir.mkdir(parents=True, exist_ok=True)
    keep = set()
    for tid, (rows, st) in model["samples"].items():
        if rows is not None:
            fn = sdir / f"{tid}.csv"
            pd.DataFrame(rows, columns=["test_id", "risk_id", "item_rank", "item", "item_transactions", "row_id",
                                        "date", "amount", "supplier", "service", "category", "narrative", "tag"]
                         ).to_csv(fn, index=False)
            keep.add(fn.name)
    for old in sdir.glob("T-*.csv"):
        if old.name not in keep:
            old.unlink()
    for name, text in docs.items():
        (out / name).write_text(text, encoding="utf-8")
    figs = {k: v for k, v in flatten(pack).items() if not isinstance(v, list)}
    figs.update({f"pack.tests.{tid}.recipe": st["recipe"] for tid, (_, st) in model["samples"].items()
                 if st.get("sampled")})
    (out / "pack-figures.json").write_text(json.dumps({
        "note": "Every figure build_pack.py computed itself. `figures` are the pack's own values (placeholders "
                "{{$pack.<key>}}); `from_analytics` are analytics.json values the plan placed in text.",
        "register_version": scope["version"],
        "inputs_sha256": {k: br.sha(P[k]) for k in ("analytics", "history", "rules", "ratings", "plan")},
        "figures": figs, "from_analytics": seen}, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"OK: register v{scope['version']}: {pack['risks_in_scope']} risks, {pack['controls_total']} controls, "
          f"{pack['tests_total']} tests, {pack['samples_transactions']} sampled transactions in "
          f"{pack['samples_files']} file(s), {pack['pbc_total']} PBC items, {pack['rules_cited']}/"
          f"{pack['rules_total']} rules cited, {pack['rules_not_tested']} listed as not tested")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gate", action="store_true", help="run only the auditor-gate check")
    ap.add_argument("--outputs", default="outputs")
    ap.add_argument("--analytics-full", default=None)
    ap.add_argument("--spend", default=None, help="cleaned spend CSV (default: analytics-full/cleaned_spend.csv)")
    a = ap.parse_args(argv)
    try:
        return run(a)
    except Refused as e:
        if e.code == 1:
            print(f"REFUSED: {len(e.errors)} problem(s), nothing written:", file=sys.stderr)
            for x in e.errors:
                print(f"  - {x}", file=sys.stderr)
        else:
            print(f"ERROR: {e.errors[0]}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
