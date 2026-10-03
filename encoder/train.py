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