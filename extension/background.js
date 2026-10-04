// Muhaqiq background worker v0.3 — makes the API call on behalf of content scripts (not bound by page CSP).
// Docs: https://developer.chrome.com/docs/extensions/develop/concepts/messaging
const API = "https://rahafawwad--muhaqiq-span-detector-web.modal.run/spans";

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  fetch(API, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: msg.text }) })
    .then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(spans => { console.log("muhaqiq api ok", spans.length); reply(spans); })
    .catch(e => { console.warn("muhaqiq api error", e.message); reply({ error: e.message }); });
  return true;                                           // keep the message channel open for the async reply
});