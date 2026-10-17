"""Analysis settings (not procurement thresholds). Source: CLAUDE.md / spend-analyst definition."""
import re
ROOT = "/Users/isabelliu1218/Desktop/sony capstone/procurement-audit-planner"
EXPECTED_COLS = ["Service", "Expenditure category", "Narrative", "Date", "Net amount", "Supplier name"]
SHEET = "Data to publish"
ANALYSIS_SETTINGS = {
    "band_fraction": {"value": 0.9, "source": "CLAUDE.md test 1: [0.9 x threshold, threshold)"},
    "context_band_fraction": {"value": 0.8, "source": "spend-analyst definition: adjacent lower band [0.8T,0.9T)"},
    "split_window_days": {"value": 30, "source": "CLAUDE.md test 2"},
    "duplicate_window_days": {"value": 7, "source": "CLAUDE.md test 4"},
    "spend_vs_award_ratio": {"value": 1.25, "source": "CLAUDE.md test 6"},
    "top_n": {"value": 20, "source": "CLAUDE.md: top-20 in analytics.json"},
    "candidate_ratio": {"value": 0.85, "source": "spend-analyst definition: difflib ratio for candidates"},
    "max_plausible_contract_years": {"value": 15, "source": "analyst setting for date_warnings / implausible duration"},
    "export_cap_rows": {"value": 1000, "source": "CLAUDE.md: Contracts Finder 1,000-row export cap"},
}
S = {k: v["value"] for k, v in ANALYSIS_SETTINGS.items()}
COUNCIL_NAME_NORM = "WEST BERKSHIRE COUNCIL"
BUYER_NAMES = ["west berkshire council", "west berkshire"]
PENSION_PAT = re.compile(r"LGPS|pension|superannuation|national insurance|HMRC|council tax|business rates|NNDR|precept|\blevy\b", re.I)
PUBLIC_BODY_PAT = re.compile(r"\bcouncil\b|\bcncl\b|county council|royal borough|combined authority|\bNHS\b.*\b(trust|icb|ics)\b|\b(trust|icb|ics)\b.*\bNHS\b|integrated care (board|system)|\bpolice\b|fire (and|&) rescue", re.I)
REVIEW_PAT = re.compile(r"school|academy|trust|college|NHS|foundation", re.I)
