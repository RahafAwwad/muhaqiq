"""Muhaqiq API on Modal (CPU). GPU model lives in api/llm_modal.py and is called over HTTP (LLM_URL secret).
POST /spans   {"text"}                 -> detected spans only
POST /verify  {"text", "question"?}    -> {"summary", "citations", "related"?, "disclosure"}
  citation = span + verdict + source + rulings + diff + partial + translations + attribution (for its SOURCE span) + searched
Docs: https://modal.com/docs/guide/webhooks · https://modal.com/docs/guide/secrets
Deploy from the repo root:  modal deploy api/modal_app.py
"""
import modal

MODEL = "muhaqiq/muhaqiq-span-detector"
VERDICTS = ["مطابق", "لفظ مختلف", "لم نجده", "يحتاج مراجعة"]
DISCLOSURE = "أداة ذكاء اصطناعي: الأحكام من المصادر لا من النموذج؛ ما لم نجده لا نحكم عليه، والمسائل الشخصية تُحال إلى أهل العلم."

def download():
    from huggingface_hub import snapshot_download
    snapshot_download(MODEL)

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
    import attribution, recommend

    api = FastAPI(title="Muhaqiq API")
    api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def analyse(text):
        spans = find_spans(text)
        last = None                                             # the most recent AYAH/MATN, to pair a SOURCE span with
        for s in spans:
            if s["label"] in ("AYAH", "MATN"):
                s.update(verify_full(s["text"], s["label"])); last = s
            elif s["label"] == "SOURCE" and last and s["start"] - last["end"] < 80 and last.get("verdict") != "لم نجده":
                s["attribution"] = attribution.check(s["text"], last["label"], last)
                last["attribution"] = s["attribution"]
        return spans

    @api.post("/spans")
    def spans(body: dict):
        return find_spans(body["text"])

    @api.post("/verify")
    def verify_text(body: dict):
        citations = analyse(body["text"])
        out = {"summary": {v: sum(c.get("verdict") == v for c in citations) for v in VERDICTS},
               "attribution_issues": sum(c.get("attribution", {}).get("verdict") == "العزو غير دقيق" for c in citations if c["label"] == "SOURCE"),
               "citations": citations, "disclosure": DISCLOSURE}
        if body.get("question"):
            try: out["related"] = recommend.recommend(body["question"])
            except Exception as e: out["related"] = {"error": str(e)}
        return out

    return api
