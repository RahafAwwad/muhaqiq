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

# Uthmani spellings without the medial alef, matched inside a word so prefixes (و، ف، ب، ال…) still work.
# Only unambiguous names/words: never ملك/مالك-type pairs, which are real qira'at differences.
RASM_STEMS = {"سموات": "سماوات", "ابرهيم": "ابراهيم", "اسمعيل": "اسماعيل", "اسحق": "اسحاق", "سليمن": "سليمان",
              "هرون": "هارون", "لقمن": "لقمان", "يايها": "يا ايها", "ياادم": "يا ادم"}
STEM = re.compile("|".join(RASM_STEMS))

def norm(s):
    s = s.replace("ﷺ", " ")
    s = TASHKEEL.sub("", s)
    s = re.sub("[إأآٱ]", "ا", s)
    s = re.sub(r"[^\w\s]", " ", s)                       # punctuation, quotes, brackets, ﴿﴾, *
    s = " ".join(RASM.get(w, w) for w in s.split())      # rasm spellings -> modern (before ة/ى folding)
    s = STEM.sub(lambda m: RASM_STEMS[m.group()], s)    # السموات / والسموات -> السماوات
    s = s.replace("ة", "ه").replace("ى", "ي")
    s = re.sub("[ؤئء]", "", s)                            # hamza seats differ between editions (مسؤولا / مسئولا)
    s = re.sub(r"(?<!\S)([وفبكل]) (?=\S)", r"\1", s)       # "و لم" -> "ولم", "ب سبح" -> "بسبح" (a lone letter is never a word)
    s = HON.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()
