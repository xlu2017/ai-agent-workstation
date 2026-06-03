/**
 * UI-to-Code Bridge — Background Service Worker
 *
 * Receives element selection events from content script.
 * Phase 1: Logs metadata and forwards to ui-bridge-service.
 * Future: Resolves source maps to exact file:line.
 */

const BRIDGE_SERVICE_URL = "http://localhost:9876";

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "ELEMENT_SELECTED") {
    console.log("[UI-Bridge Background] Element selected:", msg.payload);

    // Forward to bridge service for source map resolution
    fetch(`${BRIDGE_SERVICE_URL}/api/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(msg.payload),
    })
      .then((r) => r.json())
      .then((result) => {
        console.log("[UI-Bridge Background] Resolution:", result);
        // Future: Open file in editor, send to agent context
      })
      .catch((err) => {
        console.warn("[UI-Bridge Background] Service unavailable:", err.message);
      });
  }
});
