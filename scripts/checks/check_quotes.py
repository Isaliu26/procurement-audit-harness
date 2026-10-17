#!/usr/bin/env python3
"""Quote check: (1) run the extract-rules verifier on outputs/rules.json against
data/contract-rules.pdf (every verbatim_quote on its stated page, schema, clause coverage);
(2) every rule citation in risk-register.md names a rule in rules.json with the same clause,
and every quoted excerpt in the register (a line starting '> ') is text from that rule's
verbatim_quote. Usage: check_quotes.py [--root DIR]"""
import re
import subprocess
import sys

from _util import CITE_RULE, VERIFIER, cli, load_json, need, result


def norm(s):
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("‘", "'").replace("“", '"')
                  .replace("”", '"')).strip().lower()


def run(root, final=False):
    r = result("quotes")
    rules_p, pdf = need(root / "outputs" / "rules.json"), need(root / "data" / "contract-rules.pdf")
    reg_p = need(root / "outputs" / "risk-register.md")
    rules = {x["rule_id"]: x for x in load_json(rules_p)["rules"]}

    proc = subprocess.run([sys.executable, "-I", str(need(VERIFIER, "verify_quotes.py")), str(rules_p), str(pdf)],
                          capture_output=True, text=True)
    lines = [l for l in (proc.stdout + proc.stderr).splitlines() if l.strip()]
    r["checked"] += len(rules)
    if proc.returncode != 0:
        r["failures"] += [f"verify_quotes.py exit {proc.returncode}: {l}" for l in lines
                          if not l.startswith("WARN")][:25] or [f"verify_quotes.py exit {proc.returncode}"]
    summary = next((l for l in reversed(lines) if l.startswith(("PASS", "FAIL"))), "")
    r["notes"].append(f"verify_quotes.py: {summary or 'no summary line'}")

    text = reg_p.read_text(encoding="utf-8")
    n_cites = n_excerpts = 0
    for ln_no, line in enumerate(text.splitlines(), 1):
        for m in CITE_RULE.finditer(line):
            rid, clause = m.group(1), (m.group(2) or "").strip()
            n_cites += 1
            if rid not in rules:
                r["failures"].append(f"risk-register.md:{ln_no}: [rule:{rid}] is not in rules.json")
            elif clause and clause != str(rules[rid]["clause"]):
                r["failures"].append(f"risk-register.md:{ln_no}: [rule:{rid}] printed as cl. {clause} but rules.json "
                                     f"says cl. {rules[rid]['clause']}")
        if line.startswith(">"):
            ids = [m.group(1) for m in CITE_RULE.finditer(line)]
            body = re.sub(r"\[[^\]]*\]", "", line.lstrip("> ")).strip().strip('"“”')
            for part in [p.strip() for p in re.split(r"\.\.\.|…", body) if p.strip()]:
                n_excerpts += 1
                srcs = [rules[i]["verbatim_quote"] for i in ids if i in rules]
                if not srcs:
                    r["failures"].append(f"risk-register.md:{ln_no}: quoted excerpt with no [rule:ID] to check it against")
                elif not any(norm(part) in norm(q) for q in srcs):
                    r["failures"].append(f"risk-register.md:{ln_no}: excerpt {part[:60]!r} is not in the verbatim_quote "
                                         f"of {', '.join(ids)}")
    r["checked"] += n_cites + n_excerpts
    r["notes"].append(f"risk-register.md: {n_cites} rule citation(s), {n_excerpts} quoted excerpt(s) checked")
    return r


if __name__ == "__main__":
    sys.exit(cli("quotes", run))
