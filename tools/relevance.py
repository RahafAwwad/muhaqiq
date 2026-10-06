"""Is the citation relevant to the question? CAMeLBERT cross-encoder fine-tuned on IslamicEval Subtask 4 (muhaqiq/muhaqiq-relevance).
Output is an automatic NOTE for the reader, never a verdict on the citation's authenticity.
https://huggingface.co/docs/transformers/main_classes/pipelines#transformers.TextClassificationPipeline
"""
from transformers import pipeline

MODEL = "muhaqiq/muhaqiq-relevance"
CONF = 0.8          # dev macro-F1 is only 0.61 (n=282, train/dev label distribution differs) -> flag only confident cases
_clf = None

def score(question, citation):
    """-> {"label": "متصل"|"قد لا يتصل بالسؤال", "score": 0..1 (confidence that it IS relevant)}"""
    global _clf
    if _clf is None: _clf = pipeline("text-classification", model=MODEL, top_k=None)
    probs = {p["label"]: p["score"] for p in _clf({"text": question, "text_pair": citation}, truncation=True, max_length=256)[0]}
    rel = probs.get("متصل", probs.get("LABEL_1", 0.0))
    # three states: the model must be confident either way; in between we say so instead of defaulting to "متصل"
    if rel >= CONF:       label, note = "متصل", ""
    elif rel <= 1 - CONF: label, note = "قد لا يتصل بالسؤال", "ملاحظة آلية (تجريبي): الاستشهاد قد لا يكون متصلًا بالسؤال المطروح"
    else:                 label, note = "غير مؤكد", "لم يتمكن النموذج من الحكم على صلة الاستشهاد بالسؤال"
    return {"label": label, "score": round(rel, 3), "experimental": True, "note": note}

if __name__ == "__main__":
    print(score("ما فضل صيام يوم عرفة؟", "صيام يوم عرفة أحتسب على الله أن يكفر السنة التي قبله والسنة التي بعده"))
    print(score("ما فضل صيام يوم عرفة؟", "إنما الأعمال بالنيات"))
