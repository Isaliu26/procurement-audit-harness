---
name: extract-rules
description: Convert data/contract-rules.pdf (West Berkshire Council Contract Rules) into outputs/rules.json - one entry per testable rule with clause, page, thresholds as printed and a verbatim quote, every other clause excluded with a reason, then verify it with verify_quotes.py. Run only when the human invokes /extract-rules.
---

# extract-rules

Turn the council's Contract Rules PDF into `outputs/rules.json`: the criteria the
rest of the audit tests against. You read and judge; you never invent. Every
value must be printed in the PDF, and every rule carries a quote that
`verify_quotes.py` finds on the stated page.

## 0. Preconditions: stop and report if any fail

- `data/contract-rules.pdf` exists. Do not modify anything in `data/`.
- `pdftotext` and `pdfinfo` are on PATH (poppler).
- If `outputs/rules.json` already exists, say so and ask before overwriting it.

## 1. Read the whole document

```bash
D=$(mktemp -d)
pdfinfo data/contract-rules.pdf | grep Pages
for p in $(seq 1 "$(pdfinfo data/contract-rules.pdf | awk '/^Pages/{print $2}')"); do
  pdftotext -f $p -l $p        data/contract-rules.pdf "$D/p$p.txt"
  pdftotext -f $p -l $p -layout data/contract-rules.pdf "$D/p$p.layout.txt"
done
.venv/bin/python .claude/skills/extract-rules/verify_quotes.py --inventory
```

Read every page in both modes before you write anything. The `--inventory` list is
the exact set of clause ids you must classify, with the page each starts on.

- **Layout mode** shows the structure: clause numbers, table rows and columns.
- **Plain mode** keeps each table cell's text together. Copy quotes from plain
  mode; in layout mode, table columns interleave line by line.

### Structure of this document

| Part | Pages | Content | Clause ids |
| --- | --- | --- | --- |
| Sections 1–11 | 1–10 | Numbered clauses and sub-clauses (e.g. `4.3`, `7.4.2`, `10.7.9.1`). Unnumbered sub-headings ("Preliminaries", "Advertising", ...) are not clauses | as printed |
| Appendix A | 11 | Delegated authority to award: four unlabelled value bands, each with its decision maker | `AppA-1` … `AppA-4`, top to bottom |
| Appendix B | 12–13 | Value bands and mandatory award/advertising processes: rows A, B1, B2, C, D. Then footnotes marked `*`, `**`, `***`, `****` | `AppB-A` … `AppB-D`; `AppB-note-1` … `AppB-note-4` (by number of stars) |
| Appendix C | 14–15 | Circumstances excluded from competition, rows A–F, each with the record/approval required. Then a closing sentence ("In the interests of clarity …") | `AppC-A` … `AppC-F`; `AppC-closing` |

Section numbers (`1`…`11`) and `AppA`/`AppB`/`AppC` are valid ids too. Use them
only to exclude a whole heading or as `defined_in`. They never need an entry of
their own.

## 2. Classify every clause

Every inventory id must be covered, either by a rule or by an exclusion. An entry
for a parent clause covers its children (excluding `8.1` covers `8.1.1`–`8.1.7`).
A clause must never be in both lists.

**Testable rule.** An auditor could check compliance on a sample of procurements,
contracts or payments and get a pass or fail. The clause states at least one of:
- a value threshold that changes what is required,
- a mandatory action ("must", "shall", "is required"),
- a named approver or decision maker.

Make **one entry per distinct testable requirement**. A clause or table row that
imposes two requirements gets two rules with the same `clause`. For example, an
Appendix B row has both an award procedure and an advertising requirement.

**Excluded.** Give a one-line reason (at most 160 characters). Typical reasons:
- definition or interpretation,
- purpose or background,
- a heading with no requirement,
- non-mandatory guidance ("should consider", "may", "advice should be sought"),
- a list stem whose items are entered separately,
- outside procurement audit scope (e.g. custody of the Seal),
- no observable evidence,
- ambiguous, with the specific ambiguity named.

If you cannot tell what a clause requires, exclude it as ambiguous. **Never guess.**

## 3. Fill each rule

