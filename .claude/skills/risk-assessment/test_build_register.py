#!/usr/bin/env python3
"""Fixture test for build_register.py: one good risk (R-01), one broken risk (R-02),
then the auditor gate: decisions applied, left unapplied, and unrequested changes.

Run: .venv/bin/python .claude/skills/risk-assessment/test_build_register.py
"""
import contextlib
import copy
import io
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_register as br  # noqa: E402

ANALYTICS = {
    "generated_at": "2026-01-01T00:00:00+00:00",
    "tests": {
        "split_purchases@25000": {"counts": {"flagged_items": 299}, "totals_gbp": {"combined": 23514371.83},
                                  "top20": [{"supplier": "ACME", "n_payments": 3}]},
        "off_contract": {"counts": {"flagged_items": 632}},
    },
}
RULES = {"rules": [{"rule_id": "CPR-13", "clause": "6.16", "type": "anti-avoidance"},
                   {"rule_id": "CPR-60", "clause": "AppB-B1", "type": "procurement-route"}]}
MATRIX_ROWS = {5: "Moderate High Extreme Extreme Extreme", 4: "Moderate High High Extreme Extreme",
               3: "Low Moderate High High Extreme", 2: "Low Moderate Moderate High High",
               1: "Low Low Low Moderate Moderate"}
HISTORY = {
    "audits": [
        {"id": "AUD-01", "audit_title": "Contract Letting", "opinion": "Reasonable Assurance"},
        {"id": "AUD-12", "audit_title": "Personal Budgets (Direct Payments)", "opinion": "Limited Assurance"},
    ],
    "discrepancies": [{"id": f"DIS-0{n}"} for n in (1, 2, 3, 4, 5, 7)],
    "scoring_method": {
        "usable": True,
        "likelihood_scale": [{"id": f"LIK-0{6 - s}", "score": s, "label": lab} for s, lab in
                             [(5, "Certain"), (4, "Almost Certain"), (3, "Likely"), (2, "Unlikely"), (1, "Rare")]],
        "impact_scale": [{"id": f"IMP-0{6 - s}", "score": s, "label": lab} for s, lab in
                         [(5, "Critical"), (4, "Major"), (3, "Medium"), (2, "Minor"), (1, "Negligible")]],
        "matrix": [{"id": f"MTX-0{6 - i}", "impact_row": f"{i} X",
                    "cells": " ".join(f"{lab}({l * i})" for l, lab in enumerate(row.split(), 1))}
                   for i, row in MATRIX_ROWS.items()],
        "bands": [{"id": "BND-01", "label": "Extreme (Red)", "score_range": "15 -25"},
                  {"id": "BND-02", "label": "Medium - High (Amber)", "score_range": "8-12"},
                  {"id": "BND-03", "label": "Moderate", "score_range": "4-6"},
                  {"id": "BND-04", "label": "Low (Green)", "score_range": "Up to 3"}],
        "escalation": [{"id": "ESC-01", "band": "Extreme (Red) 15 -25", "quote": "Add to Corporate | Risk Register."},
                       {"id": "ESC-02", "band": "Medium - High (Amber) 8-12", "quote": "Seek assurance | that controls work."},
                       {"id": "ESC-03", "band": "Moderate 4-6", "quote": "4-6 | 4-6 | None | Monitor risk"},
                       {"id": "ESC-04", "band": "Low (Green) Up to 3", "quote": "Up to 3 | None"}],
    },
}

GOOD = {
    "id": "R-01", "title": "Payments split to stay under the quote threshold", "theme": "splitting",
    "statement": "Same-supplier payments may be split so each stays under the threshold [rule:CPR-13].",
    "likelihood": {"base_score": 3, "rubric": "L3",
                   "justification": "{{$.tests.split_purchases@25000.counts.flagged_items}} flagged groups "
                                    "[metric:$.tests.split_purchases@25000.counts.flagged_items] against [rule:CPR-13].",
                   "uplift": {"applied": True, "audit_ids": ["AUD-12"],
                              "reason": "Prior limited-assurance audit on payment controls [history:AUD-12]."}},
    "impact": {"score": 3, "justification": "Combined {{$.tests.split_purchases@25000.totals_gbp.combined|gbp}} "
                                            "[metric:$.tests.split_purchases@25000.totals_gbp.combined]."},
    "evidence": ["Top group: {{$.tests.split_purchases@25000.top20.0.supplier}} "
                 "[metric:$.tests.split_purchases@25000.top20]"],
    "focus": "Test the flagged groups for a single underlying requirement.",
}
BROKEN = {
    "id": "R-02", "title": "Off-contract spend", "theme": "off-contract",
    "statement": "Suppliers with no notice.",
    "likelihood": {"base_score": 4, "rubric": "L4", "justification": "Looks widespread."},   # no citation
    "impact": {"score": 3, "justification": "Large [metric:$.tests.off_contract.nope]."},      # bad citation
    "evidence": ["{{$.tests.off_contract.counts.flagged_items}} suppliers"],
    "focus": "Check contracts.",
}

