"""Character spans -> token BIO labels, with sliding windows done by hand.
(tokenizers >= 0.23.1 has a bug that drops overflow windows, so we don't use return_overflowing_tokens.)
Reads the Hub dataset, writes ./data_tok
"""
from datasets import load_dataset
from transformers import AutoTokenizer

MODEL = "CAMeL-Lab/bert-base-arabic-camelbert-msa"
DATASET = "muhaqiq/span-data"
LABELS = ["O","B-AYAH","I-AYAH","B-ISNAD","I-ISNAD","B-MATN","I-MATN","B-SOURCE","I-SOURCE"]
label2id = {l: i for i, l in enumerate(LABELS)}
WIN, STRIDE = 510, 128            # 510 tokens + [CLS] + [SEP] = 512

tok = AutoTokenizer.from_pretrained(MODEL)

def windows(text):
    """Tokenize once (no truncation) and yield (input_ids, offsets) windows of <=512 with overlap."""
    enc = tok(text, add_special_tokens=False, return_offsets_mapping=True)
    ids, offs = enc["input_ids"], enc["offset_mapping"]
    start = 0
    while True:
        chunk_ids, chunk_offs = ids[start:start+WIN], offs[start:start+WIN]
        yield ([tok.cls_token_id] + chunk_ids + [tok.sep_token_id], [(0, 0)] + chunk_offs + [(0, 0)])
        if start + WIN >= len(ids): break
        start += WIN - STRIDE

def label_window(offsets, spans):
    labels = []
    for s_tok, e_tok in offsets:
        lab = "O"
        if e_tok > s_tok:
            for s in spans:                       # token overlaps span (a span may start mid-token: "وعن" vs gold "عن")
                if s["start"] < e_tok and s_tok < s["end"]:
                    lab = ("B-" if s_tok <= s["start"] else "I-") + s["label"]; break
        labels.append(label2id[lab] if e_tok > s_tok else -100)
    return labels

def label_tokens(batch):
    out = {"input_ids": [], "attention_mask": [], "labels": []}
    for text, spans in zip(batch["text"], batch["spans"]):
        for ids, offs in windows(text):
            out["input_ids"].append(ids); out["attention_mask"].append([1] * len(ids))
            out["labels"].append(label_window(offs, spans))
    return out

if __name__ == "__main__":
    ds = load_dataset(DATASET)
    ds = ds.map(label_tokens, batched=True, remove_columns=ds["train"].column_names)
    ds.save_to_disk("data_tok"); print(ds)