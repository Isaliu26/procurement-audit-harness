import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json, datetime as dt
import pandas as pd, numpy as np
from config import *
import clean, contracts as ct, thresholds as th, tests as T_
from tests import _round, _bytag_rows, supplier_table, reaches, PAY_COLS
from tagging import TAGS, M as TAGMAP
from common import normalise_supplier, sha256

OUT = f"{ROOT}/outputs"; FULL = f"{OUT}/analytics-full"
os.makedirs(FULL, exist_ok=True)
TOP = S["top_n"]

def stop(msg):
    print("STOP: " + msg); sys.exit(2)

try:
    thr = th.build()
except th.RulesError as e: stop(str(e))
try:
    raw, inputs, blank_total = clean.read_workbooks()
except clean.InputError as e: stop(str(e))
except Exception as e: stop(f"workbook read failed: {e}")

df = clean.classify(raw)
rows_read, gbp_read = len(df), float(df.amount.sum())
exc = df[df.excl_reason != ""].copy(); a = df[df.excl_reason == ""].copy()
assert len(exc) + len(a) == rows_read and abs(exc.amount.sum() + a.amount.sum() - gbp_read) < 0.01, "reconciliation failed"
wstart, wend, months = clean.window(df)
factor = 12 / months
W_START = wstart.normalize()

# ---- cleaning outputs
exc_out = exc.rename(columns={"excl_reason": "reason"})[["row_id", "reason", "service", "category", "narrative", "date", "amount", "supplier", "tag"]]
exc_out.to_csv(f"{FULL}/excluded_rows.csv", index=False)
pairs = exc[exc.excl_reason.isin(["pension_statutory", "internal"])].groupby(["excl_reason", "narrative", "supplier"]).amount.agg(["count", "sum"]).reset_index().rename(columns={"excl_reason": "reason", "count": "rows", "sum": "gbp"})
pairs.to_csv(f"{FULL}/exclusion_pairs.csv", index=False)
pb = a[a.supplier.astype(str).str.contains(REVIEW_PAT)].groupby("supplier").amount.agg(["count", "sum"]).reset_index().rename(columns={"count": "rows", "sum": "gbp"}).sort_values("gbp", ascending=False)
pb.to_csv(f"{FULL}/public_body_review.csv", index=False)
a_out = a[["row_id", "service", "category", "narrative", "date", "amount", "supplier", "supplier_norm", "tag"]]
a_out.to_csv(f"{FULL}/cleaned_spend.csv", index=False)

red = exc[exc.excl_reason == "redacted_supplier"]
cleaning = {
    "rows_read": rows_read, "gbp_read": round(gbp_read, 2), "blank_rows_skipped": int(blank_total),
    "analysed": {"rows": len(a), "gbp": round(float(a.amount.sum()), 2)},
    "excluded": {r: {"rows": int((exc.excl_reason == r).sum()), "gbp": round(float(exc[exc.excl_reason == r].amount.sum()), 2)}
                 for r in ["redacted_supplier", "pension_statutory", "internal", "other_public_body"]},
    "excluded_total": {"rows": len(exc), "gbp": round(float(exc.amount.sum()), 2)},
    "reconciliation": {"rows_read_equals_analysed_plus_excluded": True, "gbp_reconciles_to_penny": True},
    "redacted_by_category": {k: {"rows": int(v["count"]), "gbp": round(float(v["sum"]), 2)} for k, v in red.groupby("category").amount.agg(["count", "sum"]).iterrows()},
    "redacted_by_tag": _bytag_rows(red),
    "identical_rows_all_fields": {"rows_in_identical_groups": int(df.duplicated(["service", "category", "narrative", "date", "amount", "supplier"], keep=False).sum()),
                                  "extra_copies": int(df.duplicated(["service", "category", "narrative", "date", "amount", "supplier"]).sum()),
                                  "note": "kept; never de-duplicated; possible duplicates only"},
    "public_body_review": {"suppliers": int(len(pb)), "file": "outputs/analytics-full/public_body_review.csv"},
    "exclusion_pairs": {"pairs": int(len(pairs)), "file": "outputs/analytics-full/exclusion_pairs.csv"},
    "supplier_normalisation": "uppercase; & -> AND; apostrophes deleted; other punctuation -> space; drop LTD/LIMITED/PLC/LLP; collapse whitespace",
    "distinct_suppliers_analysed": int(a.supplier_norm.nunique()),
}
window_j = {"first_payment": str(wstart), "last_payment": str(wend), "months": int(months), "annualising_factor": round(factor, 6),
            "label": "annualised estimate = supplier total in window x 12 / months"}

