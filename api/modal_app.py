"""Muhaqiq API on Modal (CPU). GPU model lives in api/llm_modal.py and is called over HTTP (LLM_URL secret).
POST /spans   {"text"}                 -> detected spans only
POST /verify  {"text", "question"?, "single"?} -> {"summary", "citations", "related"?, "disclosure"}
  single=true: the whole text is ONE ayah/hadith (no detection) — for «دليل واحد» and the extension's right-click
  citation = span + verdict + source + rulings + diff + partial + translations + attribution (for its SOURCE span) + searched
Docs: https://modal.com/docs/guide/webhooks · https://modal.com/docs/guide/secrets
Deploy from the repo root:  modal deploy api/modal_app.py
"""
import modal

MODEL = "muhaqiq/muhaqiq-span-detector"
RELEVANCE = "muhaqiq/muhaqiq-relevance"
VERDICTS = ["مطابق", "لفظ مختلف", "لم نجده", "يحتاج مراجعة"]
DISCLOSURE = "أداة ذكاء اصطناعي: الأحكام من المصادر لا من النموذج؛ ما لم نجده لا نحكم عليه، والمسائل الشخصية تُحال إلى أهل العلم."

def download():
    from huggingface_hub import snapshot_download
    snapshot_download(MODEL); snapshot_download(RELEVANCE)

image = (modal.Image.debian_slim(python_version="3.12")
         .pip_install("transformers", "torch", "huggingface_hub", "fastapi[standard]", "rapidfuzz", "requests")
         .run_function(download)
         .add_local_file("encoder/predict.py", "/root/predict.py")
         .add_local_dir("tools", "/root/tools"))

app = modal.App("muhaqiq-span-detector", image=image)

@app.function(cpu=2, memory=4096, scaledown_window=300, secrets=[modal.Secret.from_name("muhaqiq-keys")])  # LLM_URL, TAVILY_KEY
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def web():
    import sys; sys.path.insert(0, "/root/tools")
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from predict import find_spans
    from rescue import verify_full
    import attribution, recommend, relevance

    api = FastAPI(title="Muhaqiq API")
    api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    import verify as V
    LOW = 0.6                                                   # detector confidence below this -> «ثقة منخفضة» on the card

    def check_quote(s, text, lo, hi, question=None):
        """verify one AYAH/MATN span in place, then repair its edges from the source"""
        s["detector_score"] = s.pop("score", None)              # verification writes its own "score"
        kept = V.clean_span(s["text"])                          # «… يوم الفطر سنن» -> drop «سنن» from the span itself
        if kept and kept != " ".join(s["text"].split()):
            last = kept.split()[-1]; cut = s["text"].rfind(last, 0, len(s["text"]) - 1) + len(last)
            if cut > len(last): s["end"] = s["start"] + cut; s["text"] = text[s["start"]:s["end"]]
        s["low_confidence"] = s["detector_score"] is not None and s["detector_score"] < LOW
        s.update(verify_full(s["text"], s["label"]))
        a, b = V.repair_boundaries(text, s["start"], s["end"], s, lo, hi)
        if (a, b) != (s["start"], s["end"]):
            s.update(start=a, end=b, text=text[a:b], repaired=True)
            V.refresh(s, s["text"], s["label"])
        if question and s.get("verdict"):
            try: s["relevance"] = relevance.score(question, s["text"])
            except Exception as e: s["relevance"] = {"error": str(e)}

    def analyse(text, question=None):
        spans = find_spans(text)
        last = None                                             # the most recent AYAH/MATN, to pair a SOURCE span with
        for k, s in enumerate(spans):
            if s["label"] in ("AYAH", "MATN"):
                lo = spans[k - 1]["end"] if k else 0
                hi = spans[k + 1]["start"] if k + 1 < len(spans) else len(text)
                check_quote(s, text, lo, hi, question); last = s
            elif s["label"] == "SOURCE" and last and s["start"] - last["end"] < 80 and last.get("verdict") not in (None, "لم نجده"):
                s["attribution"] = attribution.check(s["text"], last["label"], last)
                last["attribution"] = s["attribution"]
        return spans

    def one_quote(text):
        """«دليل واحد»: the whole input IS the quote (no detection). A trailing «رواه …» / «[البقرة: 255]» found by the
        detector is split off and used for the source check. Tried as an ayah first, then as a hadith."""
        claim = next((s for s in find_spans(text) if s["label"] == "SOURCE" and s["start"] > len(text) * 0.4), None)
        quote = text[:claim["start"]].rstrip(" \t\n-–—:،,.()[]") if claim else text.strip()
        best = None
        for label in ("AYAH", "MATN"):                          # sources only first: fast, no GPU
            r = V.verify(quote, label, short_rule=False)
            if r.get("verdict") in ("مطابق", "لفظ مختلف"): best = (label, r); break
            if best is None or (r.get("score") or 0) > (best[1].get("score") or 0): best = (label, r)
        label, r = best
        if r.get("verdict") not in ("مطابق", "لفظ مختلف"):     # neither matched: now ask ALLaM, for the closer type only
            r = verify_full(quote, label)
        cit = {"label": label, "start": text.index(quote) if quote in text else 0, "text": quote, "single": True, **r}
        cit["end"] = cit["start"] + len(quote)
        out = [cit]
        if claim and r.get("verdict") not in (None, "لم نجده"):
            claim["attribution"] = cit["attribution"] = attribution.check(claim["text"], label, cit)
            out.append(claim)
        return out

    @api.post("/spans")
    def spans(body: dict):
        return find_spans(body["text"])

    @api.post("/verify")
    def verify_text(body: dict):
        """{"text", "question"?, "single"?}: single=true treats the whole text as one ayah/hadith (no detection)"""
        citations = one_quote(body["text"]) if body.get("single") else analyse(body["text"], body.get("question"))
        out = {"summary": {v: sum(c.get("verdict") == v for c in citations) for v in VERDICTS},
               "attribution_issues": sum(c.get("attribution", {}).get("verdict") == "المصدر غير دقيق" for c in citations if c["label"] == "SOURCE"),
               "citations": citations, "disclosure": DISCLOSURE}
        if body.get("question"):
            try: out["related"] = recommend.recommend(body["question"])
            except Exception as e: out["related"] = {"error": str(e)}
        return out

    return api
