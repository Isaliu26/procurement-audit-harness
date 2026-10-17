# Risk Register: West Berkshire Council procurement audit planning

**Version:** v2 (revision after auditor gate)
**Built from:** analytics.json (generated 2026-10-11T01:40:05+00:00, sha256 250f46389dfa), history.json (sha256 9137ff368907), rules.json (sha256 a19fb7385362), risk-ratings.json (sha256 7201819f2a5d).

These are risk indicators to investigate, drawn from published data. They are not findings of wrongdoing by the council, any department or any supplier.

## Scoring method

The council's own method, extracted into history.json from the Risk Management Strategy 2024-2027: 5-point likelihood × 5-point impact, matrix cell for the label, Table 4 for the band and escalation. Score, label and band are computed by `build_register.py`, never by the agent.

**Conflicts inside the council's method.** One reading is used and the other is marked. Neither is resolved silently. The auditor confirmed these six choices on 2026-10-10.

- **DIS-01** Impact 'Medium' is numbered (2) in para 4.3 but 3 in Table 1. Used: 3 (Table 1 and matrix row '3 Medium'). Marked, not used: the (2) in para 4.3.
- **DIS-02** Table 1 percentage ranges overlap between impact 3 and 4; the printed £ ranges abut at £500k. Used: the printed £ ranges; an exposure of exactly £500k is placed at the higher level (4). Marked, not used: the percentage-of-budget ranges.
- **DIS-03** Table 2 probability bands leave gaps (99-100%, 29-30%, below 2%). Used: the five likelihood labels and scores only, set by the rubric in SKILL.md. Marked, not used: the probability percentages.
- **DIS-04** The matrix names scores 8-12 'High'; Table 4 names that band 'Medium - High (Amber)'. Used: the Table 4 band name. Marked: the matrix label is shown beside it on every risk where they differ.
- **DIS-05** Table 4 puts risks on the Corporate Risk Register at Extreme (15-25); Figure 4 says a score of 9 or above. Used: Table 4 (15-25). Marked: a risk scoring 9-14 carries a note that the Figure 4 reading would also place it on the Corporate Risk Register.
- **DIS-07** Para 6.3 sends an Extreme risk to Directorate level to decide the register; Table 4 adds it to the Corporate Risk Register. Used: Table 4. Marked, not used: the para 6.3 routing.

## Revision v2: what changed

- **R-01** APPROVE: unchanged
- **R-02** APPROVE: unchanged
- **R-03** APPROVE: unchanged
- **R-04** APPROVE: unchanged
- **R-05** OVERRIDE ⚑: auditor set the rating (likelihood=4. Paying suppliers after their only notice has ended points to contracts rolling on without re-procurement, which is common in practice.)
- **R-06** APPROVE: unchanged
- **R-07** APPROVE: unchanged
- **R-08** REJECT: removed from scope. Auditor comment: Care placements recur by design and will be covered by a separate social care commissioning review.

## Summary

| Risk | Title | Likelihood | Impact | Score | Band |
|---|---|---|---|---|---|
| R-01 | Same-supplier payments combining past the quote threshold | 4 Almost Certain | 5 Critical | 20 | Extreme (Red) |
| R-04 | Spend with suppliers having no council contract notice | 4 Almost Certain | 5 Critical | 20 | Extreme (Red) |
| R-02 | Low-value payments clustering and combining at the lowest quote boundary | 5 Certain | 3 Medium | 15 | Extreme (Red) |
| R-03 | Combined payments approaching the high-value approval and tender tier | 3 Likely | 5 Critical | 15 | Extreme (Red) |
| R-06 | Spend running above the awarded contract value | 3 Likely | 5 Critical | 15 | Extreme (Red) |
| R-05 | Payments after the only matching notice has ended | 4 Almost Certain | 3 Medium | 12 ⚑ | Medium - High (Amber) |
| R-07 | Possible duplicate payments | 2 Unlikely | 4 Major | 8 | Medium - High (Amber) |

## Risks

### R-01: Same-supplier payments combining past the quote threshold

- **Risk:** Payments to one supplier close together may be a single requirement split so each stays under the invitation-to-quote threshold [rule:CPR-13 (cl. 6.16)] [rule:CPR-60 (cl. AppB-B1)]. These are risk indicators to investigate, not findings.
- **Likelihood:** 4 (Almost Certain). 299 flagged supplier groups, of which 208 are care or education placements and 6 grants, leaving well over twenty outside the exempt tags [metric:$.tests.split_purchases@25000.counts.flagged_items]; the combined total is far above the tier value of [rule:CPR-60 (cl. AppB-B1)]. Clustering just under the same threshold is below the L4 count, so L5 is not met [metric:$.tests.threshold_clustering@25000.counts.flagged_items].
- **Impact:** 5 (Critical). General-procurement-tagged combined value of £4,252,229 alone exceeds the top council impact band [metric:$.tests.split_purchases@25000.by_tag.general_procurement]; total combined £23,514,372 [metric:$.tests.split_purchases@25000.totals_gbp.combined].
- **Rating:** 4 × 5 = **20**, band **Extreme (Red)** [history:BND-01]
- **Evidence:**
  - Largest group: BUPA Care Services [metric:$.tests.split_purchases@25000.top20]
  - Recurring equal-amount groups: 10 [metric:$.tests.split_purchases@25000.counts.groups_all_amounts_equal]
