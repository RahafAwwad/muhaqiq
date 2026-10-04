"""Run tools/verify over the IslamicEval dev spans and compare with the annotators' status.
Gold status: correct / incorrect (span text as quoted vs the real source).  Our verdicts: مطابق / لفظ مختلف / لم نجده.
Reports the confusion table + the two numbers that matter:
  false amber/red = gold-correct spans we did NOT call مطابق   (we wrongly alarm)
  missed          = gold-incorrect spans we called مطابق       (we wrongly approve)
Usage (from repo root):  python eval/run_dev.py [N]     # N = max spans per label (default all), results -> eval/results.md
"""
import sys, json, collections, random
sys.path.insert(0, "tools")
from datasets import load_dataset
from verify import verify

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10**9
rows, table = [], collections.Counter()
for ex in load_dataset("muhaqiq/span-data")["validation"]:
    for s in ex["spans"]:
        if s["label"] not in ("AYAH", "MATN") or s["status"] not in ("correct", "incorrect"): continue
        rows.append((s["label"], s["status"], ex["text"][s["start"]:s["end"]], s.get("correction"), ex["id"]))
random.seed(0); random.shuffle(rows)
per = collections.Counter(); out = []
for label, status, text, corr, rid in rows:
    if per[label] >= N: continue
    per[label] += 1
    r = verify(text, label)
    table[(label, status, r["verdict"])] += 1
    out.append({"id": rid, "label": label, "gold": status, "verdict": r["verdict"], "score": r["score"], "text": text,
                "correction": corr, "found": (r.get("source") or r.get("closest") or {}).get("ref") or (r.get("source") or {}).get("المصدر")})
    print(f"{label} {status:9s} → {r['verdict']:8s} {r['score']:5}  {text[:50]}")

lines = ["# verify.py on IslamicEval dev\n", "| label | gold | مطابق | لفظ مختلف | لم نجده | n |", "|---|---|---|---|---|---|"]
for label in ("AYAH", "MATN"):
    for status in ("correct", "incorrect"):
        c = [table[(label, status, v)] for v in ("مطابق", "لفظ مختلف", "لم نجده")]
        lines.append(f"| {label} | {status} | {c[0]} | {c[1]} | {c[2]} | {sum(c)} |")
for label in ("AYAH", "MATN"):
    ok = table[(label, "correct", "مطابق")]; n = sum(table[(label, "correct", v)] for v in ("مطابق", "لفظ مختلف", "لم نجده"))
    bad = table[(label, "incorrect", "مطابق")]; m = sum(table[(label, "incorrect", v)] for v in ("مطابق", "لفظ مختلف", "لم نجده"))
    lines.append(f"\n{label}: false alarm on gold-correct = {n-ok}/{n} ({100*(n-ok)/max(n,1):.1f}%) · wrongly approved gold-incorrect = {bad}/{m} ({100*bad/max(m,1):.1f}%)")
open("eval/results.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
json.dump(out, open("eval/dev_verdicts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n".join(lines))
