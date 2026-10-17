"""Shared helpers for the QA checks. Each check module exposes run(root, final=False) returning
a result dict: {name, checked, failures[list of str], pending[list of str], notes[list of str]}.
A check never fixes or softens anything: it reports what it found."""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VERIFIER = REPO / ".claude" / "skills" / "extract-rules" / "verify_quotes.py"
DOCS = ("planning-memo.md", "risk-control-matrix.md", "audit-program.md")
CITE_RULE = re.compile(r"\[rule:([^\]\s]+)(?:\s*\(cl\.\s*([^)]*)\))?")
IN_SCOPE = {"APPROVE", "OVERRIDE"}


class MissingInput(Exception):
    pass


def result(name):
    return {"name": name, "checked": 0, "failures": [], "pending": [], "notes": []}


def need(path, what=None):
    p = Path(path)
    if not p.exists():
        raise MissingInput(f"{what or p.name} not found ({p}); the pack has not been built or an input is missing")
    return p


def load_json(path, what=None):
    p = need(path, what)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise MissingInput(f"{p.name} is not valid JSON: {e}")


def parse_md_table(text, must_have):
    """First table whose header row contains every name in must_have -> list of dicts (lower-cased keys)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]
        low = [c.lower() for c in cells]
        if all(m in low for m in must_have):
            rows = []
            for ln in lines[i + 2:]:
                if not ln.startswith("|"):
                    break
                vals = [c.strip() for c in re.split(r"(?<!\\)\|", ln.strip())[1:-1]]
                rows.append(dict(zip(low, vals + [""] * (len(low) - len(vals)))))
            return rows
    return None


def cli(name, run_fn):
    ap = argparse.ArgumentParser(description=f"QA check: {name}")
    ap.add_argument("--root", default=str(REPO), help="project root holding data/ and outputs/")
    ap.add_argument("--final", action="store_true", help="also require challenges.md to be complete")
    a = ap.parse_args()
    res = safe_run(name, run_fn, Path(a.root), a.final)
    print(format_result(res))
    return 1 if res["failures"] else 0


def safe_run(name, run_fn, root, final):
    try:
        return run_fn(root, final)
    except MissingInput as e:
        r = result(name)
        r["failures"].append(f"NOT RUN: {e}")
        return r


def format_result(r):
    status = "FAIL" if r["failures"] else "PASS"
    L = [f"{r['name']}: {status} ({r['checked']} checked, {len(r['failures'])} failure(s)"
         + (f", {len(r['pending'])} pending" if r["pending"] else "") + ")"]
    L += [f"  FAIL {x}" for x in r["failures"]] + [f"  PENDING {x}" for x in r["pending"]] \
        + [f"  note {x}" for x in r["notes"]]
    return "\n".join(L)
