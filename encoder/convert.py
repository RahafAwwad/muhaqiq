"""IslamicEval JSONL -> Muhaqiq span JSONL.
In : {"id", "question", "generated_answer", "annotations":[{"segments":[{"type","span_start","span_end","label"}], "correction"}]}
Out: {"id", "text", "spans":[{"start","end","label","status","correction"}]}
     status = correct / incorrect / N/A ; correction = gold text(s) when annotated (kept for the restorer, Step 7)

Cleaning rules (BIO tagging allows one label per token, so spans must not overlap):
  1. trim quotes/brackets/spaces from span edges      e.g. SOURCE "(رواه البخاري)" -> "رواه البخاري"
  2. drop a span that overlaps an earlier/longer span (keep the outer one)   e.g. SOURCE inside ISNAD
  3. identical offsets with two labels -> keep one by priority AYAH > MATN > ISNAD > SOURCE
Usage: python convert.py data/train.jsonl data/train_spans.jsonl
"""
import json, sys

TYPE2LABEL = {"Ayah": "AYAH", "matn": "MATN", "isnad": "ISNAD", "claimed_source": "SOURCE"}
PRIORITY = ["AYAH", "MATN", "ISNAD", "SOURCE"]
EDGE = ' \n\t"«»()[]*:،.'                      # characters that are not part of a citation

def trim(text, s):
    while s["start"] < s["end"] and text[s["start"]] in EDGE: s["start"] += 1
    while s["end"] > s["start"] and text[s["end"] - 1] in EDGE: s["end"] -= 1
    return s

def clean(text, spans):
    spans = [trim(text, s) for s in spans if s["end"] > s["start"]]
    spans.sort(key=lambda s: (s["start"], -s["end"], PRIORITY.index(s["label"])))   # outer first, then priority
    keep = []
    for s in spans:                              # rule 2 + 3: skip anything that overlaps a kept span
        if not any(s["start"] < k["end"] and k["start"] < s["end"] for k in keep):
            keep.append(s)
    return keep

def convert(src, dst):
    n_rec = n_span = n_drop = 0
    with open(src, encoding="utf-8") as f, open(dst, "w", encoding="utf-8") as out:
        for line in f:
            if not line.strip(): continue
            r = json.loads(line)
            spans = [{"start": s["span_start"], "end": s["span_end"],
                      "label": TYPE2LABEL[s["type"]], "status": s.get("label", "N/A"),
                      "correction": a.get("correction")}
                     for a in r["annotations"] for s in a["segments"]]
            kept = clean(r["generated_answer"], spans)
            out.write(json.dumps({"id": r["id"], "text": r["generated_answer"], "spans": kept},
                                 ensure_ascii=False) + "\n")
            n_rec += 1; n_span += len(kept); n_drop += len(spans) - len(kept)
    print(f"{dst}: {n_rec} records, {n_span} spans kept, {n_drop} nested/duplicate spans dropped")

if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])