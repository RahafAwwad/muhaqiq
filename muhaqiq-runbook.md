# Muhaqiq — detailed build runbook (v2)

How to use this: do the steps in order. Every step has **Do** (exact commands and file contents), **Why** (what you are actually doing, in plain words), **Done when** (a check you can see), **Read** (the official page), and **In a company** (what the same step looks like at scale — for learning, not for this week).

Dates: hackathon 4–6 Oct. Steps 0–5 = the starting version you declare. Steps 6–9 = hackathon. Step 7 (ALLaM fine-tune) is droppable. Step 10 = stretch features if time remains.

Conventions: `$` = run in your laptop terminal. Cells marked `# Colab` run in a Colab notebook. Replace `muhaqiq` with your actual HF org/user name if different.

---

## Glossary (read once)

- **Encoder / token classification** — a BERT-type model that reads text and labels every token; we label tokens as inside an ayah/isnad/matn/source or not. Also called NER.
- **Fine-tuning** — taking a pre-trained model and training it a little more on your labelled data so it learns your task. The model already knows Arabic; you teach it where citations are.
- **Epoch** — one full pass over the training data. **Learning rate** — how big each update step is (3e-5 is the usual safe value for BERT). **Batch size** — how many examples per step.
- **Checkpoint** — a saved copy of the model mid-training. **Hub** — huggingface.co, where models/datasets are stored like GitHub for files.
- **LoRA / QLoRA** — fine-tuning a big model by training a small set of extra weights (an "adapter") instead of all 7B parameters; QLoRA additionally loads the base model in 4-bit so it fits on a 16 GB GPU.
- **Endpoint / API** — a URL that accepts a request (text) and returns a response (JSON). **FastAPI** — the Python library that makes one. **Space** — a free server on Hugging Face that runs your API. **CORS** — a browser rule; the server must say "pages from other sites may call me".
- **Content script** — JavaScript that a Chrome extension injects into a web page.

---

## Step 0 — Accounts, tools, repository

### Do

0.1 On your laptop: Python 3.11+, git, VS Code. Check:
```
$ python3 --version
$ git --version
```

0.2 Hugging Face: huggingface.co → Sign up → Settings → **Access Tokens → New token → type: Write** → copy it. Then:
```
$ pip install -U huggingface_hub
$ huggingface-cli login        # paste the token when asked
$ huggingface-cli whoami       # prints your username
```
0.3 HF organisation: huggingface.co/organizations/new → name `muhaqiq`.

0.4 GitHub repo: github.com/new → `muhaqiq` (public, Apache-2.0 licence, add .gitignore: Python). Then:
```
$ git clone https://github.com/<you>/muhaqiq.git
$ cd muhaqiq
$ mkdir -p encoder space web extension tools api eval data
$ printf "data/\n*.jsonl\ndata_tok/\n.env\n" >> .gitignore      # never commit data or secrets
$ git add . && git commit -m "scaffold" && git push
```
0.5 Google Colab: colab.research.google.com → New notebook → Runtime → Change runtime type → **T4 GPU** → Save. Kaggle: kaggle.com → Settings → Phone verification (unlocks 30 GPU-h/week) — backup for Step 7.

### Why
Everything you make must live somewhere that survives a closed laptop: code on GitHub, models/data on the Hub. The token is how Colab proves it's you when it uploads.

### Done when
`huggingface-cli whoami` prints your name and the repo folder exists with the sub-folders.

### In a company
Same split: code in GitHub/GitLab, models in a registry (HF Hub, MLflow, Weights & Biases Artifacts, or SageMaker Model Registry), secrets in a vault (AWS Secrets Manager / 1Password), never in code.

---

## Step 1 — Data: convert, upload, verify

### Do

1.1 Download the public IslamicEval Subtask A train/dev files into `data/`. Open one record and note the field names. Then edit the `FIELDS` block in the file below to match.

1.2 `encoder/convert.py`:
```python
"""Convert IslamicEval Subtask A records to Muhaqiq JSONL.
Output line: {"text": "...", "spans": [{"start": 127, "end": 161, "label": "AYAH"}]}
EDIT the FIELDS block to match the real file (open one record to see the names).
"""
import json, sys

FIELDS = {                       # <-- edit these four names to match the dataset
    "text": "response",          # key holding the full answer text
    "spans": "citations",        # key holding the list of annotated segments
    "start": "start", "end": "end", "type": "type",
}
LABEL_MAP = {"Ayah": "AYAH", "Isnad": "ISNAD", "Hadith matn": "MATN", "Claimed source": "SOURCE"}

def convert(src, dst):
    n = 0
    with open(src, encoding="utf-8") as f, open(dst, "w", encoding="utf-8") as out:
        records = json.load(f) if src.endswith(".json") else [json.loads(l) for l in f]
        for r in records:
            spans = [{"start": s[FIELDS["start"]], "end": s[FIELDS["end"]],
                      "label": LABEL_MAP[s[FIELDS["type"]]]} for s in r[FIELDS["spans"]]]
            out.write(json.dumps({"text": r[FIELDS["text"]], "spans": spans}, ensure_ascii=False) + "\n")
            n += 1
    print(f"{dst}: {n} records")

convert(sys.argv[1], sys.argv[2])
```
Run:
```
$ python encoder/convert.py data/subtaskA_train.json data/train.jsonl
$ python encoder/convert.py data/subtaskA_dev.json   data/dev.jsonl
$ head -c 600 data/train.jsonl          # eyeball one line
```

