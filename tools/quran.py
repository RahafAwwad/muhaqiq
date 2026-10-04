"""Quran lookup against a local copy of all 6,236 ayat (downloaded once from quran.com API v4).
API: https://api-docs.quran.com/docs/content_apis_versioned/verses-by-chapter-number
Fuzzy matching: https://rapidfuzz.github.io/RapidFuzz/Usage/process.html
Build the index once:  python quran.py build
"""
import json, os, sys, requests
from rapidfuzz import process, fuzz
from normalize import norm

PATH = os.path.join(os.path.dirname(__file__), "quran.json")
API = "https://api.quran.com/api/v4/verses/by_chapter/{}?fields=text_uthmani,text_imlaei_simple&per_page=300"

def build():
    verses = []
    for ch in range(1, 115):
        for v in requests.get(API.format(ch), timeout=30).json()["verses"]:
            verses.append({"key": v["verse_key"], "uthmani": v["text_uthmani"], "simple": v["text_imlaei_simple"]})
    json.dump(verses, open(PATH, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"{PATH}: {len(verses)} ayat")

VERSES = json.load(open(PATH, encoding="utf-8")) if os.path.exists(PATH) else []
# single ayat + each ayah joined with the next one (quotes often run across an ayah boundary)
UNITS = [dict(v) for v in VERSES]
for a, b in zip(VERSES, VERSES[1:]):
    if a["key"].split(":")[0] == b["key"].split(":")[0]:
        UNITS.append({"key": f'{a["key"]}-{b["key"].split(":")[1]}', "uthmani": a["uthmani"] + " ۝ " + b["uthmani"],
                      "simple": a["simple"] + " " + b["simple"]})
NORMS = [norm(u["simple"]) for u in UNITS]

def fit(q, c, **kw):
    """How well the quote fits inside the candidate: partial match only when the candidate is at least as long."""
    return fuzz.partial_ratio(q, c) if len(c) >= len(q) else fuzz.ratio(q, c)

def search(text, k=5):
    """Top-k units by fit of the normalised span. Returns [{ref, text, simple, url, score}]."""
    hits = process.extract(norm(text), NORMS, scorer=fit, limit=k)
    return [{"ref": UNITS[i]["key"], "text": UNITS[i]["uthmani"], "simple": UNITS[i]["simple"],
             "url": "https://quran.com/" + UNITS[i]["key"].split("-")[0], "score": round(score, 1)} for _, score, i in hits]

if __name__ == "__main__":
    if sys.argv[1:] == ["build"]: build()
    else:
        for t in ["ولا تنسوا الفضل بينكم", "إِنَّ الْمُتَّقِينَ فِي مَقَامٍ أَمِينٍ", "لَمْ يَلِدْ وَلَمْ يُولَدْ * وَلَمْ يَكُن لَّهُ كُفُوًا أَحَدٌ"]:
            print(t, "→", search(t)[0]["ref"], search(t)[0]["score"])
