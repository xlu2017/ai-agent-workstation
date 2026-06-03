const BRIDGE_URL = "http://localhost:9876";

document.getElementById("inspect").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id) {
    chrome.tabs.sendMessage(tab.id, { type: "ACTIVATE_INSPECT" });
    window.close();
  }
});

document.getElementById("send-selection").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id) {
    chrome.tabs.sendMessage(tab.id, { type: "SEND_SELECTION" });
    window.close();
  }
});

// Check bridge health
async function checkBridge() {
  const statusEl = document.getElementById("status");
  try {
    const resp = await fetch(`${BRIDGE_URL}/health`);
    if (resp.ok) {
      statusEl.textContent = "Bridge service connected";
      statusEl.className = "status connected";
    } else {
      statusEl.textContent = `Bridge error: ${resp.status}`;
      statusEl.className = "status error";
    }
  } catch (e) {
    statusEl.textContent = "Bridge service not running";
    statusEl.className = "status error";
  }

  // Show sessions
  try {
    const resp = await fetch(`${BRIDGE_URL}/sessions`);
    if (resp.ok) {
      const data = await resp.json();
      const infoEl = document.getElementById("session-info");
      infoEl.textContent = `${data.sessions.length} session(s) active`;
    }
  } catch (e) {}
}

checkBridge();