1.3 Upload to the Hub (private until the licence allows public):
```
$ pip install datasets
$ python -c "
from datasets import load_dataset
ds = load_dataset('json', data_files={'train':'data/train.jsonl','validation':'data/dev.jsonl'})
ds.push_to_hub('muhaqiq/span-data', private=True); print(ds)"
```

1.4 `encoder/prepare.py` (final version — 4 labels, long texts handled with sliding windows):
```python
"""Character spans -> token BIO labels. Reads the Hub dataset, writes ./data_tok
Long answers are split into 512-token windows that overlap by 128 tokens (stride)."""
from datasets import load_dataset
from transformers import AutoTokenizer

MODEL = "CAMeL-Lab/bert-base-arabic-camelbert-msa"
LABELS = ["O","B-AYAH","I-AYAH","B-ISNAD","I-ISNAD","B-MATN","I-MATN","B-SOURCE","I-SOURCE"]
label2id = {l: i for i, l in enumerate(LABELS)}
tok = AutoTokenizer.from_pretrained(MODEL)

def label_tokens(batch):
    enc = tok(batch["text"], truncation=True, max_length=512, stride=128,
              return_overflowing_tokens=True, return_offsets_mapping=True)
    all_labels = []
    for i, offsets in enumerate(enc["offset_mapping"]):
        spans = batch["spans"][enc["overflow_to_sample_mapping"][i]]
        labels = []
        for start, end in offsets:
            lab = "O"
            if end > start:
                for s in spans:
                    if s["start"] <= start < s["end"]:
                        lab = ("B-" if start == s["start"] else "I-") + s["label"]; break
            labels.append(label2id[lab] if end > start else -100)
        all_labels.append(labels)
    enc["labels"] = all_labels
    enc.pop("offset_mapping"); enc.pop("overflow_to_sample_mapping")
    return enc

if __name__ == "__main__":
    ds = load_dataset("muhaqiq/span-data")
    ds = ds.map(label_tokens, batched=True, remove_columns=["text", "spans"])
    ds.save_to_disk("data_tok"); print(ds)
```

1.5 `encoder/check.py` (round-trip test — do spans survive conversion?):
```python
from datasets import load_dataset
from transformers import AutoTokenizer
from prepare import LABELS, label_tokens, MODEL
tok = AutoTokenizer.from_pretrained(MODEL)

def labels_to_spans(offsets, labels):
    spans, cur = [], None
    for (s, e), l in zip(offsets, labels):
        tag = LABELS[l] if l != -100 else "O"
        if tag.startswith("B-") or (tag.startswith("I-") and cur is None):
            if cur: spans.append(cur)
            cur = {"start": s, "end": e, "label": tag[2:]}
        elif tag.startswith("I-") and cur and cur["label"] == tag[2:]:
            cur["end"] = e
        else:
            if cur: spans.append(cur)
            cur = None
    return spans + ([cur] if cur else [])

ok = total = 0
for ex in load_dataset("muhaqiq/span-data")["validation"]:
    enc = tok(ex["text"], truncation=True, max_length=512, stride=128,
              return_overflowing_tokens=True, return_offsets_mapping=True)
    labs = label_tokens({"text": [ex["text"]], "spans": [ex["spans"]]})["labels"]
    back = set()
    for offsets, l in zip(enc["offset_mapping"], labs):
        back |= {(s["start"], s["end"], s["label"]) for s in labels_to_spans(offsets, l)}
    gold = {(s["start"], s["end"], s["label"]) for s in ex["spans"]}
    total += len(gold); ok += len(gold & back)
    for s in gold - back: print("LOST:", s, repr(ex["text"][s[0]:s[1]][:40]))
print(f"round-trip: {ok}/{total} spans recovered ({100*ok/total:.1f}%)")
```
Run:
```
$ pip install transformers
$ cd encoder && python check.py
```

### Why
Training only learns what the labels say. If a gold span starts at a space, or the tokenizer splits differently from the annotation, the model is taught the wrong boundaries and you only find out after an hour of GPU. The round-trip test catches this in seconds.

