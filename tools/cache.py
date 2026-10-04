"""Disk cache for external calls. Commit tools/cache.json so demos are deterministic and sources aren't hammered."""
import json, hashlib, os

PATH = os.path.join(os.path.dirname(__file__), "cache.json")
_c = json.load(open(PATH, encoding="utf-8")) if os.path.exists(PATH) else {}

def cached(key, fn):
    k = hashlib.sha1(key.encode()).hexdigest()
    if k not in _c:
        _c[k] = fn()
        json.dump(_c, open(PATH, "w", encoding="utf-8"), ensure_ascii=False)
    return _c[k]