- **Proposed focus:** Recommend testing the largest non-care groups for one underlying requirement, excluding equal-amount recurring care charges.

### R-04: Spend with suppliers having no council contract notice

- **Risk:** Suppliers whose annualised estimate exceeds the notice threshold have no exact-name council notice [rule:CPR-61 (cl. AppB-B1)] [rule:CPR-14 (cl. 6.19)]. Many may hold frameworks or contracts not published as notices. Risk indicators to investigate.
- **Likelihood:** 4 (Almost Certain). 632 suppliers flagged, of which 123 grants and 299 care placements are exempt tags, leaving well over twenty [metric:$.tests.off_contract.counts.flagged_items]; annualised estimate £249,179,061 exceeds the tier of [rule:CPR-61 (cl. AppB-B1)]. The Contracts Finder export only holds larger contracts, which limits this test [metric:$.limitations]. [history:RT-01 (Contracts & Partnerships (procurement contract and relationship manage)]
- **Impact:** 5 (Critical). General-procurement-tagged three-month payments £24,547,481 [metric:$.tests.off_contract.by_tag.general_procurement] exceed the top band; value for money is a registered theme [history:RT-03 (Competition & Markets (value for money))].
- **Rating:** 4 × 5 = **20**, band **Extreme (Red)** [history:BND-01]
- **Evidence:**
  - Largest supplier: VolkerHighways Ltd [metric:$.tests.off_contract.top20]
  - Suppliers with a near-miss candidate notice: 17 [metric:$.tests.off_contract.counts.with_candidate_notice]
- **Proposed focus:** Recommend requesting contract, framework or exclusion evidence for the largest non-care, non-grant suppliers, starting with near-miss name candidates.

### R-02: Low-value payments clustering and combining at the lowest quote boundary

- **Risk:** Many payments sit just under, or combine past, the lowest procurement-route boundary [rule:CPR-59 (cl. AppB-A)], and the anti-splitting rule applies [rule:CPR-13 (cl. 6.16)]. Risk indicators to investigate.
- **Likelihood:** 5 (Certain). Two independent tests meet L4 at this tier: 272 split groups [metric:$.tests.split_purchases@1000.counts.flagged_items] and 294 near-threshold payments [metric:$.tests.threshold_clustering@1000.counts.flagged_items], each with well over twenty items outside the exempt tags, engaging [rule:CPR-59 (cl. AppB-A)]. Much of the clustering is care-tagged, which may reflect tariff pricing.
- **Impact:** 3 (Medium). General-procurement-tagged combined value £238,647 falls in the Medium band [metric:$.tests.split_purchases@1000.by_tag.general_procurement]; the lower-value tier limits financial exposure per [rule:CPR-59 (cl. AppB-A)].
- **Rating:** 5 × 3 = **15**, band **Extreme (Red)** [history:BND-01]
- **Evidence:**
  - Near-threshold payments in general procurement: 49 [metric:$.tests.threshold_clustering@1000.by_tag]
- **Proposed focus:** Recommend a small targeted sample of non-care groups to confirm whether quotes were obtained; lower priority than the larger-tier split risk.

### R-03: Combined payments approaching the high-value approval and tender tier

- **Risk:** Payments to one supplier combine past the high-value tier [rule:CPR-64 (cl. AppB-C)] [rule:CPR-04 (cl. 4.3)], which carries enhanced approval. Risk indicators to investigate.
- **Likelihood:** 3 (Likely). 12 flagged groups, with 5 in the care tag, leaving between five and nineteen outside the exempt tags [metric:$.tests.split_purchases@500000.counts.flagged_items]; no payment clusters just under the tier [metric:$.tests.threshold_clustering@500000.counts.flagged_items].
- **Impact:** 5 (Critical). General-procurement-tagged combined value £6,596,260 [metric:$.tests.split_purchases@500000.by_tag.general_procurement] engages the approval rule [rule:CPR-04 (cl. 4.3)].
- **Rating:** 3 × 5 = **15**, band **Extreme (Red)** [history:BND-01]
- **Evidence:**
  - Largest group: VolkerHighways Ltd [metric:$.tests.split_purchases@500000.top20]
- **Proposed focus:** Recommend confirming the approval route and any existing contract for the few non-care groups.

### R-06: Spend running above the awarded contract value

- **Risk:** Annualised spend is well above the annual equivalent of the award, which may indicate spend beyond the award without an approved variation [rule:CPR-70 (cl. AppC-E)] [rule:CPR-71 (cl. AppC-E)]. Award values may be estimates. Risk indicators to investigate.
- **Likelihood:** 3 (Likely). 7 suppliers flagged of 18 assessed, none in exempt tags [metric:$.tests.spend_vs_award.counts.flagged_items], engaging [rule:CPR-70 (cl. AppC-E)].
- **Impact:** 5 (Critical). Flagged annualised estimate £2,535,073 [metric:$.tests.spend_vs_award.totals_gbp.annualised_estimate_flagged], an annualised estimate of the spend at these suppliers, not of any overspend.
- **Rating:** 3 × 5 = **15**, band **Extreme (Red)** [history:BND-01]
- **Evidence:**
  - Highest ratio supplier: NEC SOFTWARE SOLUTIONS UK LIMITED at 6.13 times [metric:$.tests.spend_vs_award.top20]
- **Proposed focus:** Recommend comparing payments with the award and any variation approvals for the flagged suppliers.

### R-05: Payments after the only matching notice has ended

- **Risk:** Suppliers paid in the window whose every matching notice ended earlier may indicate spend after expiry without an approved extension [rule:CPR-69 (cl. AppC-D)]. A newer contract may exist without a notice. Risk indicators to investigate.
- **Likelihood:** 4 (Almost Certain). 8 suppliers flagged, none in exempt tags, which is between five and nineteen [metric:$.tests.expired_notice_spend.counts.flagged_items], engaging [rule:CPR-69 (cl. AppC-D)].
- **Impact:** 3 (Medium). Three-month payments £243,364 fall in the Medium band [metric:$.tests.expired_notice_spend.totals_gbp.three_month].
- **Rating:** 4 × 3 = **12**, band **Medium - High (Amber)** [history:BND-02]. Matrix label: High (differs from the Table 4 band name; DIS-04)
- **Escalation (Table 4):** Seek assurance that identified controls are effective Allocate to Service Director to put in place Controls Assurance. [history:ESC-02]
- **Marked, not applied:** the Figure 4 reading (score 9 or above) would also place this on the Corporate Risk Register (DIS-05).
- ⚑ **AUDITOR OVERRIDE:** likelihood 3 → 4. The agent proposed score 9. Auditor comment: likelihood=4. Paying suppliers after their only notice has ended points to contracts rolling on without re-procurement, which is common in practice.
- **Evidence:**
  - Largest supplier: Hope & Clay (Construction) Ltd [metric:$.tests.expired_notice_spend.top20]
- **Proposed focus:** Recommend requesting extension or new-contract records for each flagged supplier.

### R-07: Possible duplicate payments

- **Risk:** Repeated same-amount payments to one supplier within a short window may be duplicates to investigate; identical rows may be legitimate. Financial control is a registered theme [history:RT-02 (Finance (financial control, fraud and corruption))].
- **Likelihood:** 2 (Unlikely). 651 flagged items [metric:$.tests.duplicates.counts.flagged_items], but no Contract Procedure Rule directly addresses duplicate payments, so L3 and L4 conditions are not met; the Accounts Payable audit was Reasonable [history:AUD-11 (Accounts Payable: Reasonable Assurance)]. Lower level taken.
- **Impact:** 4 (Major). General-procurement-tagged group total £799,632 [metric:$.tests.duplicates.by_tag.general_procurement].
- **Rating:** 2 × 4 = **8**, band **Medium - High (Amber)** [history:BND-02]. Matrix label: High (differs from the Table 4 band name; DIS-04)
- **Escalation (Table 4):** Seek assurance that identified controls are effective Allocate to Service Director to put in place Controls Assurance. [history:ESC-02]
- **Evidence:**
  - Groups identical on every field: 453 [metric:$.tests.duplicates.counts.identical_on_all_fields_groups]
- **Proposed focus:** Recommend a lower-priority sample of non-care identical groups against invoices.

## Excluded risks (not rated)

None.

Removed at the auditor's request: R-08.

## Auditor decisions

Recorded in `outputs/auditor-comments.md` (APPROVE, REJECT, REVISE or OVERRIDE per risk). The table below mirrors that file as at this build.

| Risk | Rating | Decision | Comment |
|---|---|---|---|
| R-01 | 20 Extreme (Red) | APPROVE |  |
| R-04 | 20 Extreme (Red) | APPROVE |  |
| R-02 | 15 Extreme (Red) | APPROVE |  |
| R-03 | 15 Extreme (Red) | APPROVE |  |
| R-06 | 15 Extreme (Red) | APPROVE |  |
| R-05 | 12 Medium - High (Amber) ⚑ | OVERRIDE | likelihood=4. Paying suppliers after their only notice has ended points to contracts rolling on without re-procurement, which is common in practice. |
| R-07 | 8 Medium - High (Amber) | APPROVE | Keep likelihood at 2: no Contract Procedure Rule covers duplicates, and many identical rows may be export artefacts. |
