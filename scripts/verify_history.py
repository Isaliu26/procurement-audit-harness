#!/usr/bin/env python3
"""Verify outputs/history.json produced by the findings-analyst.

Checks:
  1. structure: required top-level sections, source list, item fields, unique ids
  2. every source file exists in data/committee, its sha256 and page count match
  3. every quote sits on its stated pdf_page (1-based physical page), copy-exact
     apart from whitespace. A table quote is fragments joined by ' | ', each
     fragment found on that page, in order. Plain and -layout text are both tried
  4. an item's audit_title / opinion fields appear inside its own quote
  5. no scoring: records carry no rating, score, priority or similar field
  6. every discrepancy has evidence that verifies; every gap says where it looked

Usage:
  verify_history.py [history.json]
Exit codes: 0 pass, 1 errors found, 2 could not run.
Needs pdftotext and pdfinfo (poppler). Standard library only.
"""
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY = ROOT / "outputs" / "history.json"
COMMITTEE_DIR = "data/committee"

SECTIONS = ["sources", "audits", "follow_ups", "advisory_work", "agreed_actions",
            "risk_themes", "scoring_method", "discrepancies", "gaps"]
ITEM_SECTIONS = ["audits", "follow_ups", "advisory_work", "agreed_actions", "risk_themes"]
SCORING_PARTS = ["impact_scale", "likelihood_scale", "matrix", "bands", "appetite", "escalation"]
# Records never score: none of these may appear on a recorded item.
FORBIDDEN_KEYS = {"rating", "risk_rating", "score", "risk_score", "priority", "severity",
                  "risk_level", "likelihood", "impact", "rag", "assessment"}
FRAGMENT_SEP = " | "
MIN_FRAGMENT = 3
SOURCE_FIELDS = {"file", "pages", "sha256"}