# ---- tagging
g = a.groupby("tag").amount.agg(["count", "sum"])
gen = a[a.tag == "general_procurement"].groupby("narrative").amount.agg(["count", "sum"]).sort_values("sum", ascending=False).head(TOP)
tagging = {"method": "heuristic on published fields; first match wins in order " + " > ".join(TAGMAP["order"]),
           "map_file": "scripts/tag_map.json", "map": TAGMAP["rules"],
           "by_tag": {t: {"rows": int(g.loc[t, "count"]) if t in g.index else 0, "gbp": round(float(g.loc[t, "sum"]), 2) if t in g.index else 0.0} for t in TAGS},
           "unmapped_review": [{"narrative": n, "rows": int(r["count"]), "gbp": round(float(r["sum"]), 2)} for n, r in gen.iterrows()],
           "unmapped_review_note": "top 20 narratives by GBP left in general_procurement, for auditor review"}

# ---- contracts
have_c = ct.present()
notices = None; cinfo = {"present": False}
if have_c:
    try: notices, cinfo = ct.load(W_START)
    except Exception as e: stop(f"contracts.csv unusable: {e}")

sup = supplier_table(a, months)
sup_rows = a.groupby("supplier_norm").row_id.apply(lambda s: ";".join(s)).to_dict()
sup["row_ids"] = sup.supplier_norm.map(sup_rows)
quote, notice = thr["quote"], thr["notice"]

def sup_meets(v, th_):
    return reaches(v, th_["value"], th_["inclusive"])

# matching
notice_status = {}; cand_rows = []; matching = {"present": False}
if have_c:
    by_norm = notices.groupby("supplier_norm")
    nn = {k: (g_.supplier.iloc[0], list(g_.notice_id)) for k, g_ in by_norm}
    scope = sup[sup.annualised_estimate_gbp.map(lambda v: sup_meets(v, notice))] if notice else sup.iloc[0:0]
    for s in sup.itertuples():
        if s.supplier_norm in nn:
            ids = notices[notices.supplier_norm == s.supplier_norm]
            notice_status[s.supplier_norm] = "exact_active" if ids.active.any() else "exact_expired_only"
        else: notice_status[s.supplier_norm] = "none"
    cand_for = {}
    for s in sup[sup.supplier_norm.isin(scope.supplier_norm) & (sup.supplier_norm.map(notice_status) == "none")].itertuples():
        cs = ct.candidates(s.supplier, s.supplier_norm, nn)
        if cs:
            cand_for[s.supplier_norm] = cs[0]
            for raw_, nid, reason, ratio in cs:
                cand_rows.append(dict(spend_supplier=s.supplier, notice_supplier=raw_, notice_id=nid, reason=reason, ratio=ratio, annualised_estimate_gbp=round(s.annualised_estimate_gbp, 2)))
    em = scope[scope.supplier_norm.map(notice_status) != "none"]
    tot_scope = scope.total_gbp.sum()
    matching = {"present": True, "suppliers_in_scope": int(len(scope)), "scope_definition": "annualised estimate meets the notice threshold",
                "exact_matched": int(len(em)), "no_exact_match": int(len(scope) - len(em)),
                "no_exact_with_candidate": int(sum(1 for x in scope.supplier_norm if notice_status[x] == "none" and x in cand_for)),
                "exact_match_share_of_suppliers": round(len(em) / len(scope), 4) if len(scope) else None,
                "exact_match_share_of_gbp": round(float(em.total_gbp.sum() / tot_scope), 4) if tot_scope else None,
                "method": "exact = identical normalised name; candidates (difflib>=0.85, token containment with >=2 tokens in the smaller name, trading-as part) are never counted as matches"}
    cinfo["matching"] = matching
cand_df = pd.DataFrame(cand_rows, columns=["spend_supplier", "notice_supplier", "notice_id", "reason", "ratio", "annualised_estimate_gbp"])
cand_df.to_csv(f"{FULL}/match_candidates.csv", index=False)
cand_for = locals().get("cand_for", {})

