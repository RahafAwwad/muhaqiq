"""hadeethenc.com (organisers' list, p.9): authentic hadiths with explanations, translated into 70+ languages.
API (Postman docs linked from hadeethenc.com/api-docs), base https://hadeethenc.com/api/v1/ :
  categories/list/?language=ar                     -> [{id, title, hadeeths_count, parent_id}]
  hadeeths/list/?language=ar&category_id=ID&page=N&per_page=50 -> {data: [{id, title}], meta: {...}}
  hadeeths/one/?language=LANG&id=ID                -> {id, title, hadeeth, attribution, grade, explanation, ...}
Build a local Arabic index once (python hadeethenc.py build -> tools/hadeethenc.json), then match locally;
the matched id gives the explanation page and translations: https://hadeethenc.com/{lang}/browse/hadith/{id}
Usage terms: no modification of content; credit HadeethEnc.com.
"""
import json, os, sys, time, requests
from rapidfuzz import process, fuzz
from normalize import norm

BASE = "https://hadeethenc.com/api/v1/"
PATH = os.path.join(os.path.dirname(__file__), "hadeethenc.json")

def get(path, **params):
    r = requests.get(BASE + path, params=params, timeout=30); r.raise_for_status(); return r.json()

def build():
    cats = get("categories/list/", language="ar")
    ids = set()
    for c in cats:
        page = 1
        while True:
            d = get("hadeeths/list/", language="ar", category_id=c["id"], page=page, per_page=50)
            ids |= {h["id"] for h in d.get("data", [])}
            if page >= int(d.get("meta", {}).get("last_page", 1)): break
            page += 1
    out = []
    for i, hid in enumerate(sorted(ids)):
        h = get("hadeeths/one/", language="ar", id=hid)
        out.append({"id": hid, "title": h.get("title", ""), "text": h.get("hadeeth", ""), "attribution": h.get("attribution", ""),
                    "grade": h.get("grade", ""), "explanation": (h.get("explanation") or "")[:400]})
        if i % 200 == 0: print(i, "/", len(ids)); time.sleep(0.2)
    json.dump(out, open(PATH, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"{PATH}: {len(out)} hadiths")

ITEMS = json.load(open(PATH, encoding="utf-8")) if os.path.exists(PATH) else []
NORMS = [norm(h["text"]) for h in ITEMS]

def fit(q, c, **kw):
    return fuzz.partial_ratio(q, c) if len(c) >= len(q) else fuzz.ratio(q, c)

def search(text, k=5):
    """Top-k hadiths as verify() candidates: text + المصدر/الحكم from hadeethenc + hadeethenc_id for translations."""
    hits = process.extract(norm(text), NORMS, scorer=fit, limit=k) if NORMS else []
    return [{"text": ITEMS[i]["text"], "المصدر": ITEMS[i]["attribution"], "خلاصة حكم المحدث": ITEMS[i]["grade"],
             "المحدث": "موسوعة الأحاديث النبوية", "hadeethenc_id": ITEMS[i]["id"],
             "url": f"https://hadeethenc.com/ar/browse/hadith/{ITEMS[i]['id']}", "score": round(s, 1)} for _, s, i in hits]

if __name__ == "__main__":
    if sys.argv[1:] == ["build"]: build()
    else: print(search("إنما الأعمال بالنيات")[:1])
