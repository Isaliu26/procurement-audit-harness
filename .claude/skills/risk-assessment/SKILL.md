---
name: risk-assessment
description: Method for the risk-assessor agent. Merge rules.json, analytics.json and history.json into outputs/risk-register.md by writing judgments to outputs/risk-ratings.json (cited, with {{$.path}} placeholders for every figure) and running build_register.py, which resolves citations, fills figures, computes the council's score and band, and enforces the auditor gate. Load when rating risks or revising the register after the auditor's decisions.
---

# risk-assessment

You judge; the script computes. You write **judgments and citations** to
`outputs/risk-ratings.json`. `build_register.py` (next to this file) does everything
numeric: it fills figures, computes score, matrix label and band from the council's
own method in `history.json`, and renders `outputs/risk-register.md` and
`outputs/auditor-comments.md`. You never type a figure, never multiply likelihood by
impact, never pick a band.

Output language is **indicators to investigate**, never wrongdoing by the council, a
department or a supplier. Avoid fraud, corruption, misconduct, illegal, unlawful
(the builder warns on them).

## 0. Preconditions: stop and report if any fail

- `outputs/rules.json`, `outputs/analytics.json`, `outputs/history.json` exist.
- `history.json` → `scoring_method.usable` is read by the builder. If false it falls
  back to a 1-5 Very low…Very high scale and says so in the register header. Do not
  invent a method yourself.
- Inspect the inputs with aggregates only (`jq 'keys'`, counts, `.head()`), never dump
  whole files into context. List the paths you can cite:
  `jq -r '.tests|keys[]' outputs/analytics.json`; ids in `history.json`
  (`AUD-*` audits, `FUP-*` follow-ups, `RT-*` risk themes, `GAP-*`, `PLN-*`).

## 1. Choose the risks

One risk per theme the evidence supports, typically 5-10. Every risk needs a rule
(what the council requires), a data signal (analytics metric) and, where it exists,
a history item. A risk with no evidence is not a risk; leave it out.

Draw only on what analytics already measured. Respect its limitations
(`$.limitations`): spend dates are payment-run timestamps; Contracts Finder holds
only contracts above about the notice threshold; 3-month figures are annualised
estimates; care and grant spend is tagged and may follow other routes.

## 2. Write `outputs/risk-ratings.json`

The example shows the shape only. Its scores are illustrative, not a finding; rate your own
risks from the rubric in section 3.

```json
{
  "risks": [
    {
      "id": "R-01",
      "title": "Payments split to stay under the quote threshold",
      "theme": "splitting",
      "statement": "Same-supplier payments may be split so each stays under the threshold [rule:CPR-13].",
      "likelihood": {
        "base_score": 4,
        "rubric": "L4",
        "justification": "{{$.tests.split_purchases@25000.counts.flagged_items}} flagged groups [metric:$.tests.split_purchases@25000.counts.flagged_items] against [rule:CPR-13].",
        "uplift": {"applied": true, "audit_ids": ["AUD-12"],
                   "reason": "Prior limited-assurance audit on payment controls [history:AUD-12]."}
      },
      "impact": {
        "score": 5,
        "justification": "Combined {{$.tests.split_purchases@25000.totals_gbp.combined|gbp}} [metric:$.tests.split_purchases@25000.totals_gbp.combined]."
      },
      "evidence": ["Top group: {{$.tests.split_purchases@25000.top20.0.supplier}} [metric:$.tests.split_purchases@25000.top20]"],
      "focus": "Test the flagged groups for a single underlying requirement."
    }
  ]
}
```

### Citations: three kinds, all resolved by the builder

| Tag | Resolves against | Example |
|---|---|---|
| `[rule:ID]` | `rules.json` → `rules[].rule_id` | `[rule:CPR-13]` |
| `[metric:$.path]` | `analytics.json` by dotted path (list items by index: `.top20.0`) | `[metric:$.tests.off_contract.counts.flagged_items]` |
| `[history:ID]` | any `id` in `history.json` | `[history:AUD-12]`, `[history:RT-01]` |

Metric keys can contain `@` (`split_purchases@25000`); that is fine. Keys with spaces
cannot be used in a placeholder; cite the parent container instead.

**Hard rule:** the `likelihood.justification` and the `impact.justification` each need
at least one citation that resolves. Otherwise the builder **drops the risk** and lists
it under "Excluded risks". An unresolvable placeholder anywhere in a risk also drops it.
An unresolvable citation next to a good one is kept but shown as `⚠ UNRESOLVED` and warned.

### Figures: placeholders only

Every number in prose is `{{$.path}}`, optionally `|gbp`, `|gbp2`, `|pct` (for 0-1
ratios), `|int`, `|ratio`, `|raw`. Default: integers with commas, floats to 2 places.
A digit left in prose (other than ids such as CPR-13 or L3) triggers a "figure typed in
prose" warning. A placeholder must point at a value, not a list or object.

### Repeat-finding uplift

If audit history shows a **repeat or related finding on the same theme**, set
`likelihood.uplift.applied` true. The builder adds one point (cap 5) and states
"Base N + 1 repeat-finding uplift = M" in the register. `audit_ids` must be `AUD-*` or
`FUP-*` items whose opinion is adverse (Limited Assurance, No Assurance, Weak,
Unsatisfactory); anything else drops the risk. A Reasonable or Substantial opinion is
**not** a repeat finding. Only uplift when the audited area really is the same theme;
say why in `reason`.

