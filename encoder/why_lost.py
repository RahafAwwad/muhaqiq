"""Show why check.py loses a span: tokens around its edges + neighbouring spans."""
from datasets import load_dataset
from prepare import tok, windows, label_window, LABELS
from check import labels_to_spans

ds = load_dataset("muhaqiq/span-data")["validation"]
shown = 0
for r in ds:
    gold = {(s["start"], s["end"], s["label"]) for s in r["spans"]}
    got = set()
    for ids, offs in windows(r["text"]):
        got |= {(s["start"], s["end"], s["label"]) for s in labels_to_spans(offs, label_window(offs, r["spans"]))}
    for (a, b, lab) in sorted(gold - got):
        print(f"\n{r['id']} LOST {lab} ({a},{b}): {r['text'][a:b]!r}")
        print("  neighbours:", [(s["start"], s["end"], s["label"]) for s in r["spans"] if abs(s["start"] - a) < 150])
        enc = tok(r["text"], add_special_tokens=False, return_offsets_mapping=True)
        print("  tokens at edges:", [(o, tok.convert_ids_to_tokens(i)) for i, o in zip(enc["input_ids"], enc["offset_mapping"])
                                      if o[0] <= a < o[1] or o[0] < b <= o[1] or a - 3 <= o[0] <= a or b <= o[1] <= b + 3])
        print("  recovered near:", sorted(x for x in got if abs(x[0] - a) < 20))
        shown += 1
    if shown >= 6: break