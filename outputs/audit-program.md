# Audit program

**Pack version:** built from register v2. **Built from:** analytics (sha256 250f46389dfa) history (sha256 9137ff368907) rules (sha256 a19fb7385362) ratings (sha256 7201819f2a5d) plan (sha256 abfe27bedda5).

These are risk indicators to investigate, drawn from published data. They are not findings of wrongdoing by the council, any department or any supplier.

## R-01: Same-supplier payments combining past the quote threshold

**Rating:** 20 Extreme (Red) (likelihood 4 Almost Certain, impact 5 Critical). **Sample allowance for this score:** 25 items per sampled test.

**Risk indicator:** Payments to one supplier close together may be a single requirement split so each stays under the invitation-to-quote threshold [rule:CPR-13 (cl. 6.16)] [rule:CPR-60 (cl. AppB-B1)]. These are risk indicators to investigate, not findings.

### Expected control C-01

A requirement at or above the quote tier is quoted from at least three sources [rule:CPR-60 (cl. AppB-B1)] (works, concession and light touch contracts follow [rule:CPR-62 (cl. AppB-B2)]) and is not split or disaggregated to avoid the quote tier [rule:CPR-13 (cl. 6.16)].

#### Test T-01

**Objective:** Check whether grouped same-supplier payments relate to one underlying requirement, using general-procurement and premises groups only (care placements and grants follow other routes) [rule:CPR-13 (cl. 6.16)]. The spend data carries no works or goods marker, so works-type groups are identified from the supporting records requested [rule:CPR-62 (cl. AppB-B2)].

**Test step:** For each sampled group compare orders, invoices and quotes, and confirm the combined value was quoted under [rule:CPR-60 (cl. AppB-B1)] [metric:$.tests.split_purchases@25000.counts.flagged_items]. Record whether a framework or contract covers the group.

**Sample:** `split_purchases.csv`; filter tier == 25000; filter tag in ["general_procurement", "premises"]; sort combined_gbp descending; take the first N in that order. 85 items qualify; 25 drawn (score-based size). 554 transactions worth £2,843,912 are listed in `outputs/samples/T-01.csv`.

1 item(s) hold more transactions than the listing cap; the CSV shows the earliest ones and the `item_transactions` column gives the full count.

| # | Item | Transactions | Value listed |
|---|---|---|---|
| 1 | WEST BERKSHIRE MENCAP | 48 | £283,986 |
| 2 | VolkerHighways Ltd | 32 | £258,306 |
| 3 | PURLEY PARK TRUST LTD | 51 | £231,204 |
| 4 | VolkerHighways Ltd | 37 | £223,741 |
| 5 | PURLEY PARK TRUST LTD | 28 | £195,203 |
| 6 | The Better Group Ltd | 15 | £187,440 |
| 7 | WEST BERKSHIRE MENCAP | 35 | £131,481 |
| 8 | WEAVAWAY TRAVEL LTD | 25 | £94,891 |
| 9 | WEST BERKSHIRE MENCAP | 32 | £89,819 |
| 10 | VolkerHighways Ltd | 10 | £87,810 |
| 11 | Roadside Technologies Ltd | 10 | £84,070 |
| 12 | Newbury & District Ltd | 9 | £81,262 |
| 13 | FD TRAVELS LIMITED T/A SCHOOL EXPRESS | 30 | £77,831 |
| 14 | The Better Group Ltd | 4 | £77,145 |
| 15 | BROADWAY CARS | 30 | £76,613 |
| 16 | WEAVAWAY TRAVEL LTD | 20 | £74,460 |
| 17 | FD TRAVELS LIMITED T/A SCHOOL EXPRESS | 33 | £72,689 |
| 18 | Elior UK PLC | 4 | £72,329 |
| 19 | KB Real Estate Management Ltd | 46 | £71,105 |
| 20 | Newbury & District Ltd | 10 | £69,328 |
| 21 | Triple Value Impact | 5 | £68,028 |
| 22 | Elior UK PLC | 4 | £65,914 |
| 23 | PAYPOINT MOBILE & ONLINE | 5 | £58,399 |
| 24 | SOUTHERN COACH LINES LTD | 16 | £55,532 |
| 25 | BROADWAY CARS | 16 | £55,326 |

