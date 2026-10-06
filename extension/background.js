// Muhaqiq background worker v1.0 — the only place that talks to the API (pages' CSP can block content-script fetches).
// Also owns the right-click menu and the toolbar badge.
// Docs: messaging https://developer.chrome.com/docs/extensions/develop/concepts/messaging
//       contextMenus https://developer.chrome.com/docs/extensions/reference/api/contextMenus
//       badge https://developer.chrome.com/docs/extensions/reference/api/action#method-setBadgeText
const API = "https://rahafawwad--muhaqiq-span-detector-web.modal.run/verify";
const TIMEOUT = 150000;                                    // first call after idle may wake ALLaM on the GPU (~90 s)

async function verify(body) {
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), TIMEOUT);
  try {
    const r = await fetch(API, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: ctl.signal });
    if (!r.ok) throw new Error("HTTP " + r.status);
    return await r.json();
  } finally { clearTimeout(t); }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: "verify", title: "تحقّق بمُحقِّق", contexts: ["selection"] });
  chrome.contextMenus.create({ id: "related", title: "مصادر موثوقة لهذا السؤال (مُحقِّق)", contexts: ["selection"] });
  chrome.storage.sync.get({ mode: "general", auto: true }, s => chrome.storage.sync.set(s));
});

// right-click on selected text: verify it (and, for "related", treat it as a question too) and show the panel in that tab
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const text = info.selectionText || "", send = m => chrome.tabs.sendMessage(tab.id, m).catch(() => {});
  send({ type: "loading", text });
  try {
    const data = await verify(info.menuItemId === "related" ? { text, question: text } : { text, single: true });   // a selection = one quote
    send({ type: "result", text, data });
  } catch (e) { send({ type: "error", error: e.name === "AbortError" ? "timeout" : e.message }); }
});

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg.type === "verify") {                             // from content.js: one batch of page text
    verify({ text: msg.text })
      .then(d => { console.log("muhaqiq ok", d.citations.length); reply(d); })
      .catch(e => { console.warn("muhaqiq api error", e.message); reply({ error: e.message }); });
    return true;                                           // keep the channel open for the async reply
  }
  if (msg.type === "count" && sender.tab) {                // badge: number of citations found; red if any needs attention
    chrome.action.setBadgeText({ tabId: sender.tab.id, text: msg.n ? String(msg.n) : "" });
    chrome.action.setBadgeBackgroundColor({ tabId: sender.tab.id, color: msg.bad ? "#B4443A" : "#1F8A72" });
  }
});
