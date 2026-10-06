"""Verdict for one detected span, by literal comparison with the sources. The guardrail of Muhaqiq:
  مطابق   — the normalised span is contained in a source text
  لفظ مختلف — a window of a source text is close (>= NEAR) but not identical: canonical text + word diff
  لم نجده  — nothing close enough in the sources we searched (NOT "fabricated": we only report what we searched)
Grades (hadith) are quoted from dorar.net verbatim, never generated.
difflib: https://docs.python.org/3/library/difflib.html · rapidfuzz: https://rapidfuzz.github.io/RapidFuzz/
"""
import difflib, re
from rapidfuzz import fuzz
from normalize import norm, HON
import quran, dorar, hadeethenc

SAME = {"AYAH": 99.5, "MATN": 97}   # >= SAME: orthographic only -> مطابق. Quran wording is fixed, so near-exact for ayat
NEAR = 80                     # [NEAR, SAME): wording differs -> لفظ مختلف ; below: لم نجده. Tuned on dev (eval/results.md)
CANONICAL = ["متفق عليه", "صحيح البخاري", "صحيح مسلم", "سنن أبي داود", "سنن الترمذي", "سنن النسائي", "سنن ابن ماجه", "مسند أحمد"]

def content_words(text):
    """Source words + which of them carry content. Honorifics (صلى الله عليه وسلم، رضي الله عنه…) are removed by
    norm(), so they must not count towards the window length — otherwise a window of n words comes out short and
    starts or ends in the middle of the source text. -> [(raw_word, normalised_word_or_'')]"""
    words = [w for w in text.split() if norm(w)]                     # drop punctuation-only tokens like "،"
    toks = [norm(w) for w in words]
    for k in range(len(toks) - 1):                                   # a lone و/ف/ب/ك/ل belongs to the next word ("ب سبح")
        if toks[k] in ("و", "ف", "ب", "ك", "ل") and toks[k + 1]:
            toks[k + 1] = toks[k] + toks[k + 1]; toks[k] = ""
    joined, starts, pos = "", [], 0                                  # where each token starts in the joined string
    for t in toks:
        starts.append(len(joined)); joined += (t + " ") if t else ""
    hon = [False] * len(words)
    for m in HON.finditer(joined):                                   # same honorific list as norm()
        for k, st in enumerate(starts):
            if m.start() <= st < m.end(): hon[k] = True
    return [(w, "" if h or not t else t) for w, t, h in zip(words, toks, hon)]

def best_window(span, text):
    """Best-matching run of source words with about as many CONTENT words as `span`. -> (score, window_text)
    The window keeps the source's own honorifics and spelling; only the counting ignores them."""
    s = norm(span); n = len(s.split())
    cw = content_words(text)
    idx = [k for k, (_, t) in enumerate(cw) if t]                     # positions of content words
    best = (0, "")
    for size in (n, n - 1, n + 1):                                   # same length first; a different length must win by 3 points
        if size < 1: continue
        for a in range(0, max(1, len(idx) - size + 1)):
            sel = idx[a:a + size]
            if not sel: continue
            r = fuzz.ratio(s, " ".join(cw[k][1] for k in sel))
            if r > best[0] + (0 if size == n else 3):
                best = (r, " ".join(w for w, _ in cw[sel[0]:sel[-1] + 1]))
    return best

def diff_words(a, b):
    """Word-level edits turning a (as quoted) into b (canonical window). [(op, from, to)]"""
    A, B = a.split(), b.split()
    sm = difflib.SequenceMatcher(None, [norm(w) for w in A], [norm(w) for w in B])
    ops = [(op, " ".join(A[i1:i2]), " ".join(B[j1:j2])) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]
    same = lambda x, y: norm(x).replace(" ", "") == norm(y).replace(" ", "")   # spelling/spacing only: «بسبح» = «ب سبح», «:» = «»
    return [o for o in ops if not same(o[1], o[2])]