# ---- tests
TESTS = {}
def top_pay(df_, n=TOP, by="amount"):
    return [_round({c: r[c] for c in PAY_COLS}) for _, r in df_.sort_values(by, ascending=False).head(n).iterrows()]
def tag_counts_group(df_, val):
    g_ = df_.groupby("tag")[val].agg(["count", "sum"])
    return {t: {"count": int(g_.loc[t, "count"]) if t in g_.index else 0, "gbp": round(float(g_.loc[t, "sum"]), 2) if t in g_.index else 0.0} for t in TAGS}
def fcsv(df_, name):
    out = df_.copy()
    for c in out.columns:
        if str(out[c].dtype).startswith("float"): out[c] = out[c].round(2)
    out.to_csv(f"{FULL}/{name}", index=False)

LIMIT_DATES = "Spend dates are payment-run timestamps, not invoice dates, so windows are measured on payment-run dates."
LIM = [
    "Spend dates are payment-run timestamps, not invoice or transaction dates; the 30-day and 7-day windows are measured on payment-run dates.",
    "Rows with supplier 'Redacted' cannot be tested by supplier; they are excluded and reported by Expenditure category and tag.",
    f"Only {months} months of data, so the x{12/months:g} annualisation is an estimate (annualised estimate).",
    "The Contracts Finder notice export holds only contracts above about 25,000 GBP; absence of a notice for a smaller supplier is expected and is never a finding.",
    "Tags are a heuristic on published fields (Narrative, Expenditure category, Service, supplier text), not a classification of the underlying contract.",
    "Supplier matching between spend and notices is by normalised name only; the spend data carries no Companies House number. Candidates are never counted as matches.",
    "The spend data has no transaction id; identical rows are kept and treated as possible duplicates, never confirmed ones.",
    "Redacted-supplier, pension/statutory, internal and other public-body rows are outside the supplier tests; public-body review list and exclusion pairs are provided for the auditor to confirm.",
    "Boundary treatment follows the PDF wording as stored in rules.json: the 500,000 GBP boundary is exclusive on both sides (CPR-62 high, CPR-64 low), so a payment or total of exactly 500,000 does not reach that tier and is not flagged by the 500,000 tests.",
    "The 1,000 GBP lower bound is stored as exclusive (CPR-59), so a total must exceed 1,000 to reach that tier; amounts of exactly 1,000 are not treated as reaching it.",
    "Auditor decisions pending, nothing excluded: public_body_review.csv (101 names) and exclusion_pairs.csv (5 pairs) remain in the analysed population for the auditor to review.",
]

