#!/usr/bin/env python3
"""Fixture test for build_pack.py: two risks, a real register built by build_register.py (v1, then
v2 after the auditor's decisions), then the gate and the plan checks. Includes the three required
failures: a missing risk, an uncited control and an unaccounted rule.

Run: .venv/bin/python .claude/skills/audit-program/test_build_pack.py
"""
import contextlib
import copy
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_pack as bp  # noqa: E402

br = bp.br

ANALYTICS = {
    "generated_at": "2026-01-01T00:00:00+00:00",
    "limitations": ["Spend dates are payment-run timestamps, not invoice dates."],
    "tests": {
        "split_purchases@25000": {"counts": {"flagged_items": 3}, "totals_gbp": {"combined": 90000.0},
                                  "top20": [{"supplier": "ACME"}]},
        "threshold_clustering@1000": {"counts": {"flagged_items": 4}, "totals_gbp": {"total": 3900.0}},
    },
}
RULES = {"rules": [
    {"rule_id": "CPR-13", "clause": "6.16", "type": "anti-avoidance"},
    {"rule_id": "CPR-60", "clause": "AppB-B1", "type": "procurement-route"},
    {"rule_id": "CPR-61", "clause": "AppB-B1", "type": "advertising"},
    {"rule_id": "CPR-99", "clause": "9.9", "type": "documentation"},
]}
HISTORY = {"scoring_method": {"usable": False}, "audits": [{"id": "AUD-01", "audit_title": "Contract Letting",
                                                           "opinion": "Reasonable Assurance"}]}


def risk(rid, title, rules, lik, imp, metric):
    return {"id": rid, "title": title, "theme": rid.lower(),
            "statement": "Risk indicators to investigate " + " ".join(f"[rule:{r}]" for r in rules) + ".",
            "likelihood": {"base_score": lik, "rubric": f"L{lik}",
                           "justification": f"{{{{{metric}.counts.flagged_items}}}} flagged [metric:{metric}.counts.flagged_items].",
                           "uplift": {"applied": False, "audit_ids": [], "reason": "Not a repeat finding [history:AUD-01]."}},
            "impact": {"score": imp, "justification": f"Exposure noted [metric:{metric}.counts.flagged_items]."},
            "evidence": [f"Flagged: {{{{{metric}.counts.flagged_items}}}} [metric:{metric}.counts.flagged_items]"],
            "focus": "Recommend a targeted sample."}


RATINGS = {"risks": [
    risk("R-01", "Same-supplier payments combining past the quote threshold", ["CPR-13", "CPR-60"], 4, 5,
         "$.tests.split_purchases@25000"),
    risk("R-02", "Low-value payments clustering at the lowest quote boundary", ["CPR-13"], 2, 3,
         "$.tests.threshold_clustering@1000"),
]}

SPEND_HEAD = "row_id,service,category,narrative,date,amount,supplier,supplier_norm,tag"
SPEND = [(f"S:{i}", "Highways", "Supplies", "Works", f"2026-05-{i:02d} 10:00:00", amt, sup, sup.upper(), "general_procurement")
         for i, (amt, sup) in enumerate([(9000, "Acme Ltd"), (9500, "Acme Ltd"), (9800, "Acme Ltd"),
                                         (990, "Bolt Ltd"), (980, "Bolt Ltd"), (975, "Cog Ltd"), (960, "Cog Ltd"),
                                         (2000, "Dyno Ltd"), (3000, "Dyno Ltd"), (500, "Elm Ltd")], 1)]
SPLIT = ("tier,supplier,combined_gbp,tag,row_ids\n"
         "25000,Acme Ltd,28300,general_procurement,S:1;S:2;S:3\n"
         "25000,Dyno Ltd,5000,general_procurement,S:8;S:9\n"
         "1000,Bolt Ltd,1970,general_procurement,S:4;S:5\n")
CLUSTER = ("tier,row_id,amount,supplier\n1000,S:4,990,Bolt Ltd\n1000,S:5,980,Bolt Ltd\n"
           "1000,S:6,975,Cog Ltd\n1000,S:7,960,Cog Ltd\n")

