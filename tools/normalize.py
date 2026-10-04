"""Arabic normalisation for matching: strip tashkeel, unify letter variants, drop punctuation,
undo Uthmani rasm spellings, merge detached و/ف, and remove honorific phrases (they are not part of the quoted text).
Unicode Arabic block: https://www.unicode.org/charts/PDF/U0600.pdf
"""
import re

TASHKEEL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")   # harakat, small marks, tatweel
RASM = {"الصلوة": "الصلاة", "الزكوة": "الزكاة", "الحيوة": "الحياة", "الربوا": "الربا", "النجوة": "النجاة",
        "مشكوة": "مشكاة", "كمشكوة": "كمشكاة", "منوة": "مناة", "الغدوة": "الغداة", "بالغدوة": "بالغداة"}
HONORIFICS = [r"صلي الله عليه و?سلم", r"صلي الله عليه و?اله و?سلم", r"عليه الصلاه و?السلام", r"عليه السلام",
              r"رضي الله عنهم?ا?", r"رضي الله عنهن", r"عز و?جل", r"سبحانه و?تعالي", r"تبارك و?تعالي", r"تعالي"]
HON = re.compile(r"(?<!\S)(" + "|".join(HONORIFICS) + r")(?!\S)")

def norm(s):
    s = s.replace("ﷺ", " ")
    s = TASHKEEL.sub("", s)
    s = re.sub("[إأآٱ]", "ا", s)
    s = re.sub(r"[^\w\s]", " ", s)                       # punctuation, quotes, brackets, ﴿﴾, *
    s = " ".join(RASM.get(w, w) for w in s.split())      # rasm spellings -> modern (before ة/ى folding)
    s = s.replace("ة", "ه").replace("ى", "ي")
    s = re.sub("[ؤئء]", "", s)                            # hamza seats differ between editions (مسؤولا / مسئولا)
    s = re.sub(r"(?<!\S)([وف]) (?=\S)", r"\1", s)         # "و لم" -> "ولم"
    s = HON.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()
