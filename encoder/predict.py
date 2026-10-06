"""Find ayah/hadith spans in any text.
pipeline + aggregation_strategy merges B-/I- tokens into whole spans with char offsets:
https://huggingface.co/docs/transformers/main_classes/pipelines#transformers.TokenClassificationPipeline
"first" labels each WORD by its first sub-token, so a span never stops or breaks in the middle of a word
("simple" did, which produced 1-word fragments and dropped last words). Same-label pieces separated only by
spaces/punctuation are then joined back into one span.
Long texts are split at paragraph / sentence breaks (BERT takes 512 tokens max), then at spaces if still
too long, and offsets are shifted back to the original text.
"""
import re
from transformers import pipeline

detect = pipeline("token-classification", model="muhaqiq/muhaqiq-span-detector",
                  aggregation_strategy="first")
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

GAP = re.compile(r"^[\s\W]{0,3}$")          # only spaces / punctuation between two pieces of one quote

def merge_adjacent(spans, text):
    """[«قال: إن» MATN][«لكل قوم عيدا» MATN] -> one MATN span. Score = the lower of the two (stay cautious)."""
    out = []
    for s in sorted(spans, key=lambda x: x["start"]):
        if out and out[-1]["label"] == s["label"] and GAP.match(text[out[-1]["end"]:s["start"]]):
            p = out[-1]; p["end"] = s["end"]; p["text"] = text[p["start"]:p["end"]]; p["score"] = min(p["score"], s["score"])
        else:
            out.append(dict(s))
    return out

def find_spans(text):
    out = []
    for off, piece in chunks(text):
        if not piece.strip(): continue
        out += [{"label": s["entity_group"], "start": off + s["start"], "end": off + s["end"],
                 "text": text[off + s["start"]:off + s["end"]], "score": round(float(s["score"]), 3)}
                for s in detect(piece)]
    return merge_adjacent(out, text)

if __name__ == "__main__":
    text = "قال الله تعالى: ولا تنسوا الفضل بينكم. وقال النبي ﷺ: إنما الأعمال بالنيات."
    for s in find_spans(text):
        print(s)