**Needs (PBC):** PBC-01, PBC-02

## R-04: Spend with suppliers having no council contract notice

**Rating:** 20 Extreme (Red) (likelihood 4 Almost Certain, impact 5 Critical). **Sample allowance for this score:** 25 items per sampled test.

**Risk indicator:** Suppliers whose annualised estimate exceeds the notice threshold have no exact-name council notice [rule:CPR-61 (cl. AppB-B1)] [rule:CPR-14 (cl. 6.19)]. Many may hold frameworks or contracts not published as notices. Risk indicators to investigate.

### Expected control C-04

Contracts above the tier are competed and advertised [rule:CPR-61 (cl. AppB-B1)] [rule:CPR-63 (cl. AppB-B2)] [rule:CPR-65 (cl. AppB-D)] so that a notice exists, or an exclusion or framework basis is recorded [rule:CPR-14 (cl. 6.19)].

#### Test T-04

**Objective:** Check whether suppliers with no exact-name notice hold a contract, framework or recorded exclusion, excluding care placements and grants [rule:CPR-61 (cl. AppB-B1)].

**Test step:** For each sampled supplier request contract, framework or exclusion evidence. Suppliers with a near-miss candidate notice are sampled first, then the largest by annualised estimate; the candidate names are in outputs/analytics-full/off_contract.csv (candidate_notice column) [metric:$.tests.off_contract.counts.with_candidate_notice] [metric:$.tests.off_contract.counts.flagged_items].

**Sample:** `off_contract.csv`; filter tag in ["general_procurement", "premises"]; sort candidate_notice descending, annualised_estimate_gbp descending; take the first N in that order. 209 items qualify; 25 drawn (score-based size). 456 transactions worth £15,342,300 are listed in `outputs/samples/T-04.csv`.

4 item(s) hold more transactions than the listing cap; the CSV shows the earliest ones and the `item_transactions` column gives the full count.

| # | Item | Transactions | Value listed |
|---|---|---|---|
| 1 | WCL UK Ltd (Trading as Everything ICT) | 1 | £102,883 |
| 2 | The Advocacy People (formerly SEAP) | 3 | £31,653 |
| 3 | Swan Advocacy | 8 | £51,216 |
| 4 | SOUTHERN COACH LINES LTD | 16 | £55,532 |
| 5 | Solutions4Health Ltd | 4 | £45,278 |
| 6 | Sikandar Hayat t/a Prompt Cars | 40 | £187,250 |
| 7 | POTTINGER'S HIRE SERVICE | 8 | £9,352 |
| 8 | Mark Dillon t/a Penmar Transport Ltd | 15 | £35,282 |
| 9 | MRS M F RICHARDSON T/A MFR Contracts | 13 | £15,365 |
| 10 | S RICHARDS T/AS K RICKETTS & S RICHARDS TAXIS | 8 | £17,144 |
| 11 | Glen Cleaning Company Ltd | 68 | £67,942 |
| 12 | ELITE SECURITY GROUP | 9 | £10,178 |
| 13 | D J TRAVEL | 16 | £67,967 |
| 14 | BROADWAY CARS | 46 | £131,939 |
| 15 | ABC TRAVEL (WOKINGHAM) LIMITED T/A ABC TRAVEL | 24 | £63,141 |
| 16 | N Mehmood T/A A Star Executive Cars Ltd | 7 | £12,489 |
| 17 | VolkerHighways Ltd | 126 | £2,301,072 |
| 18 | VEOLIA ES WEST BERKSHIRE LTD (CHAPS ONLY) | 3 | £6,186,065 |
| 19 | Millbrook Healthcare Limited | 4 | £3,459,365 |
| 20 | RUSKIN MILL TRUST | 9 | £795,198 |
| 21 | SoftwareONE UK Ltd | 4 | £522,979 |
| 22 | Livity Life Ltd | 9 | £513,075 |
| 23 | WEST BERKSHIRE MENCAP | 115 | £205,555 |
| 24 | PURLEY PARK TRUST LTD | 94 | £292,964 |
| 25 | Elior UK PLC | 9 | £161,416 |

