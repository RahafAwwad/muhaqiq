"""Trusted sources for the user's question, following the organisers' content levels (reference pack p.2):
  أ stable facts · ب explanation · ج contested/sensitive · د personal fatwa -> NO links as answers, referral only.
Search is restricted to the organisers' approved sites (Tavily `include_domains`): https://docs.tavily.com/documentation/api-reference/endpoint/search
Level classification: ALLaM via the Modal /chat route (LLM_URL). Env: TAVILY_KEY, LLM_URL.
"""
import os, re, requests

SITES = ["islamqa.info", "binbaz.org.sa", "binothaimeen.net", "dorar.net", "dawa.center", "islamic-content.com",
         "hadeethenc.com", "islamweb.net", "tafsir.net"]
LEVELS = ("أ: معلومات أصلية مستقرة (القرآن، الأحاديث الصحيحة، أركان الإسلام، السيرة، القيم)\n"
          "ب: شرح وتعريف واستدلال (المفاهيم، المقارنات، الشبهات العامة)\n"
          "ج: مسائل خلافية أو عالية الحساسية (الخلاف الفقهي، المسائل العقدية التفصيلية، القضايا التاريخية الجدلية)\n"
          "د: فتوى أو حالة شخصية (حكم على واقعة لشخص بعينه، صحة عقد أو عبادة لشخص، نزاع أسري، مسألة قانونية أو طبية)")
REFER = "هذه حالة شخصية تحتاج فتوى من جهة مؤهلة؛ لا نقدم حكمًا، ويمكنك سؤال أهل العلم عبر المواقع المعتمدة."

PERSONAL = ["أنا ", "زوجي", "زوجتي", "طلقني", "طلقت", "هل يجوز لي", "هل علي", "حالتي", "في بلدي", "أعيش في", "أنا في",
            "ابني", "ابنتي", "أمي", "أبي", "أخي", "عقدت", "اشتريت", "وقعت", "فعلت", "نذرت", "حلفت", "حكمي", "ماذا أفعل"]

def level(question):
    """Content level أ/ب/ج/د. A personal-case marker decides د by rule; otherwise ALLaM picks among the four."""
    if any(m in question for m in PERSONAL): return "د"
    url = os.environ.get("LLM_URL", "").rstrip("/")
    if not url or "placeholder" in url: return "ب"
    try:
        r = requests.post(f"{url}/chat", timeout=120, json={"prompt":
            f"صنّف السؤال التالي إلى أحد المستويات. أجب بحرف واحد فقط من غير شرح: أ أو ب أو ج أو د.\n{LEVELS}\nالسؤال: {question}"}).json()
        m = re.search(r"(?<![\w])([أبجد])(?![\w])", r.get("text") or "")
        return m.group(1) if m else "ب"
    except Exception as e:
        print("level model unavailable:", e); return "ب"

def search(question, n=3, sites=SITES):
    r = requests.post("https://api.tavily.com/search", timeout=30, json={
        "api_key": os.environ["TAVILY_KEY"], "query": question, "include_domains": sites, "max_results": n}).json()
    return [{"title": x["title"], "url": x["url"], "snippet": x.get("content", "")[:200]} for x in r.get("results", [])]

def recommend(question):
    lv = level(question)
    if lv == "د": return {"level": lv, "links": [], "refer": True, "note": REFER}
    return {"level": lv, "links": search(question), "refer": lv == "ج",
            "note": "مسألة فيها خلاف بين أهل العلم — انظر أقوالهم في المصادر المعتمدة" if lv == "ج" else ""}

def explain_link(span, label):
    """'اقرأ الشرح' for a verified hadith (hadeethenc) or the tafsir for an ayah (tafsir.net / dorar)."""
    sites = ["hadeethenc.com"] if label == "MATN" else ["tafsir.net", "dorar.net"]
    hits = search(span, n=1, sites=sites)
    return hits[0] if hits else None

if __name__ == "__main__":
    for q in ["ما هي أركان الإسلام؟", "ما حكم أكل لحم الضفدع؟", "أنا في بريطانيا وزوجي طلقني عبر رسالة، هل وقع الطلاق؟"]:
        r = recommend(q); print(q, "→", r["level"], r.get("note") or [l["url"] for l in r["links"]])
