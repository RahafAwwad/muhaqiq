// Muhaqiq content script v1.0
//  • auto-colours citations on chat sites (and any page when you press «افحص هذه الصفحة»)
//  • click a coloured quote -> side panel with source, grade, diff, attribution, translations, «اسأل أهل العلم»
//  • right-click results (from background.js) open in the same panel
// render.js (loaded first, see manifest) provides MQ.card / MQ.CSS / MQ.askText.
// TreeWalker: https://developer.mozilla.org/docs/Web/API/Document/createTreeWalker · Shadow DOM: https://developer.mozilla.org/docs/Web/API/Element/attachShadow
console.log("muhaqiq content v1.0");

const AUTO_SITES = /(^|\.)(chatgpt\.com|gemini\.google\.com|x\.com|twitter\.com|claude\.ai|perplexity\.ai)$/;
const SEL = "p, li, blockquote, [data-testid='tweetText']";
const BATCH = 1500;                                        // characters per API call (several paragraphs together)
const cache = new Map();                                   // batch text -> /verify result
const found = new Map();                                   // mark id -> citation
let mode = "general", auto = true, timer = null, nextId = 0, pausedUntil = 0;
const pending = new WeakMap();                             // el -> text seen last tick (wait until streaming stops)

chrome.storage.sync.get({ mode: "general", auto: true }, s => { mode = s.mode; auto = s.auto; start(); });
chrome.storage.onChanged.addListener(c => { if (c.mode) mode = c.mode.newValue; if (c.auto) { auto = c.auto.newValue; start(); } });

function start() {
  clearInterval(timer);
  if (auto && AUTO_SITES.test(location.hostname)) timer = setInterval(() => scan(false), 4000);
}

function ask(text) {                                       // resolves to /verify JSON or null
  return new Promise(res => {
    try {
      chrome.runtime.sendMessage({ type: "verify", text }, r => {
        if (chrome.runtime.lastError || !r || r.error) return res(null);
        res(r);
      });
    } catch (e) { clearInterval(timer); res(null); }       // "Extension context invalidated": this old copy stops quietly
  });
}

function candidates(all) {
  return [...document.querySelectorAll(SEL)].filter(el => {
    const t = el.textContent;
    if (el.dataset.mq || el.closest("#muhaqiq-host") || !/[؀-ۿ]/.test(t) || t.trim().length < 20) return false;
    if (el.querySelector("p, li, blockquote")) return false;          // the inner block will be checked instead
    if (all) return true;
    const stable = pending.get(el) === t; pending.set(el, t);          // chat answers stream in: wait one tick
    return stable;
  });
}

async function scan(all) {
  if (Date.now() < pausedUntil) return;
  const blocks = candidates(all); let batch = [], len = 0;
  if (all && !blocks.length) { panel(`<p class="pn-note">لم نجد نصوصًا عربية جديدة لفحصها في هذه الصفحة.</p>`); return; }
  if (all) panel(loadingHtml(`نفحص ${blocks.length} فقرة…`));
  for (const el of blocks) {
    if (len + el.textContent.length > BATCH && batch.length) { if (!(await send(batch))) break; batch = []; len = 0; }
    batch.push(el); len += el.textContent.length + 2;
  }
  if (batch.length) await send(batch);
  report();
  if (all) panel(summaryHtml(), true);
}

// one API call for several paragraphs joined by blank lines; citations are split back by offset
async function send(batch) {
  const texts = batch.map(el => el.textContent), key = texts.join("\n\n");
  let data = cache.get(key);
  if (!data) {
    data = await ask(key);
    if (!data) { pausedUntil = Date.now() + 30000; console.warn("muhaqiq: API failed, pausing 30 s"); return false; }
    cache.set(key, data);
  }
  let off = 0;
  batch.forEach((el, k) => {
    const t = texts[k];
    const mine = data.citations.filter(c => c.verdict && c.start >= off && c.end <= off + t.length)
                              .map(c => ({ ...c, start: c.start - off, end: c.end - off }));
    if (el.textContent === t) { mine.forEach(c => wrap(el, c)); el.dataset.mq = "done"; }
    off += t.length + 2;
  });
  return true;
}

