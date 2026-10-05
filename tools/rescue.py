"""Hard cases (لم نجده): ask the restorer what the quote was meant to be, then LOOK IT UP.
Nothing a model says is shown unverified. Optional second voter (any OpenAI-compatible API) for the ensemble gate:
  both lead to the same verified source text -> لفظ مختلف (suggested) ; one, or they disagree -> يحتاج مراجعة
Env: LLM_URL (Modal llm endpoint, required) · LLM_B_URL / LLM_B_KEY / LLM_B_MODEL (optional second voter)
"""
import os, json, re, requests
from normalize import norm
import verify as V

LLM = os.environ.get("LLM_URL", "").rstrip("/")
RELATED = 60                  # min window ratio between the quote and a proposed source for it to be shown as a candidate

def propose_a(span, label):
    if not LLM or "placeholder" in LLM: return ""
    try:
        r = requests.post(f"{LLM}/restore", json={"span": span, "label": label}, timeout=120).json()
        return (r.get("canonical") or "").strip()
    except Exception as e:
        print("restorer unavailable:", e); return ""

def propose_b(span, label):
    url, key, model = (os.environ.get(f"LLM_B_{k}") for k in ("URL", "KEY", "MODEL"))
    if not url: return ""
    kind = {"AYAH": "القرآن الكريم", "MATN": "الحديث النبوي"}[label]
    prompt = (f"النص التالي اقتباس من {kind} وقد يكون محرَّفًا. أعد اللفظ الصحيح كاملًا كما في المصدر بصيغة JSON "
              f"بالمفتاحين canonical و reference، وإن لم تعرف فاجعل canonical فارغًا.\nالنص: {span}\nJSON:")
    try:
        r = requests.post(f"{url}/chat/completions", headers={"Authorization": f"Bearer {key}"}, timeout=60,
                          json={"model": model, "temperature": 0, "messages": [{"role": "user", "content": prompt}]}).json()
        m = re.search(r"\{.*\}", r["choices"][0]["message"]["content"], re.S)
        return (json.loads(m.group()).get("canonical") or "").strip() if m else ""
    except Exception as e:
        print("model B unavailable:", e); return ""

def rescue(span, label, searched):
    """Returns a verdict dict (same shape as verify) or None if the models add nothing."""
    found = {}
    for name, fn in (("restorer", propose_a), ("model B", propose_b)):
        p = fn(span, label)
        if not p or norm(p) == norm(span): continue
        searched.append((f"{name} proposal → source", p))
        r = V.verify(p, label)
        if r["verdict"] == "مطابق": found[name] = r["source"]
    if not found: return None
    texts = {norm(s.get("simple") or s["text"]) for s in found.values()}
    src = next(iter(found.values()))
    window_score, window = V.best_window(span, src.get("simple") or src["text"])
    if (len(found) == 2 and len(texts) == 1) or (len(found) == 1 and window_score >= V.NEAR):
        return {"verdict": "لفظ مختلف", "score": round(window_score, 1), "source": src, "canonical": window,
                "diff": V.diff_words(span, window), "via": list(found), "searched": searched}
    if window_score >= RELATED:                       # a real text that resembles the quote: worth a human look
        return {"verdict": "يحتاج مراجعة", "score": round(window_score, 1), "candidates": [s.get("ref") or s.get("المصدر") for s in found.values()],
                "closest": src, "closest_window": window, "via": list(found), "searched": searched}
    return None                                       # the model proposed something unrelated: ignore it

def verify_full(span, label):
    r = V.verify(span, label)
    if r["verdict"] != "لم نجده": return r
    return rescue(span, label, r["searched"]) or r
