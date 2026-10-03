"""Find ayah/hadith spans in any text.
pipeline + aggregation_strategy merges B-/I- tokens into whole spans with char offsets:
https://huggingface.co/docs/transformers/main_classes/pipelines#transformers.TokenClassificationPipeline
Long texts are split at paragraph / sentence breaks (BERT takes 512 tokens max) and offsets shifted back.
"""
import re
from transformers import pipeline

detect = pipeline("token-classification", model="muhaqiq/muhaqiq-span-detector",
                  aggregation_strategy="simple", device_map="auto")
MAX_TOKENS = 400

def chunks(text):
    """Yield (offset, piece): pieces end after a newline or a sentence end, each <= MAX_TOKENS."""
    pos, buf = 0, ""
    for part in re.split(r"(?<=\n)|(?<=[.!؟]\s)", text):          # split points keep every character
        if buf and len(detect.tokenizer.tokenize(buf + part)) > MAX_TOKENS:
            yield pos, buf; pos += len(buf); buf = ""
        buf += part
    if buf: yield pos, buf

def find_spans(text):
    out = []
    for off, piece in chunks(text):
        out += [{"label": s["entity_group"], "start": off + s["start"], "end": off + s["end"],
                 "text": text[off + s["start"]:off + s["end"]], "score": round(float(s["score"]), 3)}
                for s in detect(piece)]
    return out

if __name__ == "__main__":
    text = "قال الله تعالى: ولا تنسوا الفضل بينكم. وقال النبي ﷺ: إنما الأعمال بالنيات."
    for s in find_spans(text):
        print(s)
