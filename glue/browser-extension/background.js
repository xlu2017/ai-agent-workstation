/**
 * Background service worker for AI Agent UI Bridge.
 *
 * Responsibilities:
 * - Forward events from content script to UI bridge service
 * - Manage context menu items
 * - Track active session
 */

const BRIDGE_URL = "http://localhost:9876";

// --- Context Menu Setup ---

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "send-selection-to-agent",
    title: "Send selection to agent",
    contexts: ["selection"],
  });

  chrome.contextMenus.create({
    id: "inspect-element-for-agent",
    title: "Inspect element for agent",
    contexts: ["all"],
  });
});

// --- Context Menu Handlers ---

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (!tab?.id) return;

  if (info.menuItemId === "send-selection-to-agent") {
    chrome.tabs.sendMessage(tab.id, { type: "SEND_SELECTION" });
  } else if (info.menuItemId === "inspect-element-for-agent") {
    chrome.tabs.sendMessage(tab.id, { type: "ACTIVATE_INSPECT" });
  }
});

// --- Event Forwarding ---

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "UI_BRIDGE_EVENT") {
    forwardToBridge(message.payload)
      .then((result) => sendResponse({ status: "ok", result }))
      .catch((error) => sendResponse({ status: "error", error: error.message }));
    return true; // Keep message channel open for async response
  }
});

async function forwardToBridge(event) {
  const endpoint = event.type === "inspect" ? "/inspect" : "/selection";
  try {
    const response = await fetch(`${BRIDGE_URL}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(event),
    });
    if (!response.ok) {
      console.warn(`Bridge responded ${response.status}`);
      return { forwarded: false, status: response.status };
    }
    return await response.json();
  } catch (error) {
    console.warn("Bridge service unavailable:", error.message);
    return { forwarded: false, error: error.message };
  }
}
