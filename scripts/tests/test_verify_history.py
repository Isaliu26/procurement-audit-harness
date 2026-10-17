#!/usr/bin/env python3
"""Plant one error at a time in a copy of the clean fixture; verify_history must
reject each with the expected message, and must pass the untouched fixture.
Run: .venv/bin/python scripts/tests/test_verify_history.py   (exit 0 = all behave)"""
import copy, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from verify_history import verify  # noqa: E402

base = json.loads((HERE / "fixtures" / "history_fixture.json").read_text())


def plant(fn):
    h = copy.deepcopy(base)
    fn(h)
    return h


CASES = [
    ("wrong page", lambda h: h["audits"][0].update(pdf_page=2), "quote not verified"),
    ("page out of range", lambda h: h["audits"][0].update(pdf_page=9), "outside 1.."),
    ("one word altered", lambda h: h["audits"][0].update(quote=h["audits"][0]["quote"].replace("Reasonable", "Reasonible")), "not on page"),
    ("quote swapped to another real opinion", lambda h: h["audits"][0].update(quote=h["audits"][0]["quote"].replace("Reasonable", "Substantial")), "not in its own quote"),
    ("invented quote", lambda h: h["risk_themes"][0].update(quote="Procurement fraud is rife | across the council"), "not on page"),
    ("fragments out of order", lambda h: h["audits"][0].update(quote="Reasonable Assurance | Contract Letting"), "page order"),
    ("empty quote", lambda h: h["audits"][1].update(quote="  "), "quote missing or empty"),
    ("missing quote key on item", lambda h: h["follow_ups"][0].pop("quote"), "quote missing"),
    ("missing source_file", lambda h: h["advisory_work"][0].pop("source_file"), "missing source_file"),
    ("source file not in data/committee", lambda h: h["audits"][0].update(source_file="nope.pdf"), "not found"),
    ("title not in quote", lambda h: h["audits"][0].update(audit_title="Accounts Payable"), "not in its own quote"),
    ("opinion not in quote", lambda h: h["audits"][0].update(opinion="Substantial Assurance"), "not in its own quote"),
    ("scoring field on an item", lambda h: h["audits"][0].update(rating="High"), "records, never scores"),
    ("duplicate id", lambda h: h["audits"][1].update(id="AUD-01"), "duplicate id"),
    ("missing id", lambda h: h["audits"][1].pop("id"), "missing id"),
    ("wrong sha256", lambda h: h["sources"][0].update(sha256="0" * 64), "sha256"),
    ("wrong page count", lambda h: h["sources"][0].update(pages=99), "but the PDF has"),
    ("committee PDF not listed", lambda h: h["sources"].pop(), "not listed"),
    ("missing section", lambda h: h.pop("gaps"), "missing top-level section"),
    ("usable method with no matrix", lambda h: h["scoring_method"].update(matrix=[]), "scoring_method.matrix"),
    ("unusable method with no reason", lambda h: h["scoring_method"].update(usable=False), "no 'reason'"),
    ("bad evidence quote in discrepancy", lambda h: h["discrepancies"][0]["evidence"][0].update(quote="Medium (7)"), "not on page"),
    ("discrepancy without evidence", lambda h: h["discrepancies"][0].update(evidence=[]), "evidence"),
    ("discrepancy resolved", lambda h: h["discrepancies"][0].update(resolution="typo"), "not resolved"),
    ("gap without looked_in", lambda h: h["gaps"][0].pop("looked_in"), "looked_in"),
    ("fragment too short to verify", lambda h: h["scoring_method"]["matrix"][0].update(quote="5 | 10"), "too short"),
]

failed = 0
errs = verify(base)
print(("ok  " if not errs else "BAD ") + "clean fixture passes", errs[:3] if errs else "")
failed += bool(errs)
for name, fn, expect in CASES:
    errs = verify(plant(fn))
    hit = any(expect in e for e in errs)
    print(("ok  " if hit else "BAD ") + f"{name}: " + ("caught" if hit else f"NOT caught (wanted {expect!r}, got {errs[:2]})"))
    failed += not hit
print(f"{len(CASES) + 1 - failed}/{len(CASES) + 1} behave as expected")
sys.exit(1 if failed else 0)
