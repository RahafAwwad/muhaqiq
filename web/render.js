// Muhaqiq shared renderer — turns one /verify citation into an HTML card. Used by the website (web/) and the
// extension (extension/render.js is a copy: `cp web/render.js extension/`). No framework, plain strings.
// API contract: api/README.md · Template literals: https://developer.mozilla.org/docs/Web/JavaScript/Reference/Template_literals
(function () {
  const SURAHS = ["الفاتحة","البقرة","آل عمران","النساء","المائدة","الأنعام","الأعراف","الأنفال","التوبة","يونس","هود","يوسف","الرعد","إبراهيم","الحجر","النحل","الإسراء","الكهف","مريم","طه","الأنبياء","الحج","المؤمنون","النور","الفرقان","الشعراء","النمل","القصص","العنكبوت","الروم","لقمان","السجدة","الأحزاب","سبأ","فاطر","يس","الصافات","ص","الزمر","غافر","فصلت","الشورى","الزخرف","الدخان","الجاثية","الأحقاف","محمد","الفتح","الحجرات","ق","الذاريات","الطور","النجم","القمر","الرحمن","الواقعة","الحديد","المجادلة","الحشر","الممتحنة","الصف","الجمعة","المنافقون","التغابن","الطلاق","التحريم","الملك","القلم","الحاقة","المعارج","نوح","الجن","المزمل","المدثر","القيامة","الإنسان","المرسلات","النبأ","النازعات","عبس","التكوير","الانفطار","المطففين","الانشقاق","البروج","الطارق","الأعلى","الغاشية","الفجر","البلد","الشمس","الليل","الضحى","الشرح","التين","العلق","القدر","البينة","الزلزلة","العاديات","القارعة","التكاثر","العصر","الهمزة","الفيل","قريش","الماعون","الكوثر","الكافرون","النصر","المسد","الإخلاص","الفلق","الناس"];

  // verdict -> css class + one-line meaning (عام mode shows only this line + source)
  const V = {
    "مطابق":        { cls: "ok",     icon: "✓" },
    "لفظ مختلف":    { cls: "diff",   icon: "≠" },
    "لم نجده":      { cls: "none",   icon: "؟" },
    "يحتاج مراجعة": { cls: "review", icon: "!" },
  };
  const WEAK = /ضعيف|موضوع|باطل|لا أصل|منكر|كذب|مكذوب|واه|شديد الضعف|لا يصح|لا يثبت|غير محفوظ|شاذ|متروك|ليس بشيء/;
  const ASK_URL = "https://islamqa.info/ar";   // where «اسأل أهل العلم» sends people; change to any approved fatwa service

  // source check («المصدر المذكور»): accept the new API wording and the old «العزو…» wording
  const ATT = { "العزو صحيح": "المصدر صحيح", "العزو غير دقيق": "المصدر غير دقيق" };
  const attVerdict = a => a ? (ATT[a.verdict] || a.verdict) : "";
  const attBad = a => attVerdict(a) === "المصدر غير دقيق";
  const attUnsure = a => attVerdict(a) === "لم نتحقق من المصدر";

  const esc = s => String(s ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  const toAr = n => String(n).replace(/\d/g, d => "٠١٢٣٤٥٦٧٨٩"[d]);

  function quranRef(ref) {                            // "2:255" -> "البقرة: ٢٥٥" ; "2:255-256" -> "البقرة: ٢٥٥–٢٥٦"
    const m = /^(\d+):(\d+)(?:-(\d+))?$/.exec(ref || ""); if (!m) return ref || "";
    return `${SURAHS[+m[1] - 1] || "سورة " + m[1]}: ${toAr(m[2])}${m[3] ? "–" + toAr(m[3]) : ""}`;
  }
  const kind = c => c.label === "AYAH" ? "آية" : c.label === "MATN" ? "حديث" : c.label === "ISNAD" ? "إسناد" : "مصدر مذكور";

  function where(src, label) {                        // "صحيح البخاري · ١" or "البقرة: ٢٥٥"
    if (!src) return "";
    if (label === "AYAH") return quranRef(src.ref);
    return [src["المصدر"], src["الصفحة أو الرقم"]].filter(Boolean).join(" · ");
  }
  const grade = src => (src && src["خلاصة حكم المحدث"] || "").replace(/^\[|\]$/g, "").trim();
  const SAHIHAYN = /صحيح البخاري|صحيح مسلم|متفق عليه/;
  const isWeak = c => {
    const rs = c.rulings || [];
    if ([c.source || {}, ...rs].some(r => SAHIHAYN.test(r["المصدر"] || ""))) return false;      // in البخاري / مسلم
    const weak = rs.filter(r => WEAK.test(r["خلاصة حكم المحدث"] || "")).length;
    return WEAK.test(grade(c.source)) || (rs.length > 0 && weak * 2 > rs.length);                // most graders weaken it
  };

  function reason(c) {                                // the plain-language line, also used in CSV and «اسأل»
    const w = where(c.source || c.closest, c.label);
    switch (c.verdict) {
      case "مطابق":
        return c.label === "AYAH" ? `مطابق لنص المصحف — ${w}` : `النص موجود بلفظه في ${w || "المصادر"}` + (isWeak(c) ? "، لكن في الحكم عليه كلام — انظر أحكام المحدثين" : "");
      case "لفظ مختلف": return `اللفظ يختلف عمّا في ${w || "المصدر"}؛ اللفظ الصحيح: «${c.canonical}»`;
      case "لم نجده":   return "لم نجده في المصادر المعتمدة؛ لا نحكم عليه بصحة ولا بطلان." + (c.single ? " وقد لا يكون آيةً ولا حديثًا (كدعاءٍ أو قولٍ مأثور)." : "");
      case "يحتاج مراجعة": return "يشبه نصًّا في المصادر ولم نتأكد منه؛ يُعرض على أهل العلم.";
    }
    return "";
  }

  function diffHtml(diff) {
    return (diff || []).map(([op, a, b]) =>
      op === "replace" ? `<li><del>${esc(a)}</del> ← <ins>${esc(b)}</ins></li>` :
      op === "delete"  ? `<li><del>${esc(a)}</del> <small>(زائدة)</small></li>` :
                         `<li><ins>${esc(b)}</ins> <small>(ناقصة)</small></li>`).join("");
  }

  function rulingsHtml(rs, max) {
    const rows = (rs || []).slice(0, max).map(r => `<tr><td>${esc(r["المحدث"])}</td><td>${esc(r["المصدر"])} ${esc(r["الصفحة أو الرقم"])}</td>
      <td class="${WEAK.test(r["خلاصة حكم المحدث"] || "") ? "mq-weak" : ""}">${esc((r["خلاصة حكم المحدث"] || "").replace(/^\[|\]$/g, ""))}</td></tr>`).join("");
    return rows ? `<table class="mq-rulings"><thead><tr><th>المحدّث</th><th>المصدر</th><th>الحكم</th></tr></thead><tbody>${rows}</tbody></table>` : "";
  }

  const LANGS = { en: "English", fr: "Français", ur: "اردو", id: "Indonesia", tr: "Türkçe", quranenc: "QuranEnc", explanation: "الشرح" };

  // card(c, mode, i): mode "general" (عام) or "expert" (متخصص); i = index for the «اسأل» button
  function card(c, mode, i) {
    if (!c.verdict) {                                  // SOURCE / ISNAD spans: only the attribution, if any
      return "";
    }
    const v = V[c.verdict] || V["يحتاج مراجعة"], expert = mode === "expert";
    const src = c.source || c.closest, w = where(src, c.label), g = grade(c.source);
    const att = c.attribution, badAtt = attBad(att), unsureAtt = attUnsure(att);
    let h = `<article class="mq-card mq-${v.cls}" data-i="${i}">
      <header><span class="mq-badge">${v.icon} ${esc(c.verdict)}</span><span class="mq-kind">${kind(c)}</span>
      ${badAtt ? `<span class="mq-badge mq-att">المصدر غير دقيق</span>` : unsureAtt ? `<span class="mq-chip mq-chip-warn">لم نتحقق من المصدر</span>` : ""}
      ${c.low_confidence ? `<span class="mq-chip mq-chip-warn" title="نموذج الكشف لم يكن واثقًا من أن هذا النص آية أو حديث">ثقة منخفضة في الكشف</span>` : ""}
      ${c.via ? `<span class="mq-chip" title="اقترح وكيل مُحقِّق الذكي لفظًا محتملًا، ثم بحثنا عنه في المصادر؛ الحكم من المصدر لا من النموذج">استُدرك بالوكيل الذكي</span>` : ""}</header>
      <blockquote>${esc(c.text)}</blockquote>
      <p class="mq-reason">${esc(reason(c))}</p>${c.note ? `<p class="mq-note">${esc(c.note)}</p>` : ""}`;

    if (g && c.verdict !== "يحتاج مراجعة")
      h += `<p class="mq-grade ${isWeak(c) ? "mq-weak" : ""}">حكم المحدّث: ${esc(g)}${c.source["المحدث"] ? " — " + esc(c.source["المحدث"]) : ""}</p>`;
    if (att && (attVerdict(att) !== "لا يمكن التحقق" || att.note))   // «لا يمكن التحقق» is shown only when it carries a note
      h += `<p class="mq-attline ${badAtt ? "mq-bad" : ""}">المصدر المذكور: «${esc(att.claimed)}» — ${esc(attVerdict(att))}`
        + (att.note ? `<br><small>${esc(att.note)}</small>` : badAtt && att.found ? `<br><small>وجدناه في: ${esc([].concat(att.found).join("، "))}</small>` : "") + `</p>`;
    if (expert && att && (att.basis || (att.graded_in || []).length))
      h += `<p class="mq-note">${att.basis ? "أساس الفحص: " + esc(att.basis) : ""}${(att.graded_in || []).length ? `<br>حكم عليه أيضًا: ${esc(att.graded_in.join("، "))}` : ""}</p>`;
    if (c.partial)
      h += `<p class="mq-note">اقتباس جزئي (${toAr(Math.round(c.quoted_fraction * 100))}٪ من النص)${expert ? "" : " — النص الكامل في المصدر"}</p>`;

    if (c.relevance && !c.relevance.error && (expert || c.relevance.label !== "متصل"))   // a doubt is shown in both modes
      h += `<p class="mq-note mq-rel">الصلة بالسؤال (تجريبي): ${esc(c.relevance.label)}${c.relevance.note ? " — " + esc(c.relevance.note) : ""}</p>`;
    if (expert && c.repaired)
      h += `<p class="mq-note">وُسِّعت حدود الاقتباس لتطابق المصدر (كان الكشف الآلي قد اقتطع كلمة أو أكثر).</p>`;
    if (expert) {
      if (c.diff && c.diff.length) h += `<h4>الفرق كلمةً كلمة</h4><ul class="mq-difflist">${diffHtml(c.diff)}</ul>`;
      if (src && src.text) h += `<h4>${c.verdict === "مطابق" || c.verdict === "لفظ مختلف" ? "نص المصدر" : "أقرب نص وجدناه"} ${w ? "— " + esc(w) : ""}</h4><p class="mq-src">${esc(c.closest_window || src.text)}</p>`;
      if (c.partial && c.full_text) h += `<details><summary>النص الكامل</summary><p class="mq-src">${esc(c.full_text)}</p></details>`;
      if (c.rulings && c.rulings.length) h += `<h4>أحكام المحدّثين (منقولة من الدرر السنية)</h4>${rulingsHtml(c.rulings, 8)}`;
      if (c.candidates) h += `<p class="mq-note">نصوص مرشّحة: ${esc(c.candidates.filter(Boolean).join("، "))}</p>`;
      if (c.searched && c.searched.length)
        h += `<details><summary>سجل البحث (${toAr(c.searched.length)})</summary><ul class="mq-log">${c.searched.map(s => `<li>${esc(Array.isArray(s) ? s.join(" — ") : s)}</li>`).join("")}</ul></details>`;
    }

    const links = [];
    const matched = c.verdict === "مطابق" || c.verdict === "لفظ مختلف";
    if (src && src.url && matched) links.push(`<a href="${esc(src.url)}" target="_blank" rel="noopener">فتح المصدر ↗</a>`);
    else if (src && src.url && (expert || c.verdict === "يحتاج مراجعة"))
      links.push(`<a href="${esc(src.url)}" target="_blank" rel="noopener" title="ليس مطابقًا للنص — أقرب ما قارنّا به">أقرب نص قارنّا به ↗</a>`);
    if (!matched && c.label === "MATN")
      links.push(`<a href="https://dorar.net/hadith/search?q=${encodeURIComponent(c.text.slice(0, 80))}" target="_blank" rel="noopener">ابحث عن نصّك في الدرر ↗</a>`);
    if (!matched && c.label === "AYAH")
      links.push(`<a href="https://quran.com/search?q=${encodeURIComponent(c.text.slice(0, 80))}" target="_blank" rel="noopener">ابحث عن نصّك في quran.com ↗</a>`);
    for (const [k, url] of Object.entries(c.translations || {}))
      if (expert || k === "explanation") links.push(`<a href="${esc(url)}" target="_blank" rel="noopener">${esc(LANGS[k] || k)}</a>`);
    const ask = c.verdict !== "مطابق" || badAtt || unsureAtt || isWeak(c);
    h += `<footer>${links.join("")}${ask ? `<button class="mq-ask" data-ask="${i}">اسأل أهل العلم</button>` : ""}</footer></article>`;
    return h;
  }

  // annotate(text, citations): the text with <mark> on every span; AYAH/MATN coloured by verdict
  function annotate(text, cits) {
    let out = "", at = 0;
    cits.forEach((c, i) => {
      if (c.start < at) return;                       // never overlap
      const cls = c.verdict ? "mq-m-" + (V[c.verdict] || V["يحتاج مراجعة"]).cls : "mq-m-meta";
      out += esc(text.slice(at, c.start)) + `<mark class="${cls}" data-i="${i}" title="${esc(c.verdict || kind(c))}">${esc(text.slice(c.start, c.end))}</mark>`;
      at = c.end;
    });
    return out + esc(text.slice(at));
  }

  function askText(c) {                               // a ready-to-send question for a scholar / fatwa service
    return `السلام عليكم ورحمة الله،\nوجدتُ هذا النص منسوبًا على أنه ${kind(c)}:\n«${c.text}»\n` +
      (c.attribution ? `والمصدر المذكور معه: ${c.attribution.claimed}\n` : "") +
      `ونتيجة الفحص الآلي (مُحقِّق): ${c.verdict} — ${reason(c)}\nفما صحة هذا النص ولفظه؟ وجزاكم الله خيرًا.`;
  }

  function csv(cits) {                                // UTF-8 with BOM so Excel shows Arabic
    const head = ["النوع", "النص", "الحكم", "التوضيح", "الموضع", "حكم المحدث", "المصدر المذكور", "نتيجة فحص المصدر", "اللفظ الصحيح", "الرابط"];
    const rows = cits.filter(c => c.verdict).map(c => [kind(c), c.text, c.verdict, reason(c), where(c.source || c.closest, c.label),
      grade(c.source), c.attribution?.claimed || "", attVerdict(c.attribution), c.canonical || "", (c.source || c.closest || {}).url || ""]);
    return "﻿" + [head, ...rows].map(r => r.map(x => `"${String(x).replace(/"/g, '""')}"`).join(",")).join("\r\n");
  }

  const DISCLAIMER = "الكشف آلي بنموذج مُدرَّب، وقد يفوته بعض الأدلة أو يقتطع بعضها؛ إن لم يظهر دليل تبحث عنه فتحقّق منه مباشرة بوضع «دليل واحد».";

  const CSS = `
  .mq-card{background:#fff;border:1px solid var(--mq-line,#E3DED2);border-inline-start:5px solid var(--c);border-radius:12px;padding:14px 16px;margin:0 0 12px;font:15px/1.7 var(--mq-sans,"IBM Plex Sans Arabic",Tahoma,sans-serif);color:#10213F;text-align:right;direction:rtl}
  .mq-card header{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:6px}
  .mq-badge{background:var(--c);color:#fff;border-radius:999px;padding:2px 10px;font-weight:600;font-size:13px}
  .mq-badge.mq-att{background:#B4443A}
  .mq-kind{color:#5A6B85;font-size:13px}
  .mq-chip{border:1px solid #1F8A72;color:#1F8A72;border-radius:999px;padding:1px 8px;font-size:12px;cursor:help}.mq-chip-warn{border-color:#B7791F;color:#7A5212;cursor:default}
  .mq-card blockquote{margin:6px 0;padding:8px 12px;background:var(--bg);border-radius:8px;font-family:var(--mq-serif,Amiri,"Traditional Arabic",serif);font-size:18px;line-height:1.9}
  .mq-card p{margin:6px 0}.mq-card h4{margin:12px 0 4px;font-size:13px;color:#5A6B85;font-weight:600}
  .mq-reason{font-weight:500}.mq-grade{font-size:14px}.mq-weak{color:#B4443A;font-weight:600}
  .mq-attline{font-size:14px}.mq-attline.mq-bad{color:#B4443A}
  .mq-note{font-size:13px;color:#5A6B85}.mq-rel{background:#FBF0DC;color:#7A5212;border-radius:6px;padding:2px 8px}
  .mq-src{font-family:var(--mq-serif,Amiri,serif);font-size:17px;background:#F7F5EF;padding:8px 12px;border-radius:8px}
  .mq-difflist{margin:0;padding-inline-start:18px}.mq-difflist del{background:#F8E4E1;color:#8A2F27}.mq-difflist ins{background:#E3F3EE;color:#14624F;text-decoration:none}
  .mq-rulings{width:100%;border-collapse:collapse;font-size:13px}.mq-rulings th,.mq-rulings td{border-bottom:1px solid #EEE9DD;padding:4px 6px;text-align:right}
  .mq-rulings th{color:#5A6B85;font-weight:600}
  .mq-log{font-size:12px;color:#5A6B85;margin:4px 0;padding-inline-start:18px;word-break:break-word}
  .mq-card details summary{cursor:pointer;color:#1F8A72;font-size:13px;margin-top:6px}
  .mq-card footer{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;margin-top:10px;font-size:13px}
  .mq-card footer a{color:#1F8A72;text-decoration:none;font-weight:600}.mq-card footer a:hover{text-decoration:underline}
  .mq-ask{margin-inline-start:auto;background:#10213F;color:#F7F5EF;border:0;border-radius:8px;padding:6px 12px;font:inherit;font-weight:600;cursor:pointer}
  .mq-ask:hover{background:#1F8A72}
  .mq-ok{--c:#1F8A72;--bg:#E3F3EE}.mq-card.mq-diff{--c:#B7791F;--bg:#FBF0DC}.mq-none{--c:#B4443A;--bg:#F8E4E1}.mq-review{--c:#4C5FA8;--bg:#E7EAF6}
  mark.mq-m-ok{background:#D2EEE5;border-bottom:2px solid #1F8A72}
  mark.mq-m-diff{background:#F8E7C4;border-bottom:2px solid #B7791F}
  mark.mq-m-none{background:#F5D6D2;border-bottom:2px solid #B4443A}
  mark.mq-m-review{background:#DCE1F4;border-bottom:2px solid #4C5FA8}
  mark.mq-m-meta{background:none;border-bottom:1px dashed #8FA3BF;color:inherit}
  mark[class^="mq-m-"]{color:inherit;border-radius:3px;padding:0 1px;cursor:pointer}`;

  globalThis.MQ = { DISCLAIMER, attVerdict, attBad, attUnsure, V, SURAHS, ASK_URL, esc, toAr, quranRef, kind, where, grade, isWeak, reason, card, annotate, askText, csv, CSS };
})();