### Done when
`check.py` prints ≥ 98%. If spans are LOST with a 1–2 character difference: the gold offset includes a leading space/bracket — strip it in `convert.py` (`while text[start].isspace(): start += 1`). Note the rule in the README; the same rule applies at evaluation.

### Read
HF course ch.6 §3 (offset mapping, overflow/stride) · Datasets `push_to_hub`.

### In a company
Data is versioned (DVC, LakeFS, or HF dataset revisions), with a schema check in CI so a changed field name fails before training, not after.

---

## Step 2 — Fine-tune the encoder (Colab)

### Do

2.1 `encoder/train.py`:
```python
"""Fine-tune CAMeLBERT for citation span detection.
Checkpoints: Drive (survives Colab disconnects) + Hub (survives everything)."""
import os, numpy as np, evaluate
from datasets import load_from_disk
from transformers import (AutoTokenizer, AutoModelForTokenClassification,
                          DataCollatorForTokenClassification, TrainingArguments, Trainer)
from prepare import MODEL, LABELS

SMOKE = os.environ.get("SMOKE") == "1"          # SMOKE=1 python train.py  -> 200 examples, 1 epoch
OUT = os.environ.get("OUT", "muhaqiq-span-detector")

ds = load_from_disk("data_tok")
if SMOKE: ds["train"] = ds["train"].select(range(200)); ds["validation"] = ds["validation"].select(range(100))
tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForTokenClassification.from_pretrained(
    MODEL, num_labels=len(LABELS), id2label=dict(enumerate(LABELS)),
    label2id={l: i for i, l in enumerate(LABELS)})
seqeval = evaluate.load("seqeval")

def compute_metrics(p):
    preds = np.argmax(p.predictions, axis=2)
    true = [[LABELS[l] for l in row if l != -100] for row in p.label_ids]
    pred = [[LABELS[q] for q, l in zip(prow, lrow) if l != -100] for prow, lrow in zip(preds, p.label_ids)]
    r = seqeval.compute(predictions=pred, references=true)
    out = {"f1": r["overall_f1"], "precision": r["overall_precision"], "recall": r["overall_recall"]}
    out.update({f"f1_{k}": v["f1"] for k, v in r.items() if isinstance(v, dict)})   # per-label F1
    return out

args = TrainingArguments(OUT, learning_rate=3e-5, num_train_epochs=1 if SMOKE else 4,
    per_device_train_batch_size=8 if SMOKE else 16, per_device_eval_batch_size=32,
    eval_strategy="epoch", save_strategy="epoch", save_total_limit=2,
    load_best_model_at_end=True, metric_for_best_model="f1", fp16=True, logging_steps=20,
    push_to_hub=not SMOKE, hub_model_id="muhaqiq/muhaqiq-span-detector", hub_strategy="checkpoint",
    report_to="none")

trainer = Trainer(model=model, args=args, train_dataset=ds["train"], eval_dataset=ds["validation"],
                  data_collator=DataCollatorForTokenClassification(tok), compute_metrics=compute_metrics)
trainer.train(resume_from_checkpoint=os.environ.get("RESUME") == "1")
print(trainer.evaluate())
if not SMOKE: trainer.push_to_hub(); tok.push_to_hub("muhaqiq/muhaqiq-span-detector")
```

2.2 Colab notebook, cell by cell:
```python
# Colab cell 1 — setup
!pip install -q transformers datasets evaluate seqeval accelerate
from huggingface_hub import login; login()                 # paste WRITE token
from google.colab import drive; drive.mount('/content/drive')
!git clone https://github.com/<you>/muhaqiq.git && cd muhaqiq/encoder
%cd /content/muhaqiq/encoder
```
```python
# Colab cell 2 — tokenise (1–2 min)
!python prepare.py
```
```python
# Colab cell 3 — SMOKE run (~5 min). Checking: loss goes down, f1 > 0, no crash.
!SMOKE=1 python train.py
```
```python
# Colab cell 4 — REAL run (20–60 min). Output on Drive so a disconnect loses nothing.
!OUT=/content/drive/MyDrive/muhaqiq/span-detector python train.py
```
```python
# Colab cell 5 — only if Colab disconnected mid-run: re-run cells 1–2, then
!RESUME=1 OUT=/content/drive/MyDrive/muhaqiq/span-detector python train.py
```
```python
# Colab cell 6 — try it
from transformers import pipeline
d = pipeline("token-classification", model="muhaqiq/muhaqiq-span-detector", aggregation_strategy="simple")
d("قال الله تعالى: ولا تنسوا الفضل بينكم. وقال النبي ﷺ: إنما الأعمال بالنيات. رواه البخاري")
```

2.3 Write results into the model card: on the Hub, the model page → Edit model card → paste the per-label F1 from the last `evaluate()` print.

