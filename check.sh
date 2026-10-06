#!/usr/bin/env bash
# Muhaqiq repo check — run from the repo root before every commit.
#   bash check.sh                      # files + code checks only
#   bash check.sh https://...modal.run # also calls that API (live or the `modal serve` -dev URL)
# Prints ✓ / ✗ per check and a total at the end. Changes nothing.
cd "$(dirname "$0")"
pass=0; fail=0
ok()  { echo "  ✓ $1"; pass=$((pass+1)); }
bad() { echo "  ✗ $1"; fail=$((fail+1)); }

echo "1. Files that must exist"
for f in README.md .github/workflows/pages.yml \
         api/modal_app.py api/llm_modal.py api/README.md \
         tools/normalize.py tools/cache.py tools/quran.py tools/quran.json tools/dorar.py tools/hadeethenc.py tools/hadeethenc.json \
         tools/verify.py tools/attribution.py tools/rescue.py tools/recommend.py tools/relevance.py tools/README.md \
         encoder/predict.py \
         web/index.html web/render.js web/icon.svg web/mark.svg \
         extension/manifest.json extension/background.js extension/content.js extension/render.js extension/styles.css \
         extension/popup.html extension/popup.js extension/icons/icon16.png extension/icons/icon32.png extension/icons/icon48.png extension/icons/icon128.png; do
  [ -s "$f" ] && ok "$f" || bad "$f missing or empty"
done

echo "2. Git: nothing deleted by accident"
del=$(git ls-files --deleted)
[ -z "$del" ] && ok "no deleted tracked files" || bad "deleted: $(echo $del)  →  git restore \$(git ls-files --deleted)"

echo "3. Versions (catches an old file put back by mistake)"
grep -q '"version": "1.0.0"' extension/manifest.json && ok "manifest v1.0" || bad "extension/manifest.json is not v1.0"
grep -q '/verify' extension/background.js && ok "background.js calls /verify" || bad "extension/background.js is the old /spans version"
grep -q 'content v1.0' extension/content.js && ok "content.js v1.0" || bad "extension/content.js is old"
cmp -s web/render.js extension/render.js && ok "render.js identical in web/ and extension/" || bad "render.js differs → cp web/render.js extension/"
grep -q 'attVerdict' web/render.js && ok "render.js has «المصدر» wording" || bad "web/render.js is old"
grep -q 'URLSearchParams' web/index.html && ok "index.html has ?api= switch" || bad "web/index.html is old"
grep -q 'id="moreBox"' web/index.html && ok "index.html has «اعرف المزيد» section" || bad "web/index.html has no learn-more section"
grep -q 'المصدر غير دقيق' api/modal_app.py && ok "modal_app counts «المصدر غير دقيق»" || bad "api/modal_app.py still counts «العزو»"
grep -q 'SAHIHAYN' tools/attribution.py && ok "attribution.py new source check" || bad "tools/attribution.py is old"
grep -q 'disagreement' tools/recommend.py && ok "recommend.py new (no model levels)" || bad "tools/recommend.py is old"
grep -q 'غير مؤكد' tools/relevance.py && ok "relevance.py three states" || bad "tools/relevance.py is old"
grep -q 'aggregation_strategy="first"' encoder/predict.py && ok "predict.py word-level spans + joining" || bad "encoder/predict.py is old (simple aggregation)"
grep -q 'repair_boundaries' tools/verify.py && grep -q 'repair_boundaries' api/modal_app.py && ok "boundary repair wired in" || bad "boundary repair missing (tools/verify.py or api/modal_app.py old)"
grep -q 'one_quote' api/modal_app.py && ok "API has «دليل واحد» (single)" || bad "api/modal_app.py has no single mode"
grep -q 'id="single"' web/index.html && grep -q 'DISCLAIMER' web/render.js && ok "site has «دليل واحد» + disclaimer" || bad "web/ missing single mode or disclaimer"
grep -q 'verify_gapped' tools/verify.py && grep -q 'failed=None' tools/dorar.py && ok "ellipsis + dorar-failure handling present" || bad "tools/verify.py or tools/dorar.py old"
grep -q 'غير محفوظ' web/render.js && ok "render.js knows «غير محفوظ / شاذ / متروك»" || bad "web/render.js old (weak terms)"
grep -q 'single: true' extension/background.js && ok "extension right-click checks the selection as one quote" || bad "extension/background.js is old"

