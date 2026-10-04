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

def search(text):
    def go():
        r = requests.get("https://dorar.net/dorar_api.json", params={"skey": text}, timeout=30,
                         headers={"User-Agent": "Muhaqiq/0.1 (hadith verification; contact in README)"})
        return parse(r.json().get("ahadith", {}).get("result", ""))
    return cached("dorar:" + text, go)

if __name__ == "__main__":
    for h in search("إنما الأعمال بالنيات")[:3]:
        print(h["text"][:60], "|", h["المحدث"], "|", h["المصدر"], "|", h["خلاصة حكم المحدث"])
