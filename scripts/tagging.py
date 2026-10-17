import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json, re
TAGS = ["grant", "care_or_education_placement", "agency_staff", "premises", "general_procurement"]
M = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tag_map.json")))
R = M["rules"]
def tag_row(narr, cat, service, supplier):
    n, c, s, p = str(narr or ""), str(cat or ""), str(service or ""), str(supplier or "")
    if re.search(R["grant"]["narrative_regex"], n, re.I): return "grant"
    r = R["care_or_education_placement"]
    if n in r["narrative_exact"] or (n in r["narrative_in_service"]["narratives"] and re.search(r["narrative_in_service"]["service_regex"], s, re.I)):
        return "care_or_education_placement"
    r = R["agency_staff"]
    if re.search(r["narrative_regex"], n, re.I) or re.search(r["supplier_regex"], p, re.I): return "agency_staff"
    r = R["premises"]
    if c in r["category_exact"] or re.search(r["narrative_regex"], n, re.I): return "premises"
    return "general_procurement"