failures = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


class Env:
    def __init__(self):
        self.d = Path(tempfile.mkdtemp(prefix="regtest-"))
        self.paths = {k: self.d / f for k, f in dict(
            analytics="analytics.json", history="history.json", rules="rules.json", ratings="risk-ratings.json",
            register="risk-register.md", comments="auditor-comments.md", state=".register-state.json").items()}
        self.write("analytics", ANALYTICS)
        self.write("history", HISTORY)
        self.write("rules", RULES)

    def write(self, k, obj):
        self.paths[k].write_text(json.dumps(obj, indent=1))

    def run(self):
        argv = []
        for k, p in self.paths.items():
            argv += [f"--{k}", str(p)]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = br.main(argv)
        return code, out.getvalue(), err.getvalue()

    def text(self, k):
        return self.paths[k].read_text()

    def decide(self, rows):
        """rows: {risk_id: (decision, comment)} written into the comments table."""
        lines = []
        for line in self.text("comments").splitlines():
            m = re.match(r"\| (R-\d+) \|", line)
            if m and m.group(1) in rows:
                cells = br.ROW_SPLIT.split(line)[1:-1]
                cells = [c.strip() for c in cells]
                cells[3], cells[4] = rows[m.group(1)]
                line = "| " + " | ".join(cells) + " |"
            lines.append(line)
        self.paths["comments"].write_text("\n".join(lines) + "\n")


def ratings(*risks, revision=None):
    r = {"risks": [copy.deepcopy(x) for x in risks]}
    if revision:
        r["revision"] = revision
    return r


# ---------------------------------------------------------------- initial build
e = Env()
e.write("ratings", ratings(GOOD, BROKEN))
code, out, err = e.run()
reg = e.text("register")
check(code == 0, f"initial build exits 0 (got {code}) {err}")
check("DROPPED R-02" in out and "no resolvable citation" in out, "broken risk R-02 is dropped for a missing citation")
check("no such key 'nope'" in out, "unresolvable [metric:] on R-02 reported")
check("### R-01" in reg and "### R-02" not in reg, "register rates R-01 only")
check("R-02" in reg.split("## Excluded risks")[1].split("## Auditor decisions")[0], "R-02 listed under Excluded risks")
check("299 flagged groups" in reg, "placeholder filled from analytics.json")
check("£23,514,372" in reg and "ACME" in reg, "gbp format and list-index placeholder filled")
check("[rule:CPR-13 (cl. 6.16)]" in reg, "rule citation resolved to its clause")
check("Base 3 + 1 repeat-finding uplift = 4" in reg and "Limited Assurance" in reg, "uplift stated explicitly with its audit")
check("4 × 3 = **12**" in reg and "**Medium - High (Amber)**" in reg, "score 12 and Table 4 band computed")
check("Matrix label: High" in reg, "matrix label vs Table 4 band mismatch is marked")
check("Figure 4 reading" in reg, "Figure 4 note shown for a 9-14 score")
check("**DIS-04**" in reg and "**DIS-05**" in reg and "Marked" in reg, "conflicts listed in the header")
check(reg.rstrip().splitlines()[-3].startswith("| Risk |") or "## Auditor decisions" in reg.split("## Excluded risks")[1],
      "register ends with Auditor decisions section")
check(reg.index("## Auditor decisions") > reg.index("## Excluded risks"), "Auditor decisions is the last section")
cm = e.text("auditor-comments.md" if False else "comments")
check("| R-01 |" in cm and "R-02" not in cm.split("| Risk | Title")[1], "comments template: one row per rated risk")
check(br.parse_comments(e.paths["comments"])["R-01"] == {"decision": "", "comment": ""}, "Decision and Comment blank")

# typed figure + accusation warnings
t = copy.deepcopy(GOOD)
t["statement"] = "About 300 payments look like fraud [rule:CPR-13]."
e2 = Env()
e2.write("ratings", ratings(t))
code, out, err = e2.run()
check("figure typed in prose: '300'" in out and "accusatory wording 'fraud'" in out, "typed figure and accusatory wording warned")

# uplift must cite an adverse opinion
u = copy.deepcopy(GOOD)
u["likelihood"]["uplift"]["audit_ids"] = ["AUD-01"]
e3 = Env()
e3.write("ratings", ratings(u))
code, out, err = e3.run()
check("DROPPED R-01" in out and "not an adverse opinion" in out, "uplift citing a non-adverse audit drops the risk")

# decisions kept when the comments file is rewritten
e.decide({"R-01": ("APPROVE", "agreed")})
code, out, err = e.run()
check(code == 1 and "revision" in err, "decisions without a revision block are refused")
e.write("ratings", ratings(GOOD, revision={"round": 2, "changes": []}))
code, out, err = e.run()
check(code == 0, f"approve + empty revision block builds v2 (got {code}) {err}")
check("## Revision v2" in e.text("register") and "R-01** APPROVE" in e.text("register"), "revision header names the decision")
check(br.parse_comments(e.paths["comments"])["R-01"]["decision"] == "APPROVE", "decision kept after the file was rewritten")

