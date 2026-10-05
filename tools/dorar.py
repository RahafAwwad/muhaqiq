"""Hadith lookup via dorar.net's documented search API (no key): https://dorar.net/article/389
GET https://dorar.net/dorar_api.json?skey=<text>  ->  {"ahadith": {"result": "<html>"}}
Each hit: <div class="hadith">TEXT</div><div class="hadith-info">الراوي / المحدث / المصدر / الصفحة أو الرقم / خلاصة حكم المحدث</div>
"""
import re, html, requests
from cache import cached

INFO_KEYS = ["الراوي", "المحدث", "المصدر", "الصفحة أو الرقم", "خلاصة حكم المحدث"]

def strip(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()

def parse(result):
    hits = []
    for text, info in re.findall(r'<div class="hadith"[^>]*>(.*?)</div>\s*<div class="hadith-info">(.*?)</div>', result, re.S):
        text = re.sub(r"^\d+\s*-\s*", "", strip(text)).rstrip(" .")         # drop the leading "1 - " and trailing dots
        info = strip(info)
        fields = {k: (re.search(rf"{k}:\s*(.*?)(?=\s(?:{'|'.join(INFO_KEYS)}):|$)", info) or [None, ""])[1].strip() for k in INFO_KEYS}
        hits.append({"text": text, **fields, "url": "https://dorar.net/hadith/search?q=" + requests.utils.quote(text[:60])})
    return hits

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Muhaqiq/0.1 (hadith verification; contact in README)",
           "Accept": "application/json, text/javascript, */*", "Accept-Language": "ar,en;q=0.8", "Referer": "https://dorar.net/hadith"}

def search(text):
    def go():
        r = None
        try:
            r = requests.get("https://dorar.net/dorar_api.json", params={"skey": text}, timeout=30, headers=HEADERS)
            return parse(r.json().get("ahadith", {}).get("result", ""))
        except Exception as e:                                    # non-JSON (block page / rate limit) or network error
            print(f"dorar unavailable for {text[:30]!r}: {e}; reply starts: {(r.text if r is not None else '')[:120]!r}")
            raise                                                 # not cached, so the next call retries
    try: return cached("dorar:" + text, go)
    except Exception: return []

if __name__ == "__main__":
    for h in search("إنما الأعمال بالنيات")[:3]:
        print(h["text"][:60], "|", h["المحدث"], "|", h["المصدر"], "|", h["خلاصة حكم المحدث"])