**Needs (PBC):** PBC-05, PBC-06

## R-02: Low-value payments clustering and combining at the lowest quote boundary

**Rating:** 15 Extreme (Red) (likelihood 5 Certain, impact 3 Medium). **Sample allowance for this score:** 15 items per sampled test.

**Risk indicator:** Many payments sit just under, or combine past, the lowest procurement-route boundary [rule:CPR-59 (cl. AppB-A)], and the anti-splitting rule applies [rule:CPR-13 (cl. 6.16)]. Risk indicators to investigate.

### Expected control C-02

Requirements in the lowest quote band are quoted from an appropriate source [rule:CPR-59 (cl. AppB-A)] and not split to stay under the quote boundary [rule:CPR-13 (cl. 6.16)].

#### Test T-02

**Objective:** Check whether payments just under the lowest quote boundary are supported by a quote and a single requirement, excluding care placements and grants [rule:CPR-59 (cl. AppB-A)].

**Test step:** For each sampled group obtain the quote and order and confirm the requirement was not divided [metric:$.tests.split_purchases@1000.counts.flagged_items].

**Sample:** `split_purchases.csv`; filter tier == 1000; filter tag in ["general_procurement", "premises"]; sort combined_gbp descending; take the first N in that order. 135 items qualify; 15 drawn (score-based size). 201 transactions worth £141,419 are listed in `outputs/samples/T-02.csv`.

| # | Item | Transactions | Value listed |
|---|---|---|---|
| 1 | WEST BERKSHIRE MENCAP | 21 | £14,452 |
| 2 | WEST BERKSHIRE MENCAP | 17 | £12,358 |
| 3 | SOVEREIGN HOUSING GROUP | 18 | £12,202 |
| 4 | SOVEREIGN HOUSING GROUP | 18 | £12,202 |
| 5 | THE NEWBURY COMMUNITY RESOURCE CENTRE LTD | 15 | £10,790 |
| 6 | BERKSHIRE MECHANICAL SERVICES | 13 | £10,105 |
| 7 | BERKSHIRE MECHANICAL SERVICES | 14 | £9,550 |
| 8 | Glen Cleaning Company Ltd | 12 | £9,491 |
| 9 | Glen Cleaning Company Ltd | 11 | £9,067 |
| 10 | Glen Cleaning Company Ltd | 13 | £8,734 |
| 11 | ANCHOR PIPEWORK LIMITED | 10 | £6,974 |
| 12 | ANCHOR PIPEWORK LIMITED | 10 | £6,693 |
| 13 | Tennent Homes 2019 Limited | 10 | £6,600 |
| 14 | PURLEY PARK TRUST LTD | 10 | £6,317 |
| 15 | CONNICK TREE CARE | 9 | £5,885 |

**Needs (PBC):** PBC-03, PBC-01

## R-03: Combined payments approaching the high-value approval and tender tier

**Rating:** 15 Extreme (Red) (likelihood 3 Likely, impact 5 Critical). **Sample allowance for this score:** 15 items per sampled test.

**Risk indicator:** Payments to one supplier combine past the high-value tier [rule:CPR-64 (cl. AppB-C)] [rule:CPR-04 (cl. 4.3)], which carries enhanced approval. Risk indicators to investigate.

### Expected control C-03

An award in the high-value tier is treated as a Key Decision of the Council [rule:CPR-04 (cl. 4.3)]; works, concession and light touch contracts follow the full tender route [rule:CPR-64 (cl. AppB-C)] and goods and services above the Threshold follow [rule:CPR-65 (cl. AppB-D)].

#### Test T-03

**Objective:** Check the approval route and any existing contract for combined payments reaching the high-value tier, excluding care placements and grants [rule:CPR-04 (cl. 4.3)].

**Test step:** For each sampled group confirm the route applying to its type (works-type [rule:CPR-64 (cl. AppB-C)], goods and services [rule:CPR-65 (cl. AppB-D)]), the tender record and the Key Decision record [rule:CPR-04 (cl. 4.3)] [metric:$.tests.split_purchases@500000.counts.flagged_items].

