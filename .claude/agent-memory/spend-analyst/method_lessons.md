---
name: spend-analyst-method-lessons
description: Parsing quirks and pitfalls for the WBC spend and Contracts Finder data (method only, no evidence)
metadata:
  type: feedback
---

- Run Python with `-I`: it drops the script dir from sys.path, so each script needs `sys.path.insert(0, dirname(__file__))` before sibling imports.
- Spend workbooks: header is row 1 in some files and row 2 in others; one file has trailing blank rows. Excel row number = list index + 1 when reading with iter_rows from row 1.
- contracts.csv `Published Date` has mixed UTC offsets (+00:00 / +01:00): pandas gives an object column, so take `.year` per element, not `.dt`.
- Redacted supplier rows are numerous (mostly Transfer Payment care allowances); exclude and report by category and tag.
- Council-tax narratives with supplier "West Berkshire Council" fall under pension_statutory (checked before internal), so `internal` can be 0.
- Inclusive flags: the 1,000 and 500,000 values are exclusive lower bounds, 25,000 inclusive; derive "reaches tier" from the stored lower-bound flag.
