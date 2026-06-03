/**
 * UI-to-Code Bridge — Content Script
 *
 * Injects element selection overlay into the page.
 * When user clicks an element while bridge is active:
 * 1. Captures element metadata (tag, classes, React fiber, data attributes)
 * 2. Sends to background script for source map resolution
 *
 * Phase 1: Scaffolding only — captures element info, does not resolve source maps yet.
 */

let bridgeActive = false;
let overlay = null;

function createOverlay() {
  overlay = document.createElement("div");
  overlay.id = "ui-bridge-overlay";
  overlay.style.cssText = `
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    z-index: 999999; cursor: crosshair; pointer-events: all;
  `;
  document.body.appendChild(overlay);
}

function removeOverlay() {
  if (overlay) {
    overlay.remove();
    overlay = null;
  }
}

function getReactFiber(element) {
  // Attempt to find React fiber node for component identification
  const key = Object.keys(element).find(
    (k) => k.startsWith("__reactFiber$") || k.startsWith("__reactInternalInstance$")
  );
  if (!key) return null;

  const fiber = element[key];
  return {
    type: fiber?.type?.name || fiber?.type?.displayName || null,
    source: fiber?._debugSource || null,
    owner: fiber?._debugOwner?.type?.name || null,
  };
}

function getElementMetadata(element) {
  const rect = element.getBoundingClientRect();
  const fiber = getReactFiber(element);

  return {
    tag: element.tagName.toLowerCase(),
    id: element.id || null,
    classes: Array.from(element.classList),
    dataAttributes: Object.fromEntries(
      Array.from(element.attributes)
        .filter((a) => a.name.startsWith("data-"))
        .map((a) => [a.name, a.value])
    ),
    text: element.textContent?.slice(0, 100) || null,
    rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
    react: fiber,
    xpath: getXPath(element),
  };
}

function getXPath(element) {
  if (!element.parentElement) return "/" + element.tagName.toLowerCase();
  const siblings = Array.from(element.parentElement.children).filter(
    (e) => e.tagName === element.tagName
  );
  const index = siblings.indexOf(element) + 1;
  const suffix = siblings.length > 1 ? `[${index}]` : "";
  return getXPath(element.parentElement) + "/" + element.tagName.toLowerCase() + suffix;
}

// Listen for activation message from popup/background
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "ACTIVATE_BRIDGE") {
    bridgeActive = true;
    createOverlay();
    overlay.addEventListener("click", handleClick);
    sendResponse({ status: "activated" });
  } else if (msg.type === "DEACTIVATE_BRIDGE") {
    bridgeActive = false;
    removeOverlay();
    sendResponse({ status: "deactivated" });
  }
});

function handleClick(event) {
  event.preventDefault();
  event.stopPropagation();

  // Temporarily hide overlay to get the actual element underneath
  overlay.style.pointerEvents = "none";
  const element = document.elementFromPoint(event.clientX, event.clientY);
  overlay.style.pointerEvents = "all";

  if (!element) return;

  const metadata = getElementMetadata(element);
  console.log("[UI-Bridge] Selected element:", metadata);

  // Send to background script for source map resolution
  chrome.runtime.sendMessage({
    type: "ELEMENT_SELECTED",
    payload: metadata,
  });

  // Deactivate after selection
  bridgeActive = false;
  removeOverlay();
}
