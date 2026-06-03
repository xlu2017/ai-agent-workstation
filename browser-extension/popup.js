document.getElementById("activate").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  chrome.tabs.sendMessage(tab.id, { type: "ACTIVATE_BRIDGE" });
  document.getElementById("status").textContent = "Bridge active. Click any element.";
});

document.getElementById("deactivate").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  chrome.tabs.sendMessage(tab.id, { type: "DEACTIVATE_BRIDGE" });
  document.getElementById("status").textContent = "Ready.";
});