echo "4. Code compiles"
python -m py_compile api/*.py tools/*.py encoder/predict.py 2>/tmp/mq_py && ok "all Python files compile" || bad "Python syntax: $(head -3 /tmp/mq_py)"
python -c "import json; json.load(open('extension/manifest.json'))" 2>/dev/null && ok "manifest.json is valid JSON" || bad "manifest.json invalid JSON"
if command -v node >/dev/null; then
  for f in web/render.js extension/*.js; do node --check "$f" 2>/dev/null && ok "JS syntax $f" || bad "JS syntax error in $f"; done
else echo "  – node not installed: JS syntax skipped (brew install node to enable)"; fi

echo "5. Logic tests (no network)"
out=$(cd tools && python attribution.py 2>&1)
echo "$out" | grep -q 'رواه البخاري → المصدر صحيح' && ok "Bukhari + صحيح الترغيب → المصدر صحيح" || bad "attribution test 1"
echo "$out" | grep -q 'رواه الترمذي → لم نتحقق من المصدر' && ok "Tirmidhi vs «متفق عليه» → لم نتحقق (not «wrong»)" || bad "attribution test 2"
echo "$out" | grep -q 'رواه أحمد → لم نتحقق من المصدر' && ok "أحمد شاكر is not مسند أحمد" || bad "attribution test 3"
echo "$out" | grep -q 'surah names parsed: 114 / 114' && ok "all 114 surah names parsed (القيامة is not ق)" || bad "surah name parsing"
echo "$out" | grep -q 'الدخان 38–39' && ok "correction shows the full ayah range" || bad "ayah range in correction"
echo "$out" | grep -q 'اسم السورة يُكتب «الرحمن» لا «الرحمان»' && ok "misspelled surah name → still checked, spelling noted" || bad "misspelled surah name"
echo "$out" | grep -q 'لا توجد سورة باسم «المحبة»' && ok "non-existent surah name → «المصدر غير دقيق»" || bad "unknown surah name"
echo "$out" | grep -q 'عدد آياتها 286 فلا توجد الآية 300' && ok "ayah number past the end of the surah" || bad "ayah number out of range"
echo "$out" | grep -q 'لم يُذكر اسم السورة' && ok "number without a surah name → shows where the ayah is" || bad "reference without surah name"
python - <<'PY' 2>/dev/null && ok "window keeps the whole hadith when it contains «صلى الله عليه وسلم»" || bad "best_window misaligned (canonical text cut short)"
import sys; sys.path.insert(0, "tools")
from verify import best_window, diff_words
q = "كَانَ رَسُولُ اللَّهِ صَلَّى اللَّهُ عَلَيْهِ وَسَلَّمَ يَقْرَأُ فِي الْعِيدَيْنِ وَفِي الْجُمُعَةِ بِسَبِّحِ اسْمَ رَبِّكَ الْأَعْلَى"
src = "كان رسولُ اللهِ صلَّى اللهُ عليه وسلَّمَ يقرأ في العيدَين وفي الجمعةِ ب سبِّحِ اسمَ ربِّك الأَعْلى و هلْ أتاك"
sc, w = best_window(q, src)
assert sc == 100 and w.startswith("كان رسولُ") and diff_words(q, w) == []
PY
python - <<'PY' 2>/dev/null && ok "boundary repair restores the missing last word («النحر», «الطريق»)" || bad "boundary repair"
import sys; sys.path.insert(0, "tools")
from verify import repair_boundaries
for doc, span, src, want in [
  ("نَهَى عَنْ صِيَامِ يَوْمَيْنِ يَوْمِ الْفِطْرِ وَيَوْمِ النَّحْرِ رواه مسلم", "نَهَى عَنْ صِيَامِ يَوْمَيْنِ يَوْمِ الْفِطْرِ وَيَوْمِ",
   "نهى رسولُ اللهِ صلَّى اللهُ عليه وسلَّم عن صيامِ يومينِ يومِ الفِطرِ ويومِ النَّحرِ", "وَيَوْمِ النَّحْرِ"),
  ("إِذَا كَانَ يَوْمُ عِيدٍ خَالَفَ الطَّرِيقَ رواه البخاري", "إِذَا كَانَ يَوْمُ عِيدٍ خَالَفَ", "كان إذا كان يومُ عيدٍ خالفَ الطريقَ", "خَالَفَ الطَّرِيقَ")]:
    a = doc.index(span); na, nb = repair_boundaries(doc, a, a + len(span), {"verdict": "مطابق", "source": {"text": src}})
    assert doc[na:nb].endswith(want) and "رواه" not in doc[na:nb], doc[na:nb]
PY
python - <<'PY' 2>/dev/null && ok "detector pieces of one quote are joined" || bad "merge_adjacent"
import re
src = open("encoder/predict.py", encoding="utf-8").read()
ns = {"re": re}; exec(src[src.index("GAP = "):src.index("def find_spans")], ns)
t = "قال : إن لكل قوم عيدا وهذا عيدنا رواه البخاري"
sp = [{"label": "MATN", "start": t.index("إن"), "end": t.index("قوم") + 3, "score": .9},
      {"label": "MATN", "start": t.index("عيدا"), "end": t.index("عيدنا") + 5, "score": .7}]
for x in sp: x["text"] = t[x["start"]:x["end"]]
m = ns["merge_adjacent"](sp, t); assert len(m) == 1 and m[0]["text"] == "إن لكل قوم عيدا وهذا عيدنا"
PY
python - <<'PY' 2>/dev/null && ok "ayah quoted with «...» → «مطابق» + the left-out words" || bad "ellipsis quotes"
import sys, types; sys.path.insert(0, "tools")
import verify as V
A = "ويسألونك عن المحيض قل هو أذى فاعتزلوا النساء في المحيض ولا تقربوهن حتى يطهرن فإذا تطهرن فأتوهن من حيث أمركم الله"
V.candidates = lambda t, l, s: [{"ref": "2:222", "text": A, "simple": A, "url": "https://quran.com/2"}]
r = V.verify("ويسألونك عن المحيض قل هو أذى فاعتزلوا النساء في المحيض... فإذا تطهرن فأتوهن من حيث أمركم الله", "AYAH")
assert r["verdict"] == "مطابق" and "ولا تقربوهن حتى يطهرن" in r["note"], r
PY
python - <<'PY' >/dev/null 2>&1 && ok "dorar unreachable → «يحتاج مراجعة», not a verdict from partial data" || bad "dorar-down handling"
import sys; sys.path.insert(0, "tools")
import verify as V, dorar, hadeethenc
def boom(*a, **k): raise RuntimeError("down")
dorar.requests.get = boom; dorar.cached = lambda k, f: f(); hadeethenc.search = lambda t, k=5: []
r = V.verify("العهد الذي بيننا وبينهم الصلاة فمن تركها فقد كفر", "MATN")
assert r["verdict"] == "يحتاج مراجعة" and "الدرر" in r["note"], r
PY
python - <<'PY' 2>/dev/null && ok "1-word fragments («أن», «سألت») are skipped, not «مطابق»" || bad "short fragments still verified"
import sys; sys.path.insert(0, "tools")
from verify import verify
assert verify("أن", "MATN")["verdict"] is None and verify("سألت", "MATN")["verdict"] is None
PY
python - <<'PY' 2>/dev/null && ok "ayah counts match tools/quran.json (114 surahs)" || bad "AYAH_COUNTS differ from tools/quran.json"
import sys, json, collections; sys.path.insert(0, "tools")
from attribution import AYAH_COUNTS
c = collections.Counter(int(v["key"].split(":")[0]) for v in json.load(open("tools/quran.json", encoding="utf-8")))
assert [c[i] for i in range(1, 115)] == AYAH_COUNTS
PY
python -c "import sys; sys.path.insert(0,'tools'); from normalize import norm; assert norm('السموات')==norm('السماوات') and norm('ملك')!=norm('مالك')" 2>/dev/null \
  && ok "السموات = السماوات, ملك ≠ مالك" || bad "rasm normalisation"

if [ -n "$1" ]; then
  API="${1%/}"
  echo "6. API $API (first call may take ~1–2 min while it wakes up)"
  r=$(curl -s -m 200 -X POST "$API/verify" -H 'Content-Type: application/json' \
      -d '{"text":"قال تعالى: ﴿وَمَا خَلَقْتُ الْجِنَّ وَالْإِنسَ إِلَّا لِيَعْبُدُونِ﴾ [البقرة: 56]","question":"هل تصح الصلاة بدون وضوء؟"}')
  [ -n "$r" ] && ok "API answered" || bad "no answer from API"
  echo "$r" | grep -q 'المصدر غير دقيق' && ok "wrong surah → «المصدر غير دقيق»" || bad "wrong surah not caught (old code deployed? run modal serve/deploy)"
  echo "$r" | grep -q '"disagreement"' && ok "new recommender is running" || bad "old recommender still running (redeploy)"
  echo "$r" | grep -q 'مسألة فيها خلاف بين أهل العلم' && bad "old «خلاف» sentence still produced" || ok "no model-made «خلاف» sentence"
  r3=$(curl -s -m 200 -X POST "$API/verify" -H 'Content-Type: application/json' \
      -d '{"text":"يحرم صوم يومي العيد لحديث أبي سعيد: أن رسول الله صلى الله عليه وسلم نهى عن صيام يومين يوم الفطر ويوم النحر رواه مسلم (827)."}')
  echo "$r3" | python -c "import sys,json; d=json.load(sys.stdin); m=[c for c in d['citations'] if c['label']=='MATN']; assert m and m[0]['text'].rstrip().endswith('النحر'), [c['text'] for c in m]" 2>/dev/null \
    && ok "quote ends with «النحر» (detector + repair)" || bad "quote still cut before «النحر»"
  r4=$(curl -s -m 200 -X POST "$API/verify" -H 'Content-Type: application/json' -d '{"text":"إنما الأعمال بالنيات رواه البخاري","single":true}')
  echo "$r4" | python -c "import sys,json; c=json.load(sys.stdin)['citations'][0]; assert c.get('single') and c['verdict']=='مطابق'" 2>/dev/null \
    && ok "«دليل واحد» mode verifies the whole input" || bad "single mode (redeploy / modal serve again?)"
  r2=$(curl -s -m 120 -X POST "$API/verify" -H 'Content-Type: application/json' \
      -d '{"text":"قال النبي ﷺ: إنما الأعمال بالنيات. رواه الترمذي"}')
  echo "$r2" | grep -q 'المصدر غير دقيق' && bad "Tirmidhi (correct) flagged as wrong" || ok "Tirmidhi not flagged as wrong"
fi

echo; echo "Passed $pass, failed $fail"; [ $fail -eq 0 ]
