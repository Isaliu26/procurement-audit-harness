#!/usr/bin/env python3
"""Number check: every figure of three or more digits, or with a £ sign, in planning-memo.md,
risk-control-matrix.md and audit-program.md must be a value in analytics.json, pack-figures.json,
rules.json or outputs/samples/*.csv (rounded the way the builder prints it).
Skipped: row ids, rule/test/control/risk/audit ids, dates, years, clause and page references,
hex digests, and figures glued to letters (names such as 1ST CHOICE).
Usage: check_numbers.py [--root DIR]"""
import bisect
import csv
import re
import sys

from _util import DOCS, cli, load_json, need, result

NUM = re.compile(r"(?<![\w.,])(£?)(\d[\d,]*(?:\.\d+)?)(%?)(?![\w])")
STRIP = [
    re.compile(r"[\w.-]+_published:\d+"),                          # spend row ids
    re.compile(r"\b[A-Za-z]{1,6}-\d+[\w-]*"),                      # CPR-13, T-01, C-02, R-03, PBC-04, AUD-01
    re.compile(r"\bcl\.\s*[\w.-]+"),                               # clause references
    re.compile(r"\b[Pp]ages?\s+\d+(?:\s*[-–]\s*\d+)?"),            # page references
    re.compile(r"\bsha256\s+[0-9a-f]+"), re.compile(r"\b[0-9a-f]{8,}\b"),  # digests
    re.compile(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?"),  # ISO dates and times
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),                    # D/M/Y dates
    re.compile(r"\bv\d+\b"),                                       # versions
    re.compile(r"`[^`]*\.(?:csv|json|md|py)`"),                    # file names in code spans
]
YEAR = re.compile(r"(?:19|20)\d{2}")
DIG = re.compile(r"\d")


def leaves(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from leaves(v)
    elif isinstance(o, list):
        for v in o:
            yield from leaves(v)
    else:
        yield o


def allowed_values(root):
    vals = []
    out = root / "outputs"

    def add(x):
        vals.append(float(x))
        if 0 < abs(x) <= 1 and not float(x).is_integer():
            vals.append(float(x) * 100)           # |pct

    sources = [load_json(need(out / "analytics.json")), load_json(need(out / "pack-figures.json")),
               load_json(need(out / "rules.json"))]
    for src in sources:
        for v in leaves(src):
            if isinstance(v, bool) or v is None:
                continue
            if isinstance(v, (int, float)):
                add(v)
            elif isinstance(v, str):
                for m in re.findall(r"\d[\d,]*(?:\.\d+)?", v):
                    try:
                        add(float(m.replace(",", "")))
                    except ValueError:
                        pass
    n_csv = 0
    for f in sorted((out / "samples").glob("*.csv")):
        n_csv += 1
        with open(f, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                for v in row.values():
                    for m in re.findall(r"\d[\d,]*(?:\.\d+)?", v or ""):
                        add(float(m.replace(",", "")))
    return sorted(set(vals)), n_csv


def matches(sorted_vals, x, decimals):
    tol = 0.5 + 1e-9 if decimals == 0 else 0.5 * 10 ** -decimals + 1e-9
    i = bisect.bisect_left(sorted_vals, x - tol)
    return i < len(sorted_vals) and sorted_vals[i] <= x + tol


def run(root, final=False):
    r = result("numbers")
    vals, n_csv = allowed_values(root)
    r["notes"].append(f"{len(vals):,} distinct allowed values from analytics, pack-figures, rules and {n_csv} sample file(s)")
    for doc in DOCS:
        text = need(root / "outputs" / doc).read_text(encoding="utf-8")
        for ln_no, line in enumerate(text.splitlines(), 1):
            for pat in STRIP:
                line = pat.sub(" ", line)
            for m in NUM.finditer(line):
                pound, body, pct = m.groups()
                digits = len(DIG.findall(body))
                if digits < 3 and not pound:
                    continue
                if not pound and not pct and "." not in body and "," not in body and YEAR.fullmatch(body):
                    continue                                          # a year
                r["checked"] += 1
                x = float(body.replace(",", ""))
                dec = len(body.split(".")[1]) if "." in body else 0
                if not matches(vals, x, dec):
                    r["failures"].append(f"{doc}:{ln_no}: {pound}{body}{pct} is not a value in analytics.json, "
                                         "pack-figures.json, rules.json or outputs/samples/*.csv")
    return r


if __name__ == "__main__":
    sys.exit(cli("numbers", run))
