"""Trusted sources for the user's question (organisers' approved sites only, Tavily `include_domains`).
Rules — the system never makes a religious claim of its own:
  • personal case (level د)  -> decided by a fixed word list, referral only, no links presented as an answer
  • "there is scholarly disagreement" -> shown ONLY when a retrieved fatwa itself says so, quoted with its link
  • links are "the closest answers we found", filtered by search score and word overlap with the question
Tavily search API: https://docs.tavily.com/documentation/api-reference/endpoint/search   Env: TAVILY_KEY
"""
import os, re, requests
from normalize import norm

SITES = ["islamqa.info", "binbaz.org.sa", "binothaimeen.net", "dorar.net", "dawa.center", "islamic-content.com",
         "hadeethenc.com", "islamweb.net", "tafsir.net"]
REFER = "هذه حالة شخصية تحتاج فتوى من جهة مؤهلة؛ لا نقدم حكمًا، ويمكنك سؤال أهل العلم عبر المواقع المعتمدة."
PERSONAL = ["أنا ", "زوجي", "زوجتي", "طلقني", "طلقت", "هل يجوز لي", "هل علي", "حالتي", "في بلدي", "أعيش في", "أنا في",
            "ابني", "ابنتي", "أمي", "أبي", "أخي", "عقدت", "اشتريت", "وقعت", "فعلت", "نذرت", "حلفت", "حكمي", "ماذا أفعل"]
DISAGREE = ["اختلف العلماء", "اختلف أهل العلم", "اختلف الفقهاء", "محل خلاف", "مسألة خلافية", "على قولين", "على أقوال",
            "في المسألة خلاف", "خلاف بين العلماء", "خلاف بين أهل العلم", "والراجح"]
STOP = {"ما", "هل", "حكم", "في", "من", "عن", "على", "الى", "او", "و", "ان", "هو", "هي", "ذلك", "هذا", "كيف", "لماذا", "متى", "يجوز", "الاسلام"}
MIN_SCORE, KEEP = 0.45, 3          # Tavily relevance score floor; links shown

def personal(question):
    return any(m in question for m in PERSONAL)

def words(t):
    return {w for w in norm(t).split() if len(w) > 2 and w not in STOP}

def overlap(question, text):
    q = words(question)
    return len(q & words(text)) / len(q) if q else 0.0

def search(question, n=6, sites=SITES):
    r = requests.post("https://api.tavily.com/search", timeout=30, json={
        "api_key": os.environ["TAVILY_KEY"], "query": question, "include_domains": sites, "max_results": n}).json()
    hits = [{"title": x["title"], "url": x["url"], "snippet": x.get("content", "")[:240], "score": round(x.get("score", 0), 2),
             "overlap": round(overlap(question, x["title"] + " " + x.get("content", "")), 2),
             "_content": x.get("content", "")} for x in r.get("results", [])]
    hits = [h for h in hits if h["score"] >= MIN_SCORE and h["overlap"] > 0]     # drop off-topic pages
    hits.sort(key=lambda h: (overlap(question, h["title"]), h["score"]), reverse=True)  # title matching the question first
    return hits[:KEEP]

def disagreement(hits):
    """A source that itself states disagreement -> {"phrase", "url", "title"}; else None. Never inferred by a model."""
    for h in hits:
        for p in DISAGREE:
            if p in h["_content"]:
                return {"phrase": p, "url": h["url"], "title": h["title"]}
    return None

def recommend(question):
    if personal(question):
        return {"level": "د", "links": [], "refer": True, "note": REFER}
    hits = search(question)
    d = disagreement(hits)
    for h in hits: h.pop("_content", None)
    return {"level": None, "links": hits, "refer": False, "disagreement": d,
            "note": "" if hits else "لم نجد إجابة مباشرة في المواقع المعتمدة؛ يمكنك سؤال أهل العلم."}

def explain_link(span, label):
    """'اقرأ الشرح' for a verified hadith (hadeethenc) or the tafsir for an ayah (tafsir.net / dorar)."""
    sites = ["hadeethenc.com"] if label == "MATN" else ["tafsir.net", "dorar.net"]
    hits = search(span, n=2, sites=sites)
    return hits[0] if hits else None

if __name__ == "__main__":
    for q in ["ما هي أركان الإسلام؟", "هل تصح الصلاة بدون وضوء؟", "ما حكم قتل الضفدع؟", "أنا في بريطانيا وزوجي طلقني عبر رسالة، هل وقع الطلاق؟"]:
        r = recommend(q)
        print(q, "→", r["level"] or "-", r["note"] or "", r.get("disagreement"))
        for l in r["links"]: print("   ", l["score"], l["overlap"], l["title"], l["url"])
