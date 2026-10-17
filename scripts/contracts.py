import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import re, difflib, datetime as dt
import pandas as pd
from config import *
from common import normalise_supplier, sha256

EXPECTED = ["Notice Identifier", "Organisation Name", "Published Date", "Awarded Date", "Awarded Value",
            "Contract start date", "Contract end date", "Title", "Status",
            "Supplier [Name|Address|Ref type|Ref Number|Is SME|Is VCSE]"]
SUPCOL = EXPECTED[-1]
PATH = f"{ROOT}/data/contracts.csv"

def present(): return os.path.exists(PATH)

def _d(s, fmt):
    if s is None or (isinstance(s, float) and pd.isna(s)) or str(s).strip() == "": return pd.NaT
    return pd.Timestamp(dt.datetime.strptime(str(s).strip(), fmt))

def parse_suppliers(packed):
    out = []
    if packed is None or (isinstance(packed, float) and pd.isna(packed)): return out
    for blk in str(packed).split("]["):
        blk = blk.strip().strip("[]")
        if not blk: continue
        p = blk.split("|")
        name = p[0].strip()
        ref = p[3].strip() if len(p) > 3 and len(p) > 2 and p[2].strip() == "COMPANIES_HOUSE" else ""
        out.append((name, ref))
    return out

def load(window_start):
    raw = pd.read_csv(PATH, dtype=str)
    missing = [c for c in EXPECTED if c not in raw.columns]
    if missing: raise ValueError(f"contracts.csv lacks expected columns: {missing}")
    org = raw["Organisation Name"].fillna("").str.strip().str.casefold()
    keep = org.isin(BUYER_NAMES)
    dropped = raw.loc[~keep, "Organisation Name"].fillna("").str.strip().value_counts()
    k = raw[keep].copy()
    k["pub"] = [pd.Timestamp(dt.datetime.strptime(s.strip(), "%Y-%m-%dT%H:%M:%S%z")) if isinstance(s, str) else pd.NaT for s in k["Published Date"]]
    k["cstart"] = [_d(s, "%d/%m/%Y") for s in k["Contract start date"]]
    k["cend"] = [_d(s, "%d/%m/%Y") for s in k["Contract end date"]]
    k["awarded_date"] = [_d(s, "%d/%m/%Y") for s in k["Awarded Date"]]
    k["award_value"] = pd.to_numeric(k["Awarded Value"], errors="coerce")
    ws = pd.Timestamp(window_start).normalize()
    k["active"] = k["cend"].isna() | (k["cend"] >= ws)
    rows = []
    for _, r in k.iterrows():
        sups = parse_suppliers(r[SUPCOL])
        for nm, ref in sups:
            rows.append(dict(notice_id=r["Notice Identifier"], supplier=nm, supplier_norm=normalise_supplier(nm), ch_number=ref,
                             n_suppliers=len(sups), award_value=r["award_value"], cstart=r["cstart"], cend=r["cend"], active=r["active"], title=r["Title"]))
    sup = pd.DataFrame(rows)
    warns = []
    cap = {"raw_rows": int(len(raw)), "cap": S["export_cap_rows"]}
    if len(raw) >= S["export_cap_rows"]: warns.append(f"raw rows {len(raw)} >= {S['export_cap_rows']}: export may be truncated")
    yrs = k["pub"].map(lambda x: x.year).value_counts().sort_index()
    allyrs = range(int(yrs.index.min()), int(yrs.index.max()) + 1)
    empty = [y for y in allyrs if y not in yrs.index]
    if empty: warns.append(f"years with no notices between first and last publication year: {empty}")
    date_warn = []
    for _, r in k.iterrows():
        if pd.notna(r["cend"]) and pd.notna(r["cstart"]):
            yrs_ = (r["cend"] - r["cstart"]).days / 365.25
            if yrs_ <= 0: date_warn.append({"notice_id": r["Notice Identifier"], "issue": "end date not after start date"})
            elif yrs_ > S["max_plausible_contract_years"]: date_warn.append({"notice_id": r["Notice Identifier"], "issue": f"duration over {S['max_plausible_contract_years']} years"})
        if pd.notna(r["cend"]) and r["cend"].year > ws.year + S["max_plausible_contract_years"]:
            date_warn.append({"notice_id": r["Notice Identifier"], "issue": "end date more than max plausible years after window"})
        if pd.isna(r["cend"]): date_warn.append({"notice_id": r["Notice Identifier"], "issue": "blank contract end date (treated as active)"})
    info = {"present": True, "file": "data/contracts.csv", "sha256": sha256(PATH), "raw_rows": int(len(raw)), "kept_rows": int(len(k)),
            "dropped_rows": int((~keep).sum()), "dropped_buyers": {str(a): int(b) for a, b in dropped.items()},
            "notice_supplier_rows": int(len(sup)), "notices_multi_supplier": int((k[SUPCOL].map(lambda x: len(parse_suppliers(x))) > 1).sum()),
            "active_notices": int(k["active"].sum()), "ended_before_window": int((~k["active"]).sum()),
            "publication_year_counts": {int(a): int(b) for a, b in yrs.items()},
            "export_cap": cap, "warnings": warns, "date_warnings": date_warn[:50], "date_warnings_total": len(date_warn)}
    return sup, info

_TA = re.compile(r"\bt/a:?|\btrading as\b", re.I)
def ta_parts(name):
    parts = [p for p in _TA.split(str(name))]
    return [normalise_supplier(p) for p in parts] if len(parts) > 1 else []

def candidates(spend_name, spend_norm, notice_names):
    """notice_names: dict norm -> (raw, [notice_ids]). Returns non-exact candidates list."""
    out = []
    st = set(spend_norm.split()); parts = ta_parts(spend_name)
    for nn, (raw, ids) in notice_names.items():
        if nn == spend_norm: continue
        reason, ratio = None, None
        if parts and nn in [p for p in parts if p]: reason = "trading-as part equals notice name"
        else:
            nt = set(nn.split())
            if nt and st and ((len(nt) >= 2 and nt <= st) or (len(st) >= 2 and st <= nt)): reason = "tokens of one name contained in the other"
            if reason is None and nn and difflib.SequenceMatcher(None, spend_norm, nn).quick_ratio() >= S["candidate_ratio"]:
                r_ = difflib.SequenceMatcher(None, spend_norm, nn).ratio()
                if r_ >= S["candidate_ratio"]: reason = f"difflib ratio >= {S['candidate_ratio']}"
        if reason:
            ratio = difflib.SequenceMatcher(None, spend_norm, nn).ratio()
            out.append((raw, ids[0], reason, round(ratio, 3)))
    out.sort(key=lambda x: -x[3])
    return out
