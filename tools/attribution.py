"""Source check (المصدر المذكور): does the claimed source match where the text actually is?
  AYAH : claimed "البقرة: 31" vs found ref "2:151" -> المصدر صحيح / المصدر غير دقيق (الصواب: البقرة 151)
  MATN : claimed "رواه البخاري" vs PRIMARY collections attested by dorar entries + hadeethenc's attribution line
         -> المصدر صحيح / المصدر غير دقيق (only with complete evidence) / لم نتحقق من المصدر / لا يمكن التحقق
Pure rules, no model. Surah names are the standard Arabic names; aliases cover common alternatives.
"""
import re
from rapidfuzz import process, fuzz
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

# ayat per surah (Hafs, 6,236 total); check.sh compares it with tools/quran.json
AYAH_COUNTS = [7,286,200,176,120,165,206,75,129,109,123,111,43,52,99,128,111,110,98,135,112,78,118,64,77,227,93,88,69,60,34,
 30,73,54,45,83,182,88,75,85,54,53,89,59,37,35,38,29,18,45,60,49,62,55,78,96,29,22,24,13,14,11,11,18,12,12,30,52,52,44,28,28,20,
 56,40,31,50,40,46,42,29,19,36,25,22,17,19,26,30,20,15,21,11,8,8,19,5,8,8,11,11,8,3,9,5,4,7,3,6,3,5,4,5,6]
NAME_FUZZ = 80          # «الرحمان» -> «الرحمن» counts as a spelling slip of a real name; below this the name is unknown

# longest names first, whole words only: "القيامة" must never match the one-letter surah "ق" (or "ص", "طه", "يس")
NAMES_BY_LEN = sorted(NAME2NUM.items(), key=lambda kv: -len(kv[0]))

def read_ayah_claim(text):
    """What the writer claimed, and how well we could read it:
    {"surah", "ayah", "name_written", "status": exact | misspelled | unknown_name | no_name}"""
    t = " " + norm(text.replace("سورة", " ").replace("الآية", " ").replace("آية", " ").replace("الايه", " ")) + " "
    nums = re.findall(r"\d+", t); ayah = int(nums[-1]) if nums else None
    for name, n in NAMES_BY_LEN:
        if re.search(rf"(?<!\S){re.escape(name)}(?!\S)", t):
            return {"surah": n, "ayah": ayah, "name_written": name, "status": "exact"}
    written = re.sub(r"[\d\s]+", " ", t).strip()                 # whatever is left once numbers are removed
    if not written: return {"surah": None, "ayah": ayah, "name_written": "", "status": "no_name"}
    hit = process.extractOne(written, list(NAME2NUM), scorer=fuzz.ratio)
    if hit and hit[1] >= NAME_FUZZ and len(written) > 2:
        return {"surah": NAME2NUM[hit[0]], "ayah": ayah, "name_written": as_written(text), "status": "misspelled"}
    return {"surah": None, "ayah": ayah, "name_written": as_written(text), "status": "unknown_name"}

def as_written(text):
    """the name exactly as the writer typed it, for messages («المحبة», not the normalised «المحبه»)"""
    t = re.sub(r"سورة|الآية|آية|الاية|اية", " ", text)
    return re.sub(r"\s+", " ", re.sub(r"[\d\[\]\(\)﴿﴾{}:/\\\-–،,.]", " ", t)).strip()

def parse_ayah_claim(text):
    """(surah_no, ayah_no) or None — kept for older callers and the tests"""
    c = read_ayah_claim(text)
    return (c["surah"], c["ayah"]) if c["surah"] else None

def parse_hadith_claim(text):
    """'رواه البخاري ومسلم' / 'متفق عليه' / 'أخرجه الترمذي' -> list of collection names"""
    t = norm(text)
    if "متفق عليه" in t or "الصحيحين" in t: return ["صحيح البخاري", "صحيح مسلم"]
    return [c for k, c in COLLECTIONS.items() if k in t]

# Verdict wording (UI says «المصدر», not «العزو»)
OK, WRONG, UNSURE, NA = "المصدر صحيح", "المصدر غير دقيق", "لم نتحقق من المصدر", "لا يمكن التحقق"
HADEETHENC = "موسوعة الأحاديث النبوية"
SAHIHAYN = {"صحيح البخاري", "صحيح مسلم"}

def collection_of(entry):
    """dorar/hadeethenc entry -> set of PRIMARY collections it attests (where the hadith is narrated with a chain).
    dorar: the entry's المحدث is the collection's author (البخاري -> صحيح البخاري). Graders (الألباني in صحيح الترغيب,
    أحمد شاكر…) are NOT primary: exact name match, so 'أحمد شاكر' never counts as مسند أحمد.
    hadeethenc: its curated attribution line ('متفق عليه', 'رواه أبو داود والترمذي') is parsed."""
    if entry.get("المحدث") == HADEETHENC:
        return set(parse_hadith_claim(entry.get("المصدر", "")))
    c = COLLECTIONS.get(norm(entry.get("المحدث", "")).strip())
    return {c} if c else set()