## 3. Likelihood rubric (use it exactly; two runs on the same evidence must agree)

The council's likelihood labels (Rare 1…Certain 5) describe occurrence in 12 months.
Our evidence is an indicator count, not a probability, so the council's percentage
bands are **not** used (they have gaps, DIS-03). Rate by the evidence below, using the
`base_score` and matching `rubric` code. Take the **highest level whose conditions are
all met**. Counts come from `counts.flagged_items` of the relevant test unless stated.
"Outside exempt tags" means excluding `by_tag` grant and care_or_education_placement.

| Level | Code | Conditions |
|---|---|---|
| 1 Rare | `L1` | The relevant test ran and flagged **0** items, and history shows no related finding. |
| 2 Unlikely | `L2` | Flagged items exist but (a) all or nearly all sit in the exempt tags, or (b) fewer than 5 outside them, or (c) the test only flags context (lower band) not breaches of a stated rule. |
| 3 Likely | `L3` | 5 to 19 flagged items outside the exempt tags, **or** a test with stated limitations flags at least 20 items and a rule (`[rule:]`) is directly engaged. |
| 4 Almost Certain | `L4` | 20 or more flagged items outside the exempt tags, **and** a rule is directly engaged, **and** the flagged £ total is at least the tier value of that rule. |
| 5 Certain | `L5` | L4 is met on **two independent tests** for the same theme (for example split_purchases and threshold_clustering at the same tier). |

Rules of use:
- A theme with no test behind it (policy or documentation rules only) cannot exceed
  L2 on data; say "no analytics test; rated on history" and cite a `[history:]` item.
- Apply the uplift **after** choosing `base_score`; never fold it into the base.
- Never rate on one supplier or one payment. Counts of items, not anecdotes.
- If two levels both seem to fit, take the lower and explain in the justification.

## 4. Impact guide

Use the council's Table 1 **printed £ bands** (the percentage ranges overlap, DIS-02):
under £17.5k = 1 Negligible; £17.5k-£175k = 2 Minor; £175k-£500k = 3 Medium;
£500k-£2m = 4 Major; over £2m = 5 Critical. An exposure of exactly £500k is level 4.
The exposure is a named analytics £ metric (for example `totals_gbp`), not a guess;
cite it. Impact 3 is **Medium = 3** (para 4.3 prints "(2)", also DIS-01). Where
non-financial impact (service, reputation, compliance) drives the rating, cite the
rule or history item behind it and say so. Annualised estimates are estimates; say
"annualised estimate".

## 5. Build

```bash
.venv/bin/python .claude/skills/risk-assessment/build_register.py
```

It reads `outputs/{analytics,history,rules,risk-ratings}.json` and writes
`outputs/risk-register.md`, `outputs/auditor-comments.md` and the hidden state file
`outputs/.register-state.json` (what the gate compares against; never edit it).

- Exit 0: built. Read the `DROPPED` and `WARN` lines and fix them in
  `risk-ratings.json`, then re-run. Do not hand-edit `risk-register.md`.
- Exit 1: refused, nothing written (a rating-file error or a failed revision check).
- Exit 2: an input is missing or the scoring method is unusable.

The register states every conflict inside the council's scoring method (which
reading is used, which is marked) in its header. The builder owns that; do not
resolve them differently in your prose.

## 6. After the auditor gate (revision)

The auditor fills `outputs/auditor-comments.md`, one Decision per risk:

| Decision | What you do |
|---|---|
| APPROVE | Leave the risk exactly as it is. |
| REJECT | Delete the risk from `risk-ratings.json`; record it in `revision.changes` (`action: "removed"`). |
| REVISE | Change the risk as the Comment asks, nothing more; record it (`action: "revised"`, the `fields` changed, a `reason`). |
| OVERRIDE | Do nothing. The builder applies the auditor's `likelihood=N`/`impact=N`, marks it ⚑ and keeps your score beside it. |

Then add a `revision` block (even when nothing changed) and re-run the builder:

```json
"revision": {"round": 2, "changes": [
  {"risk_id": "R-01", "action": "revised", "fields": ["impact.score"], "reason": "auditor asked for impact 2"}
]}
```

`round` must be the new version (the previous register's version plus one). A new risk
is only allowed when an auditor comment asked for it: `"action": "added"` with
`"auditor_ref": "<risk id of the comment>"`.

The builder **refuses** (exit 1, nothing written) when a decision was left unapplied
(REJECT still present, REVISE with no change), when anything changed that no decision
asked for (including a risk silently dropped), when a rejected risk reappears, or when
`round` is wrong. On success the register opens with "Revision vN: what changed",
naming each decision, the fields changed and the reasons. Remove the `revision` block
once the auditor has no new decisions; a stale one is refused.

## 7. Report back (main agent relays it)

Under 200 words: risks rated with score and band (as printed in the register), risks
dropped and why, warnings, the conflicts the header marks, and the request that the
auditor complete `outputs/auditor-comments.md`. Never state a figure you did not read
from the register or the builder output.

## Tests

`.venv/bin/python .claude/skills/risk-assessment/test_build_register.py` runs a fixture
with one good and one broken risk, and every gate case (decisions kept, REJECT, REVISE,
OVERRIDE, unrequested changes). Run it after any change to the builder.
