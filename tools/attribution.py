"""Attribution check (العزو): does the claimed source match where the text was actually found?
  AYAH : claimed "البقرة: 31" vs found ref "2:151"      -> العزو صحيح / العزو غير دقيق (الصواب: البقرة 151)
  MATN : claimed "رواه البخاري" vs rulings' المصدر list -> العزو صحيح / العزو غير دقيق (وجدناه في: ...) / لا يمكن التحقق
Pure rules, no model. Surah names are the standard Arabic names; aliases cover common alternatives.
"""
import re
from normalize import norm

SURAHS = ["الفاتحة","البقرة","آل عمران","النساء","المائدة","الأنعام","الأعراف","الأنفال","التوبة","يونس","هود","يوسف","الرعد",
 "إبراهيم","الحجر","النحل","الإسراء","الكهف","مريم","طه","الأنبياء","الحج","المؤمنون","النور","الفرقان","الشعراء","النمل","القصص",
 "العنكبوت","الروم","لقمان","السجدة","الأحزاب","سبأ","فاطر","يس","الصافات","ص","الزمر","غافر","فصلت","الشورى","الزخرف","الدخان",
 "الجاثية","الأحقاف","محمد","الفتح","الحجرات","ق","الذاريات","الطور","النجم","القمر","الرحمن","الواقعة","الحديد","المجادلة","الحشر",
 "الممتحنة","الصف","الجمعة","المنافقون","التغابن","الطلاق","التحريم","الملك","القلم","الحاقة","المعارج","نوح","الجن","المزمل","المدثر",
 "القيامة","الإنسان","المرسلات","النبأ","النازعات","عبس","التكوير","الانفطار","المطففين","الانشقاق","البروج","الطارق","الأعلى","الغاشية",
 "الفجر","البلد","الشمس","الليل","الضحى","الشرح","التين","العلق","القدر","البينة","الزلزلة","العاديات","القارعة","التكاثر","العصر","الهمزة",
 "الفيل","قريش","الماعون","الكوثر","الكافرون","النصر","المسد","الإخلاص","الفلق","الناس"]
ALIASES = {"المؤمن": "غافر", "بني إسرائيل": "الإسراء", "الانشراح": "الشرح", "الدهر": "الإنسان", "براءة": "التوبة", "ال عمران": "آل عمران"}
NAME2NUM = {norm(n): i + 1 for i, n in enumerate(SURAHS)}
NAME2NUM.update({norm(a): NAME2NUM[norm(b)] for a, b in ALIASES.items()})

COLLECTIONS = {"البخاري": "صحيح البخاري", "مسلم": "صحيح مسلم", "ابو داود": "سنن أبي داود", "ابي داود": "سنن أبي داود",
               "الترمذي": "سنن الترمذي", "النسايي": "سنن النسائي", "ابن ماجه": "سنن ابن ماجه", "احمد": "مسند أحمد",
               "مالك": "الموطأ", "الموطا": "الموطأ", "الحاكم": "المستدرك", "البيهقي": "البيهقي", "الطبراني": "الطبراني",
               "ابن حبان": "صحيح ابن حبان", "ابن خزيمه": "صحيح ابن خزيمة", "الدارمي": "سنن الدارمي", "البزار": "البزار", "ابو يعلي": "أبو يعلى"}

def parse_ayah_claim(text):
    """'[البقرة: 31]' / 'سورة البقرة الآية 31' / 'البقرة 31' -> (surah_no, ayah_no) or None"""
    t = norm(text.replace("سورة", " ").replace("الآية", " ").replace("آية", " "))
    nums = re.findall(r"\d+", t)
    for name, n in NAME2NUM.items():
        if name in t: return (n, int(nums[-1])) if nums else (n, None)
    return None

def parse_hadith_claim(text):
    """'رواه البخاري ومسلم' / 'متفق عليه' / 'أخرجه الترمذي' -> list of collection names"""
    t = norm(text)
    if "متفق عليه" in t or "الصحيحين" in t: return ["صحيح البخاري", "صحيح مسلم"]
    return [c for k, c in COLLECTIONS.items() if k in t]

def check(claim_text, label, result):
    """-> {'claimed','found','verdict','note'} ; result = verify() output for the paired AYAH/MATN span."""
    src = result.get("source") or {}
    if label == "AYAH":
        c = parse_ayah_claim(claim_text)
        if not c or not src.get("ref"): return {"claimed": claim_text, "verdict": "لا يمكن التحقق"}
        s, a = c; fs, fa = src["ref"].split("-")[0].split(":")
        ok = int(fs) == s and (a is None or int(fa) == a or src["ref"].endswith(f"-{a}"))
        found = f"{SURAHS[int(fs)-1]} {fa}"
        return {"claimed": claim_text, "found": found, "verdict": "العزو صحيح" if ok else "العزو غير دقيق",
                "note": "" if ok else f"الصواب: [{found}]"}
    claimed = parse_hadith_claim(claim_text)
    sources = [r.get("المصدر", "") for r in result.get("rulings", [])] or [src.get("المصدر", "")]
    if not claimed or not any(sources): return {"claimed": claim_text, "verdict": "لا يمكن التحقق"}
    ok = any(any(c in s for s in sources) for c in claimed)
    return {"claimed": claim_text, "found": sorted({s for s in sources if s}), "verdict": "العزو صحيح" if ok else "العزو غير دقيق",
            "note": "" if ok else "وجدناه في: " + "، ".join(sorted({s for s in sources if s})[:4])}

if __name__ == "__main__":
    print(parse_ayah_claim("[البقرة: 31]"), parse_ayah_claim("سورة آل عمران الآية 103"), parse_hadith_claim("رواه البخاري ومسلم"), parse_hadith_claim("متفق عليه"))