PLAN = {
    "register_version": 2,
    "memo": {"objective": "Plan testing of {{$pack.risks_in_scope}} approved risks [rule:CPR-13].",
             "approach": "Targeted samples from the flagged lists, sized by score."},
    "risks": [
        {"risk_id": "R-01",
         "controls": [{"id": "C-01", "description": "Requirements above the quote threshold are quoted for [rule:CPR-60] "
                                                      "and not split [rule:CPR-13]."}],
         "tests": [{"id": "T-01", "control_ids": ["C-01"], "objective": "Check for a single underlying requirement.",
                    "step": "For each sampled group, compare invoices and orders [metric:$.tests.split_purchases@25000.counts.flagged_items].",
                    "sample": {"file": "split_purchases.csv", "filter": [{"col": "tier", "op": "==", "value": 25000}],
                               "sort": [{"col": "combined_gbp", "desc": True}], "n": "by_score"},
                    "pbc": ["Orders and invoices for the sampled suppliers", "Quotes obtained"]}]},
        {"risk_id": "R-02",
         "controls": [{"id": "C-02", "description": "At least one quote is sought for low-value purchases [rule:CPR-61]."}],
         "tests": [{"id": "T-02", "control_ids": ["C-02"], "objective": "Confirm a quote was sought.",
                    "step": "Inspect the quote record for each sampled payment [rule:CPR-61].",
                    "sample": {"file": "threshold_clustering.csv", "sort": [{"col": "amount", "desc": True}], "n": "by_score"},
                    "pbc": ["Orders and invoices for the sampled suppliers"]}]},
    ],
    "not_tested": [{"rule_ids": ["CPR-99"], "reason": "Documentation requirement with no spend-data evidence."}],
}

failures = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


class Fx:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.o = Path(self.tmp.name) / "outputs"
        (self.o / "analytics-full").mkdir(parents=True)
        for name, obj in (("analytics", ANALYTICS), ("rules", RULES), ("history", HISTORY)):
            (self.o / f"{name}.json").write_text(json.dumps(obj))
        (self.o / "risk-ratings.json").write_text(json.dumps(RATINGS))
        full = self.o / "analytics-full"
        (full / "cleaned_spend.csv").write_text(SPEND_HEAD + "\n" + "\n".join(",".join(map(str, r)) for r in SPEND) + "\n")
        (full / "split_purchases.csv").write_text(SPLIT)
        (full / "threshold_clustering.csv").write_text(CLUSTER)

    def register(self, ratings=None):
        if ratings is not None:
            (self.o / "risk-ratings.json").write_text(json.dumps(ratings))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return br.main(["--analytics", str(self.o / "analytics.json"), "--history", str(self.o / "history.json"),
                            "--rules", str(self.o / "rules.json"), "--ratings", str(self.o / "risk-ratings.json"),
                            "--register", str(self.o / "risk-register.md"), "--comments", str(self.o / "auditor-comments.md"),
                            "--state", str(self.o / ".register-state.json")])

    def decide(self, decisions):
        p = self.o / "auditor-comments.md"
        out = []
        for line in p.read_text().splitlines():
            cells = line.split("|")
            if line.startswith("| R-") and cells[1].strip() in decisions:
                cells[4] = f" {decisions[cells[1].strip()]} "
            out.append("|".join(cells))
        p.write_text("\n".join(out) + "\n")

    def approved_v2(self, decisions=None):
        assert self.register() == 0
        self.decide(decisions or {"R-01": "APPROVE", "R-02": "APPROVE"})
        r = copy.deepcopy(RATINGS)
        r["revision"] = {"round": 2, "changes": []}
        assert self.register(r) == 0

    def plan(self, plan):
        (self.o / "audit-plan.json").write_text(json.dumps(plan))

    def pack(self, *flags):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = bp.main(["--outputs", str(self.o), *flags])
        return code, out.getvalue(), err.getvalue()

    def written(self):
        return [p.name for p in (self.o / "samples").glob("*")] if (self.o / "samples").exists() else [], \
            [n for n in ("planning-memo.md", "risk-control-matrix.md", "audit-program.md", "pack-figures.json")
             if (self.o / n).exists()]


def mutated(fn):
    p = copy.deepcopy(PLAN)
    fn(p)
    return p


# ---- 1. gate: v1 register is not a revision
fx = Fx()
assert fx.register() == 0
code, out, err = fx.pack("--gate")
check(code == 1 and "not a revision" in err, "gate fails on a v1 register (decisions not applied)")

# ---- 2. gate: undecided risk
fx.decide({"R-01": "APPROVE"})
r = copy.deepcopy(RATINGS)
r["revision"] = {"round": 2, "changes": []}
fx.register(r)
code, out, err = fx.pack("--gate")
check(code == 1 and "R-02: undecided" in err, "gate fails when a register risk is undecided")

# ---- 3. gate passes once both are decided and the register is a revision
fx = Fx()
fx.approved_v2()
code, out, err = fx.pack("--gate")
check(code == 0 and "2 risk(s) in scope" in out, "gate passes: both risks decided, register is v2")
check(fx.written() == ([], []), "--gate writes nothing")

