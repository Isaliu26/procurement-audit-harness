# Risk-control matrix

**Pack version:** built from register v2. **Built from:** analytics (sha256 250f46389dfa) history (sha256 9137ff368907) rules (sha256 a19fb7385362) ratings (sha256 7201819f2a5d) plan (sha256 abfe27bedda5).

These are risk indicators to investigate, drawn from published data. They are not findings of wrongdoing by the council, any department or any supplier.

## Risks, controls and tests

| Risk | Rating | Rule | Expected control | Test | Sample |
|---|---|---|---|---|---|
| R-01 Same-supplier payments combining past the quote threshold | 20 Extreme (Red) | CPR-13 (cl. 6.16), CPR-60 (cl. AppB-B1), CPR-62 (cl. AppB-B2) | C-01: A requirement at or above the quote tier is quoted from at least three sources [rule:CPR-60 (cl. AppB-B1)] (works, concession and light touch contracts follow [rule:CPR-62 (cl. AppB-B2)]) and is not split or disaggregated to avoid the quote tier [rule:CPR-13 (cl. 6.16)]. | T-01 | T-01: 25 items, 554 transactions |
| R-04 Spend with suppliers having no council contract notice | 20 Extreme (Red) | CPR-14 (cl. 6.19), CPR-61 (cl. AppB-B1), CPR-63 (cl. AppB-B2), CPR-65 (cl. AppB-D) | C-04: Contracts above the tier are competed and advertised [rule:CPR-61 (cl. AppB-B1)] [rule:CPR-63 (cl. AppB-B2)] [rule:CPR-65 (cl. AppB-D)] so that a notice exists, or an exclusion or framework basis is recorded [rule:CPR-14 (cl. 6.19)]. | T-04 | T-04: 25 items, 456 transactions |
| R-02 Low-value payments clustering and combining at the lowest quote boundary | 15 Extreme (Red) | CPR-13 (cl. 6.16), CPR-59 (cl. AppB-A) | C-02: Requirements in the lowest quote band are quoted from an appropriate source [rule:CPR-59 (cl. AppB-A)] and not split to stay under the quote boundary [rule:CPR-13 (cl. 6.16)]. | T-02 | T-02: 15 items, 201 transactions |
| R-03 Combined payments approaching the high-value approval and tender tier | 15 Extreme (Red) | CPR-04 (cl. 4.3), CPR-64 (cl. AppB-C), CPR-65 (cl. AppB-D) | C-03: An award in the high-value tier is treated as a Key Decision of the Council [rule:CPR-04 (cl. 4.3)]; works, concession and light touch contracts follow the full tender route [rule:CPR-64 (cl. AppB-C)] and goods and services above the Threshold follow [rule:CPR-65 (cl. AppB-D)]. | T-03 | T-03: 7 items, 139 transactions |
| R-06 Spend running above the awarded contract value | 15 Extreme (Red) | CPR-70 (cl. AppC-E), CPR-71 (cl. AppC-E) | C-06: A variation is approved in advance in writing by the Monitoring Officer and chief finance officer where the contract value is below the Threshold [rule:CPR-70 (cl. AppC-E)], or by the relevant board where it is above the Threshold [rule:CPR-71 (cl. AppC-E)]. | T-06 | T-06: 7 items, 30 transactions |
| R-05 Payments after the only matching notice has ended | 12 Medium - High (Amber) ⚑ | CPR-69 (cl. AppC-D) | C-05: An extension to an existing contract is only used where the contract provides for it, with the approval of the chief finance officer [rule:CPR-69 (cl. AppC-D)]. | T-05 | T-05: 8 items, 60 transactions |
| R-07 Possible duplicate payments | 8 Medium - High (Amber) | CPR-06 (cl. 5.1.1) | C-07: Each published payment in the spend transparency data [rule:CPR-06 (cl. 5.1.1)] is supported by one invoice and is paid once. | T-07 | T-07: 5 items, 16 transactions |

## Rule coverage

Every rule in `rules.json` is cited by an approved risk, control or test, or listed as not tested with a reason.

