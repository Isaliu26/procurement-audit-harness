#!/usr/bin/env python3
"""Verify outputs/rules.json produced by the extract-rules skill.

Checks:
  1. schema of the source block, every rule, excluded item, parameter and note
  2. rule IDs are sequential (CPR-01, CPR-02, ...)
  3. every threshold parameter a rule references is declared, with a null value
  4. every verbatim quote appears on its stated PDF page(s)
  5. every clause the PDF contains is either in rules or in excluded
  6. the known drafting problems of this PDF version are recorded in notes

Usage:
  verify_quotes.py [rules.json] [contract-rules.pdf]
  verify_quotes.py --inventory [contract-rules.pdf]   # list clause ids and pages

Exit codes: 0 pass, 1 errors found, 2 could not run.
Needs pdftotext and pdfinfo (poppler). Standard library only.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RULES = ROOT / "outputs" / "rules.json"
DEFAULT_PDF = ROOT / "data" / "contract-rules.pdf"

TYPES = {
    "procurement-route", "approval", "anti-avoidance", "advertising", "exception",
    "exclusion", "evaluation", "documentation", "contract-terms", "transparency",
}
EVIDENCE = {"spend_data", "contracts_register", "council_records"}
NOTE_KINDS = {"contradiction", "drafting_gap", "ambiguity"}
RULE_FIELDS = {
    "rule_id", "clause", "page", "page_end", "type", "scope", "condition",
    "threshold_low", "threshold_low_param", "threshold_low_inclusive", "threshold_low_text",
    "threshold_high", "threshold_high_param", "threshold_high_inclusive", "threshold_high_text",
    "required_action", "approver", "evidence_source", "verbatim_quote",
}
FRAGMENT_SEP = " | "
MIN_FRAGMENT = 10
MAX_REASON = 160

# Appendix A has four unlabelled value bands; rows in Appendices B and C are lettered.
APPENDIX_A_ROWS = 4
ANCHORS = {"AppC-closing": "In the interests of clarity"}

# Drafting problems found in this version of the PDF when the skill was built.
# rules.json must carry a note whose clauses include each set.
REQUIRED_NOTES = [
    ("£500,000 falls in neither Appendix B row B2 nor row C", {"AppB-B2", "AppB-C"}),
    ("clause numbering jumps 5.1.1 -> 5.2 -> 5.2.1", {"5.2"}),
    ("blank placeholders 'Parts [] (Call-In) and [] (Forward Plan)'", {"AppA-3"}),
    ("blank placeholder 'Part []' in the document title", {"1"}),
    ("garbled sentence in 7.4.2 ('provided and an exception report')", {"7.4.2"}),
]

FOOTER_RE = re.compile(r"^\s*\$\w+\.docx\b.*$")
SECTION_RE = re.compile(r"^\s{0,8}(\d{1,2})\s{2,}[A-Z]")
CLAUSE_RE = re.compile(r"^\s{0,14}(\d{1,2}(?:\.\d{1,2}){1,3})(?=\s)")
APPENDIX_RE = re.compile(r"^\s*Contract Rules - Appendix ([A-Z])\b")
ROW_RE = re.compile(r"^\s{0,6}(A|B1|B2|B|C|D|E|F)(?:\s{2,}|\s*$)")
FOOTNOTE_RE = re.compile(r"^\s{0,3}(\*{1,4})\s?\S")
RULE_ID_RE = re.compile(r"^CPR-\d{2,3}$")
PARAM_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

TRANSLATE = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", " ": " ",
    "": " ", "": " ", "•": " ",
})


def norm(text):
    """Normalise for quote matching: quotes, dashes, bullets, line-end hyphens, whitespace."""
    text = unicodedata.normalize("NFKC", text).translate(TRANSLATE)
    text = re.sub(r"-[ \t]*\n\s*", "-", text)
    return re.sub(r"\s+", " ", text).strip()


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


class Pdf:
    def __init__(self, path):
        self.path = path
        info = run(["pdfinfo", str(path)])
        self.pages = int(re.search(r"^Pages:\s+(\d+)", info, re.M).group(1))
        self.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        self.plain = {n: self._page(n, False) for n in range(1, self.pages + 1)}
        self.layout = {n: self._page(n, True) for n in range(1, self.pages + 1)}

    def _page(self, n, layout):
        cmd = ["pdftotext", "-f", str(n), "-l", str(n)] + (["-layout"] if layout else []) + [str(self.path), "-"]
        lines = [l for l in run(cmd).replace("\f", "").split("\n") if not FOOTER_RE.match(l)]
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and lines[-1].strip() == str(n):  # plain mode prints the page number on its own line
            lines.pop()
        return "\n".join(lines)

    def text(self, first, last):
        pages = range(first, last + 1)
        return (norm("\n".join(self.plain[n] for n in pages)),
                norm("\n".join(self.layout[n] for n in pages)))

    def find(self, fragment):
        f = norm(fragment)
        return [n for n in self.plain if f in self.text(n, n)[0] or f in self.text(n, n)[1]]


def inventory(pdf):
    """Clause ids in document order as (id, page, required). Sections are valid ids, not required."""
    items, appendix = [], None
    for n in range(1, pdf.pages + 1):
        for line in pdf.layout[n].split("\n"):
            m = APPENDIX_RE.match(line)
            if m:
                appendix = m.group(1)
                items.append((f"App{appendix}", n, False))
                if appendix == "A":
                    items += [(f"AppA-{i}", n, True) for i in range(1, APPENDIX_A_ROWS + 1)]
                continue
            if appendix is None:
                m = CLAUSE_RE.match(line)
                if m:
                    items.append((m.group(1), n, True))
                    continue
                m = SECTION_RE.match(line)
                if m:
                    items.append((m.group(1), n, False))
                continue
            m = ROW_RE.match(line)
            if m and appendix in "BC":
                items.append((f"App{appendix}-{m.group(1)}", n, True))
                continue
            m = FOOTNOTE_RE.match(line)
            if m and appendix == "B":
                items.append((f"AppB-note-{len(m.group(1))}", n, True))
        for cid, anchor in ANCHORS.items():
            if anchor in pdf.plain[n]:
                items.append((cid, n, True))
    seen, out = set(), []
    for item in items:
        if item[0] not in seen:
            seen.add(item[0])
            out.append(item)
    return out


def parent(cid):
    if cid.startswith("App"):
        return cid.split("-")[0] if "-" in cid else None
    return cid.rsplit(".", 1)[0] if "." in cid else None


def ancestors(cid):
    out, p = [], parent(cid)
    while p:
        out.append(p)
        p = parent(p)
    return out


def spans(inv):
    """Page span of each clause: from its label to the next clause that is not its descendant."""
    out = {}
    for i, (cid, page, _) in enumerate(inv):
        end = inv[-1][1]
        for nid, npage, _ in inv[i + 1:]:
            if cid not in ancestors(nid):
                end = npage
                break
        out[cid] = (page, max(page, end))
    return out


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def err(self, where, msg):
        self.errors.append(f"{where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"{where}: {msg}")


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def check_page_fields(r, where, obj, pdf, required=True):
    page, page_end = obj.get("page"), obj.get("page_end")
    if page is None and not required:
        return None
    if not is_int(page) or not 1 <= page <= pdf.pages:
        r.err(where, f"page must be an integer 1-{pdf.pages}, got {page!r}")
        return None
    if page_end is None:
        return page, page
    if not is_int(page_end) or not page <= page_end <= pdf.pages:
        r.err(where, f"page_end must be an integer {page}-{pdf.pages}, got {page_end!r}")
        return None
    return page, page_end


def check_quote(r, where, quote, pages, pdf):
    if not isinstance(quote, str) or not quote.strip():
        r.err(where, "verbatim_quote missing or empty")
        return
    if "..." in quote or "…" in quote:
        r.err(where, f"verbatim_quote contains an ellipsis; quote contiguous text, separating table cells with '{FRAGMENT_SEP.strip()}'")
    if pages is None:
        return
    plain, layout = pdf.text(*pages)
    for frag in quote.split(FRAGMENT_SEP):
        f = norm(frag)
        if len(f) < MIN_FRAGMENT:
            r.err(where, f"quote fragment too short to verify ({len(f)} chars): {frag!r}")
            continue
        if f in plain or f in layout:
            continue
        found = pdf.find(frag)
        hint = f"; found on page(s) {found}" if found else "; not found anywhere in the PDF"
        label = f"page {pages[0]}" if pages[0] == pages[1] else f"pages {pages[0]}-{pages[1]}"
        r.err(where, f"quote not on {label}{hint}: {frag[:70]!r}")


def check_clause_ref(r, where, cid, valid, span_of, pages):
    if not isinstance(cid, str) or not cid:
        r.err(where, f"clause must be a non-empty string, got {cid!r}")
        return False
    if cid not in valid:
        r.err(where, f"unknown clause {cid!r} (run --inventory for valid ids)")
        return False
    if pages and cid in span_of:
        lo, hi = span_of[cid]
        if not (lo <= pages[0] <= hi):
            r.err(where, f"page {pages[0]} is outside clause {cid}'s pages {lo}-{hi}")
    return True


def check_bound(r, where, rule, side, params, quote):
    val, par = rule.get(f"threshold_{side}"), rule.get(f"threshold_{side}_param")
    inc, txt = rule.get(f"threshold_{side}_inclusive"), rule.get(f"threshold_{side}_text")
    if val is not None and (not is_int(val) or val < 0):
        r.err(where, f"threshold_{side} must be a non-negative GBP integer or null, got {val!r}")
    if par is not None:
        if not isinstance(par, str) or par not in params:
            r.err(where, f"threshold_{side}_param {par!r} is not declared in parameters")
    if val is not None and par is not None:
        r.err(where, f"threshold_{side} and threshold_{side}_param are both set; use one")
    if val is None and par is None:
        if inc is not None or txt is not None:
            r.err(where, f"threshold_{side}_inclusive/_text must be null when the bound is open")
        return
    if not isinstance(inc, bool):
        r.err(where, f"threshold_{side}_inclusive must be true or false when the bound is set")
    if not isinstance(txt, str) or not txt.strip():
        r.err(where, f"threshold_{side}_text (the bound as printed) is required when the bound is set")
    elif isinstance(quote, str) and norm(txt) not in norm(quote):
        r.err(where, f"threshold_{side}_text {txt!r} does not appear in verbatim_quote")


def check_rules(r, data, pdf, valid, span_of):
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        r.err("rules", "must be a non-empty list")
        return []
    params = data.get("parameters") if isinstance(data.get("parameters"), dict) else {}
    width = 3 if len(rules) > 99 else 2
    for i, rule in enumerate(rules, 1):
        where = f"rules[{i - 1}]"
        if not isinstance(rule, dict):
            r.err(where, "must be an object")
            continue
        rid = rule.get("rule_id")
        where = f"{rid or where}"
        expected = f"CPR-{i:0{width}d}"
        if not isinstance(rid, str) or not RULE_ID_RE.match(rid):
            r.err(where, f"rule_id must look like {expected}, got {rid!r}")
        elif rid != expected:
            r.err(where, f"rule_id out of sequence: expected {expected}")
        for extra in sorted(set(rule) - RULE_FIELDS):
            r.warn(where, f"unexpected field {extra!r}")
        pages = check_page_fields(r, where, rule, pdf)
        check_clause_ref(r, where, rule.get("clause"), valid, span_of, pages)
        if rule.get("type") not in TYPES:
            r.err(where, f"type must be one of {sorted(TYPES)}, got {rule.get('type')!r}")
        for field in ("scope", "condition", "required_action"):
            if not isinstance(rule.get(field), str) or not rule[field].strip():
                r.err(where, f"{field} must be a non-empty string")
        if "approver" not in rule or not (rule["approver"] is None or (isinstance(rule["approver"], str) and rule["approver"].strip())):
            r.err(where, "approver must be a non-empty string or null")
        ev = rule.get("evidence_source")
        if not isinstance(ev, list) or not ev or not set(ev) <= EVIDENCE:
            r.err(where, f"evidence_source must be a non-empty list drawn from {sorted(EVIDENCE)}, got {ev!r}")
        quote = rule.get("verbatim_quote")
        check_quote(r, where, quote, pages, pdf)
        for side in ("low", "high"):
            check_bound(r, where, rule, side, params, quote)
        lo, hi = rule.get("threshold_low"), rule.get("threshold_high")
        if is_int(lo) and is_int(hi) and lo >= hi:
            r.err(where, f"threshold_low {lo} must be below threshold_high {hi}")
        if isinstance(quote, str) and re.search(r"\bThreshold\b", quote) \
                and not rule.get("threshold_low_param") and not rule.get("threshold_high_param"):
            r.warn(where, "quote names 'Threshold' but no threshold parameter is referenced")
    if not any(isinstance(x, dict) and x.get("type") == "anti-avoidance" for x in rules):
        r.err("rules", "no rule has type 'anti-avoidance' (CLAUDE.md requires the no-splitting rule to be flagged)")
    return rules


def check_parameters(r, data, rules, pdf, valid):
    params = data.get("parameters")
    if not isinstance(params, dict):
        r.err("parameters", "must be an object (use {} if the PDF names no unquantified thresholds)")
        return
    used = {x.get(f"threshold_{s}_param") for x in rules if isinstance(x, dict) for s in ("low", "high")} - {None}
    for key, p in params.items():
        where = f"parameters.{key}"
        if not PARAM_KEY_RE.match(key):
            r.err(where, "key must be UPPER_SNAKE_CASE")
        if not isinstance(p, dict):
            r.err(where, "must be an object")
            continue
        if "value" not in p:
            r.err(where, "value field missing (must be null)")
        elif p["value"] is not None and not (isinstance(p.get("value_source"), str) and p["value_source"].strip()):
            r.err(where, "value must be null; the PDF does not print it (only a human may set it, with value_source)")
        for field in ("printed_as", "defined_in"):
            if not isinstance(p.get(field), str) or not p[field].strip():
                r.err(where, f"{field} must be a non-empty string")
        if isinstance(p.get("defined_in"), str) and p["defined_in"] not in valid:
            r.err(where, f"defined_in {p['defined_in']!r} is not a clause id")
        pages = check_page_fields(r, where, p, pdf)
        if pages and isinstance(p.get("printed_as"), str) and norm(p["printed_as"]) not in pdf.text(*pages)[0]:
            r.err(where, f"printed_as {p['printed_as']!r} not found on page {pages[0]}")
        if key not in used:
            r.warn(where, "declared but not referenced by any rule")


def check_excluded(r, data, pdf, valid, span_of):
    excluded = data.get("excluded")
    if not isinstance(excluded, list):
        r.err("excluded", "must be a list")
        return []
    ids = []
    for i, x in enumerate(excluded):
        where = f"excluded[{i}]"
        if not isinstance(x, dict):
            r.err(where, "must be an object")
            continue
        if ("clause" in x) == ("clauses" in x):
            r.err(where, "give exactly one of clause or clauses")
            continue
        cids = [x["clause"]] if "clause" in x else x["clauses"]
        if not isinstance(cids, list) or not cids:
            r.err(where, "clauses must be a non-empty list")
            continue
        pages = check_page_fields(r, where, x, pdf)
        for cid in cids:
            if check_clause_ref(r, f"{where} {cid}", cid, valid, span_of, pages if len(cids) == 1 else None):
                ids.append(cid)
        reason = x.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            r.err(where, "reason must be a non-empty string")
        elif "\n" in reason or len(reason) > MAX_REASON:
            r.err(where, f"reason must be one line of at most {MAX_REASON} characters")
    return ids


def check_notes(r, data, pdf, valid):
    notes = data.get("notes")
    if not isinstance(notes, list):
        r.err("notes", "must be a list (use [] if there are none)")
        return
    for i, n in enumerate(notes):
        where = f"notes[{i}]"
        if not isinstance(n, dict):
            r.err(where, "must be an object")
            continue
        if n.get("kind") not in NOTE_KINDS:
            r.err(where, f"kind must be one of {sorted(NOTE_KINDS)}, got {n.get('kind')!r}")
        cids = n.get("clauses")
        if not isinstance(cids, list) or not cids:
            r.err(where, "clauses must be a non-empty list")
        else:
            for cid in cids:
                if cid not in valid:
                    r.err(where, f"unknown clause {cid!r}")
        pages = check_page_fields(r, where, n, pdf)
        if not isinstance(n.get("note"), str) or not n["note"].strip():
            r.err(where, "note must be a non-empty string")
        if "verbatim_quote" in n:
            check_quote(r, where, n["verbatim_quote"], pages, pdf)
    noted = [set(n["clauses"]) for n in notes if isinstance(n, dict) and isinstance(n.get("clauses"), list)]
    for label, cids in REQUIRED_NOTES:
        if not any(cids <= s for s in noted):
            r.err("notes", f"missing required note: {label} (clauses must include {sorted(cids)})")


def check_coverage(r, inv, rule_ids, excluded_ids):
    ruled, excl = set(rule_ids), set(excluded_ids)
    for cid in sorted(ruled & excl):
        r.err(f"clause {cid}", "appears in both rules and excluded")
    for cid in excl:
        kids = [x for x in ruled if cid in ancestors(x)]
        if kids:
            r.warn(f"clause {cid}", f"excluded, but descendants {sorted(kids)} are rules; the reason must cover only the stem")
    covered = ruled | excl
    for cid, page, required in inv:
        if required and cid not in covered and not any(a in covered for a in ancestors(cid)):
            r.err(f"clause {cid} (page {page})", "in neither rules nor excluded")


def check_source(r, data, pdf):
    src = data.get("source")
    if not isinstance(src, dict):
        r.err("source", "must be an object with file, pages and sha256")
        return
    if src.get("pages") != pdf.pages:
        r.err("source", f"pages is {src.get('pages')!r} but the PDF has {pdf.pages}")
    if src.get("sha256") != pdf.sha256:
        r.err("source", "sha256 does not match the PDF; rules.json was built from a different file")
    if not isinstance(src.get("file"), str):
        r.err("source", "file must be the PDF path")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inventory", action="store_true", help="print the clause ids the PDF contains, then exit")
    ap.add_argument("paths", nargs="*", help="[rules.json] [pdf], or [pdf] with --inventory")
    args = ap.parse_args()

    for tool in ("pdftotext", "pdfinfo"):
        if not shutil.which(tool):
            print(f"ERROR: {tool} not found; install poppler.", file=sys.stderr)
            return 2

    if args.inventory:
        pdf_path = Path(args.paths[0]) if args.paths else DEFAULT_PDF
        rules_path = None
    else:
        rules_path = Path(args.paths[0]) if args.paths else DEFAULT_RULES
        pdf_path = Path(args.paths[1]) if len(args.paths) > 1 else DEFAULT_PDF
    for p in filter(None, (pdf_path, rules_path)):
        if not p.is_file():
            print(f"ERROR: {p} not found.", file=sys.stderr)
            return 2

    pdf = Pdf(pdf_path)
    inv = inventory(pdf)
    missing_anchors = [cid for cid in ANCHORS if cid not in {i[0] for i in inv}]

    if args.inventory:
        for cid, page, required in inv:
            print(f"{cid}\t{page}" + ("" if required else "\t(section heading; optional)"))
        print(f"{sum(1 for i in inv if i[2])} clauses to classify, {pdf.pages} pages")
        for cid in missing_anchors:
            print(f"WARNING: expected item {cid} not found; the PDF may have changed", file=sys.stderr)
        return 0

    try:
        data = json.loads(rules_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FAIL: {rules_path} is not valid JSON: {e}")
        return 1
    r = Report()
    if not isinstance(data, dict):
        print("FAIL: top level must be an object with source, parameters, rules, excluded, notes")
        return 1
    for extra in sorted(set(data) - {"source", "parameters", "rules", "excluded", "notes"}):
        r.warn("top level", f"unexpected key {extra!r}")
    for cid in missing_anchors:
        r.warn(cid, "expected item not found in the PDF; it may have changed")

    valid = {cid for cid, _, _ in inv}
    span_of = spans(inv)
    check_source(r, data, pdf)
    rules = check_rules(r, data, pdf, valid, span_of)
    check_parameters(r, data, rules, pdf, valid)
    excluded_ids = check_excluded(r, data, pdf, valid, span_of)
    check_notes(r, data, pdf, valid)
    check_coverage(r, inv, [x.get("clause") for x in rules if isinstance(x, dict)], excluded_ids)

    for w in r.warnings:
        print(f"WARN  {w}")
    for e in r.errors:
        print(f"ERROR {e}")
    n_ex = len(data.get("excluded") or []) if isinstance(data.get("excluded"), list) else 0
    summary = (f"{len(rules)} rules, {n_ex} excluded entries, "
               f"{len(data.get('parameters') or {})} parameters, {len(data.get('notes') or [])} notes")
    if r.errors:
        print(f"FAIL: {len(r.errors)} error(s), {len(r.warnings)} warning(s). {summary}")
        return 1
    print(f"PASS: {len(r.warnings)} warning(s). {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
