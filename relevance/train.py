"""Subtask 4 — is the citation relevant to the question? CAMeLBERT cross-encoder on (question, citation).
Data: data/train_task_4.tsv (question_id, Response_ID, Annotation_ID, span_type, span_text, relevance_label 0/1)
      + question text joined from data/train.jsonl by Response_ID. Dev TSV used if present, else a 10% split.
HF sequence-pair classification: https://huggingface.co/docs/transformers/tasks/sequence_classification
Run on Colab/Modal T4:  python relevance/train.py   (SMOKE=1 for a 2-minute check)
"""
import os, csv, json, numpy as np
from datasets import Dataset
from transformers import (AutoTokenizer, AutoModelForSequenceClassification, DataCollatorWithPadding,
                          TrainingArguments, Trainer)

MODEL = "CAMeL-Lab/bert-base-arabic-camelbert-msa"
HUB = "muhaqiq/muhaqiq-relevance"
SMOKE = os.getenv("SMOKE") == "1"

def questions(path):
    """Response_ID -> question text, from the IslamicEval JSONL."""
    return {json.loads(l)["id"]: json.loads(l)["question"] for l in open(path, encoding="utf-8") if l.strip()}

def rows(tsv, q):
    out = []
    for r in csv.DictReader(open(tsv, encoding="utf-8"), delimiter="\t"):
        if r["Response_ID"] in q and r["relevance_label"] in ("0", "1"):
            out.append({"question": q[r["Response_ID"]], "citation": r["span_text"], "label": int(r["relevance_label"])})
    return out

q = questions("data/train.jsonl")
train = rows("data/train_task_4.tsv", q)
if os.path.exists("data/dev_task_4.tsv"):
    dev = rows("data/dev_task_4.tsv", {**q, **questions("data/dev.jsonl")})
else:
    ds = Dataset.from_list(train).train_test_split(test_size=0.1, seed=0); train, dev = list(ds["train"]), list(ds["test"])
if SMOKE: train, dev = train[:200], dev[:50]
POS_RATE = float(np.mean([r['label'] for r in train]))
print(f"train {len(train)} · dev {len(dev)} · positive rate train {POS_RATE:.2f} / dev {np.mean([r['label'] for r in dev]):.2f}")

tok = AutoTokenizer.from_pretrained(MODEL)
enc = lambda b: tok(b["question"], b["citation"], truncation=True, max_length=256)     # [CLS] question [SEP] citation [SEP]
tr, dv = (Dataset.from_list(x).map(enc, batched=True) for x in (train, dev))
model = AutoModelForSequenceClassification.from_pretrained(MODEL, num_labels=2, id2label={0: "غير متصل", 1: "متصل"})

def prf(pred, y, c):
    tp = ((pred == c) & (y == c)).sum(); fp = ((pred == c) & (y != c)).sum(); fn = ((pred != c) & (y == c)).sum()
    pr, rc = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    return pr, rc, 2 * pr * rc / max(pr + rc, 1e-9)

def metrics(p):
    """Macro-F1 over both classes (the dev set is far more balanced than train, so positive-class F1 alone is misleading)."""
    pred = p.predictions.argmax(-1); y = p.label_ids
    (p1, r1, f1), (p0, r0, f0) = prf(pred, y, 1), prf(pred, y, 0)
    return {"accuracy": (pred == y).mean(), "macro_f1": (f0 + f1) / 2, "f1_relevant": f1, "f1_irrelevant": f0,
            "recall_irrelevant": r0, "pred_positive_rate": (pred == 1).mean()}

class WeightedTrainer(Trainer):
    """Cross-entropy with a class weight for the rare 'not relevant' label (train is ~84% positive)."""
    def compute_loss(self, model, inputs, return_outputs=False, **kw):
        import torch
        labels = inputs.pop("labels"); out = model(**inputs)
        w = torch.tensor([POS_RATE / (1 - POS_RATE), 1.0], device=out.logits.device)     # [weight(0), weight(1)]
        loss = torch.nn.functional.cross_entropy(out.logits, labels, weight=w)
        return (loss, out) if return_outputs else loss

args = TrainingArguments("muhaqiq-relevance", learning_rate=2e-5, num_train_epochs=1 if SMOKE else 3,
                         per_device_train_batch_size=16, eval_strategy="epoch", save_strategy="epoch", save_total_limit=1,
                         load_best_model_at_end=True, metric_for_best_model="macro_f1", fp16=True, report_to="none",
                         push_to_hub=not SMOKE, hub_model_id=HUB)
trainer = WeightedTrainer(model=model, args=args, train_dataset=tr, eval_dataset=dv, data_collator=DataCollatorWithPadding(tok), compute_metrics=metrics)
trainer.train(); print(trainer.evaluate())
if not SMOKE: trainer.push_to_hub(); tok.push_to_hub(HUB)