def hadith_queries(text):
    """dorar is a keyword search: whole span, then 4-word windows (robust to a corrupted word)."""
    w = norm(text).split()
    qs = [text] + [" ".join(w[i:i + 4]) for i in (0, max(0, len(w) // 2 - 2), max(0, len(w) - 4))]
    return list(dict.fromkeys(q for q in qs if len(q.split()) >= 2))

def candidates(text, label, searched):
    if label == "AYAH":
        searched.append(("quran (local index of 6236 ayat)", text))
        return quran.search(text)
    hits = []
    for q in hadith_queries(text):
        failed = []
        hits += dorar.search(q, failed)
        searched.append(("dorar.net — تعذّر الوصول" if failed else "dorar.net", q))
        if len(hits) >= 10: break
    searched.append(("hadeethenc.com (local index)", text))
    return hits + hadeethenc.search(text)

def rank_key(h, score):
    """Higher is better: score, then canonical collection, then a grade containing صحيح."""
    src, grade = h.get("المصدر", ""), h.get("خلاصة حكم المحدث", "")
    return (round(score), any(c in src for c in CANONICAL), "صحيح" in grade and "ضعيف" not in grade)

def rulings(scored, label):
    """Every scholar's ruling on the same wording (hadith): [{المحدث, المصدر, الصفحة أو الرقم, خلاصة حكم المحدث}]"""
    if label != "MATN": return []
    seen, out = set(), []
    for key, score, window, h in sorted(scored, key=lambda x: -x[1]):
        k = (h.get("المحدث"), h.get("المصدر"), h.get("الصفحة أو الرقم"))
        if score >= SAME["MATN"] and k not in seen:
            seen.add(k); out.append({f: h.get(f, "") for f in ("المحدث", "المصدر", "الصفحة أو الرقم", "خلاصة حكم المحدث")})
    return out[:8]

def partial(text, src):
    """اقتباس مجتزأ: the quote is a small part of a longer ayah/matn — show the whole so the reader sees the context."""
    full = src.get("simple") or src.get("text", "")
    n, m = len(norm(text).split()), len(norm(full).split())
    return {"partial": True, "full_text": src.get("text") or full, "quoted_fraction": round(n / m, 2)} if m and n / m < 0.6 else {}

def translations(label, src):
    """Links to the same text in other languages; verification stays on the Arabic, the links are navigation only."""
    if label == "AYAH" and src.get("ref"):
        s, a = src["ref"].split("-")[0].split(":")
        return {"en": f"https://quran.com/{s}/{a}", "quranenc": f"https://quranenc.com/en/browse/english_saheeh/{s}/{a}"}
    if label == "MATN" and src.get("hadeethenc_id"):
        return {"explanation": f"https://hadeethenc.com/ar/browse/hadith/{src['hadeethenc_id']}",
                **{lang: f"https://hadeethenc.com/{lang}/browse/hadith/{src['hadeethenc_id']}" for lang in ("en", "fr", "ur", "id", "tr")}}
    return {}

MIN_CHARS = 8          # shorter spans ("أن", "سألت", ". الخ") are detector noise: not verified, not shown
SHORT = 4              # 2–4 words found inside a much longer text -> يحتاج مراجعة, not مطابق
TRAILING = {"سنن", "رواه", "أخرجه", "اخرجه", "صحيح", "متفق", "مسند", "انظر"}   # a source name glued to the end of a quote

def clean_span(text):
    """drop a trailing source word the detector swallowed: «… يوم الفطر سنن» -> «… يوم الفطر»"""
    w = text.split()
    while len(w) > 2 and norm(w[-1]) in {norm(x) for x in TRAILING}: w.pop()
    return " ".join(w)

DORAR_DOWN = "تعذّر الوصول إلى الدرر السنية الآن؛ لم نحكم من بيانات ناقصة — أعد المحاولة بعد قليل."
GAP = re.compile(r"\s*(?:\.{2,}|…)\s*")                       # «...» / «…» = words left out of the quote

def dorar_failed(searched):
    return any("تعذّر" in s[0] for s in searched)

def as_in_source(raw, phrase):
    """the normalised words `phrase` as they are spelled in the source text `raw` («حتي» -> «حتى»)"""
    want = phrase.split(); words = [w for w in raw.split() if norm(w)]; toks = [norm(w) for w in words]
    for i in range(len(toks) - len(want) + 1):
        if toks[i:i + len(want)] == want: return " ".join(words[i:i + len(want)])
    return phrase

def verify_gapped(text, label):
    """«…في المحيض ... فإذا تطهرن…»: every part must occur IN ORDER in one source text (an ayah, two adjacent ayat,
    or one hadith). The source decides; the left-out words are shown. -> result dict or None"""
    parts = [p for p in GAP.split(text) if len(norm(p).split()) >= 2]
    if len(parts) < 2: return None
    searched = []
    for h in candidates(max(parts, key=len), label, searched):
        full = norm(h.get("simple") or h["text"]); pos, cuts = 0, []
        for p in parts:
            i = full.find(norm(p), pos)
            if i < 0: break
            cuts.append((i, i + len(norm(p)))); pos = cuts[-1][1]
        else:
            raw = h.get("simple") or h["text"]
            omitted = [as_in_source(raw, full[a[1]:b[0]].strip()) for a, b in zip(cuts, cuts[1:]) if full[a[1]:b[0]].strip()]
            return {"verdict": "مطابق", "score": 100, "source": h, "gapped": True, "omitted": omitted,
                    "note": "اقتباس مع حذف" + (": …[" + "] … [".join(omitted) + "]…" if omitted else ""),
                    "rulings": rulings([(None, 100, "", h)], label), "translations": translations(label, h), "searched": searched}
    return None

def verify(text, label, short_rule=True):
    """short_rule=False in «دليل واحد» mode: the user says the whole input is the quote, so a short opening
    like «إنما الأعمال بالنيات» is a real (partial) quote, not detector noise."""
    text = clean_span(text)
    if len(norm(text).replace(" ", "")) < MIN_CHARS:
        return {"verdict": None, "skipped": "مقطع قصير جدًا للتحقق"}
    if GAP.search(text):
        r = verify_gapped(text, label)
        if r: return r
        text = GAP.sub(" ", text).strip()                      # no source has the parts in order: compare as one text
    searched = []
    scored = []
    for h in candidates(text, label, searched):
        score, window = best_window(text, h.get("simple") or h["text"])
        scored.append((rank_key(h, score), score, window, h))
    if not scored:
        if dorar_failed(searched):
            return {"verdict": "يحتاج مراجعة", "score": 0, "note": DORAR_DOWN, "searched": searched}
        return {"verdict": "لم نجده", "score": 0, "searched": searched}
    key, score, window, best = max(scored, key=lambda x: x[0])
    contained = norm(text) in norm(best.get("simple") or best["text"])
    henc = next((h for _, sc, _, h in scored if h.get("hadeethenc_id") and sc >= SAME["MATN"]), best)   # same wording on hadeethenc?
    extra = {"rulings": rulings(scored, label), "translations": translations(label, henc if label == "MATN" else best), "searched": searched}
    full = norm(best.get("simple") or best["text"])
    if short_rule and contained and len(norm(text).split()) <= SHORT and len(norm(text)) < 0.3 * len(full):
        return {"verdict": "يحتاج مراجعة", "score": round(score, 1), "closest": best, "closest_window": window,
                "note": "مقطع قصير من نص أطول؛ لا يكفي للحكم — راجع النص الكامل", "searched": searched}
    if contained or score >= SAME[label]:
        return {"verdict": "مطابق", "score": 100 if contained else round(score, 1), "source": best, **partial(text, best), **extra}
    if label == "MATN" and dorar_failed(searched):
        return {"verdict": "يحتاج مراجعة", "score": round(score, 1), "closest": best, "closest_window": window,
                "note": DORAR_DOWN, "searched": searched}
    if score >= NEAR:
        return {"verdict": "لفظ مختلف", "score": round(score, 1), "source": best, "canonical": window,
                "diff": diff_words(text, window), **extra}
    return {"verdict": "لم نجده", "score": round(score, 1), "closest": best, "closest_window": window, "searched": searched}

if __name__ == "__main__":
    tests = [("إنما الأعمال بالنيات وإنما لكل امرئ ما نوى", "MATN"),
             ("إنما الأعمال بالنيات وإنما لكل امرئ ما قصد", "MATN"),
             ("وَعَلَّمَكُمْ مَا لَمَ تَعْلَمُوا", "AYAH"),
             ("قُلْ هُوَ الْحَلَالُ وَالْحَرَامُ", "AYAH"),
             ("من قرأ سورة الواقعة كل ليلة صار غنيا في أسبوع", "MATN")]
    for t, l in tests:
        r = verify(t, l)
        src = r.get("source") or r.get("closest") or {}
        print(f"\n{l}: {t}\n  → {r['verdict']} ({r['score']})  {src.get('ref') or src.get('المصدر', '')} | {src.get('خلاصة حكم المحدث', '')}")
        if r.get("diff"): print("  canonical:", r["canonical"], "\n  diff:", r["diff"])
        if r.get("closest_window"): print("  closest:", r["closest_window"])


# ---------- boundary repair: the detector often stops one word early («ويوم الفطر ويوم» without «النحر») ----------
EDGE_PUNCT = "«»\"'()[]{}﴿﴾:؛;,،.!؟?-–—…"
PREV_WORD = re.compile(r"(\S+)\s*$")

def _match(doc_piece, full):
    """100 if contained in the source, else the best window score."""
    n = norm(doc_piece)
    if n and n in norm(full): return 100.0
    return best_window(doc_piece, full)[0]

def repair_boundaries(doc, start, end, result, lo=0, hi=None, max_words=3):
    """Extend [start, end) by up to `max_words` words on each side when the SOURCE continues with exactly those
    words — the source decides, not a guess. Never crosses into the neighbouring spans (lo, hi). -> (start, end)"""
    hi = len(doc) if hi is None else hi
    src = result.get("source") or {}
    full = src.get("simple") or src.get("text") or ""
    if result.get("verdict") not in ("مطابق", "لفظ مختلف") or not full: return start, end
    base = _match(doc[start:end], full)
    for _ in range(max_words):                                   # forwards
        m = re.compile(r"\s*(\S+)").match(doc, end)
        if not m or m.end(1) > hi: break
        core = m.group(1).rstrip(EDGE_PUNCT)
        if not norm(core) or "\n" in doc[end:m.start(1)]: break
        new_end = m.start(1) + len(core)
        sc = _match(doc[start:new_end], full)
        if sc < base or (sc == base and base < 100): break      # the next word is not the source's next word
        end, base = new_end, sc
    for _ in range(max_words):                                   # backwards
        m = PREV_WORD.search(doc, 0, start)
        if not m or m.start(1) < lo: break
        core = m.group(1).lstrip(EDGE_PUNCT)
        if not norm(core) or "\n" in doc[m.end(1):start]: break
        new_start = m.end(1) - len(core)
        sc = _match(doc[new_start:end], full)
        if sc < base or (sc == base and base < 100): break
        start, base = new_start, sc
    return start, end

def refresh(result, text, label):
    """after a boundary change: recompute score / canonical / diff / partial against the same source (no new search)"""
    src = result.get("source") or {}
    full = src.get("simple") or src.get("text") or ""
    if not full: return result
    sc, window = best_window(text, full)
    contained = norm(text) in norm(full)
    for k in ("partial", "full_text", "quoted_fraction", "canonical", "diff"): result.pop(k, None)
    if contained or sc >= SAME[label]:
        result.update(verdict="مطابق", score=100 if contained else round(sc, 1), **partial(text, src))
    else:
        result.update(score=round(sc, 1), canonical=window, diff=diff_words(text, window))
    return result