2.4 (If you have the official Subtask A scorer) `encoder/predict_dev.py`: run the pipeline over every dev text, write the task's submission format, run the scorer. Record the number.

### Why
Smoke first: every bug shows up in the first 50 steps; a smoke run costs 5 minutes, a failed real run costs an hour. Drive + Hub: Colab kills idle sessions; `hub_strategy="checkpoint"` means the last checkpoint is also on the Hub so you can resume from anywhere.

### Done when
Cell 6 returns spans with the right labels on text it has never seen, and the model page on the Hub shows files + a card with numbers.

### Read
HF "Token classification" task guide · `TrainingArguments` (push_to_hub, hub_strategy, resume_from_checkpoint) · seqeval.

### In a company
Training runs on a managed GPU service (AWS SageMaker, GCP Vertex AI, Azure ML, or Modal/RunPod/Lambda for smaller teams) launched from a script, not a notebook; experiments logged to Weights & Biases or MLflow; the chosen checkpoint promoted in a model registry with its eval numbers attached.

---

## Step 3 — Serve the encoder (Gradio Space)

### Do

3.1 huggingface.co/new-space → owner `muhaqiq`, name `span-detector`, SDK **Gradio**, hardware CPU basic, public.

3.2 Files (push them with git — a Space is a git repo):
```
$ git clone https://huggingface.co/spaces/muhaqiq/span-detector
$ cd span-detector
```
`app.py`:
```python
import gradio as gr
from transformers import pipeline
detect = pipeline("token-classification", model="muhaqiq/muhaqiq-span-detector",
                  aggregation_strategy="simple")
def find_spans(text):
    return [{"label": s["entity_group"], "start": s["start"], "end": s["end"],
             "text": text[s["start"]:s["end"]], "score": round(float(s["score"]), 3)} for s in detect(text)]
gr.Interface(find_spans, gr.Textbox(lines=8, label="نص"), gr.JSON(label="الاستشهادات"),
             title="Muhaqiq — span detector").launch()
```
`requirements.txt`:
```
transformers
torch
```
```
$ git add . && git commit -m "space" && git push
```
Watch the **Logs** tab on the Space page until it says Running (3–5 min).

