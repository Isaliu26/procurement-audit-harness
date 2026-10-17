---
name: builder-quirks
description: How-to lessons for writing audit-plan.json against build_pack.py
metadata:
  type: feedback
---

- Any digit in prose (amounts, "151", "R-08", "S151") is refused as a typed figure; write "the quote tier", "chief finance officer", etc. Ids like CPR-13/T-01 are fine.
- Risk ids in risk-ratings.json are under key `id`, not `risk_id`.
- Sample recipe filters apply to groups, not expanded rows; sample rows carry a `tag` column only. Sort on `candidate_notice` desc puts candidate suppliers first.
- `in` filter takes a list value. Edit audit-plan.json via json load/dump (ensure_ascii=False), not sed on £.
- Challenger tends to raise ~9 round-1 points on sample coverage, approvers named in controls, and limitations; pre-empt by naming approvers and skipped populations.