// wrap characters [c.start, c.end) of el's text in <mark>, across text nodes, without touching links or React's elements
function wrap(el, c) {
  const id = String(nextId++); found.set(id, c);
  const cls = "mq mq-m-" + (MQ.V[c.verdict] || MQ.V["يحتاج مراجعة"]).cls;
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), hits = [];
  let pos = 0, n;
  while ((n = walker.nextNode())) {
    const L = n.data.length;
    if (pos + L > c.start && pos < c.end) hits.push([n, Math.max(c.start - pos, 0), Math.min(c.end - pos, L)]);
    pos += L; if (pos >= c.end) break;
  }
  for (const [node, a, b] of hits) {
    const mid = a > 0 ? node.splitText(a) : node;
    if (b - a < mid.data.length) mid.splitText(b - a);
    const m = document.createElement("mark");
    m.className = cls; m.dataset.mqId = id; m.title = "مُحقِّق: " + c.verdict;
    mid.replaceWith(m); m.appendChild(mid);
  }
}

function report() {
  const all = [...found.values()], bad = all.filter(c => c.verdict !== "مطابق" || MQ.attBad(c.attribution) || MQ.isWeak(c)).length;
  try { chrome.runtime.sendMessage({ type: "count", n: all.length, bad }); } catch (e) {}
}

// ---------- side panel (inside a shadow root so page CSS can't break it) ----------
let host, root;
function panel(html, keep) {
  if (!host) {
    host = document.createElement("div"); host.id = "muhaqiq-host";
    root = host.attachShadow({ mode: "open" });
    document.documentElement.append(host);
    root.addEventListener("click", onPanelClick);
  }
  root.innerHTML = `<style>${MQ.CSS}${PANEL_CSS}</style>
    <aside dir="rtl"><header><img src="${chrome.runtime.getURL("icons/icon48.png")}" alt=""><b>مُحقِّق</b>
      <span class="pn-mode">${mode === "expert" ? "متخصص" : "عام"}</span><button class="pn-x" title="إغلاق">✕</button></header>
      <div class="pn-body">${html}</div>
      <footer>أداة ذكاء اصطناعي: الأحكام من المصادر لا من النموذج؛ ما لم نجده لا نحكم عليه، والمسائل الشخصية تُحال إلى أهل العلم.</footer></aside>`;
  host.style.display = "block";
}
let shown = [];                                            // citations currently in the panel (for «اسأل أهل العلم»)
function cardsHtml(cits) { shown = cits; return cits.map((c, i) => MQ.card(c, mode, i)).join(""); }
const loadingHtml = msg => `<div class="pn-load"><div class="pn-spin"></div><div>${MQ.esc(msg)}<br><small>أول طلب بعد فترة خمول قد يستغرق حتى دقيقة ونصف.</small></div></div>`;

function summaryHtml() {
  const cits = [...found.values()], counts = {};
  cits.forEach(c => counts[c.verdict] = (counts[c.verdict] || 0) + 1);
  if (!cits.length) return `<p class="pn-note">لم نجد آيات أو أحاديث في هذه الصفحة.</p>`;
  return `<div class="pn-sum">${Object.keys(MQ.V).map(v => `<span class="mq-${MQ.V[v].cls}"><b>${MQ.toAr(counts[v] || 0)}</b> ${v}</span>`).join("")}</div>
    <p class="pn-note">انقر على أي اقتباس ملوّن في الصفحة لعرض تفاصيله.<br>${MQ.esc(MQ.DISCLAIMER).replace("بوضع «دليل واحد»", "بتحديده ثم «تحقّق بمُحقِّق»")}</p>${cardsHtml(cits.filter(c => c.verdict !== "مطابق" || MQ.isWeak(c) || MQ.attBad(c.attribution)))}`;
}

function relatedHtml(r) {
  if (!r || r.error) return "";
  if (r.refer) return `<div class="pn-refer"><b>مسألة تتعلق بحالة شخصية</b><p>${MQ.esc(r.note)}</p></div>`;
  const d = r.disagreement;
  return `<h3>أقرب ما وجدنا في المواقع المعتمدة</h3><p class="pn-note">روابط للقراءة، لا حكم من مُحقِّق.</p>
    ${d ? `<p class="pn-refer">ذكر أحد المصادر أن في المسألة خلافًا («${MQ.esc(d.phrase)}») — <a href="${MQ.esc(d.url)}" target="_blank" rel="noopener">${MQ.esc(d.title)}</a></p>` : ""}
    <ul class="pn-links">${r.links.map(l => `<li><a href="${MQ.esc(l.url)}" target="_blank" rel="noopener">${MQ.esc(l.title)}</a><small>${MQ.esc(new URL(l.url).hostname)}</small></li>`).join("") || `<li>${MQ.esc(r.note || "لا نتائج في المواقع المعتمدة.")}</li>`}</ul>`;
}

