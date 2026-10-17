# Auditor comments: risk register decisions

Register version: v2. Complete the **Decision** and **Comment** columns, then ask for the risk-assessor to be re-run. Do not edit the Risk ids or the header row. Avoid the `|` character in comments.

| Decision | Meaning | Comment needed |
|---|---|---|
| APPROVE | Keep this risk as rated, in scope | no |
| REJECT | Remove this risk from the register | optional |
| REVISE | Agent must change this risk as the Comment asks | yes: what to change |
| OVERRIDE | Auditor sets the rating; the register marks it | yes: `likelihood=N` and/or `impact=N` |

| Risk | Title | Rating | Decision | Comment |
|---|---|---|---|---|
| R-01 | Same-supplier payments combining past the quote threshold | 20 Extreme (Red) | APPROVE |  |
| R-04 | Spend with suppliers having no council contract notice | 20 Extreme (Red) | APPROVE |  |
| R-02 | Low-value payments clustering and combining at the lowest quote boundary | 15 Extreme (Red) | APPROVE |  |
| R-03 | Combined payments approaching the high-value approval and tender tier | 15 Extreme (Red) | APPROVE |  |
| R-06 | Spend running above the awarded contract value | 15 Extreme (Red) | APPROVE |  |
| R-05 | Payments after the only matching notice has ended | 12 Medium - High (Amber) ⚑ | OVERRIDE | likelihood=4. Paying suppliers after their only notice has ended points to contracts rolling on without re-procurement, which is common in practice. |
| R-07 | Possible duplicate payments | 8 Medium - High (Amber) | APPROVE | Keep likelihood at 2: no Contract Procedure Rule covers duplicates, and many identical rows may be export artefacts. |
| R-08 | Care and education placement spend without a published notice | removed | REJECT | Care placements recur by design and will be covered by a separate social care commissioning review. |