for tier in thr["tiers"]:
    Tv = tier["value"]; mid = f"threshold_clustering@{Tv}"
    band, ex = T_.threshold_clustering(a, tier)
    band_out = band[["tier", "band_low"] + PAY_COLS]
    TESTS[mid] = dict(test="threshold_clustering", metric_id=mid, status="ran",
        parameters={"tier_gbp": Tv, "rule_ids": tier["rule_ids"], "band": f"[{ex['band_low']:g}, {Tv})", "band_fraction": S["band_fraction"], "tier_inclusive_basis": tier["reach_basis"]},
        counts={"flagged_items": int(len(band)), "context_lower_band_count": ex["context_lower_band_count"]},
        totals_gbp={"flagged": round(float(band.amount.sum()), 2), "context_lower_band": ex["context_lower_band_gbp"]},
        by_tag=tag_counts_group(band, "amount") if len(band) else {t: {"count": 0, "gbp": 0.0} for t in TAGS},
        top20=top_pay(band) if len(band) else [], top_suppliers=ex["top_suppliers"], full_list_file="outputs/analytics-full/threshold_clustering.csv",
        interpretation=f"Payments just below {Tv:,} GBP (within 10 percent) may indicate amounts shaped to stay under a procurement route boundary; the adjacent lower band is shown for context so the auditor can judge whether the concentration is unusual. Innocent explanations include fixed or tariff prices, standard rates for recurring care or service charges, and round-number pricing. Worth confirming against quotes or tender records. Care placements may be lawfully outside competition (Appendix C row F, {', '.join(thr['appC_F'])}).")
    TESTS[mid]["_df"] = band_out
    sp = T_.split_purchases(a, tier); mid2 = f"split_purchases@{Tv}"
    TESTS[mid2] = dict(test="split_purchases", metric_id=mid2, status="ran",
        parameters={"tier_gbp": Tv, "rule_ids": tier["rule_ids"] + thr["anti_avoidance_rule_ids"], "window_days": S["split_window_days"], "condition": "same normalised supplier, >=2 payments each below the tier within the window, combined total reaches the tier", "tier_inclusive_basis": tier["reach_basis"]},
        counts={"flagged_items": int(len(sp)), "payments_in_groups": int(sp.n_payments.sum()) if len(sp) else 0, "groups_all_amounts_equal": int(sp.all_amounts_equal.sum()) if len(sp) else 0},
        totals_gbp={"combined": round(float(sp.combined_gbp.sum()), 2) if len(sp) else 0.0},
        by_tag=tag_counts_group(sp, "combined_gbp") if len(sp) else {t: {"count": 0, "gbp": 0.0} for t in TAGS},
        top20=[_round({c: r[c] for c in ["supplier", "tag", "n_payments", "combined_gbp", "span_days", "all_amounts_equal", "row_ids"]}) for _, r in sp.sort_values("combined_gbp", ascending=False).head(TOP).iterrows()],
        full_list_file="outputs/analytics-full/split_purchases.csv",
        interpretation=f"Several payments to one supplier close together whose combined value reaches {Tv:,} GBP may indicate a requirement split into smaller purchases (anti-avoidance rule {', '.join(thr['anti_avoidance_rule_ids'])}), consistent with a pattern worth confirming. Innocent explanations: regular recurring payments (common for care packages and rents, see all_amounts_equal), separate unrelated orders, or one contract invoiced in instalments. {LIMIT_DATES} Windows are anchored greedily so each payment sits in one group per tier.")
    TESTS[mid2]["_df"] = sp

# duplicates
du = T_.duplicates(a)
TESTS["duplicates"] = dict(test="duplicates", metric_id="duplicates", status="ran",
    parameters={"window_days": S["duplicate_window_days"], "condition": "same normalised supplier, same amount to the penny, dates chained within window"},
    counts={"flagged_items": int(len(du)), "payments_in_groups": int(du.n_payments.sum()) if len(du) else 0, "identical_on_all_fields_groups": int(du.identical_on_all_fields.sum()) if len(du) else 0},
    totals_gbp={"group_total": round(float(du.total_gbp.sum()), 2) if len(du) else 0.0, "excess_over_one_per_group": round(float((du.total_gbp - du.amount).sum()), 2) if len(du) else 0.0},
    by_tag=tag_counts_group(du, "total_gbp") if len(du) else {t: {"count": 0, "gbp": 0.0} for t in TAGS},
    top20=[_round({c: r[c] for c in ["supplier", "tag", "amount", "n_payments", "total_gbp", "span_days", "identical_on_all_fields", "row_ids"]}) for _, r in du.sort_values("total_gbp", ascending=False).head(TOP).iterrows()],
    full_list_file="outputs/analytics-full/duplicates.csv",
    interpretation="Repeated same-amount payments to one supplier within 7 days are possible duplicate payments to investigate, not confirmed ones. Groups identical on every published field are flagged separately; with no transaction id they may still be separate legitimate payments (for example several invoices of the same value, or weekly or per-person care charges). " + LIMIT_DATES)
TESTS["duplicates"]["_df"] = du

# off_contract & friends
SKIP = "data/contracts.csv not present"
def supp_view(s_df):
    s_df = s_df.copy()
    s_df["notice_status"] = s_df.supplier_norm.map(notice_status) if have_c else "not_assessed"
    s_df["candidate_notice"] = s_df.supplier_norm.map(lambda x: cand_for[x][0] if x in cand_for else "")
    s_df["candidate_reason"] = s_df.supplier_norm.map(lambda x: f"{cand_for[x][2]} (ratio {cand_for[x][3]})" if x in cand_for else "")
    return s_df
