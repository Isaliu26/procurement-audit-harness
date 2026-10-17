# Challenges

Pack versions reviewed: v1, v2, v3 (register v2). These are risk indicators to investigate, not findings of wrongdoing by the council, any department or any supplier.

| # | Type | Risk | Challenge | Citation | Ask | Planner response | Status | Verified |
|---|---|---|---|---|---|---|---|---|
| 1 | sample | R-01 | Sampled groups include care- and grant-tagged transactions despite the exempt-tag filter | [metric:$.tests.split_purchases@25000.by_tag]; samples/T-01..T-04.csv | Exclude exempt-tagged rows from expanded transactions or mark them context only | accepted: recipe filters groups not rows; memo limitation added that tag-marked rows are context only | resolved | v2 (planning-memo.md limitation) |
| 2 | sample | R-04 | T-04 step says start with near-miss candidates but the sort does not target them; 25 of 209 items | [metric:$.tests.off_contract.counts.with_candidate_notice]; T-04 | Target the 17 candidates or reword; state value coverage | accepted: step reworded, candidate_notice column in source list, largest by annualised estimate | resolved | v3 (see #9) |
| 3 | coverage | R-03 | agency_staff groups (2 groups, £1,076,284) dropped by the T-03 tag filter | [metric:$.tests.split_purchases@500000.by_tag.agency_staff]; [rule:CPR-04] | Include agency_staff or justify | accepted: agency_staff added to T-03 filter | resolved | v2 (T-03 filter; 139 rows incl. 12 agency) |
| 4 | coverage | ALL | CPR-62 not tested although evidence_source includes spend_data | [rule:CPR-62]; not_tested | Trace to R-01/T-01 or give a specific reason | accepted: CPR-62 cited in C-01, CPR-63 in C-04, removed from not_tested | resolved | v2 |
| 5 | control | R-03 | C-03 cites CPR-64 (works only) and omits the Key Decision requirement of CPR-04 | [rule:CPR-64] [rule:CPR-04]; C-03, T-03 | Reword control and step | accepted: C-03 names Key Decision (CPR-04), CPR-64 works, CPR-65 goods/services; T-03 asks for Key Decision record | resolved | v2 |
| 6 | test | R-07 | T-07 samples identical groups only; 651 flagged items vs 453 identical groups | [metric:$.tests.duplicates.counts.flagged_items]; T-07 | Widen filter or justify with second sample | accepted: identical-only filter dropped; identical sorted first | resolved | v2 (T-07 filter and sort) |
| 7 | coverage | R-06 | 19 suppliers skipped by spend_vs_award not stated as a limitation or PBC | [metric:$.tests.spend_vs_award.counts.skipped_with_reason]; memo Limitations | Add limitation and PBC item | accepted: limitation added with skipped counts; PBC-10 added to T-06 | resolved | v2 (memo limitation, PBC-10) |
| 8 | control | R-05 | C-05/C-06 do not name the approvers or the CPR-70/71 value split | [rule:CPR-69] [rule:CPR-70] [rule:CPR-71]; C-05, C-06 | Name approvers; steps request them | accepted: C-05 and C-06 name approvers and CPR-70/71 split; T-05, T-06 steps request them | resolved | v2 |
| 9 | sample | R-04 | Follow-up to #2: T-04.csv has no candidate_notice column and sort unchanged; candidates not shown to be sampled | [metric:$.tests.off_contract.counts.with_candidate_notice]; T-04 | Point to analytics-full/off_contract.csv and state limitation, or sort candidates first | accepted: T-04 sorts candidate_notice first then annualised estimate; step names off_contract.csv; memo limitation added | resolved | v3 (audit-plan.json T-04 sort, planning-memo.md) |

## For the auditor

None. No row ended as for the auditor.
