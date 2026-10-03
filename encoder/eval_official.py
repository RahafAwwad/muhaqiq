"""IslamicEval 2026 Subtask 1 metric: character-level macro-F1 over 5 classes
(neither, Ayah, matn, isnad, claimed_source), pooled over the whole dev set.
https://sites.google.com/view/islamiceval2026/evaluation-scripts
Also writes dev_pred.tsv in the official submission format.
"""
import numpy as np
from datasets import load_dataset
from sklearn.metrics import f1_score, classification_report
from predict import find_spans

LABEL2OFF = {"AYAH": "Ayah", "MATN": "matn", "ISNAD": "isnad", "SOURCE": "claimed_source"}
CLASSES = ["neither", "Ayah", "matn", "isnad", "claimed_source"]

def char_labels(text, spans):
    lab = np.zeros(len(text), dtype=int)                       # 0 = neither
    for s in spans: lab[s["start"]:s["end"]] = CLASSES.index(LABEL2OFF[s["label"]])
    return lab

gold_all, pred_all, rows = [], [], []
for ex in load_dataset("muhaqiq/span-data")["validation"]:
    pred = find_spans(ex["text"])
    gold_all.append(char_labels(ex["text"], ex["spans"])); pred_all.append(char_labels(ex["text"], pred))
    rows += [f'{ex["id"]}\t{i+1}\t{LABEL2OFF[s["label"]]}\t{s["start"]}\t{s["end"]}' for i, s in enumerate(pred)] \
            or [f'{ex["id"]}\t1\tNoAnnotation\t-\t-']
gold, pred = np.concatenate(gold_all), np.concatenate(pred_all)
print(classification_report(gold, pred, target_names=CLASSES, digits=4))
print({"F1 Score": round(f1_score(gold, pred, average="macro"), 4)})
open("dev_pred.tsv", "w").write("Response_ID\tAnnotation_ID\tSegment_Type\tSpan_Start\tSpan_End\n" + "\n".join(rows) + "\n")