async function onPanelClick(e) {
  if (e.target.closest(".pn-x")) { host.style.display = "none"; return; }
  const b = e.target.closest("[data-ask]");
  if (b && shown[b.dataset.ask]) {
    try { await navigator.clipboard.writeText(MQ.askText(shown[b.dataset.ask])); b.textContent = "نُسخ السؤال ✓"; } catch (err) {}
    window.open(MQ.ASK_URL, "_blank", "noopener");
  }
}

// click on a coloured quote in the page
document.addEventListener("click", e => {
  const m = e.target.closest && e.target.closest("mark[data-mq-id]");
  if (!m) return;
  e.preventDefault(); e.stopPropagation();
  panel(cardsHtml([found.get(m.dataset.mqId)]));
}, true);

// messages from background (right-click) and popup (scan button)
chrome.runtime.onMessage.addListener(msg => {
  if (msg.type === "scan") scan(true);
  if (msg.type === "loading") panel(loadingHtml("نتحقق من النص المحدد…"));
  if (msg.type === "error") panel(`<p class="pn-err">${msg.error === "timeout" ? "انتهت المهلة؛ جرّب مرة أخرى — الطلب الثاني أسرع." : "تعذّر الاتصال بالخادم: " + MQ.esc(msg.error)}</p>`);
  if (msg.type === "result") {
    const cits = msg.data.citations.filter(c => c.verdict);
    panel((cits.length ? cardsHtml(cits) : `<p class="pn-note">لم نجد آية أو حديثًا في النص المحدد.</p>`) + relatedHtml(msg.data.related));
  }
});

const PANEL_CSS = `
:host{all:initial}
aside{position:fixed;bottom:16px;left:16px;z-index:2147483647;width:min(420px,calc(100vw - 32px));max-height:min(78vh,720px);display:flex;flex-direction:column;
  background:#F7F5EF;border-radius:16px;box-shadow:0 18px 50px rgba(16,33,63,.35);overflow:hidden;font:14px/1.6 "IBM Plex Sans Arabic","Segoe UI",Tahoma,sans-serif;color:#10213F;direction:rtl;text-align:right}
aside>header{display:flex;align-items:center;gap:8px;background:#10213F;color:#F7F5EF;padding:10px 14px}
aside>header img{width:26px;height:26px}aside>header b{font:700 20px Amiri,"Traditional Arabic",serif}
.pn-mode{font-size:11px;background:rgba(95,211,181,.18);color:#5FD3B5;border-radius:999px;padding:1px 8px}
.pn-x{margin-inline-start:auto;background:none;border:0;color:#C9D4E5;font-size:16px;cursor:pointer}
.pn-body{overflow:auto;padding:12px}
aside>footer{font-size:11px;color:#5A6B85;padding:8px 14px;border-top:1px solid #E3DED2;background:#fff}
.pn-load{display:flex;gap:12px;align-items:center;padding:10px;color:#14624F}
.pn-load small{color:#5A6B85}
.pn-spin{width:22px;height:22px;border:3px solid #BFE3D8;border-top-color:#1F8A72;border-radius:50%;animation:s 1s linear infinite;flex:none}
@keyframes s{to{transform:rotate(360deg)}}
.pn-note{color:#5A6B85;margin:4px 0 10px}.pn-err{color:#8A2F27;background:#F8E4E1;padding:10px;border-radius:10px}
.pn-sum{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px}.pn-sum span{background:var(--bg);color:var(--c);border-radius:8px;padding:3px 10px;font-size:13px}.pn-sum .mq-diff{--c:#B7791F;--bg:#FBF0DC}
.pn-refer{background:#FBF0DC;border-radius:10px;padding:10px;margin:6px 0}
h3{font:700 16px Amiri,serif;margin:12px 0 6px}h3 small{font:12px sans-serif;color:#5A6B85}
.pn-links{list-style:none;margin:0;padding:0}.pn-links li{padding:6px 0;border-bottom:1px solid #EEE9DD}
.pn-links a{color:#1F8A72;font-weight:600;text-decoration:none;display:block}.pn-links small{color:#5A6B85}`;
