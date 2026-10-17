#!/usr/bin/env python3
"""Rebuild scripts/tests/fixtures/history_fixture.json: a small, correct history.json
over the real committee PDFs, used as the clean baseline by test_verify_history.py."""
import hashlib, json, subprocess, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
A = "audit-completed-work-2024-25-annual.pdf"
Q = "audit-completed-work-2025-26-q3.pdf"
R = "risk-management-strategy-2024-27.pdf"


def src(name):
    p = ROOT / "data/committee" / name
    pages = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", str(p)], capture_output=True, text=True).stdout).group(1))
    return {"file": name, "pages": pages, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def q(f, p, quote, **kw):
    return {"source_file": f, "pdf_page": p, "quote": quote, **kw}


h = {
    "sources": [src(n) for n in sorted([A, Q, R, "internal-audit-plan-2025-28.pdf"])],
    "audits": [
        q(A, 1, "Finance, Property and | Procurement | Contract Letting | Reasonable Assurance", id="AUD-01",
          audit_title="Contract Letting", opinion="Reasonable Assurance", service="Finance, Property and Procurement"),
        q(A, 1, "Systems Security (Firewall, | Antivirus, Traffic Management) | Reasonable Assurance", id="AUD-02",
          audit_title="Systems Security (Firewall, Antivirus, Traffic Management)", opinion="Reasonable Assurance"),
    ],
    "follow_ups": [
        q(A, 2, "Garland (now Burghfield | Common Federation) | Weak | Unsatisfactory", id="FUP-01",
          audit_title="Garland (now Burghfield Common Federation)", opinion_report="Weak", opinion_implementation="Unsatisfactory"),
    ],
    "advisory_work": [q(A, 2, "Transformation SWOT", id="ADV-01", audit_title="Transformation SWOT")],
    "agreed_actions": [],
    "risk_themes": [
        q(R, 33, "Contracts & | Dependency on, or failure of, contractors to deliver services or | products to the agreed cost and specification.", id="RT-01", theme="Contracts & Partnerships"),
    ],
    "scoring_method": {
        "usable": True,
        "impact_scale": [q(R, 14, "The Council evaluates its identified risks on a five-point scale", id="SM-IMP")],
        "likelihood_scale": [q(R, 15, "Risk will occur within a 12 month period | 100%", id="SM-LIK")],
        "matrix": [q(R, 18, "Moderate High High Extreme Extreme | 4 8 12 16 20", id="SM-MAT-4")],
        "bands": [q(R, 19, "Extreme | 15 -25", id="SM-BAND-X")],
        "appetite": [q(R, 17, "Financial Risk Appetite – Flexible", id="SM-APP-FIN")],
        "escalation": [q(R, 21, "Score 9 or above", id="SM-ESC")],
    },
    "discrepancies": [
        {"id": "DIS-01", "kind": "internal_inconsistency",
         "description": "Paragraph 4.3 numbers Medium impact as (2); Table 1 numbers it 3.",
         "evidence": [q(R, 14, "Negligible (1), Minor (2), Medium (2), Major (4)"),
                      q(R, 18, "Medium | 3 6 9 12 15")]},
    ],
    "gaps": [
        {"id": "GAP-01", "what": "No agreed audit actions, due dates or action status in the papers",
         "looked_in": [A, Q, "internal-audit-plan-2025-28.pdf"]},
    ],
}
out = ROOT / "scripts/tests/fixtures/history_fixture.json"
out.write_text(json.dumps(h, indent=1, ensure_ascii=False))
print("wrote", out)