**Sample:** `split_purchases.csv`; filter tier == 500000; filter tag in ["general_procurement", "premises", "agency_staff"]; sort combined_gbp descending; take the first N in that order. 7 items qualify; 7 drawn (score-based size). 139 transactions worth £7,448,239 are listed in `outputs/samples/T-03.csv`.

2 item(s) hold more transactions than the listing cap; the CSV shows the earliest ones and the `item_transactions` column gives the full count.

| # | Item | Transactions | Value listed |
|---|---|---|---|
| 1 | VolkerHighways Ltd | 55 | £2,301,072 |
| 2 | VolkerHighways Ltd | 18 | £1,690,086 |
| 3 | VolkerHighways Ltd | 51 | £1,307,720 |
| 4 | RUSKIN MILL TRUST | 5 | £550,097 |
| 5 | Comensura Ltd | 6 | £545,378 |
| 6 | Comensura Ltd | 6 | £530,907 |
| 7 | SoftwareONE UK Ltd | 4 | £522,979 |

**Needs (PBC):** PBC-04, PBC-02

## R-06: Spend running above the awarded contract value

**Rating:** 15 Extreme (Red) (likelihood 3 Likely, impact 5 Critical). **Sample allowance for this score:** 15 items per sampled test.

**Risk indicator:** Annualised spend is well above the annual equivalent of the award, which may indicate spend beyond the award without an approved variation [rule:CPR-70 (cl. AppC-E)] [rule:CPR-71 (cl. AppC-E)]. Award values may be estimates. Risk indicators to investigate.

### Expected control C-06

A variation is approved in advance in writing by the Monitoring Officer and chief finance officer where the contract value is below the Threshold [rule:CPR-70 (cl. AppC-E)], or by the relevant board where it is above the Threshold [rule:CPR-71 (cl. AppC-E)].

#### Test T-06

**Objective:** Check whether spend above the annual award is covered by an approved variation [rule:CPR-70 (cl. AppC-E)].

**Test step:** For each sampled supplier compare payments with the award, decide which rule applies from the contract value ([rule:CPR-70 (cl. AppC-E)] or [rule:CPR-71 (cl. AppC-E)]), and obtain the prior written approval from the named approvers [metric:$.tests.spend_vs_award.counts.flagged_items]. Award values may be estimates or maxima.

**Sample:** `spend_vs_award.csv`; sort ratio descending; take the first N in that order. 7 items qualify; 7 drawn (score-based size). 30 transactions worth £633,768 are listed in `outputs/samples/T-06.csv`.

| # | Item | Transactions | Value listed |
|---|---|---|---|
| 1 | NEC SOFTWARE SOLUTIONS UK LIMITED | 10 | £314,384 |
| 2 | BookingLab Limited | 1 | £24,000 |
| 3 | Exacom Systems Ltd | 1 | £12,106 |
| 4 | SMS-Environmental Ltd | 7 | £7,759 |
| 5 | Softcat Ltd | 2 | £11,005 |
| 6 | IDOX SOFTWARE LTD | 2 | £51,226 |
| 7 | TWO SAINTS LTD | 7 | £213,288 |

**Needs (PBC):** PBC-09, PBC-08, PBC-10

## R-05: Payments after the only matching notice has ended

**Rating:** 12 Medium - High (Amber) ⚑ (likelihood 4 Almost Certain, impact 3 Medium). **Sample allowance for this score:** 10 items per sampled test.

**Risk indicator:** Suppliers paid in the window whose every matching notice ended earlier may indicate spend after expiry without an approved extension [rule:CPR-69 (cl. AppC-D)]. A newer contract may exist without a notice. Risk indicators to investigate.

### Expected control C-05

An extension to an existing contract is only used where the contract provides for it, with the approval of the chief finance officer [rule:CPR-69 (cl. AppC-D)].

#### Test T-05

**Objective:** Check whether payments after the only matching notice ended are covered by an approved extension or a newer contract [rule:CPR-69 (cl. AppC-D)].

