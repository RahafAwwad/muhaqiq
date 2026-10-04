// Muhaqiq content script v0.5 — finds Arabic blocks, asks background.js for spans, wraps them in <mark>.
// Messaging docs: https://developer.chrome.com/docs/extensions/develop/concepts/messaging
console.log("muhaqiq content v0.5");

const seen = new Map();                                  // text -> spans (empty results are cached too)
let timer;                                               // the 4-second loop; stopped if the extension is reloaded

function detect(text) {                                  // resolves to an array, or null if the call failed
  return new Promise(res => {
    try {
      chrome.runtime.sendMessage({ text }, r => {
        if (chrome.runtime.lastError) { console.warn("muhaqiq bg:", chrome.runtime.lastError.message); return res(null); }
        res(Array.isArray(r) ? r : null);
      });
    } catch (e) { clearInterval(timer); res(null); }    // "Extension context invalidated": this old copy stops quietly
  });
}

async function detectCached(text) {
  if (seen.has(text)) return seen.get(text);
  const spans = await detect(text);
  if (spans) seen.set(text, spans); else console.warn("muhaqiq: call failed, will retry");
  return spans || [];
}

function highlight(el, spans) {                          // v0: block becomes plain text + marks
  const text = el.textContent; let html = "", i = 0;
  for (const s of [...spans].sort((a, b) => a.start - b.start)) {
    html += text.slice(i, s.start) + `<mark class="mq mq-${s.label}" title="${s.label} ${s.score}">${text.slice(s.start, s.end)}</mark>`;
    i = s.end;
  }
  el.innerHTML = html + text.slice(i);
}

async function run() {
  const blocks = [...document.querySelectorAll("p, li, [data-testid='tweetText']")]
      .filter(el => /[؀-ۿ]/.test(el.textContent) && el.textContent.length > 20
                    && !el.querySelector("mark.mq") && !el.dataset.busy);
  for (const el of blocks) {
    el.dataset.busy = "1";
    const spans = await detectCached(el.textContent);
    if (spans.length) { highlight(el, spans); console.log("muhaqiq marked", spans.length); }
    delete el.dataset.busy;
  }
}

timer = setInterval(run, 4000);