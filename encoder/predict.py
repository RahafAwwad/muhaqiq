"""Find ayah/hadith spans in any text.
pipeline + aggregation_strategy merges B-/I- tokens into whole spans with char offsets:
https://huggingface.co/docs/transformers/main_classes/pipelines#transformers.TokenClassificationPipeline
Long texts are split at paragraph / sentence breaks (BERT takes 512 tokens max), then at spaces if still
too long, and offsets are shifted back to the original text.
"""
import re
from transformers import pipeline

detect = pipeline("token-classification", model="muhaqiq/muhaqiq-span-detector",
                  aggregation_strategy="simple")
MAX_TOKENS = 400

def n_tokens(s):
    return len(detect.tokenizer.tokenize(s))

def parts(text):
    """Split after newlines / sentence ends; a part still too long is split at spaces. No character is lost."""
    for p in re.split(r"(?<=\n)|(?<=[.!؟]\s)", text):
        if n_tokens(p) <= MAX_TOKENS:
            yield p; continue
        buf = ""
        for w in re.split(r"(?<=\s)", p):                      # words keep their trailing space
            if buf and n_tokens(buf + w) > MAX_TOKENS: yield buf; buf = ""
            buf += w
        if buf: yield buf

def chunks(text):
    """Yield (offset, piece): consecutive parts packed up to MAX_TOKENS."""
    pos, buf = 0, ""
    for part in parts(text):
        if buf and n_tokens(buf + part) > MAX_TOKENS:
            yield pos, buf; pos += len(buf); buf = ""
        buf += part
    if buf: yield pos, buf

def find_spans(text):
    out = []
    for off, piece in chunks(text):
        if not piece.strip(): continue
        out += [{"label": s["entity_group"], "start": off + s["start"], "end": off + s["end"],
                 "text": text[off + s["start"]:off + s["end"]], "score": round(float(s["score"]), 3)}
                for s in detect(piece)]
    return out

if __name__ == "__main__":
    text = "قال الله تعالى: ولا تنسوا الفضل بينكم. وقال النبي ﷺ: إنما الأعمال بالنيات."
    for s in find_spans(text):
        print(s)