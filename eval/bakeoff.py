"""Bake-off: how many gold-INCORRECT dev spans get linked back to their real source?
  arm A  retrieval only  (tools/verify)            -> linked if verdict in {مطابق, لفظ مختلف}
  arm B  retrieval + restorer rescue (tools/rescue) -> same test after rescue
"Linked correctly" additionally requires the found source text to contain the annotators' `correction`
(window ratio >= 80), so a wrong link doesn't count. Reads eval/dev_verdicts.json written by run_dev.py.
Usage (repo root, LLM_URL set in the environment):  python eval/bakeoff.py [N]
"""
import sys, json, os
sys.path.insert(0, "tools")
import verify as V
from rescue import rescue
from normalize import norm

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10**9
rows = [r for r in json.load(open("eval/dev_verdicts.json", encoding="utf-8")) if r["gold"] == "incorrect" and r["correction"]][:N]

def correct_link(res, correction):
    src = res.get("source") or res.get("closest") or {}
    if not src: return False
    corr = correction[0] if isinstance(correction, list) else correction
    return V.best_window(corr, src.get("simple") or src.get("text", ""))[0] >= 80

stats = {"A": {"linked": 0, "correct": 0, "cand": 0}, "B": {"linked": 0, "correct": 0, "cand": 0}}
for i, r in enumerate(rows):
    a = V.verify(r["text"], r["label"])
    b = a if a["verdict"] != "لم نجده" else (rescue(r["text"], r["label"], list(a["searched"])) or a)
    for arm, res in (("A", a), ("B", b)):
        if res["verdict"] in ("مطابق", "لفظ مختلف"):
            stats[arm]["linked"] += 1; stats[arm]["correct"] += correct_link(res, r["correction"])
        elif res["verdict"] == "يحتاج مراجعة":
            stats[arm]["cand"] += correct_link(res, r["correction"])
    print(f"{i+1:3d} {r['label']} A={a['verdict']:9s} B={b['verdict']:9s} {r['text'][:45]}")

n = len(rows)
lines = [f"# Bake-off on {n} gold-incorrect dev spans (with a gold correction)\n", "| arm | linked (verdict) | linked to the *right* source | right source as a review candidate |", "|---|---|---|---|",
         *[f"| {name} | {st['linked']} ({100*st['linked']/n:.0f}%) | {st['correct']} ({100*st['correct']/n:.0f}%) | {st['cand']} ({100*st['cand']/n:.0f}%) |"
           for name, st in (("A retrieval only", stats["A"]), ("B + ALLaM restorer", stats["B"]))]]
open("eval/bakeoff.md", "w", encoding="utf-8").write("\n".join(lines) + "\n"); print("\n".join(lines))
