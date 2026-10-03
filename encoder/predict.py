"""Find ayah/hadith spans in any text.
pipeline + aggregation_strategy merges B-/I- tokens into whole spans with char offsets:
https://huggingface.co/docs/transformers/main_classes/pipelines#transformers.TokenClassificationPipeline
"""
from transformers import pipeline

detect = pipeline("token-classification", model="muhaqiq/muhaqiq-span-detector",
                  aggregation_strategy="simple", device_map="auto")

def find_spans(text):
    return [{"label": s["entity_group"], "start": s["start"], "end": s["end"],
             "text": text[s["start"]:s["end"]], "score": round(float(s["score"]), 3)}
            for s in detect(text)]

if __name__ == "__main__":
    text = "قال الله تعالى: ولا تنسوا الفضل بينكم. وقال النبي ﷺ: إنما الأعمال بالنيات."
    for s in find_spans(text):
        print(s)
