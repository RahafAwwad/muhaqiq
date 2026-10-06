// Muhaqiq popup: settings live in chrome.storage.sync, content.js listens for changes.
// Docs: https://developer.chrome.com/docs/extensions/reference/api/storage · https://developer.chrome.com/docs/extensions/reference/api/tabs#method-sendMessage
const seg = document.querySelectorAll(".seg button"), auto = document.getElementById("auto");

chrome.storage.sync.get({ mode: "general", auto: true }, s => {
  seg.forEach(b => b.classList.toggle("on", b.dataset.mode === s.mode));
  auto.checked = s.auto;
});
seg.forEach(b => b.onclick = () => {
  chrome.storage.sync.set({ mode: b.dataset.mode });
  seg.forEach(x => x.classList.toggle("on", x === b));
});
auto.onchange = () => chrome.storage.sync.set({ auto: auto.checked });

document.getElementById("scan").onclick = async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  chrome.tabs.sendMessage(tab.id, { type: "scan" }).catch(() => alert("لا يمكن فحص هذه الصفحة (صفحات المتصفح الداخلية) — أعد تحميل الصفحة ثم جرّب."));
  window.close();
};