def check(claim_text, label, result):
    """-> {claimed, verdict, found, graded_in, basis, note}; result = verify() output for the paired AYAH/MATN span.
    Absence from search results is NOT evidence: 'غير دقيق' only when the evidence is complete (Quran ref, or
    hadeethenc's full attribution line). Otherwise: 'لم نتحقق من المصدر' + where we did find it."""
    src = result.get("source") or {}
    if label == "AYAH":                                  # exact: the Quran has one place per ayah
        if not src.get("ref"): return {"claimed": claim_text, "verdict": NA}
        fs, fa = src["ref"].split("-")[0].split(":")
        found = f"{SURAHS[int(fs)-1]} {fa}" + (f"–{src['ref'].split('-')[1]}" if "-" in src["ref"] else "")
        fix = f"الصواب: [{found}]"
        c = read_ayah_claim(claim_text)
        base = {"claimed": claim_text, "found": [found], "basis": "نص المصحف"}
        if c["status"] == "no_name":
            return {**base, "verdict": NA, "note": f"لم يُذكر اسم السورة؛ موضع الآية: [{found}]"}
        if c["status"] == "unknown_name":                # a name that is not a surah at all
            return {**base, "verdict": WRONG, "note": f"لا توجد سورة باسم «{c['name_written']}»؛ {fix}"}
        s_no, a_no = c["surah"], c["ayah"]
        if a_no is not None and not 1 <= a_no <= AYAH_COUNTS[s_no - 1]:
            return {**base, "verdict": WRONG,
                    "note": f"سورة {SURAHS[s_no-1]} عدد آياتها {AYAH_COUNTS[s_no-1]} فلا توجد الآية {a_no}؛ {fix}"}
        ok = int(fs) == s_no and (a_no is None or int(fa) == a_no or src["ref"].endswith(f"-{a_no}"))
        spelled = f"اسم السورة يُكتب «{SURAHS[s_no-1]}» لا «{c['name_written']}»" if c["status"] == "misspelled" else ""
        return {**base, "verdict": OK if ok else WRONG, "spelling": spelled,
                "note": "؛ ".join(x for x in [spelled, "" if ok else fix] if x)}

    claimed = parse_hadith_claim(claim_text)
    if not claimed: return {"claimed": claim_text, "verdict": NA}
    entries = list(result.get("rulings") or []) + ([src] if src else [])
    primary, graded, curated = set(), [], None
    for e in entries:
        cols = collection_of(e); primary |= cols
        if e.get("المحدث") == HADEETHENC and e.get("المصدر"): curated = e["المصدر"]
        elif not cols and e.get("المصدر"): graded.append(f'{e.get("المحدث", "")} — {e["المصدر"]}'.strip(" —"))
    hit = [c for c in claimed if c in primary]
    out = {"claimed": claim_text, "found": sorted(primary), "graded_in": sorted(set(graded))[:6]}
    if hit:
        return {**out, "verdict": OK, "basis": "وجدنا اللفظ في " + "، ".join(hit), "note": ""}
    if curated and set(claimed) <= SAHIHAYN:            # the curated line always names the two Sahihs when they have it
        return {**out, "verdict": WRONG, "basis": f"{HADEETHENC}: {curated}", "note": f"في {HADEETHENC}: {curated}"}
    if curated:                                          # other books may be left out of the line -> not conclusive
        return {**out, "verdict": UNSURE, "basis": f"{HADEETHENC}: {curated}",
                "note": f"في {HADEETHENC}: {curated} — ولم يُذكر فيه {'، '.join(claimed)}، وقد يكون فيه أيضًا"}
    note = ("لم يظهر في نتائج البحث في " + "، ".join(claimed) + "؛ " +
            ("وجدناه في: " + "، ".join(sorted(primary)) + " — وقد يكون في المصدر المذكور أيضًا" if primary
             else "ظهر فقط في كتب الأحكام: " + "، ".join(sorted(set(graded))[:3]) if graded else "لا نعرف موضعه"))
    return {**out, "verdict": UNSURE, "basis": "نتائج البحث في الدرر السنية (قد لا تشمل كل الكتب)", "note": note}

if __name__ == "__main__":
    print(parse_ayah_claim("[البقرة: 31]"), parse_ayah_claim("سورة آل عمران الآية 103"), parse_hadith_claim("رواه البخاري ومسلم"), parse_hadith_claim("متفق عليه"))
    bad = [n for n, name in enumerate(SURAHS, 1) if parse_ayah_claim(f"{name} /5") != (n, 5) or parse_ayah_claim(f"[{name}: 5]") != (n, 5)]
    print("surah names parsed:", 114 - len(bad), "/ 114", "failures:", bad)
    print(check("القيامة /36", "AYAH", {"source": {"ref": "75:36"}})["verdict"], "|",
          check("الأنبياء / 16", "AYAH", {"source": {"ref": "44:38-39"}})["note"])
    for claim, ref in [("[الرحمان: 13]", "55:13"), ("[سورة المحبة: 5]", "55:13"), ("[البقرة: 300]", "2:255"), ("[آية 5]", "2:5")]:
        r = check(claim, "AYAH", {"source": {"ref": ref}}); print("ayah", claim, "→", r["verdict"], "|", r.get("note"))
    alb = {"المحدث": "الألباني", "المصدر": "صحيح الترغيب", "الصفحة أو الرقم": "10"}
    bk  = {"المحدث": "البخاري", "المصدر": "صحيح البخاري", "الصفحة أو الرقم": "1"}
    enc = {"المحدث": HADEETHENC, "المصدر": "متفق عليه"}
    shk = {"المحدث": "أحمد شاكر", "المصدر": "تخريج المسند"}
    for claim, rs in [("رواه البخاري", [alb, bk]),            # in both: Albani's book AND Bukhari -> صحيح
                      ("رواه البخاري", [alb]),                # only a grading book seen -> لم نتحقق (not «wrong»)
                      ("رواه الترمذي", [alb, enc]),           # curated line says متفق عليه -> غير دقيق
                      ("رواه أبو داود", [enc]),               # curated line omits Abu Dawud -> لم نتحقق (may be there too)
                      ("رواه أحمد", [shk])]:                  # أحمد شاكر is not مسند أحمد -> لم نتحقق
        r = check(claim, "MATN", {"rulings": rs}); print(claim, "→", r["verdict"], "|", r.get("note"), "|", r.get("graded_in"))