| Rule | Clause | Status | Cited by / reason |
|---|---|---|---|
| CPR-01 | 3.5 | not tested | Approval, documentation and evaluation steps evidenced only in council records; not covered by the approved risks. |
| CPR-02 | 4.1 | not tested | Approval, documentation and evaluation steps evidenced only in council records; not covered by the approved risks. |
| CPR-03 | 4.2 | not tested | Approval, documentation and evaluation steps evidenced only in council records; not covered by the approved risks. |
| CPR-04 | 4.3 | tested | C-03, R-03, T-03 |
| CPR-05 | 4.4 | not tested | Approval, documentation and evaluation steps evidenced only in council records; not covered by the approved risks. |
| CPR-06 | 5.1.1 | tested | C-07, T-07 |
| CPR-07 | 5.2 | not tested | Publication and advertising duties evidenced in council records or notices; not covered by the approved risks. |
| CPR-08 | 5.2.1 | not tested | Publication and advertising duties evidenced in council records or notices; not covered by the approved risks. |
| CPR-09 | 5.3 | not tested | Approval, documentation and evaluation steps evidenced only in council records; not covered by the approved risks. |
| CPR-10 | 6.4 | not tested | Approval, documentation and evaluation steps evidenced only in council records; not covered by the approved risks. |
| CPR-11 | 6.10 | not tested | Publication and advertising duties evidenced in council records or notices; not covered by the approved risks. |
| CPR-12 | 6.14 | not tested | Approval, documentation and evaluation steps evidenced only in council records; not covered by the approved risks. |
| CPR-13 | 6.16 | tested | C-01, C-02, R-01, R-02, T-01 |
| CPR-14 | 6.19 | tested | C-04, R-04 |
| CPR-15 | 6.20 | not tested | Approval, documentation and evaluation steps evidenced only in council records; not covered by the approved risks. |
| CPR-16 | 6.20 | not tested | Approval, documentation and evaluation steps evidenced only in council records; not covered by the approved risks. |
| CPR-17 | 6.21 | not tested | Approval, documentation and evaluation steps evidenced only in council records; not covered by the approved risks. |
| CPR-18 | 6.22 | not tested | Approval, documentation and evaluation steps evidenced only in council records; not covered by the approved risks. |
| CPR-19 | 6.24 | not tested | Approval, documentation and evaluation steps evidenced only in council records; not covered by the approved risks. |
| CPR-20 | 6.26 | not tested | Approval, documentation and evaluation steps evidenced only in council records; not covered by the approved risks. |
| CPR-21 | 7.2.1 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-22 | 7.2.2 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-23 | 7.3 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-24 | 7.3 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-25 | 7.4.1 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-26 | 7.4.3 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-27 | 7.5.1 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-28 | 7.5.2 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-29 | 7.5.3 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-30 | 8.2 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-31 | 9.1 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-32 | 9.2 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-33 | 9.3 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-34 | 10.2 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-35 | 10.3 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-36 | 10.4 | not tested | Publication and advertising duties evidenced in council records or notices; not covered by the approved risks. |
| CPR-37 | 10.5 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-38 | 10.6 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-39 | 10.7 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-40 | 10.7.7 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-41 | 10.7.10 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-42 | 11.1 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-43 | 11.3 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-44 | 11.4.1 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-45 | 11.4.2 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-46 | 11.4.3 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-47 | 11.5.1 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-48 | 11.5.2 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-49 | 11.5.3 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-50 | 11.5.4 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-51 | 11.11 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-52 | 11.13 | not tested | Waiver, exception, contract-terms and sealing rules evidenced only in council records; not covered by the approved risks. |
| CPR-53 | AppA-1 | not tested | Contract approval-level rules (Appendix A) evidenced in council records; not covered by the approved risks. |
| CPR-54 | AppA-2 | not tested | Contract approval-level rules (Appendix A) evidenced in council records; not covered by the approved risks. |
| CPR-55 | AppA-3 | not tested | Contract approval-level rules (Appendix A) evidenced in council records; not covered by the approved risks. |
| CPR-56 | AppA-3 | not tested | Contract approval-level rules (Appendix A) evidenced in council records; not covered by the approved risks. |
| CPR-57 | AppA-4 | not tested | Contract approval-level rules (Appendix A) evidenced in council records; not covered by the approved risks. |
| CPR-58 | AppA-4 | not tested | Contract approval-level rules (Appendix A) evidenced in council records; not covered by the approved risks. |
| CPR-59 | AppB-A | tested | C-02, R-02, T-02 |
| CPR-60 | AppB-B1 | tested | C-01, R-01, T-01 |
| CPR-61 | AppB-B1 | tested | C-04, R-04, T-04 |
| CPR-62 | AppB-B2 | tested | C-01, T-01 |
| CPR-63 | AppB-B2 | tested | C-04 |
| CPR-64 | AppB-C | tested | C-03, R-03, T-03 |
| CPR-65 | AppB-D | tested | C-03, C-04, T-03 |
| CPR-66 | AppC-A | not tested | Exclusion routes evidenced only in council records; not covered by the approved risks. |
| CPR-67 | AppC-B | not tested | Exclusion routes evidenced only in council records; not covered by the approved risks. |
| CPR-68 | AppC-C | not tested | Exclusion routes evidenced only in council records; not covered by the approved risks. |
| CPR-69 | AppC-D | tested | C-05, R-05, T-05 |
| CPR-70 | AppC-E | tested | C-06, R-06, T-06 |
| CPR-71 | AppC-E | tested | C-06, R-06, T-06 |
| CPR-72 | AppC-F | not tested | Exclusion routes evidenced only in council records; not covered by the approved risks. |
| CPR-73 | AppC-closing | not tested | Exclusion routes evidenced only in council records; not covered by the approved risks. |
