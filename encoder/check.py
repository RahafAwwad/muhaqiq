"""Round-trip test: gold spans -> token labels -> spans again. Run before training."""
from datasets import load_dataset
from prepare import LABELS, DATASET, windows, label_window

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

def same(gold, back):
    """Equal, or back starts <=2 chars earlier (a clitic like و/ف glued to the first word by the tokenizer)."""
    return gold[2] == back[2] and gold[1] == back[1] and 0 <= gold[0] - back[0] <= 2

if __name__ == "__main__":
    ok = total = 0
    for ex in load_dataset(DATASET)["validation"]:
        back = set()
        for ids, offs in windows(ex["text"]):
            back |= {(s["start"], s["end"], s["label"]) for s in labels_to_spans(offs, label_window(offs, ex["spans"]))}
        gold = {(s["start"], s["end"], s["label"]) for s in ex["spans"]}
        for g in gold:
            total += 1
            if any(same(g, b) for b in back): ok += 1
            else: print("LOST:", g, repr(ex["text"][g[0]:g[1]][:40]))
    print(f"round-trip: {ok}/{total} spans recovered ({100*ok/total:.1f}%)")