def sup_top(s_df, extra=()):
    cols = ["supplier", "total_gbp", "annualised_estimate_gbp", "payments", "months_paid", "dominant_tag", "notice_status", "candidate_notice", "candidate_reason"] + list(extra)
    return [_round({c: r[c] for c in cols} | {"row_ids_sample": r["row_ids"].split(";")[:5], "n_row_ids": r["payments"]}) for _, r in s_df.sort_values("annualised_estimate_gbp", ascending=False).head(TOP).iterrows()]
def sup_tag(s_df):
    s_df = s_df.rename(columns={"dominant_tag": "tag"})
    return tag_counts_group(s_df, "total_gbp") if len(s_df) else {t: {"count": 0, "gbp": 0.0} for t in TAGS}

SCOLS = ["supplier", "supplier_norm", "dominant_tag", "total_gbp", "annualised_estimate_gbp", "payments", "months_paid", "services", "notice_status", "candidate_notice", "candidate_reason", "tags", "row_ids"]
hv = supp_view(sup[sup.annualised_estimate_gbp.map(lambda v: sup_meets(v, quote))]) if quote else None
if quote:
    TESTS["high_value_suppliers"] = dict(test="high_value_suppliers", metric_id="high_value_suppliers", status="ran",
        parameters={"quote_threshold_gbp": quote["value"], "inclusive": quote["inclusive"], "rule_ids": quote["rule_ids"]},
        counts={"flagged_items": int(len(hv)), **({"notice_status": hv.notice_status.value_counts().to_dict()})},
        totals_gbp={"three_month": round(float(hv.total_gbp.sum()), 2), "annualised_estimate": round(float(hv.annualised_estimate_gbp.sum()), 2)},
        by_tag=sup_tag(hv), top20=sup_top(hv), full_list_file="outputs/analytics-full/high_value_suppliers.csv",
        interpretation="Suppliers whose annualised estimate meets the invitation-to-quote threshold: the population for which to request contract, quote or tender evidence. Being listed is not a finding; many will hold a valid framework, DPS call-off or lawful exclusion (care placements may be outside competition, Appendix C row F), or be covered by a contract not published as a notice. The annualised estimate extrapolates three months.")
    TESTS["high_value_suppliers"]["_df"] = hv[SCOLS]
    TESTS["high_value_suppliers"]["_df"] = TESTS["high_value_suppliers"]["_df"].rename(columns={"dominant_tag": "tag"})
else:
    TESTS["high_value_suppliers"] = dict(test="high_value_suppliers", metric_id="high_value_suppliers", status="skipped", reason="no quote threshold derivable from rules.json")

def skipped(name, reason): TESTS[name] = dict(test=name, metric_id=name, status="skipped", reason=reason)
if not have_c:
    for n in ["off_contract", "expired_notice_spend", "spend_vs_award"]: skipped(n, SKIP)
