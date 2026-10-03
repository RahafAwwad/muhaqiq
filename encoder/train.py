"""Fine-tune the encoder for span detection (HF task guide, step by step):
https://huggingface.co/docs/transformers/tasks/token_classification
Env switches:  SMOKE=1  -> 200 examples, 1 epoch, no Hub push (sanity check)
               OUT=dir  -> where checkpoints go (use /content/drive/... on Colab)
               RESUME=1 -> continue from the last checkpoint in OUT
"""
import os, numpy as np
from collections import Counter
from datasets import load_from_disk
from transformers import (AutoTokenizer, AutoModelForTokenClassification,
                          DataCollatorForTokenClassification, TrainingArguments, Trainer)
from prepare import MODEL, LABELS
from check import labels_to_spans

SMOKE = os.getenv("SMOKE") == "1"
OUT = os.getenv("OUT", "muhaqiq-span-detector")
HUB = "muhaqiq/muhaqiq-span-detector"

ds = load_from_disk("data_tok")
if SMOKE: ds["train"], ds["validation"] = ds["train"].select(range(200)), ds["validation"].select(range(50))

tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForTokenClassification.from_pretrained(
    MODEL, num_labels=len(LABELS),
    id2label=dict(enumerate(LABELS)), label2id={l: i for i, l in enumerate(LABELS)})

def spans(labels):
    """BIO label ids -> set of (start_token, end_token, label); token index stands in for char offsets."""
    offsets = [(i, i + 1) for i in range(len(labels))]
    return {(s["start"], s["end"], s["label"]) for s in labels_to_spans(offsets, labels)}

def compute_metrics(p):
    """Exact-match span precision/recall/F1 (what seqeval computes), overall and per label."""
    preds = np.argmax(p.predictions, axis=2)
    tp, n_pred, n_gold = Counter(), Counter(), Counter()
    for prow, lrow in zip(preds, p.label_ids):
        keep = lrow != -100                                   # drop [CLS]/[SEP]/sub-word positions
        gold, pred = spans(lrow[keep].tolist()), spans(prow[keep].tolist())
        for s in gold: n_gold[s[2]] += 1
        for s in pred: n_pred[s[2]] += 1
        for s in gold & pred: tp[s[2]] += 1
    def prf(k):
        t, np_, ng = (sum(c.values()) if k is None else c[k] for c in (tp, n_pred, n_gold))
        pr, rc = t / max(np_, 1), t / max(ng, 1)
        return pr, rc, 2 * pr * rc / max(pr + rc, 1e-9)
    pr, rc, f1 = prf(None)
    out = {"f1": f1, "precision": pr, "recall": rc}
    out.update({f"f1_{k}": prf(k)[2] for k in sorted(n_gold)})
    return out

args = TrainingArguments(OUT, learning_rate=3e-5, num_train_epochs=1 if SMOKE else 4,
                         per_device_train_batch_size=8 if SMOKE else 16, per_device_eval_batch_size=32,
                         eval_strategy="epoch", save_strategy="epoch", save_total_limit=2,
                         load_best_model_at_end=True, metric_for_best_model="f1", fp16=True,
                         push_to_hub=not SMOKE, hub_model_id=HUB, hub_strategy="checkpoint",   # every save -> Hub
                         hub_private_repo=False, report_to="none")

trainer = Trainer(model=model, args=args, train_dataset=ds["train"], eval_dataset=ds["validation"],
                  data_collator=DataCollatorForTokenClassification(tok), compute_metrics=compute_metrics)
trainer.train(resume_from_checkpoint=os.getenv("RESUME") == "1")
print(trainer.evaluate())
if not SMOKE:
    trainer.push_to_hub(); tok.push_to_hub(HUB)     # final best model + tokenizer