# ---- 4. happy path
fx.plan(PLAN)
code, out, err = fx.pack()
check(code == 0, f"valid plan builds (exit {code}) {err.strip()[:200]}")
samples, docs = fx.written()
check(sorted(samples) == ["T-01.csv", "T-02.csv"], "one sample file per test")
check(len(docs) == 4, "memo, matrix, program and pack-figures written")
import pandas as pd  # noqa: E402
t1 = pd.read_csv(fx.o / "samples" / "T-01.csv")
check(list(t1["item"].unique()) == ["Acme Ltd", "Dyno Ltd"] and len(t1) == 5, "T-01: filtered to tier 25000, sorted by combined_gbp desc, groups expanded to 5 transactions")
t2 = pd.read_csv(fx.o / "samples" / "T-02.csv")
check(len(t2) == 4 and t2.iloc[0]["amount"] == 990, "T-02: row-level file sorted by amount desc")
fig = json.loads((fx.o / "pack-figures.json").read_text())["figures"]
check(fig["risks.R-01.sample_size_allowed"] == 25 and fig["risks.R-02.sample_size_allowed"] == 5,
      "sample allowance sized by score (20 -> 25, 6 -> 5)")
check(fig["samples_transactions"] == 9 and fig["risks_in_scope"] == 2, "pack-figures lists computed counts")
memo = (fx.o / "planning-memo.md").read_text()
check("Plan testing of 2 approved risks [rule:CPR-13 (cl. 6.16)]" in memo, "placeholder and citation resolved in memo")
prog = (fx.o / "audit-program.md").read_text()
check(prog.rstrip().split("\n")[-1].startswith("| PBC-02") and "PBC-01 | Orders and invoices" in prog,
      "audit-program ends with the PBC list, shared request listed once")
check("CPR-99 | 9.9 | not tested" in (fx.o / "risk-control-matrix.md").read_text(), "matrix shows the not-tested rule and reason")
before = {p.name: p.read_bytes() for p in list((fx.o / "samples").glob("*")) + [fx.o / n for n in docs]}
fx.pack()
after = {p.name: p.read_bytes() for p in list((fx.o / "samples").glob("*")) + [fx.o / n for n in docs]}
check(before == after, "second run is byte-identical (deterministic)")


def fails(plan, needle, label):
    f = Fx()
    f.approved_v2()
    f.plan(plan)
    code, out, err = f.pack()
    check(code == 1 and needle in err, f"{label}")
    check(f.written() == ([], []), f"{label}: nothing written")


# ---- 5. the three required failures
fails(mutated(lambda p: p["risks"].pop(1)), "R-02: approved but missing from audit-plan.json", "missing risk is refused")
fails(mutated(lambda p: p["risks"][0]["controls"][0].update(description="Quotes are obtained before ordering.")),
      "C-01: uncited control", "uncited control is refused")
fails(mutated(lambda p: p.update(not_tested=[])), "not cited by any approved risk, control or test and not listed as not tested: CPR-99",
      "unaccounted rule is refused")

# ---- 6. further plan checks
fails(mutated(lambda p: p["risks"][0]["controls"].append({"id": "C-03", "description": "Extra control [rule:CPR-60]."})),
      "C-03: control has no test", "control without a test is refused")
fails(mutated(lambda p: p["risks"][0]["tests"][0].update(step="Look at the invoices.")), "T-01: uncited test",
      "test step without a rule or metric is refused")
fails(mutated(lambda p: p["risks"][0]["tests"][0]["sample"].update(file="threshold_clustering.csv", sort=[{"col": "amount"}], filter=[{"col": "amount", "op": ">", "value": 5000}])),
      "the filter leaves no items", "empty sample population is refused")
fails(mutated(lambda p: p["risks"][1]["tests"][0]["sample"].update(n=9)), "n must be 'by_score' or an integer 1-5",
      "sample larger than the score allows is refused")
fails(mutated(lambda p: p["memo"].update(approach="We will test 25 payments.")), "figure typed in prose",
      "figure typed in prose is refused")
fails(mutated(lambda p: p["memo"].update(approach="Check {{$.tests.nope.count}}.")), "no such key 'nope'",
      "unresolvable placeholder is refused")
fails(mutated(lambda p: p.update(register_version=1)), "register_version", "plan for another register version is refused")
fails(mutated(lambda p: p["risks"].append({"risk_id": "R-08", "controls": [], "tests": []})),
      "R-08: planned but not an approved risk", "plan for a non-approved risk is refused")
fails(mutated(lambda p: p["not_tested"][0].update(reason="")), "a reason is required", "not-tested rule without a reason is refused")

# ---- 7. a sampled transaction missing from the spend data
f = Fx()
f.approved_v2()
f.plan(PLAN)
(f.o / "analytics-full" / "split_purchases.csv").write_text(SPLIT.replace("S:1;S:2;S:3", "S:1;S:2;S:77"))
code, out, err = f.pack()
check(code == 1 and "not in the cleaned spend file, e.g. S:77" in err, "sampled transaction absent from the spend data is refused")

print()
print("ALL PASS" if not failures else f"{len(failures)} FAILED")
sys.exit(1 if failures else 0)