else:
    # off_contract
    sv = supp_view(sup)
    oc = sv[sv.annualised_estimate_gbp.map(lambda v: sup_meets(v, notice)) & (sv.notice_status == "none")] if notice else None
    if notice is None: skipped("off_contract", "no numeric notice threshold in rules.json")
    else:
        TESTS["off_contract"] = dict(test="off_contract", metric_id="off_contract", status="ran",
            parameters={"notice_threshold_gbp": notice["value"], "inclusive": notice["inclusive"], "rule_ids": notice["rule_ids"], "condition": "annualised estimate meets threshold and no exact name match in any council notice"},
            counts={"flagged_items": int(len(oc)), "with_candidate_notice": int((oc.candidate_notice != "").sum())},
            totals_gbp={"three_month": round(float(oc.total_gbp.sum()), 2), "annualised_estimate": round(float(oc.annualised_estimate_gbp.sum()), 2)},
            by_tag=sup_tag(oc), top20=sup_top(oc), full_list_file="outputs/analytics-full/off_contract.csv",
            interpretation="Suppliers above the notice threshold with no exact-name council notice may indicate spend without a published contract; worth confirming. The Contracts Finder export holds only contracts above about 25,000 GBP, so this test never questions suppliers below the threshold. Innocent explanations: care placements and other individual placements (possibly lawfully outside competition, Appendix C row F), framework or DPS call-offs, other public-sector bodies, notices published under a different or group name (see candidate_notice, never counted as matches), contracts awarded before 2021 or not published, grants, or utilities. Disjoint from expired_notice_spend.")
        TESTS["off_contract"]["_df"] = oc[SCOLS].rename(columns={"dominant_tag": "tag"})
    # expired
    ex_rows = []
    for s in sup.itertuples():
        if notice_status[s.supplier_norm] == "exact_expired_only":
            n_ = notices[notices.supplier_norm == s.supplier_norm]
            ex_rows.append(dict(supplier=s.supplier, supplier_norm=s.supplier_norm, tag=s.dominant_tag, total_gbp=s.total_gbp, annualised_estimate_gbp=s.annualised_estimate_gbp,
                                payments=s.payments, notice_ids=";".join(sorted(set(n_.notice_id))), latest_notice_end=n_.cend.max(), notices_matched=n_.notice_id.nunique(), row_ids=s.row_ids))
    ed = pd.DataFrame(ex_rows, columns=["supplier", "supplier_norm", "tag", "total_gbp", "annualised_estimate_gbp", "payments", "notice_ids", "latest_notice_end", "notices_matched", "row_ids"])
    TESTS["expired_notice_spend"] = dict(test="expired_notice_spend", metric_id="expired_notice_spend", status="ran",
        parameters={"window_start": str(W_START.date()), "rule_ids": thr["appC_D"], "condition": "every exact-matching notice has a contract end date before the window start; blank end date counts as active"},
        counts={"flagged_items": int(len(ed))}, totals_gbp={"three_month": round(float(ed.total_gbp.sum()), 2) if len(ed) else 0.0},
        by_tag=tag_counts_group(ed, "total_gbp") if len(ed) else {t: {"count": 0, "gbp": 0.0} for t in TAGS},
        top20=[_round({c: r[c] for c in ["supplier", "tag", "total_gbp", "annualised_estimate_gbp", "payments", "notice_ids", "latest_notice_end"]} | {"row_ids_sample": r["row_ids"].split(";")[:5], "n_row_ids": r["payments"]}) for _, r in ed.sort_values("total_gbp", ascending=False).head(TOP).iterrows()],
        full_list_file="outputs/analytics-full/expired_notice_spend.csv",
        interpretation=f"Suppliers paid in the window whose every matching notice ended before it began may indicate spend after contract expiry without an approved extension (Appendix C row D, {', '.join(thr['appC_D'])}); worth confirming. Innocent explanations: a newer contract or extension not published as a notice, an approved extension recorded only in council records, call-off from a framework, or a name-only match to a different entity. Matching is by name only. Disjoint from off_contract.")
    TESTS["expired_notice_spend"]["_df"] = ed
    # spend_vs_award
    skip_ct = {"several_active_notices": 0, "multi_supplier_notice": 0, "zero_or_missing_award_value": 0, "implausible_or_missing_duration": 0}
    sr = []
    for s in sup.itertuples():
        if notice_status[s.supplier_norm] != "exact_active": continue
        n_ = notices[(notices.supplier_norm == s.supplier_norm) & notices.active].drop_duplicates("notice_id")
        if len(n_) != 1: skip_ct["several_active_notices"] += 1; continue
        n0 = n_.iloc[0]
        if n0.n_suppliers != 1: skip_ct["multi_supplier_notice"] += 1; continue
        if pd.isna(n0.award_value) or n0.award_value <= 0: skip_ct["zero_or_missing_award_value"] += 1; continue
        if pd.isna(n0.cstart) or pd.isna(n0.cend): skip_ct["implausible_or_missing_duration"] += 1; continue
        yrs = ((n0.cend - n0.cstart).days + 1) / 365.25
        if yrs <= 0 or yrs > S["max_plausible_contract_years"]: skip_ct["implausible_or_missing_duration"] += 1; continue
        ratio = s.annualised_estimate_gbp / (n0.award_value / yrs)
        sr.append(dict(supplier=s.supplier, supplier_norm=s.supplier_norm, tag=s.dominant_tag, notice_id=n0.notice_id, awarded_value_gbp=n0.award_value, contract_start=n0.cstart, contract_end=n0.cend,
                       contract_years=round(yrs, 3), annual_award_gbp=n0.award_value / yrs, total_gbp=s.total_gbp, annualised_estimate_gbp=s.annualised_estimate_gbp, ratio=ratio, flagged=ratio >= S["spend_vs_award_ratio"], payments=s.payments, row_ids=s.row_ids))
    sra = pd.DataFrame(sr, columns=["supplier", "supplier_norm", "tag", "notice_id", "awarded_value_gbp", "contract_start", "contract_end", "contract_years", "annual_award_gbp", "total_gbp", "annualised_estimate_gbp", "ratio", "flagged", "payments", "row_ids"])
    srf = sra[sra.flagged].drop(columns="flagged") if len(sra) else sra.drop(columns="flagged")
    TESTS["spend_vs_award"] = dict(test="spend_vs_award", metric_id="spend_vs_award", status="ran",
        parameters={"ratio_threshold": S["spend_vs_award_ratio"], "rule_ids": thr["appC_E"], "contract_years": "(contract end - contract start + 1 day) / 365.25", "condition": "supplier has exactly one active exact-match notice, single-supplier, Awarded Value > 0"},
        counts={"flagged_items": int(len(srf)), "assessed": int(len(sra)), "skipped_with_reason": skip_ct},
        totals_gbp={"annualised_estimate_flagged": round(float(srf.annualised_estimate_gbp.sum()), 2) if len(srf) else 0.0},
        by_tag=tag_counts_group(srf, "total_gbp") if len(srf) else {t: {"count": 0, "gbp": 0.0} for t in TAGS},
        top20=[_round({c: r[c] for c in ["supplier", "tag", "notice_id", "awarded_value_gbp", "contract_years", "annualised_estimate_gbp", "ratio", "payments"]} | {"row_ids_sample": r["row_ids"].split(";")[:5], "n_row_ids": r["payments"]}) for _, r in srf.sort_values("ratio", ascending=False).head(TOP).iterrows()],
        full_list_file="outputs/analytics-full/spend_vs_award.csv",
        interpretation=f"Annualised spend at or above {S['spend_vs_award_ratio']} times the annual equivalent of the award may indicate spend beyond the award without an approved variation (Appendix C row E, {', '.join(thr['appC_E'])}); worth confirming. Innocent explanations: Awarded Value is often an estimate or a minimum rather than a cap, payments may include other contracts with the same supplier, lumpy or front-loaded payment profiles in a three-month window, or a variation approved in council records. Name-only matching.")
    TESTS["spend_vs_award"]["_df"] = srf