| Field | Content |
| --- | --- |
| `rule_id` | `CPR-01`, `CPR-02`, … sequential with no gaps, in document order |
| `clause` | inventory id, e.g. `"7.4.2"`, `"AppB-B1"` |
| `page` | PDF page where the quote starts; `page_end` (optional) if it runs onto later pages |
| `type` | one of `procurement-route` (quotes/tenders by value), `approval`, `anti-avoidance`, `advertising`, `exception` (waivers), `exclusion` (Appendix C circumstances), `evaluation`, `documentation`, `contract-terms`, `transparency` |
| `scope` | what the rule applies to, in the PDF's terms (e.g. "Goods and Services", "Works, Concession contracts and Light Touch contracts", "all contracts") |
| `condition` | when the rule bites, in one short line |
| `threshold_low` / `threshold_high` | GBP integers as printed; `null` if that side is open |
| `threshold_low_param` / `threshold_high_param` | parameter key when the PDF only *names* the bound (see §4); else `null` |
| `threshold_low_inclusive` / `threshold_high_inclusive` | `true`/`false` when that bound is set; `null` when open |
| `threshold_low_text` / `threshold_high_text` | the bound exactly as printed, a substring of the quote (e.g. `"less than £25,000"`); `null` when open |
| `required_action` | what must be done |
| `approver` | who approves or decides, as printed; `null` if none named |
| `evidence_source` | non-empty list from `spend_data` (testable on the payment data), `contracts_register` (testable on contracts.csv), `council_records` (needs documents from the council) |
| `verbatim_quote` | exact text from the stated page (see §5) |

The anti-splitting / anti-aggregation rule gets `"type": "anti-avoidance"`. At
least one rule must have this type.

### Reading thresholds as printed

| Printed | Bound | Inclusive |
| --- | --- | --- |
| "Above £X", "more than £X", "over £X", "exceeding £X", "in excess of £X" | low = X | false |
| "£X or more", "at least £X" | low = X | true |
| "less than £X", "below £X" | high = X | false |
| "up to £X" | high = X | true |
| "£2.5million" | 2500000 | — |

- Amounts are whole pounds.
- If the PDF prints pence, convert to the exactly equivalent whole-pound bound,
  keep the printed form in `*_text`, and add a `notes` entry. For example,
  "more than £24,999.99" becomes low = 25000, inclusive = true.
- Never round in any other way.
- Do not reconcile adjacent bands. Record each band exactly as printed, and
  report gaps or overlaps between bands in `notes`.

## 4. Named-only thresholds → `parameters`

The PDF often says "the Threshold" or "the relevant Threshold" without a £ figure.
Clause 1.4 and footnote `***` say the values live in procurement legislation and on
the intranet.

**Never fill these in from memory or from the internet.** Declare each one in the
top-level `parameters` object with `"value": null` and reference it from the rule's
`*_param` field. Use these keys:

| Key | Use when the clause refers to the Threshold for |
| --- | --- |
| `THRESHOLD_GOODS_SERVICES` | Goods & Services specifically |
| `THRESHOLD_WORKS_CONCESSIONS` | Works and/or Concession contracts specifically |
| `THRESHOLD_LIGHT_TOUCH` | Light Touch contracts specifically |
| `THRESHOLD_RELEVANT` | "the (relevant) Threshold" without saying which, or several contract types at once |

Declare only the keys the rules use. Each parameter entry contains:
- `value`: `null`,
- `printed_as`: the wording on the page,
- `defined_in`: a clause id, e.g. `"1.4"` or `"AppB-note-3"`,
- `page`,
- optionally `applies_to`.

## 5. Verbatim quotes

- Copy from the **plain-mode** text of the stated page. Keep every word,
  capital, symbol and footnote star exactly (e.g. `supplier ****(where appropriate`).
- The verifier forgives only differences in whitespace, curly versus straight
  quotes, dashes, bullet glyphs and line-end hyphens.
- Quote enough to show the condition, the action and the approver, and no more.
- **No ellipses and no paraphrase.** Where the text is split across table cells,
  quote each cell's text separately joined by ` | ` (space, pipe, space). For
  example: `"£25,000 or more | Invitations to quote must be sent via the Procurement Portal to at least three appropriate sources"`.
  Each fragment must be at least 10 characters and on the stated pages.
- Every `*_text` must appear inside the rule's quote.

## 6. Notes: contradictions and drafting gaps

