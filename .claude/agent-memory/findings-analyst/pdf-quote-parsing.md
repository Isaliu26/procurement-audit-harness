---
name: pdf-quote-parsing
description: How to build verifier-passing table quotes from the committee PDFs (plain vs -layout order)
metadata:
  type: feedback
---

The verifier tries plain text then -layout, whole quote must match ONE mode in fragment order. Wrapped cells (e.g. title continues after the opinion column in layout) break the audit_title-inside-quote check in layout mode; switch to plain mode order (title, then opinion) for those rows.

**Why:** Q3 "Recruitment ... Retention" and "Westwood Farm / Limited Assurance" failed in layout order.
**How to apply:** build quotes in a script (scripts/build_history.py), run verify_history.py, flip fragment order per failure. Single-char scores (1-5) cannot be fragments; keep them as fields.