def norm(text):
    """NFKC (ligatures) and collapse whitespace. Case and punctuation are kept."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


class Pdfs:
    def __init__(self, root):
        self.root = Path(root)
        self._pages = {}
        self._text = {}

    def path(self, name):
        return self.root / COMMITTEE_DIR / name

    def pages(self, name):
        if name not in self._pages:
            out = subprocess.run(["pdfinfo", str(self.path(name))], capture_output=True, text=True)
            m = re.search(r"^Pages:\s+(\d+)", out.stdout, re.M)
            if out.returncode or not m:
                raise RuntimeError(f"pdfinfo failed on {name}: {out.stderr.strip()}")
            self._pages[name] = int(m.group(1))
        return self._pages[name]

    def text(self, name, page, layout):
        key = (name, page, layout)
        if key not in self._text:
            cmd = ["pdftotext", "-f", str(page), "-l", str(page)] + (["-layout"] if layout else [])
            out = subprocess.run(cmd + [str(self.path(name)), "-"], capture_output=True, text=True)
            if out.returncode:
                raise RuntimeError(f"pdftotext failed on {name} p{page}: {out.stderr.strip()}")
            self._text[key] = norm(out.stdout)
        return self._text[key]


def fragments(quote):
    return [norm(f) for f in quote.split(FRAGMENT_SEP)]


def in_order(text, frags):
    pos = 0
    for f in frags:
        i = text.find(f, pos)
        if i < 0:
            return False
        pos = i + len(f)
    return True


def check_quote(pdfs, where, rec, errors):
    """Check rec['source_file'], rec['pdf_page'], rec['quote']. Return True if usable."""
    name, page, quote = rec.get("source_file"), rec.get("pdf_page"), rec.get("quote")
    if not isinstance(name, str) or not name:
        errors.append(f"{where}: missing source_file")
        return False
    if not isinstance(page, int) or isinstance(page, bool):
        errors.append(f"{where}: pdf_page must be an integer")
        return False
    if not isinstance(quote, str) or not quote.strip():
        errors.append(f"{where}: quote missing or empty")
        return False
    if not pdfs.path(name).is_file():
        errors.append(f"{where}: source_file {name!r} not found in {COMMITTEE_DIR}")
        return False
    n = pdfs.pages(name)
    if not 1 <= page <= n:
        errors.append(f"{where}: pdf_page {page} outside 1..{n} for {name}")
        return False
    frags = fragments(quote)
    short = [f for f in frags if len(f) < MIN_FRAGMENT]
    if short:
        errors.append(f"{where}: quote fragment too short to verify: {short[0]!r}")
        return False
    if not any(in_order(pdfs.text(name, page, lay), frags) for lay in (False, True)):
        missing = [f for f in frags if not any(f in pdfs.text(name, page, lay) for lay in (False, True))]
        why = f"fragment not on page: {missing[0]!r}" if missing else "fragments not in page order"
        errors.append(f"{where}: quote not verified on {name} p{page} ({why})")
        return False
    return True


def walk_quotes(node, path):
    """Yield (path, dict) for every dict that has a 'quote' key."""
    if isinstance(node, dict):
        if "quote" in node:
            yield path, node
        for k, v in node.items():
            yield from walk_quotes(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_quotes(v, f"{path}[{i}]")


def contains_forbidden(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k.lower() in FORBIDDEN_KEYS:
                return k
            hit = contains_forbidden(v)
            if hit:
                return hit
    elif isinstance(node, list):
        for v in node:
            hit = contains_forbidden(v)
            if hit:
                return hit
    return None


def verify(history, root=ROOT):
    errors = []
    pdfs = Pdfs(root)
    if not isinstance(history, dict):
        return ["history.json must be a JSON object"]

    for s in SECTIONS:
        if s not in history:
            errors.append(f"missing top-level section {s!r}")
    if errors:
        return errors

    # 1-2. sources
    declared = set()
    for i, src in enumerate(history["sources"]):
        w = f"sources[{i}]"
        if not isinstance(src, dict) or not SOURCE_FIELDS <= src.keys():
            errors.append(f"{w}: needs {sorted(SOURCE_FIELDS)}")
            continue
        p = pdfs.path(src["file"])
        if not p.is_file():
            errors.append(f"{w}: {src['file']!r} not found in {COMMITTEE_DIR}")
            continue
        declared.add(src["file"])
        if hashlib.sha256(p.read_bytes()).hexdigest() != src["sha256"]:
            errors.append(f"{w}: sha256 does not match {src['file']}")
        if pdfs.pages(src["file"]) != src["pages"]:
            errors.append(f"{w}: pages {src['pages']} but the PDF has {pdfs.pages(src['file'])}")
    on_disk = {p.name for p in (Path(root) / COMMITTEE_DIR).glob("*.pdf")}
    for name in sorted(on_disk - declared):
        errors.append(f"sources: {name} is in {COMMITTEE_DIR} but not listed")

    # item sections: ids, quotes, no scoring, title/opinion inside the quote
    seen = set()
    for sec in ITEM_SECTIONS:
        if not isinstance(history[sec], list):
            errors.append(f"{sec}: must be a list")
            continue
        for i, item in enumerate(history[sec]):
            w = f"{sec}[{i}]"
            if not isinstance(item, dict):
                errors.append(f"{w}: must be an object")
                continue
            iid = item.get("id")
            if not iid:
                errors.append(f"{w}: missing id")
            elif iid in seen:
                errors.append(f"{w}: duplicate id {iid!r}")
            seen.add(iid)
            bad = contains_forbidden(item)
            if bad:
                errors.append(f"{w}: scoring field {bad!r}: the analyst records, never scores")
            if check_quote(pdfs, f"{w} ({iid})", item, errors):
                flat = norm(item["quote"].replace(FRAGMENT_SEP, " "))
                for field in ("audit_title", "opinion", "opinion_report", "opinion_implementation"):
                    val = item.get(field)
                    if val is not None and norm(val) not in flat:
                        errors.append(f"{w} ({iid}): {field} {val!r} is not in its own quote")

    # scoring method
    sm = history["scoring_method"]
    if not isinstance(sm, dict) or not isinstance(sm.get("usable"), bool):
        errors.append("scoring_method: needs a boolean 'usable'")
    elif sm["usable"]:
        for part in SCORING_PARTS:
            if not sm.get(part):
                errors.append(f"scoring_method.{part}: empty, but usable is true")
    elif not sm.get("reason"):
        errors.append("scoring_method: usable is false but no 'reason' given")

    # 3. every quote anywhere (scoring method, discrepancy evidence, ...)
    done = {id(x) for sec in ITEM_SECTIONS for x in history[sec] if isinstance(x, dict)}
    for path, rec in walk_quotes(history, "$"):
        if id(rec) not in done:
            check_quote(pdfs, path, rec, errors)

    # 6. discrepancies and gaps
    for i, d in enumerate(history["discrepancies"]):
        w = f"discrepancies[{i}]"
        if not d.get("id") or not d.get("description"):
            errors.append(f"{w}: needs id and description")
        ev = d.get("evidence")
        if not isinstance(ev, list) or not ev:
            errors.append(f"{w}: needs a non-empty evidence list")
        if "resolution" in d or "resolved" in d:
            errors.append(f"{w}: discrepancies are recorded, not resolved")
    for i, g in enumerate(history["gaps"]):
        w = f"gaps[{i}]"
        if not g.get("id") or not g.get("what"):
            errors.append(f"{w}: needs id and what")
        if not isinstance(g.get("looked_in"), list) or not g["looked_in"]:
            errors.append(f"{w}: needs looked_in (the files searched)")
    return errors


def main(argv):
    for tool in ("pdftotext", "pdfinfo"):
        if not shutil.which(tool):
            print(f"cannot run: {tool} not installed (poppler)", file=sys.stderr)
            return 2
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_HISTORY
    try:
        history = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"cannot run: {path}: {e}", file=sys.stderr)
        return 2
    try:
        errors = verify(history)
    except RuntimeError as e:
        print(f"cannot run: {e}", file=sys.stderr)
        return 2
    n = sum(1 for _ in walk_quotes(history, "$"))
    if errors:
        print(f"FAIL: {len(errors)} problem(s) in {path.name} ({n} quotes checked)")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"PASS: {path.name}: {n} quotes verified on their stated pages")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