Record problems in the PDF itself, without fixing them. Each note is
`{"kind": "contradiction" | "drafting_gap" | "ambiguity", "clauses": [...], "page": N, "note": "...", "verbatim_quote": "..." (optional)}`.
### Required notes

These problems are known to be in this version of the PDF, and the verifier fails
if any is missing. Re-read each one in the text, describe it in your own words,
and give a `verbatim_quote` where the text can be quoted.

| Problem | `kind` | `clauses` must include | Page |
| --- | --- | --- | --- |
| Exactly £500,000 is in neither Appendix B row B2 ("less than £500,000") nor row C ("Above £500,000") | `drafting_gap` | `AppB-B2`, `AppB-C` | 12 |
| Numbering jumps from 5.1.1 to 5.2 to 5.2.1 (5.2 reads as a further list item under 5.1) | `drafting_gap` | `5.2` | 3 |
| Blank placeholders "Parts [] (Call-In) and [] (Forward Plan)" in Appendix A | `drafting_gap` | `AppA-3` | 11 |
| Blank placeholder "Part []" in the document title (use clause `1`, the first section) | `drafting_gap` | `1` | 1 |
| 7.4.2 is garbled ("… Executive Director provided and an exception report has been approved …"); the condition it sets is unclear | `ambiguity` | `7.4.2` | 6 |

Add any further problems you find. For example, 6.23 is numbered like a clause
but is only a heading.

### What else to look for

- adjacent value bands that overlap, or that leave a value covered by neither band,
- two clauses that name different approvers or thresholds for the same case,
- blank placeholders (e.g. "Part []"), numbering errors, cross-references to
  missing text, and garbled sentences,
- "should" in one place and "must" in another for the same requirement,
- thresholds the rules depend on but never state (also declared in `parameters`).

## 7. Write and verify

Write `outputs/rules.json` (UTF-8, 2-space indent):

```json
{
  "source": {"file": "data/contract-rules.pdf", "pages": 15, "sha256": "<shasum -a 256 of the PDF>"},
  "parameters": {
    "THRESHOLD_GOODS_SERVICES": {"value": null, "printed_as": "Threshold", "defined_in": "1.4", "page": 1,
                                 "applies_to": "Goods & Services"}
  },
  "rules": [
    {
      "rule_id": "CPR-01",
      "clause": "AppB-B1",
      "page": 12,
      "type": "procurement-route",
      "scope": "Goods and Services",
      "condition": "goods/services contract of £25,000 or more and below the Threshold",
      "threshold_low": 25000, "threshold_low_param": null,
      "threshold_low_inclusive": true, "threshold_low_text": "£25,000 or more",
      "threshold_high": null, "threshold_high_param": "THRESHOLD_GOODS_SERVICES",
      "threshold_high_inclusive": false, "threshold_high_text": "less than the Threshold",
      "required_action": "send invitations to quote via the Procurement Portal to at least three appropriate sources",
      "approver": null,
      "evidence_source": ["spend_data", "council_records"],
      "verbatim_quote": "£25,000 or more and less than the Threshold | Invitations to quote must be sent via the Procurement Portal to at least three appropriate sources"
    }
  ],
  "excluded": [
    {"clause": "2", "page": 2, "reason": "Purpose of the Rules: background, no requirement"},
    {"clauses": ["11.6", "11.7"], "page": 9, "reason": "Custody and use of the Seal: outside procurement audit scope"}
  ],
  "notes": []
}
```

(The example shows the shape only. Derive every entry from the PDF.)

Then run the verifier and fix every ERROR until it prints `PASS`:

```bash
.venv/bin/python .claude/skills/extract-rules/verify_quotes.py outputs/rules.json data/contract-rules.pdf
```

The verifier checks:
- the schema,
- sequential rule IDs,
- that referenced parameters are declared and null,
- that every quote fragment is on its stated pages,
- that each page lies within its clause's pages,
- that every `*_text` is inside its quote,
- that every inventory clause is covered exactly once,
- that the required notes in §6 are present.

Read every WARN as well. Either fix it, or explain in your report why it is acceptable.

## 8. Report to the human (under 200 words)

- the verifier result,
- rules by type, the number of excluded entries, and the parameters declared,
- each note in one line,
- anything you excluded as ambiguous that the auditor should decide.

Do not paste the JSON.
