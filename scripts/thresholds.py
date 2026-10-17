import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json
from config import ROOT

class RulesError(Exception): pass

def load_rules():
    try:
        r = json.load(open(f"{ROOT}/outputs/rules.json"))
        assert isinstance(r.get("rules"), list) and isinstance(r.get("parameters"), dict)
    except Exception as e:
        raise RulesError(f"outputs/rules.json missing or invalid: {e}")
    return r

def build(rules=None):
    r = rules or load_rules()
    params = r["parameters"]
    tiers, skipped = {}, {}
    def num(x): return isinstance(x, (int, float)) and not isinstance(x, bool)
    for ru in r["rules"]:
        if ru.get("type") != "procurement-route" or "spend_data" not in ru.get("evidence_source", []): continue
        for side in ("low", "high"):
            v, p = ru.get(f"threshold_{side}"), ru.get(f"threshold_{side}_param")
            inc = ru.get(f"threshold_{side}_inclusive")
            if num(v):
                t = tiers.setdefault(v, {"value": v, "rule_ids": [], "as_low_inclusive": None, "as_high_inclusive": None, "sources": []})
                if ru["rule_id"] not in t["rule_ids"]: t["rule_ids"].append(ru["rule_id"])
                t["sources"].append({"rule_id": ru["rule_id"], "side": side, "inclusive": inc})
                if side == "low" and t["as_low_inclusive"] is None: t["as_low_inclusive"] = inc
                if side == "high" and t["as_high_inclusive"] is None: t["as_high_inclusive"] = inc
            elif p:
                pv = params.get(p, {}).get("value")
                if num(pv):  # becomes active automatically
                    t = tiers.setdefault(pv, {"value": pv, "rule_ids": [], "as_low_inclusive": None, "as_high_inclusive": None, "sources": []})
                    t["rule_ids"].append(ru["rule_id"]); t["sources"].append({"rule_id": ru["rule_id"], "side": side, "inclusive": inc, "param": p})
                    if side == "low" and t["as_low_inclusive"] is None: t["as_low_inclusive"] = inc
                    if side == "high" and t["as_high_inclusive"] is None: t["as_high_inclusive"] = inc
                else:
                    s = skipped.setdefault(p, {"param": p, "rule_ids": [], "reason": "value is null in rules.json; the PDF does not print it and only a human may set it"})
                    if ru["rule_id"] not in s["rule_ids"]: s["rule_ids"].append(ru["rule_id"])
    out = []
    for v in sorted(tiers):
        t = tiers[v]
        # "reaches the tier": stored lower-bound flag if the value is a lower bound, else complement of the upper-bound flag
        if t["as_low_inclusive"] is not None: reach = bool(t["as_low_inclusive"]); basis = "threshold_low_inclusive"
        else: reach = not bool(t["as_high_inclusive"]); basis = "complement of threshold_high_inclusive"
        t["reach_inclusive"] = reach; t["reach_basis"] = basis
        out.append(t)
    quote = notice = None
    for ru in r["rules"]:
        ra = (ru.get("required_action") or "").lower()
        if quote is None and "invitation" in ra and "quote" in ra and ra.startswith("send") and isinstance(ru.get("threshold_low"), (int, float)):
            quote = {"value": ru["threshold_low"], "inclusive": ru["threshold_low_inclusive"], "rule_ids": []}
        if notice is None and ru.get("type") == "advertising" and "contracts_register" in ru.get("evidence_source", []) and isinstance(ru.get("threshold_low"), (int, float)):
            notice = {"value": ru["threshold_low"], "inclusive": ru["threshold_low_inclusive"], "rule_ids": []}
    for ru in r["rules"]:
        ra = (ru.get("required_action") or "").lower()
        if quote and ra.startswith("send") and "invitation" in ra and "quote" in ra and ru.get("threshold_low") == quote["value"]: quote["rule_ids"].append(ru["rule_id"])
        if notice and ru.get("type") == "advertising" and "contracts_register" in ru.get("evidence_source", []) and ru.get("threshold_low") == notice["value"]: notice["rule_ids"].append(ru["rule_id"])
    anti = [ru["rule_id"] for ru in r["rules"] if ru.get("type") == "anti-avoidance"]
    ext = [ru["rule_id"] for ru in r["rules"] if ru["clause"] == "AppC-D"]
    var = [ru["rule_id"] for ru in r["rules"] if ru["clause"] == "AppC-E"]
    care = [ru["rule_id"] for ru in r["rules"] if ru["clause"] == "AppC-F"]
    return {"tiers": out, "tiers_skipped": list(skipped.values()), "quote": quote, "notice": notice,
            "anti_avoidance_rule_ids": anti, "appC_D": ext, "appC_E": var, "appC_F": care}
if __name__ == "__main__":
    import pprint; pprint.pprint(build())
