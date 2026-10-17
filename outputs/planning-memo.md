# Planning memo: procurement audit, West Berkshire Council

**Pack version:** built from register v2. **Built from:** analytics (sha256 250f46389dfa) history (sha256 9137ff368907) rules (sha256 a19fb7385362) ratings (sha256 7201819f2a5d) plan (sha256 abfe27bedda5).

These are risk indicators to investigate, drawn from published data. They are not findings of wrongdoing by the council, any department or any supplier.

## Objective

Test 7 approved risk indicators in procurement spend, covering the quote, tender, approval and contract-notice rules [rule:CPR-13 (cl. 6.16)] [rule:CPR-60 (cl. AppB-B1)].

## Scope: risks approved by the auditor

7 risks are in scope. Ratings use the council's own scoring method as recorded in the register (register v2); a ⚑ marks an auditor override.

| Risk | Title | Rating | Auditor decision | Tests | Sample |
|---|---|---|---|---|---|
| R-01 | Same-supplier payments combining past the quote threshold | 20 Extreme (Red) | APPROVE | T-01 | T-01: 25 items, 554 transactions |
| R-04 | Spend with suppliers having no council contract notice | 20 Extreme (Red) | APPROVE | T-04 | T-04: 25 items, 456 transactions |
| R-02 | Low-value payments clustering and combining at the lowest quote boundary | 15 Extreme (Red) | APPROVE | T-02 | T-02: 15 items, 201 transactions |
| R-03 | Combined payments approaching the high-value approval and tender tier | 15 Extreme (Red) | APPROVE | T-03 | T-03: 7 items, 139 transactions |
| R-06 | Spend running above the awarded contract value | 15 Extreme (Red) | APPROVE | T-06 | T-06: 7 items, 30 transactions |
| R-05 | Payments after the only matching notice has ended | 12 Medium - High (Amber) ⚑ | OVERRIDE | T-05 | T-05: 8 items, 60 transactions |
| R-07 | Possible duplicate payments | 8 Medium - High (Amber) | APPROVE | T-07 | T-07: 5 items, 16 transactions |

- ⚑ **R-05** auditor override: likelihood 3 → 4, impact 3 → 3. Auditor comment: likelihood=4. Paying suppliers after their only notice has ended points to contracts rolling on without re-procurement, which is common in practice.
- **R-07** auditor comment: Keep likelihood at 2: no Contract Procedure Rule covers duplicates, and many identical rows may be export artefacts.

## Out of scope

- **R-08** Care and education placement spend without a published notice: rejected by the auditor. Care placements recur by design and will be covered by a separate social care commissioning review.
- The rejected care and education placement risk was rejected by the auditor and is not planned.

## Approach

Targeted samples are drawn from the flagged lists, sized by each risk's final score, and each sampled group is expanded to its transactions. Care placements and grants are filtered out of rule tests as they follow other routes.

## Sampling

Samples are targeted at the flagged items in `outputs/analytics-full/`, drawn by `build_pack.py` (the same inputs always give the same sample), and every sampled transaction is checked against the cleaned spend data. The number of items drawn scales with the risk's final score (score 20 or more: 25, score 15 or more: 15, score 10 or more: 10, below 10: 5), so the highest-rated risks are examined most.

In total 92 items are drawn across 7 sampled tests, covering 1,456 transactions worth £26,739,773 as published. Samples are chosen to target risk indicators, not to estimate error rates, and cannot be extrapolated to the whole population.

## Limitations

- Spend dates are payment-run timestamps, not invoice or transaction dates; the 30-day and 7-day windows are measured on payment-run dates.
- Rows with supplier 'Redacted' cannot be tested by supplier; they are excluded and reported by Expenditure category and tag.
- Only 3 months of data, so the x4 annualisation is an estimate (annualised estimate).
- The Contracts Finder notice export holds only contracts above about 25,000 GBP; absence of a notice for a smaller supplier is expected and is never a finding.
- Tags are a heuristic on published fields (Narrative, Expenditure category, Service, supplier text), not a classification of the underlying contract.
- Supplier matching between spend and notices is by normalised name only; the spend data carries no Companies House number. Candidates are never counted as matches.
- The spend data has no transaction id; identical rows are kept and treated as possible duplicates, never confirmed ones.
- Redacted-supplier, pension/statutory, internal and other public-body rows are outside the supplier tests; public-body review list and exclusion pairs are provided for the auditor to confirm.
- Boundary treatment follows the PDF wording as stored in rules.json: the 500,000 GBP boundary is exclusive on both sides (CPR-62 high, CPR-64 low), so a payment or total of exactly 500,000 does not reach that tier and is not flagged by the 500,000 tests.
- The 1,000 GBP lower bound is stored as exclusive (CPR-59), so a total must exceed 1,000 to reach that tier; amounts of exactly 1,000 are not treated as reaching it.
- Auditor decisions pending, nothing excluded: public_body_review.csv (101 names) and exclusion_pairs.csv (5 pairs) remain in the analysed population for the auditor to review.
- Sampled groups are chosen by the group's tag, so expanded transactions may include rows tagged as care placements or grants; the tag column on each sample row marks them as context only for the rule test.
- The award-ratio test could assess only 18 suppliers; 9 with several active notices, 10 on multi-supplier notices and 1 with no award value were skipped and are untested [metric:$.tests.spend_vs_award.counts.skipped_with_reason].
- Off-contract suppliers beyond the sampled items are not tested; the full list is in outputs/analytics-full/off_contract.csv.

## Rule coverage

73 rules are in `rules.json`: 14 are cited by an approved risk, control or test and 59 are listed as not tested, each with a reason (see the risk-control matrix).

## Next step

The pack goes to the challenger and the QA review, then to the auditor for sign-off (`outputs/review.md`).
