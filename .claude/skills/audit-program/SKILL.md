---
name: audit-program
description: Method for the planner agent. After the auditor has decided every register risk, write the planner's judgments (controls, test steps, sample recipes, PBC items) to outputs/audit-plan.json and run build_pack.py, which checks the gate, resolves citations, draws and verifies the samples, and renders planning-memo.md, risk-control-matrix.md and audit-program.md. Load when planning the audit of approved risks or rebuilding the pack after a challenge or QA failure.
---

# audit-program

You judge; the script computes. You write **judgments and citations** to
`outputs/audit-plan.json`. `build_pack.py` (next to this file) does everything
numeric: it works out the approved scope and each risk's final score from
`auditor-comments.md` and `risk-ratings.json`, sizes and draws every sample, checks
every sampled transaction against the cleaned spend data, and renders the three
documents and `pack-figures.json`. You never type a figure, a score or a sample size,
and you never edit the rendered files.

Output language is **risk indicators to investigate**, never wrongdoing by the council,
a department or a supplier (the builder refuses accusatory words).

## 0. Gate and preconditions

```bash
.venv/bin/python .claude/skills/audit-program/build_pack.py --gate
```

Exit 0 prints the approved scope (APPROVE and OVERRIDE risks, with final score and band).
Exit 1 means stop and report, do not plan: a register risk is undecided, a REVISE or REJECT
has not been applied, the register is still v1 (no revision after the auditor's decisions),
or `auditor-comments.md` changed after the register was built. The fix is the auditor
completing `auditor-comments.md` and the risk-assessor being re-run.

Also needed: `outputs/{rules,analytics,history,risk-ratings}.json`, `outputs/analytics-full/`
and the cleaned spend file `outputs/analytics-full/cleaned_spend.csv` (override with
`--spend`). Inspect inputs with aggregates only:
`head -3` of each analytics-full file, `jq` on keys and counts. Never dump a full file.

## 1. Plan only the approved risks

One entry per approved risk, none for rejected ones. For each risk work out, from the rules
and the analytics test behind it:

1. **Expected controls**: what the council should have in place for the rule to be met.
   Each control description cites at least one `[rule:ID]` that exists in `rules.json`.
2. **Tests**: how an auditor would check each control. Each test lists the controls it
   exercises, and every control is exercised by at least one test.
3. **A sample recipe** per test, drawn from the flagged lists in `outputs/analytics-full/`.
4. **PBC items**: the documents the auditor must request to carry out the test.

Look at rules by `evidence_source`: a rule evidenced only by `council_records` needs a
test and a PBC request, not a spend-data sample (use `"sample": null` with a reason).

## 2. Write `outputs/audit-plan.json`

```json
{
  "register_version": 2,
  "memo": {
    "objective": "Test {{$pack.risks_in_scope}} approved risk indicators ... [rule:CPR-13]",
    "approach": "Targeted samples from the flagged lists, sized by score ...",
    "points": ["Optional points for the auditor, with {{$.path}} figures."],
    "exclusions": ["Optional: why a theme is outside this pack, with a citation."],
    "limitations": ["Optional extra limits; analytics.json limitations are copied in automatically."]
  },
  "risks": [
    {
      "risk_id": "R-01",
      "controls": [
        {"id": "C-01",
         "description": "A requirement above the quote threshold is quoted for [rule:CPR-60] and not split [rule:CPR-13]."}
      ],
      "tests": [
        {"id": "T-01",
         "control_ids": ["C-01"],
         "objective": "Check whether the grouped payments relate to one underlying requirement.",
         "step": "For each sampled group compare orders, invoices and quotes [metric:$.tests.split_purchases@25000.counts.flagged_items].",
         "sample": {
           "file": "split_purchases.csv",
           "filter": [{"col": "tier", "op": "==", "value": 25000},
                      {"col": "tag", "op": "==", "value": "general_procurement"}],
           "sort": [{"col": "combined_gbp", "desc": true}],
           "n": "by_score"
         },
         "pbc": ["Purchase orders, invoices and any quotes for the sampled suppliers"]}
      ]
    }
  ],
  "not_tested": [
    {"rule_ids": ["CPR-01", "CPR-02"], "reason": "Documentation requirement: no evidence in spend data or notices."}
  ]
}
```

- `register_version` must equal the current register version (the gate prints it).
- Ids: controls `C-nn`, tests `T-nn`, unique across the whole plan. PBC items are numbered
  by the builder; the same request text in two tests becomes one PBC item.
- **Citations** (same three kinds as the register, all resolved): `[rule:ID]`,
  `[metric:$.path]` (analytics.json), `[history:ID]`. A control needs a `[rule:]`. A test
  step (or objective) needs a `[rule:]` or `[metric:]`. An unresolved citation anywhere is
  an error, not a warning.
- **Figures are placeholders only**: `{{$.tests.x.counts.y}}` for analytics values (formats
  `|gbp`, `|gbp2`, `|pct`, `|int`, `|ratio`, `|raw`), `{{$pack.<key>}}` for values the
  builder computes (see `pack-figures.json` after a build: `risks_in_scope`,
  `samples_transactions`, `tests.T-01.population_items`, ...). A digit typed in prose
  (other than ids such as CPR-13, T-01) is an error.
- **`not_tested`**: every rule in `rules.json` must be cited by an approved risk, a control
  or a test, or appear here with a reason (group rules that share a reason). A rule cited and
  also listed as not tested is an error.
- Test with no transaction sample: `"sample": null, "no_sample_reason": "..."`.

### Sample recipe

| Field | Meaning |
|---|---|
| `file` | a CSV in `outputs/analytics-full/` with a `row_ids` (groups) or `row_id` (payments) column |
| `filter` | list of `{col, op, value}`; ops `== != > >= < <= in notin contains isnull notnull` |
| `sort` | list of `{col, desc}`; stable, so ties keep file order |
| `n` | `"by_score"` (default) or an integer no larger than the score allows, with `n_reason` |
| `method` | `"top"` (default: first N after sort) or `"random"` (seeded by test id and `seed`) |
| `max_rows_per_item` | cap on transactions listed per group (default 50) |

**Sample size is set by the risk's final score** (auditor override applied): score 20+ →
25 items, 15-19 → 15, 10-14 → 10, below 10 → 5 (capped at the qualifying population).
Prefer `top` on the metric that makes the indicator strongest (combined £, ratio); use
`random` only for a population where no ordering is meaningful. Group files (split,
duplicates, off-contract) are sampled by group; each group is expanded to its transactions.
Exempt tags (care placements, grants) follow other routes: filter them out of procurement
rule tests unless the test is about them, and say so in the objective.

## 3. Build

```bash
.venv/bin/python .claude/skills/audit-program/build_pack.py
```

On success it writes `outputs/samples/<test>.csv` (one row per transaction, taken from the
cleaned spend file), `planning-memo.md`, `risk-control-matrix.md`, `audit-program.md`
(ending with the PBC list) and `pack-figures.json` (every figure the builder computed, for
the QA number check). Output is deterministic: the same inputs give identical files.

Exit 0 built. Exit 1 refused, **nothing written**; every problem is listed:
gate failure, approved risk missing from the plan, plan for a non-approved risk, uncited
control, uncited test, control with no test, unaccounted rule, unresolved citation or
placeholder, figure typed in prose, empty or oversized sample, a sampled transaction not
in the spend data. Fix `audit-plan.json` and re-run until it exits 0. Exit 2: an input
is missing.

## 4. Rebuilding

After a challenge or a QA failure, edit `audit-plan.json` and re-run. Never edit the
rendered files or `pack-figures.json`. A sample or rating that looks wrong is a recipe or
register question: change the recipe, or report it; do not work around the builder.

## Tests

`.venv/bin/python .claude/skills/audit-program/test_build_pack.py` builds a two-risk
fixture through `build_register.py` (v1, then v2) and checks the gate, a valid pack,
determinism, and refusals for a missing risk, an uncited control, an unaccounted rule and
the other plan errors. Run it after any change to the builder.
