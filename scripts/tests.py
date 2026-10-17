import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd, numpy as np
from config import *
from tagging import TAGS

TOPN = S["top_n"]

def reaches(amount, T, inclusive):
    return amount >= T if inclusive else amount > T

def _bytag_rows(df, gcol="amount"):
    g = df.groupby("tag")[gcol].agg(["count", "sum"])
    return {t: {"count": int(g.loc[t, "count"]) if t in g.index else 0, "gbp": round(float(g.loc[t, "sum"]), 2) if t in g.index else 0.0} for t in TAGS}

def _round(rec):
    out = {}
    for k, v in rec.items():
        if isinstance(v, (np.floating, float)): v = None if pd.isna(v) else round(float(v), 2)
        elif isinstance(v, (np.integer,)): v = int(v)
        elif isinstance(v, pd.Timestamp): v = v.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(v, (np.bool_,)): v = bool(v)
        out[k] = v
    return out

PAY_COLS = ["row_id", "date", "amount", "supplier", "tag", "service", "category", "narrative"]

def supplier_table(a, months):
    f = 12 / months
    g = a.groupby("supplier_norm")
    t = g.agg(total_gbp=("amount", "sum"), payments=("amount", "size"),
              months_paid=("date", lambda s: s.dt.to_period("M").nunique()),
              services=("service", lambda s: "; ".join(sorted(set(s)))),
              supplier=("supplier", lambda s: s.value_counts().index[0]))
    t["annualised_estimate_gbp"] = t.total_gbp * f
    dom = a.groupby(["supplier_norm", "tag"]).amount.sum().reset_index().sort_values(["supplier_norm", "amount"], ascending=[True, False]).drop_duplicates("supplier_norm").set_index("supplier_norm")["tag"]
    t["dominant_tag"] = dom
    t["tags"] = a.groupby("supplier_norm").tag.agg(lambda s: "; ".join(sorted(set(s))))
    t["first_row_id"] = a.sort_values(["date", "row_id"]).groupby("supplier_norm").row_id.first()
    return t.reset_index()

def threshold_clustering(a, tier):
    T, inc = tier["value"], tier["reach_inclusive"]
    lo, lo2 = S["band_fraction"] * T, S["context_band_fraction"] * T
    band = a[(a.amount >= lo) & (a.amount < T)].copy()
    ctx = a[(a.amount >= lo2) & (a.amount < lo)]
    band["tier"] = T; band["band_low"] = lo
    sup = band.groupby("supplier_norm").agg(supplier=("supplier", "first"), payments=("amount", "size"), gbp=("amount", "sum")).sort_values(["payments", "gbp"], ascending=False)
    return band, {"context_lower_band_count": int(len(ctx)), "context_lower_band_gbp": round(float(ctx.amount.sum()), 2),
                  "top_suppliers": [_round({"supplier": r.supplier, "payments": r.payments, "gbp": r.gbp}) for r in sup.head(10).itertuples()],
                  "band_low": lo, "band_high": T}

def split_purchases(a, tier):
    T, inc = tier["value"], tier["reach_inclusive"]
    W = pd.Timedelta(days=S["split_window_days"])
    sub = a[~a.amount.map(lambda x: reaches(x, T, inc))].sort_values(["supplier_norm", "date", "row_id"])
    groups = []
    for sn, g in sub.groupby("supplier_norm", sort=False):
        if len(g) < 2: continue
        d = g.date.values; used = np.zeros(len(g), bool); n = len(g)
        for i in range(n):
            if used[i]: continue
            idx = [j for j in range(i, n) if not used[j] and (d[j] - d[i]) <= W.to_timedelta64()]
            tot = g.amount.iloc[idx].sum()
            if len(idx) >= 2 and reaches(tot, T, inc):
                for j in idx: used[j] = True
                gg = g.iloc[idx]
                tg = gg.groupby("tag").amount.sum().sort_values(ascending=False)
                groups.append(dict(tier=T, supplier=gg.supplier.iloc[0], supplier_norm=sn, tag=tg.index[0], n_payments=len(gg),
                                   combined_gbp=tot, first_date=gg.date.min(), last_date=gg.date.max(),
                                   span_days=round((gg.date.max() - gg.date.min()).total_seconds() / 86400, 2),
                                   all_amounts_equal=bool(gg.amount.round(2).nunique() == 1),
                                   services="; ".join(sorted(set(gg.service))), row_ids=";".join(gg.row_id)))
            else:
                used[i] = True  # anchor consumed; later payments may anchor their own window
    cols = ["tier", "supplier", "supplier_norm", "tag", "n_payments", "combined_gbp", "first_date", "last_date", "span_days", "all_amounts_equal", "services", "row_ids"]
    return pd.DataFrame(groups, columns=cols)

def duplicates(a):
    W = pd.Timedelta(days=S["duplicate_window_days"])
    b = a.copy(); b["pennies"] = (b.amount * 100).round().astype("int64")
    b = b.sort_values(["supplier_norm", "pennies", "date", "row_id"])
    out = []
    for (sn, p), g in b.groupby(["supplier_norm", "pennies"], sort=False):
        if len(g) < 2: continue
        start = 0; dts = list(g.date)
        for i in range(1, len(g) + 1):
            if i == len(g) or (dts[i] - dts[i - 1]) > W:
                if i - start >= 2:
                    gg = g.iloc[start:i]
                    ident = bool(len(gg.drop_duplicates(["service", "category", "narrative", "date"])) == 1)
                    out.append(dict(supplier=gg.supplier.iloc[0], supplier_norm=sn, tag=gg.groupby("tag").amount.sum().idxmax(), amount=gg.amount.iloc[0],
                                    n_payments=len(gg), total_gbp=gg.amount.sum(), first_date=gg.date.min(), last_date=gg.date.max(),
                                    span_days=round((gg.date.max() - gg.date.min()).total_seconds() / 86400, 2),
                                    identical_on_all_fields=ident, services="; ".join(sorted(set(gg.service))), row_ids=";".join(gg.row_id)))
                start = i
    cols = ["supplier", "supplier_norm", "tag", "amount", "n_payments", "total_gbp", "first_date", "last_date", "span_days", "identical_on_all_fields", "services", "row_ids"]
    return pd.DataFrame(out, columns=cols)
