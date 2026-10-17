import re, hashlib
def normalise_supplier(s):
    if s is None: return ""
    s = str(s).upper().replace("&", " AND ").replace("'", "").replace("’", "")
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    s = re.sub(r"\b(LTD|LIMITED|PLC|LLP)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()
