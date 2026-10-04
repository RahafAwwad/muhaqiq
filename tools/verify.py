"""Verdict for one detected span, by literal comparison with the sources. The guardrail of Muhaqiq:
  مطابق   — the normalised span is contained in a source text
  لفظ مختلف — a window of a source text is close (>= NEAR) but not identical: canonical text + word diff
  لم نجده  — nothing close enough in the sources we searched (NOT "fabricated": we only report what we searched)
Grades (hadith) are quoted from dorar.net verbatim, never generated.
difflib: https://docs.python.org/3/library/difflib.html · rapidfuzz: https://rapidfuzz.github.io/RapidFuzz/
"""
import difflib
from rapidfuzz import fuzz
from normalize import norm
import quran, dorar, hadeethenc

SAME = {"AYAH": 99.5, "MATN": 97}   # >= SAME: orthographic only -> مطابق. Quran wording is fixed, so near-exact for ayat
NEAR = 80                     # [NEAR, SAME): wording differs -> لفظ مختلف ; below: لم نجده. Tuned on dev (eval/results.md)
CANONICAL = ["صحيح البخاري", "صحيح مسلم", "سنن أبي داود", "سنن الترمذي", "سنن النسائي", "سنن ابن ماجه", "مسند أحمد"]

def best_window(span, text):
    """Best-matching run of words in `text` with about as many words as `span`. -> (score, window_text)"""
    s, words = norm(span), [w for w in text.split() if norm(w)]      # drop punctuation-only tokens like "،"
    n, best = len(s.split()), (0, "")
    for size in (n, n - 1, n + 1):                      # same length first; a different length must win by 3 points
        for i in range(0, max(1, len(words) - size + 1)):
            w = " ".join(words[i:i + size])
            r = fuzz.ratio(s, norm(w))
            if r > best[0] + (0 if size == n else 3): best = (r, w)
    return best

def diff_words(a, b):
    """Word-level edits turning a (as quoted) into b (canonical window). [(op, from, to)]"""
    A, B = a.split(), b.split()
    sm = difflib.SequenceMatcher(None, [norm(w) for w in A], [norm(w) for w in B])
    return [(op, " ".join(A[i1:i2]), " ".join(B[j1:j2])) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]

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
        searched.append(("dorar.net", q))
        hits += dorar.search(q)
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

def verify(text, label):
    searched = []
    scored = []
    for h in candidates(text, label, searched):
        score, window = best_window(text, h.get("simple") or h["text"])
        scored.append((rank_key(h, score), score, window, h))
    if not scored:
        return {"verdict": "لم نجده", "score": 0, "searched": searched}
    key, score, window, best = max(scored, key=lambda x: x[0])
    contained = norm(text) in norm(best.get("simple") or best["text"])
    henc = next((h for _, sc, _, h in scored if h.get("hadeethenc_id") and sc >= SAME["MATN"]), best)   # same wording on hadeethenc?
    extra = {"rulings": rulings(scored, label), "translations": translations(label, henc if label == "MATN" else best), "searched": searched}
    if contained or score >= SAME[label]:
        return {"verdict": "مطابق", "score": 100 if contained else round(score, 1), "source": best, **partial(text, best), **extra}
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