**Test step:** For each sampled supplier obtain the chief finance officer's approval of the extension, or the replacement contract [rule:CPR-69 (cl. AppC-D)] [metric:$.tests.expired_notice_spend.counts.flagged_items].

**Sample:** `expired_notice_spend.csv`; sort total_gbp descending; take the first N in that order. 8 items qualify; 8 drawn (score-based size). 60 transactions worth £243,364 are listed in `outputs/samples/T-05.csv`.

| # | Item | Transactions | Value listed |
|---|---|---|---|
| 1 | Hope & Clay (Construction) Ltd | 1 | £91,307 |
| 2 | BERKSHIRE MECHANICAL SERVICES | 45 | £68,040 |
| 3 | Berkshire Womens Aid | 2 | £52,998 |
| 4 | G7 BUSINESS SOLUTIONS LIMITED | 8 | £16,365 |
| 5 | CACI Limited | 1 | £12,072 |
| 6 | Morton Pattison Ltd | 1 | £1,102 |
| 7 | Davis and Associates Consultancy Limited | 1 | £800 |
| 8 | Tactical Facilities Management Ltd | 1 | £682 |

**Needs (PBC):** PBC-07, PBC-08

## R-07: Possible duplicate payments

**Rating:** 8 Medium - High (Amber) (likelihood 2 Unlikely, impact 4 Major). **Sample allowance for this score:** 5 items per sampled test.

**Risk indicator:** Repeated same-amount payments to one supplier within a short window may be duplicates to investigate; identical rows may be legitimate. Financial control is a registered theme [history:RT-02 (Finance (financial control, fraud and corruption))].

### Expected control C-07

Each published payment in the spend transparency data [rule:CPR-06 (cl. 5.1.1)] is supported by one invoice and is paid once.

#### Test T-07

**Objective:** Check whether identical same-supplier payments are separate invoices, excluding care placements and grants [rule:CPR-06 (cl. 5.1.1)].

**Test step:** For each sampled group match payments to invoices and remittances; groups identical on every field are sampled first [metric:$.tests.duplicates.counts.identical_on_all_fields_groups]. Identical rows may be legitimate, and the full flagged population is in the duplicates list [metric:$.tests.duplicates.counts.flagged_items].

**Sample:** `duplicates.csv`; filter tag in ["general_procurement", "premises"]; sort identical_on_all_fields descending, total_gbp descending; take the first N in that order. 102 items qualify; 5 drawn (score-based size). 16 transactions worth £86,771 are listed in `outputs/samples/T-07.csv`.

| # | Item | Transactions | Value listed |
|---|---|---|---|
| 1 | WEST BERKSHIRE MENCAP | 2 | £20,918 |
| 2 | PURLEY PARK TRUST LTD | 4 | £18,731 |
| 3 | Roadside Technologies Ltd | 2 | £18,207 |
| 4 | RESPONSE ORGANISATION | 6 | £15,414 |
| 5 | WEST BERKSHIRE MENCAP | 2 | £13,501 |

**Needs (PBC):** PBC-11

## Prepared-by-client (PBC) request list

| Ref | Request | Needed for |
|---|---|---|
| PBC-01 | Purchase orders, invoices and quotation records for the sampled suppliers | T-01, T-02 |
| PBC-02 | Contract or framework agreements covering the sampled suppliers | T-01, T-03 |
| PBC-03 | Quotation records and orders for the sampled suppliers | T-02 |
| PBC-04 | Key Decision records and tender evaluation records for the sampled suppliers | T-03 |
| PBC-05 | Contract, framework or exclusion evidence for the sampled suppliers | T-04 |
| PBC-06 | Procurement route records for the sampled suppliers | T-04 |
| PBC-07 | Extension approvals or replacement contracts for the sampled suppliers | T-05 |
| PBC-08 | Contract end dates and variation records for the sampled suppliers | T-05, T-06 |
| PBC-09 | Variation approvals and current contract value for the sampled suppliers | T-06 |
| PBC-10 | Contract values and variations for suppliers skipped by the award-ratio test | T-06 |
| PBC-11 | Invoices and remittance advices for the sampled payments | T-07 |