3.3 Test in the browser (paste a paragraph). Then from the terminal (two calls — Gradio's API is submit-then-read):
```
$ curl -s -X POST https://muhaqiq-span-detector.hf.space/gradio_api/call/predict \
    -H 'Content-Type: application/json' \
    -d '{"data":["قال الله تعالى: ولا تنسوا الفضل بينكم"]}'
# -> {"event_id":"abc123"}
$ curl -s https://muhaqiq-span-detector.hf.space/gradio_api/call/predict/abc123
# -> event: complete  data: [[{"label":"AYAH",...}]]
```

### Why
A model on the Hub is a file; a Space is a running program that answers requests. Gradio gives you the web UI and the API together with zero extra code, which is why it is first. The `curl` is the proof that any program anywhere can now use your model.

### Done when
The second curl prints spans.

### Read
Hub docs "Gradio Spaces" · Gradio "Querying Gradio apps with curl".

### In a company
Inference runs behind a load balancer on autoscaling GPU/CPU containers: HF Inference Endpoints, AWS SageMaker Endpoints, GCP Cloud Run/GKE, or a Kubernetes cluster, serving with TGI/vLLM (LLMs) or Triton/ONNX Runtime (encoders), with monitoring (latency, error rate) and a CDN in front.

---

## Step 4 — Website v0

### Do

4.1 `web/index.html`:
```html
<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<title>مُحقِّق</title>
<style>
 body{font-family:system-ui;max-width:800px;margin:40px auto;padding:0 16px}
 textarea{width:100%;height:160px;font-size:18px}
 button{font-size:18px;padding:8px 24px;margin:12px 0}
 mark.AYAH{background:#cdeed9} mark.ISNAD{background:#e0d6f5} mark.MATN{background:#d3f0e6} mark.SOURCE{background:#d6e4f7}
</style></head><body>
<h1>مُحقِّق</h1>
<textarea id="t" placeholder="الصق النص هنا"></textarea>
<button id="go">اكتشاف الاستشهادات</button>
<div id="out"></div>
<script type="module">
import { Client } from "https://cdn.jsdelivr.net/npm/@gradio/client/dist/index.min.js";
const app = await Client.connect("muhaqiq/span-detector");
document.getElementById("go").onclick = async () => {
  const text = document.getElementById("t").value;
  const r = await app.predict("/predict", [text]);
  const spans = r.data[0].sort((a, b) => a.start - b.start);
  let html = "", i = 0;
  for (const s of spans) { html += text.slice(i, s.start) + `<mark class="${s.label}">${text.slice(s.start, s.end)}</mark>`; i = s.end; }
  document.getElementById("out").innerHTML = "<p>" + html + text.slice(i) + "</p>";
};
</script></body></html>
```
4.2 Test locally: open the file in Chrome (double-click). Then host: GitHub → repo Settings → Pages → Source: main, folder `/web` → URL `https://<you>.github.io/muhaqiq/`. (Or Cloudflare Pages: connect the repo, build output `web`.)

### Why
This is the required "live demo link". It is a plain page; all the intelligence is on the server. `dir="rtl"` makes Arabic lay out correctly.

### Done when
Pasting text on the public URL highlights ayat/hadith.

### Read
Gradio "Getting started with the JS client".

### In a company
A framework (Next.js/React), deployed on Vercel/Cloudflare, with analytics and error tracking (Sentry). Same idea: static front end, API behind it.

---

## Step 5 — Chrome extension v0

### Do

`extension/manifest.json`:
```json
{
  "manifest_version": 3,
  "name": "Muhaqiq — مُحقِّق",
  "version": "0.1",
  "description": "يكتشف الآيات والأحاديث في إجابات روبوتات الدردشة",
  "icons": {"128": "icon128.png"},
  "content_scripts": [{
    "matches": ["https://chatgpt.com/*", "https://gemini.google.com/*"],
    "js": ["content.js"], "css": ["styles.css"], "run_at": "document_idle"
  }],
  "host_permissions": ["https://*.hf.space/*"]
}
```
`extension/styles.css`:
```css
mark.mq-AYAH{background:#cdeed9} mark.mq-ISNAD{background:#e0d6f5}
mark.mq-MATN{background:#d3f0e6} mark.mq-SOURCE{background:#d6e4f7}
```
`extension/content.js`:
```javascript
const API = "https://muhaqiq-span-detector.hf.space/gradio_api/call/predict";

async function detect(text) {
  const r = await fetch(API, { method: "POST", headers: { "Content-Type": "application/json" },
                               body: JSON.stringify({ data: [text] }) });
  const { event_id } = await r.json();
  const s = await (await fetch(`${API}/${event_id}`)).text();          // server-sent events text
  const line = s.split("\n").find(l => l.startsWith("data:"));
  return JSON.parse(line.slice(5))[0];
}

function highlight(el, spans) {                                        // el holds one paragraph of plain text
  const text = el.textContent; let html = "", i = 0;
  for (const s of spans.sort((a, b) => a.start - b.start)) {
    html += text.slice(i, s.start) + `<mark class="mq-${s.label}">${text.slice(s.start, s.end)}</mark>`; i = s.end;
  }
  el.innerHTML = html + text.slice(i);
}

async function run() {
  const paras = [...document.querySelectorAll("p")].filter(p => /[؀-ۿ]/.test(p.textContent) && !p.dataset.mq);
  for (const p of paras) { p.dataset.mq = "1"; const spans = await detect(p.textContent); if (spans.length) highlight(p, spans); }
}
setInterval(run, 4000);     // v0: re-scan every 4 s for new answers
```
Copy the icon: `cp brand/muhaqiq-icon.png extension/icon128.png` (resize to 128 px).

Load: Chrome → `chrome://extensions` → Developer mode ON → **Load unpacked** → choose the `extension` folder → open chatgpt.com → ask a religious question → highlights appear.

### Why
The extension has no model in it; it reads the page, sends text to the same API as the website, and paints the answer back. v0 works per paragraph so offsets always refer to the text you sent. (Note: this v0 replaces the paragraph's inner HTML with plain text + marks, so links inside that paragraph are lost — acceptable for the demo; v1 wraps text nodes properly.)

### Done when
A 20-second screen recording of ChatGPT with highlighted spans exists.

### Read
Chrome docs: Content scripts · Declare permissions (host_permissions) · Load unpacked.

### In a company
Published to the Chrome Web Store (review ~1–3 days), with a background service worker, options page, and the API behind an auth key.

— Starting version complete. `git push` everything. Write `SOURCES.md` (dataset, base model, licences, how each is used). —

---

## Step 6 — Verifier tools (hackathon day 1, morning)

### Do

`tools/normalize.py`:
```python
import re
TASHKEEL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
def norm(s):
    s = TASHKEEL.sub("", s)
    s = re.sub("[إأآٱ]", "ا", s); s = s.replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()
```
`tools/cache.py` (every external call goes through this; the file is committed so judges get identical results):
```python
import json, hashlib, os
PATH = "tools/cache.json"
_c = json.load(open(PATH, encoding="utf-8")) if os.path.exists(PATH) else {}
def cached(key, fn):
    k = hashlib.sha1(key.encode()).hexdigest()
    if k not in _c:
        _c[k] = fn(); json.dump(_c, open(PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    return _c[k]
```
`tools/quran.py` (quran.com API v4 — public, no key):
```python
import requests
from cache import cached
def search(text):
    def go():
        r = requests.get("https://api.quran.com/api/v4/search", params={"q": text, "language": "ar", "size": 5}, timeout=15).json()
        return [{"ref": f'{h["verse_key"]}', "text": h["text"], "url": f'https://quran.com/{h["verse_key"]}'}
                for h in r.get("search", {}).get("results", [])]
    return cached("quran:" + text, go)
```
`tools/dorar.py` (dorar.net's search endpoint returns HTML inside JSON; unofficial — cache hard, be gentle):
```python
import requests, re, html
from cache import cached
def search(text):
    def go():
        r = requests.get("https://dorar.net/dorar_api.json", params={"skey": text}, timeout=20).json()
        blocks = re.findall(r'<div class="hadith">(.*?)</div>\s*<div class="hadith-info">(.*?)</div>', r.get("ahadith", {}).get("result", ""), re.S)
        out = []
        for h, info in blocks[:5]:
            info = html.unescape(re.sub("<[^>]+>", " ", info))
            out.append({"text": html.unescape(re.sub("<[^>]+>", "", h)).strip(), "info": re.sub(r"\s+", " ", info).strip()})
        return out
    return cached("dorar:" + text, go)
```
(Open dorar.net, search a hadith, and check the page source once: if the class names differ, adjust the regex. Grade, narrator, source are inside `info` as "المحدث: … | المصدر: … | خلاصة حكم المحدث: …".)

`tools/verify.py` (the guardrail lives here):
```python
import difflib
from normalize import norm
import quran, dorar

def diff_words(a, b):
    sm = difflib.SequenceMatcher(None, a.split(), b.split())
    return [(op, " ".join(a.split()[i1:i2]), " ".join(b.split()[j1:j2])) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]

def verify(span_text, label):
    hits = quran.search(span_text) if label == "AYAH" else dorar.search(span_text)
    if not hits:
        return {"verdict": "يحتاج مراجعة", "reason": "no source returned"}
    best = max(hits, key=lambda h: difflib.SequenceMatcher(None, norm(span_text), norm(h["text"])).ratio())
    ratio = difflib.SequenceMatcher(None, norm(span_text), norm(best["text"])).ratio()
    if norm(span_text) in norm(best["text"]):  verdict = "مطابق"
    elif ratio >= 0.75:                        verdict = "مُحرَّف"
    elif ratio < 0.4:                          verdict = "لا أصل له"
    else:                                      verdict = "يحتاج مراجعة"
    return {"verdict": verdict, "ratio": round(ratio, 3), "canonical": best["text"], "source": best,
            "diff": diff_words(span_text, best["text"]) if verdict == "مُحرَّف" else []}

if __name__ == "__main__":
    print(verify("إنما الأعمال بالنيات وإنما لكل امرئ ما نوى", "MATN"))
    print(verify("إنما الأعمال بالنيات وإنما لكل امرئ ما قصد", "MATN"))
```
Run: `$ cd tools && python verify.py`. Tune the 0.75 / 0.4 thresholds on 30 dev examples; write the chosen values in the README.

### Why
This is "verification by source": the verdict is only allowed because a source returned text; the ratio decides which verdict. The cache makes the demo deterministic and keeps you polite to dorar.

### Done when
The first call prints مطابق with a Bukhari/Muslim source; the second prints مُحرَّف with `('replace', 'قصد', 'نوى')` in the diff.

### In a company
A licensed corpus in a search engine (Elasticsearch/OpenSearch or a vector DB) instead of scraping, with rate limits and retries; external calls behind a queue.

---

## Step 7 — ALLaM restorer: bake-off → QLoRA (optional, Kaggle)

### Do

7.1 Bake-off notebook (Kaggle or Colab T4, ~1 h). Take 50 corrupted spans from Subtask B (25 ayah, 25 hadith). For each model, zero-shot, greedy:
```python
# Colab/Kaggle
!pip install -q transformers accelerate bitsandbytes
import torch, json
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
def load(name):
    tok = AutoTokenizer.from_pretrained(name)
    m = AutoModelForCausalLM.from_pretrained(name, quantization_config=BitsAndBytesConfig(load_in_4bit=True), device_map="auto")
    return tok, m
PROMPT = "النص التالي اقتباس قد يكون محرَّفًا من آية أو حديث. اكتب اللفظ الصحيح كاملًا ثم المرجع (سورة:آية أو الكتاب ورقم الحديث) بصيغة JSON بالمفاتيح canonical, reference.\nالنص: {span}\nJSON:"
def restore(tok, m, span):
    ids = tok.apply_chat_template([{"role":"user","content":PROMPT.format(span=span)}], add_generation_prompt=True, return_tensors="pt").to(m.device)
    out = m.generate(ids, max_new_tokens=200, do_sample=False)
    return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True)
```
Score: normalised exact match of `canonical` against gold. Record both numbers (ALLaM-7B-Instruct, Fanar-1-9B-Instruct). They go in the deck as the "model alone" bar.

7.2 Training data `data/restore.jsonl`, one per line, chat format:
```json
{"messages": [{"role":"user","content":"<PROMPT with the corrupted span>"},
              {"role":"assistant","content":"{\"canonical\": \"...\", \"reference\": \"...\", \"error_type\": \"تبديل كلمة\", \"takhrij\": \"أخرجه البخاري (1) ومسلم (1907) من حديث عمر بن الخطاب\"}"}]}
```
Build it from Subtask B gold (span → correct text + reference) plus synthetic corruptions (swap one word with a near-synonym, drop a clause, merge two matns, change the claimed source) using your taxonomy. 3–6k examples is enough. `push_to_hub("muhaqiq/restore-data", private=True)`.

7.3 QLoRA with Unsloth (Kaggle T4, 1 epoch ≈ 1–2 h):
```python
!pip install -q unsloth trl datasets
from unsloth import FastLanguageModel
from trl import SFTTrainer, SFTConfig
from datasets import load_dataset
model, tok = FastLanguageModel.from_pretrained("ALLaM-AI/ALLaM-7B-Instruct-preview", max_seq_length=2048, load_in_4bit=True)
model = FastLanguageModel.get_peft_model(model, r=16, lora_alpha=16, lora_dropout=0,
        target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"], use_gradient_checkpointing="unsloth")
ds = load_dataset("muhaqiq/restore-data")["train"]
ds = ds.map(lambda ex: {"text": tok.apply_chat_template(ex["messages"], tokenize=False)})
trainer = SFTTrainer(model=model, tokenizer=tok, train_dataset=ds,
    args=SFTConfig(output_dir="allam-restorer", per_device_train_batch_size=2, gradient_accumulation_steps=8,
                   num_train_epochs=1, learning_rate=2e-4, fp16=True, logging_steps=10, save_steps=200,
                   push_to_hub=True, hub_model_id="muhaqiq/muhaqiq-allam-7b-lora", hub_strategy="checkpoint"))
trainer.train()
model.push_to_hub("muhaqiq/muhaqiq-allam-7b-lora"); tok.push_to_hub("muhaqiq/muhaqiq-allam-7b-lora")
```
If Unsloth refuses the architecture: same thing with plain `peft` (`prepare_model_for_kbit_training` + `LoraConfig` + `get_peft_model`) and the same `SFTTrainer`. Re-run the bake-off script with the adapter loaded (`PeftModel.from_pretrained(base, "muhaqiq/muhaqiq-allam-7b-lora")`) → the "after" number.

7.4 Serve: new Space, SDK Gradio, hardware **ZeroGPU**; `app.py` loads base + adapter in 4-bit and exposes `restore(span)`; decorate the function with `@spaces.GPU`.

Fallback (keep it ready from the start): `tools/restore.py` with `BACKEND=api` calling a prompted API model with the same JSON contract, and `BACKEND=allam` calling the Space. Switch by environment variable.

### Why
LoRA trains ~1% of the weights, so a 7B model fits a 16 GB T4 in 4-bit. The bake-off before training tells you whether fine-tuning is worth the hours — and gives you the "before" number for the deck regardless.

### Done when
The adapter loads from the Hub and the restoration exact-match on the 50-span set is higher than the zero-shot number.

### Read
Unsloth docs (fine-tuning guide) · TRL `SFTTrainer` · PEFT LoRA conceptual guide · HF "ZeroGPU Spaces".

### In a company
Multi-GPU jobs (A100/H100) on SageMaker/Vertex/own cluster with DeepSpeed or FSDP, full or LoRA fine-tuning, evaluation harness in CI, serving with vLLM behind an API gateway.

---

## Step 8 — Pipeline + FastAPI (hackathon day 2)

### Do

`api/main.py`:
```python
import os, requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from transformers import pipeline
import sys; sys.path.append("../tools")
from verify import verify

app = FastAPI(title="Muhaqiq API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
detect = pipeline("token-classification", model="muhaqiq/muhaqiq-span-detector", aggregation_strategy="simple")

class In(BaseModel):
    text: str

@app.post("/verify")
def verify_text(body: In):
    spans = [s for s in detect(body.text) if s["entity_group"] in ("AYAH", "MATN")]
    report = []
    for s in spans:
        span_text = body.text[s["start"]:s["end"]]
        v = verify(span_text, s["entity_group"])        # Step 6; add the restorer call here in Step 7
        report.append({"label": s["entity_group"], "start": s["start"], "end": s["end"], "text": span_text, **v})
    counts = {k: sum(r["verdict"] == k for r in report) for k in ["مطابق", "مُحرَّف", "لا أصل له", "يحتاج مراجعة"]}
    return {"summary": counts, "citations": report}
```
`api/requirements.txt`: `fastapi uvicorn transformers torch requests`
`api/Dockerfile`:
```
FROM python:3.11-slim
WORKDIR /app
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api/ api/
COPY tools/ tools/
WORKDIR /app/api
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
```
Local test:
```
$ pip install -r api/requirements.txt
$ cd api && uvicorn main:app --reload
# open http://127.0.0.1:8000/docs  -> try /verify from the browser
```
Deploy: new Space `muhaqiq/api`, SDK **Docker**, push the repo contents (Dockerfile at the root of the Space). URL: `https://muhaqiq-api.hf.space/verify`.

Then switch `web/index.html` and `extension/content.js` to one `fetch` on `/verify` (plain JSON, no event id) and render verdict + diff + source link; colour by verdict instead of label.

### Why
FastAPI = the product API: one `/verify` call does everything, with documentation generated automatically at `/docs`. Docker = "my program plus everything it needs, in a box that runs the same everywhere"; the Space builds the box and runs it.

### Done when
`curl -X POST https://muhaqiq-api.hf.space/verify -H 'Content-Type: application/json' -d '{"text":"..."}'` returns a report, and the website shows it.

### Read
FastAPI First steps · Request body · CORS · Hub "Docker Spaces" (FastAPI example).

### In a company
The same container on Cloud Run / ECS / Kubernetes with autoscaling, an API gateway (auth, rate limits), structured logs, and a staging environment before production.

---

## Step 9 — Evaluate, record, ship (day 3)

9.1 `eval/run_dev.py`: call `verify_text` on every Subtask B dev item; compare verdict to gold; print accuracy per verdict, reconstruction exact-match (if Step 7), abstention rate; also run the search-only baseline (skip the restorer) for the comparison row. Save `eval/results.md`.
9.2 Freeze `tools/cache.json`, commit. Test the live URL from a phone.
9.3 Review 20 reports with a Sharia specialist (or against dorar manually); note disagreements in `eval/review.md`.
9.4 Video (≤ 2 min): extension on ChatGPT (20 s) → website report (40 s) → how it works (40 s) → results (20 s). Deck: registration deck + results slide + screenshots → PDF. Submit before 23:59 Riyadh, 6 Oct; keep the confirmation email.

---

## Step 10 — Stretch features (only after Step 9 is safe)

10.1 **Trusted-answer recommender.** For the user's original *question* (the extension can read it from the page), search a whitelist of trusted fatwa sites and show the top 3 links with the question title, so the reader can compare the chatbot's answer with a scholar-reviewed one. Implementation: a search API with a domain filter (Exa or Tavily; both have free tiers) — `search(question, include_domains=["islamqa.info","islamweb.net","binbaz.org.sa","alukah.net"])` → title + URL + snippet. No generation; you show what the sites say. Add a `/related` endpoint and a "إجابات موثوقة ذات صلة" box in the report. This fits the track's "refer to a specialist" criterion and is ~40 lines.
10.2 Shareable report link: store each report as JSON (HF Space persistent storage or a free Postgres such as Supabase) and serve `/r/<id>`.
10.3 Batch mode on the website: upload a .docx/.txt, get one report.
10.4 English UI toggle (labels only; sources stay Arabic).
10.5 Later: run the encoder in-browser with Transformers.js (ONNX export) so detection works offline; keep verification on the server.

---

## Appendix — What a company would use, in one table

| Need | This week (free) | Company |
|---|---|---|
| Code | GitHub | GitHub/GitLab + CI (GitHub Actions) |
| Data | HF dataset repo | Versioned data (DVC/LakeFS), schema checks |
| Training GPU | Colab T4 / Kaggle | SageMaker / Vertex AI / own cluster; Modal, RunPod, Lambda for startups |
| Experiment tracking | printouts + model card | Weights & Biases / MLflow |
| Model storage | HF Hub | Model registry with eval metadata |
| Serving | HF Spaces (Gradio → Docker/FastAPI, ZeroGPU) | vLLM/TGI on Kubernetes or managed endpoints; autoscaling; API gateway |
| Front end | GitHub Pages / Cloudflare Pages | Next.js on Vercel/Cloudflare; Sentry |
| Sources | public APIs + scrape with cache | licensed corpora in Elasticsearch/vector DB |
| Secrets | Space secrets / .env | Vault / cloud secrets manager |

## How to ask for help
Send the step number, the exact command, and the full output or error. One step at a time.