# ------------------------------------------------------------------ gate cases
def fresh_gate(decisions, new_ratings):
    g = Env()
    g.write("ratings", ratings(GOOD, BROKEN_FIXED))
    assert g.run()[0] == 0
    g.decide(decisions)
    g.write("ratings", new_ratings)
    return g, *g.run()


BROKEN_FIXED = copy.deepcopy(BROKEN)
BROKEN_FIXED["likelihood"]["justification"] = "Spread across suppliers [rule:CPR-60]."
BROKEN_FIXED["impact"]["justification"] = "Large [metric:$.tests.off_contract.counts.flagged_items]."
BROKEN_FIXED["evidence"] = ["{{$.tests.off_contract.counts.flagged_items}} suppliers"]

# 1. REJECT left unapplied
g, code, out, err = fresh_gate({"R-02": ("REJECT", "out of scope")},
                               ratings(GOOD, BROKEN_FIXED, revision={"round": 2, "changes": []}))
check(code == 1 and "REJECT left unapplied" in err, "REJECT left in risk-ratings.json is refused")

# 2. REJECT applied
g, code, out, err = fresh_gate({"R-01": ("APPROVE", ""), "R-02": ("REJECT", "out of scope")},
                               ratings(GOOD, revision={"round": 2, "changes": [
                                   {"risk_id": "R-02", "action": "removed", "reason": "auditor rejected"}]}))
check(code == 0 and "R-02** REJECT: removed" in g.text("register"), f"REJECT applied is built {err}")
check("Removed at the auditor's request: R-02" in g.text("register"), "rejected risk recorded in register")
check("| R-02 |" in g.text("comments") and "REJECT" in g.text("comments"), "rejected row kept in comments")

# 3. unrequested change to an approved risk
changed = copy.deepcopy(GOOD)
changed["impact"]["score"] = 4
g, code, out, err = fresh_gate({"R-01": ("APPROVE", ""), "R-02": ("APPROVE", "")},
                               ratings(changed, BROKEN_FIXED, revision={"round": 2, "changes": []}))
check(code == 1 and "R-01: changed (impact.score)" in err and "did not ask" in err, "change to an APPROVEd risk refused")

# 4. unrequested change to an undecided risk
g, code, out, err = fresh_gate({"R-01": ("APPROVE", "")},
                               ratings(GOOD, {**BROKEN_FIXED, "focus": "Something else."},
                                       revision={"round": 2, "changes": []}))
check(code == 1 and "R-02: changed (focus)" in err, "change to an undecided risk refused")

# 5. REVISE left unapplied, then applied
g, code, out, err = fresh_gate({"R-01": ("REVISE", "lower impact to 2"), "R-02": ("APPROVE", "")},
                               ratings(GOOD, BROKEN_FIXED, revision={"round": 2, "changes": []}))
check(code == 1 and "REVISE left unapplied" in err, "REVISE with no change refused")
revised = copy.deepcopy(GOOD)
revised["impact"]["score"] = 2
g.write("ratings", ratings(revised, BROKEN_FIXED, revision={"round": 2, "changes": [
    {"risk_id": "R-01", "action": "revised", "fields": ["impact.score"], "reason": "auditor asked"}]}))
code, out, err = g.run()
reg = g.text("register")
check(code == 0 and "`impact.score` 3 → 2" in reg and "auditor asked" in reg, f"REVISE applied; header names the change {err}")

# 6. OVERRIDE applied by the builder and marked
g, code, out, err = fresh_gate({"R-01": ("OVERRIDE", "likelihood=5 impact=4"), "R-02": ("APPROVE", "")},
                               ratings(GOOD, BROKEN_FIXED, revision={"round": 2, "changes": []}))
reg = g.text("register")
check(code == 0 and "AUDITOR OVERRIDE" in reg and "= **20**" in reg and "Extreme (Red)" in reg, f"OVERRIDE applied and marked {err}")
check("The agent proposed score 12" in reg, "agent's own score kept beside the override")

# 7. OVERRIDE without a value is refused
g = Env()
g.write("ratings", ratings(GOOD))
g.run()
g.decide({"R-01": ("OVERRIDE", "I disagree")})
g.write("ratings", ratings(GOOD, revision={"round": 2, "changes": []}))
code, out, err = g.run()
check(code == 1 and "OVERRIDE needs" in err, "OVERRIDE without likelihood=/impact= refused")

# 8. a refused run writes nothing new
before = g.text("register")
check("v2" not in before, "refused run leaves the previous register untouched")

# 9. a risk dropped after the gate is not silently lost
g, code, out, err = fresh_gate({"R-01": ("APPROVE", ""), "R-02": ("APPROVE", "")},
                               ratings(GOOD, BROKEN, revision={"round": 2, "changes": []}))
check(code == 1 and "R-02: removed from the register but the auditor did not reject it" in err, "post-gate drop refused")

print()
print("ALL PASS" if not failures else f"{len(failures)} FAILED")
sys.exit(1 if failures else 0)