# ---- write csvs
by_file = {}
for k, v in TESTS.items():
    if v["status"] != "ran": continue
    by_file.setdefault(v["test"], []).append(v["_df"])
for name, dfs in by_file.items():
    fcsv(pd.concat([d for d in dfs if len(d)] or [dfs[0]], ignore_index=True), f"{name}.csv")
for v in TESTS.values(): v.pop("_df", None)

# ---- analytics.json
params = {"thresholds_used": {"procurement_tiers": [{"value": t["value"], "rule_ids": t["rule_ids"], "reach_inclusive": t["reach_inclusive"], "inclusive_basis": t["reach_basis"], "sources": t["sources"]} for t in thr["tiers"]],
                              "quote_threshold": quote, "notice_threshold": notice, "anti_avoidance_rule_ids": thr["anti_avoidance_rule_ids"],
                              "note": "reach_inclusive: whether a total exactly equal to the value reaches the tier, taken from the stored inclusive flag of the rule where it is a lower bound. 'Just under' band is always [0.9T, T)."},
          "tiers_skipped": thr["tiers_skipped"],
          "analysis_settings": {k: dict(v, cited_in="CLAUDE.md / scripts/config.py") for k, v in ANALYSIS_SETTINGS.items()}}
res = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
       "inputs": {"rules": {"file": "outputs/rules.json", "sha256": sha256(f"{OUT}/rules.json")}, "spend_workbooks": inputs, "contracts": cinfo.get("file") and {"file": cinfo["file"], "sha256": cinfo["sha256"]} or None},
       "window": window_j, "limitations": LIM, "parameters": params, "cleaning": cleaning, "tagging": tagging,
       "contracts": cinfo if have_c else {"present": False}, "tests": TESTS}
json.dump(res, open(f"{OUT}/analytics.json", "w"), indent=1, default=str)
print("written", {k: (v["status"], v.get("counts", {}).get("flagged_items")) for k, v in TESTS.items()})
