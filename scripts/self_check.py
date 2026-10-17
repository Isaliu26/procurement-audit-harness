"""Independent self-check. Imports nothing from tests.py/run.py; re-derives flags from source cells."""
import glob, json, os, re, sys, csv, datetime as dt
import openpyxl
ROOT = "/Users/isabelliu1218/Desktop/sony capstone/procurement-audit-planner"
A = json.load(open(f"{ROOT}/outputs/analytics.json")); FULL = f"{ROOT}/outputs/analytics-full"
results = []
def rec(name, ok, msg=""):
    results.append((name, "PASS" if ok else "FAIL", msg)); 
def skip(name, why): results.append((name, "SKIPPED", why))

def norm(s):
    s = str(s or "").upper().replace("&", " AND ").replace("'", "").replace("’", "")
    s = re.sub(r"[^A-Z0-9]+", " ", s); s = re.sub(r"\b(LTD|LIMITED|PLC|LLP)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()

# ---- load source workbooks directly
WB = {}
for f in sorted(glob.glob(f"{ROOT}/data/spend/*.xlsx")):
    WB[os.path.splitext(os.path.basename(f))[0]] = list(openpyxl.load_workbook(f, read_only=True, data_only=True)["Data to publish"].iter_rows(values_only=True))
def cells(row_id):
    stem, n = row_id.rsplit(":", 1); r = WB[stem][int(n) - 1]
    hdr = next(i for i, x in enumerate(WB[stem]) if x and "Supplier name" in x)
    h = WB[stem][hdr]; g = lambda c: r[h.index(c)]
    d = g("Date")
    if isinstance(d, str): d = dt.datetime.strptime(d, "%m/%d/%y")
    return dict(service=g("Service"), category=g("Expenditure category"), narrative=g("Narrative"), date=d, amount=float(g("Net amount")), supplier=g("Supplier name"))
def rdcsv(name):
    with open(f"{FULL}/{name}.csv", newline="") as f: return list(csv.DictReader(f))
months = A["window"]["months"]; fac = 12 / months
tiers = {t["value"]: t for t in A["parameters"]["thresholds_used"]["procurement_tiers"]}
def reach(x, T): return x >= T if tiers[T]["reach_inclusive"] else x > T

# ---- reconciliation (independent re-read)
n = 0; tot = 0.0; blank = 0
for stem, rows in WB.items():
    hdr = next(i for i, x in enumerate(rows) if x and "Supplier name" in x)
    for r in rows[hdr + 1:]:
        if all(v is None for v in r): blank += 1; continue
        n += 1
        h = rows[hdr]; tot += float(r[h.index("Net amount")])
c = A["cleaning"]
rec("reconciliation_rows", n == c["rows_read"] == c["analysed"]["rows"] + c["excluded_total"]["rows"], f"source {n}, json {c['rows_read']}")
rec("reconciliation_gbp", abs(tot - c["gbp_read"]) < 0.01 and abs(c["analysed"]["gbp"] + c["excluded_total"]["gbp"] - c["gbp_read"]) < 0.02, f"source {tot:.2f}")
rec("blank_rows", blank == c["blank_rows_skipped"], f"{blank}")
rec("cleaned_csv_rows", len(rdcsv("cleaned_spend")) == c["analysed"]["rows"])
rec("excluded_csv_rows", len(rdcsv("excluded_rows")) == c["excluded_total"]["rows"])

# ---- notices
NOT = None
if A["contracts"].get("present"):
    NOT = []
    with open(f"{ROOT}/data/contracts.csv", newline="") as f:
        for r in csv.DictReader(f):
            if r["Organisation Name"].strip().casefold() not in ("west berkshire council", "west berkshire"): continue
            sc = [k for k in r if k.startswith("Supplier [")][0]
            blocks = [b.strip("[]") for b in r[sc].split("][") if b.strip("[]")]
            names = [b.split("|")[0] for b in blocks]
            e = r["Contract end date"].strip(); s_ = r["Contract start date"].strip()
            NOT.append(dict(id=r["Notice Identifier"], names=[norm(x) for x in names], n=len(names),
                            end=dt.datetime.strptime(e, "%d/%m/%Y") if e else None, start=dt.datetime.strptime(s_, "%d/%m/%Y") if s_ else None,
                            value=float(r["Awarded Value"] or 0)))
    rec("contracts_kept_rows", len(NOT) == A["contracts"]["kept_rows"], f"{len(NOT)}")
WSTART = dt.datetime.strptime(A["window"]["first_payment"][:10], "%Y-%m-%d")
def first(name, key, rows=None): 
    rows = rows or rdcsv(name); return max(rows, key=lambda r: float(r[key]))

def csv_count_matches(test_name, rows):
    ents = [v for v in A["tests"].values() if v["test"] == test_name and v["status"] == "ran"]
    tiered = "tier" in (rows[0] if rows else {})
    ok = True
    for v in ents:
        k = v["counts"]["flagged_items"]
        cnt = sum(1 for r in rows if float(r["tier"]) == v["parameters"]["tier_gbp"]) if tiered else len(rows)
        ok &= (k == cnt)
    return ok

def top_subset(test_name, rows, keyf):
    ok = True
    keys = {keyf(r) for r in rows}
    for v in A["tests"].values():
        if v["test"] == test_name and v["status"] == "ran":
            for it in v["top20"]:
                ok &= keyf(it) in keys
    return ok

# ---- threshold_clustering
if any(v["test"] == "threshold_clustering" for v in A["tests"].values()):
    rows = rdcsv("threshold_clustering")
    ok = csv_count_matches("threshold_clustering", rows); msgs = []
    for T in sorted({float(r["tier"]) for r in rows}):
        sub = [r for r in rows if float(r["tier"]) == T]; r = first("", "amount", sub); c_ = cells(r["row_id"])
        good = 0.9 * T <= c_["amount"] < T and abs(c_["amount"] - float(r["amount"])) < 0.005 and c_["supplier"] == r["supplier"]
        ok &= good; msgs.append(f"T={T:g}:{r['row_id']}")
    ok &= top_subset("threshold_clustering", rows, lambda r: str(r["row_id"]))
    rec("threshold_clustering", ok, "; ".join(msgs))

# ---- split_purchases
if any(v["test"] == "split_purchases" for v in A["tests"].values()):
    rows = rdcsv("split_purchases"); ok = csv_count_matches("split_purchases", rows); msgs = []
    for T in sorted({float(r["tier"]) for r in rows}):
        sub = [r for r in rows if float(r["tier"]) == T]
        if not sub: continue
        r = first("", "combined_gbp", sub); cs = [cells(x) for x in r["row_ids"].split(";")]
        amts = [x["amount"] for x in cs]; ds = sorted(x["date"] for x in cs)
        good = (len(cs) >= 2 and all(not reach(a_, T) for a_ in amts) and reach(sum(amts), T) and (ds[-1] - ds[0]).total_seconds() <= 30 * 86400
                and len({norm(x["supplier"]) for x in cs}) == 1 and abs(sum(amts) - float(r["combined_gbp"])) < 0.01
                and (len({round(a_, 2) for a_ in amts}) == 1) == (r["all_amounts_equal"] == "True"))
        ok &= good; msgs.append(f"T={T:g}:{r['row_ids'].split(';')[0]}")
    ok &= top_subset("split_purchases", rows, lambda r: str(r["row_ids"]))
    rec("split_purchases", ok, "; ".join(msgs))

# ---- duplicates
if "duplicates" in A["tests"] and A["tests"]["duplicates"]["status"] == "ran":
    rows = rdcsv("duplicates"); ok = len(rows) == A["tests"]["duplicates"]["counts"]["flagged_items"]
    r = first("", "total_gbp", rows); cs = sorted((cells(x) for x in r["row_ids"].split(";")), key=lambda x: x["date"])
    gaps_ok = all((cs[i + 1]["date"] - cs[i]["date"]).total_seconds() <= 7 * 86400 for i in range(len(cs) - 1))
    same = len({norm(x["supplier"]) for x in cs}) == 1 and len({round(x["amount"] * 100) for x in cs}) == 1
    ident = len({(x["service"], x["category"], x["narrative"], x["date"]) for x in cs}) == 1
    ok &= gaps_ok and same and len(cs) >= 2 and ident == (r["identical_on_all_fields"] == "True")
    ok &= top_subset("duplicates", rows, lambda r: str(r["row_ids"]))
    rec("duplicates", ok, r["row_ids"].split(";")[0])

# ---- supplier-level helpers
def supplier_total(r):
    cs = [cells(x) for x in r["row_ids"].split(";")]
    return len(cs), sum(x["amount"] for x in cs), {norm(x["supplier"]) for x in cs}
def exact(snorm): return [n_ for n_ in NOT if snorm in n_["names"]] if NOT is not None else None

t = A["tests"].get("high_value_suppliers", {})
if t.get("status") == "ran":
    rows = rdcsv("high_value_suppliers"); r = first("", "annualised_estimate_gbp", rows); k, s, nm = supplier_total(r)
    q = t["parameters"]["quote_threshold_gbp"]; inc = t["parameters"]["inclusive"]; ann = s * fac
    ok = k == int(r["payments"]) and abs(s - float(r["total_gbp"])) < 0.01 and (ann >= q if inc else ann > q) and len(nm) == 1
    if NOT is not None:
        ex = exact(next(iter(nm))); st = "none" if not ex else ("exact_active" if any(e["end"] is None or e["end"] >= WSTART for e in ex) else "exact_expired_only")
        ok &= st == r["notice_status"]
    ok &= len(rows) == t["counts"]["flagged_items"] and top_subset("high_value_suppliers", rows, lambda r: r["supplier"])
    rec("high_value_suppliers", ok, r["supplier"][:30])

t = A["tests"].get("off_contract", {})
if t.get("status") == "ran":
    rows = rdcsv("off_contract"); r = first("", "annualised_estimate_gbp", rows); k, s, nm = supplier_total(r); th_ = t["parameters"]["notice_threshold_gbp"]
    ok = (s * fac >= th_ if t["parameters"]["inclusive"] else s * fac > th_) and not exact(next(iter(nm))) and len(rows) == t["counts"]["flagged_items"]
    ok &= top_subset("off_contract", rows, lambda r: r["supplier"])
    # disjointness with expired test
    ex_rows = rdcsv("expired_notice_spend") if "expired_notice_spend" in A["tests"] and A["tests"]["expired_notice_spend"]["status"] == "ran" else []
    ok &= not ({r_["supplier_norm"] for r_ in rows} & {r_["supplier_norm"] for r_ in ex_rows})
    rec("off_contract", ok, r["supplier"][:30])
else: skip("off_contract", t.get("reason", "not run"))

t = A["tests"].get("expired_notice_spend", {})
if t.get("status") == "ran":
    rows = rdcsv("expired_notice_spend"); r = first("", "total_gbp", rows); k, s, nm = supplier_total(r); ex = exact(next(iter(nm)))
    ok = bool(ex) and all(e["end"] is not None and e["end"] < WSTART for e in ex) and len(rows) == t["counts"]["flagged_items"]
    ok &= top_subset("expired_notice_spend", rows, lambda r: r["supplier"])
    rec("expired_notice_spend", ok, r["supplier"][:30])
else: skip("expired_notice_spend", t.get("reason", "not run"))

t = A["tests"].get("spend_vs_award", {})
if t.get("status") == "ran":
    rows = rdcsv("spend_vs_award")
    if rows:
        r = first("", "ratio", rows); k, s, nm = supplier_total(r); ex = [e for e in exact(next(iter(nm))) if e["end"] is None or e["end"] >= WSTART]
        e = ex[0]; yrs = ((e["end"] - e["start"]).days + 1) / 365.25; ratio = s * fac / (e["value"] / yrs)
        ok = len(ex) == 1 and e["n"] == 1 and e["value"] > 0 and ratio >= t["parameters"]["ratio_threshold"] and abs(ratio - float(r["ratio"])) < 0.01 and e["id"] == r["notice_id"]
        ok &= len(rows) == t["counts"]["flagged_items"] and top_subset("spend_vs_award", rows, lambda r: r["supplier"])
        rec("spend_vs_award", ok, f"{r['supplier'][:30]} ratio {ratio:.2f}")
    else: rec("spend_vs_award", t["counts"]["flagged_items"] == 0, "no flagged rows")
else: skip("spend_vs_award", t.get("reason", "not run"))

for name, status, msg in results: print(f"{status:8} {name} {msg}")
sys.exit(1 if any(s == "FAIL" for _, s, _ in results) else 0)
