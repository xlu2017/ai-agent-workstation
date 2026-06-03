/**
 * Content script for AI Agent UI Bridge.
 *
 * Responsibilities:
 * - Inject element-source library into the page
 * - Listen for selection and inspection requests
 * - Capture element metadata and source information
 * - Send events to the background service worker
 */

const BRIDGE_SERVICE_URL = "http://localhost:9876";

let inspectMode = false;
let overlay = null;

// --- Element Source Resolution ---
// element-source resolves DOM elements to source file locations.
// We inject it into the page context to access React fiber data.

function injectElementSource() {
  if (document.getElementById("__element_source_injected")) return;

  // Inject element-source library
  const libScript = document.createElement("script");
  libScript.id = "__element_source_injected";
  libScript.src = chrome.runtime.getURL("element-source.global.js");
  (document.head || document.documentElement).appendChild(libScript);

  // Inject page-context resolver script
  const resolverScript = document.createElement("script");
  resolverScript.src = chrome.runtime.getURL("element-source-page.js");
  libScript.onload = () => {
    (document.head || document.documentElement).appendChild(resolverScript);
  };
}

// Listen for resolved source data from page context
window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  if (event.data?.type === "__UI_BRIDGE_SOURCE_RESULT") {
    handleSourceResult(event.data.payload);
  }
});

function requestSourceResolution(element) {
  // Generate a unique selector for the element
  const selector = getUniqueSelector(element);

  // Post to page context where element-source runs
  window.postMessage({
    type: "__UI_BRIDGE_RESOLVE_SOURCE",
    selector: selector,
  }, "*");

  // Return basic metadata immediately; source will arrive async
  return getElementMetadata(element);
}

// --- Element Metadata Capture ---

function getElementMetadata(element) {
  return {
    tag: element.tagName.toLowerCase(),
    id: element.id || "",
    class: element.className || "",
    attributes: getRelevantAttributes(element),
    text_content: (element.textContent || "").trim().slice(0, 200),
    xpath: getXPath(element),
  };
}

function getRelevantAttributes(element) {
  const attrs = {};
  const relevant = ["data-testid", "role", "aria-label", "href", "src", "name", "placeholder", "type", "value"];
  for (const name of relevant) {
    const val = element.getAttribute(name);
    if (val) attrs[name] = val;
  }
  return attrs;
}

function getXPath(element) {
  if (!element || element.nodeType !== 1) return "";
  const parts = [];
  let current = element;
  while (current && current.nodeType === 1) {
    let index = 1;
    let sibling = current.previousElementSibling;
    while (sibling) {
      if (sibling.tagName === current.tagName) index++;
      sibling = sibling.previousElementSibling;
    }
    parts.unshift(`${current.tagName.toLowerCase()}[${index}]`);
    current = current.parentElement;
  }
  return "/" + parts.join("/");
}

function getUniqueSelector(element) {
  if (element.id) return `#${element.id}`;
  const path = [];
  let el = element;
  while (el && el.nodeType === 1) {
    let selector = el.tagName.toLowerCase();
    if (el.id) {
      path.unshift(`#${el.id}`);
      break;
    }
    let index = 1;
    let sib = el.previousElementSibling;
    while (sib) {
      if (sib.tagName === el.tagName) index++;
      sib = sib.previousElementSibling;
    }
    if (index > 1) selector += `:nth-of-type(${index})`;
    path.unshift(selector);
    el = el.parentElement;
  }
  return path.join(" > ");
}

// --- Source Result Handler ---

let pendingEvent = null;

function handleSourceResult(payload) {
  if (!pendingEvent) return;

  const event = pendingEvent;
  pendingEvent = null;

  event.source = {
    framework: payload.framework || "",
    component: payload.componentName || null,
    file: payload.source?.filePath || null,
    line: payload.source?.lineNumber || null,
    column: payload.source?.columnNumber || null,
    confidence: payload.source?.filePath ? "high" : (payload.componentName ? "medium" : "low"),
    stack: payload.stack || [],
  };

  sendEventToBridge(event);
}

// Fallback: if no source result arrives in 500ms, send without it
function scheduleEventFallback(event) {
  pendingEvent = event;
  setTimeout(() => {
    if (pendingEvent === event) {
      pendingEvent = null;
      event.source = { framework: "", component: null, file: null, line: null, column: null, confidence: "low", stack: [] };
      sendEventToBridge(event);
    }
  }, 500);
}

// --- Event Sending ---

function sendEventToBridge(event) {
  // Send to background worker for forwarding to bridge service
  chrome.runtime.sendMessage({ type: "UI_BRIDGE_EVENT", payload: event });
}

// --- Inspect Mode (Overlay) ---

function enableInspectMode() {
  inspectMode = true;
  overlay = document.createElement("div");
  overlay.id = "__ui_bridge_overlay";
  overlay.style.cssText = "position:fixed;top:0;left:0;width:100%;height:100%;z-index:2147483647;cursor:crosshair;";
  document.body.appendChild(overlay);

  overlay.addEventListener("mousemove", onOverlayMove);
  overlay.addEventListener("click", onOverlayClick);
  overlay.addEventListener("keydown", onOverlayKey);
  overlay.tabIndex = 0;
  overlay.focus();
}

function disableInspectMode() {
  inspectMode = false;
  if (overlay) {
    overlay.remove();
    overlay = null;
  }
  removeHighlight();
}

let highlightBox = null;

function highlightElement(element) {
  removeHighlight();
  const rect = element.getBoundingClientRect();
  highlightBox = document.createElement("div");
  highlightBox.id = "__ui_bridge_highlight";
  highlightBox.style.cssText = `position:fixed;top:${rect.top}px;left:${rect.left}px;width:${rect.width}px;height:${rect.height}px;border:2px solid #4f46e5;background:rgba(79,70,229,0.1);pointer-events:none;z-index:2147483646;border-radius:2px;`;
  document.body.appendChild(highlightBox);
}

function removeHighlight() {
  if (highlightBox) {
    highlightBox.remove();
    highlightBox = null;
  }
}

function onOverlayMove(e) {
  const underneath = document.elementFromPoint(e.clientX, e.clientY);
  if (underneath && underneath !== overlay && underneath !== highlightBox) {
    highlightElement(underneath);
  }
}

function onOverlayClick(e) {
  e.preventDefault();
  e.stopPropagation();
  disableInspectMode();

  const element = document.elementFromPoint(e.clientX, e.clientY);
  if (!element) return;

  const metadata = getElementMetadata(element);
  const event = {
    type: "inspect",
    session_id: getCurrentSessionId(),
    url: window.location.href,
    selected_text: "",
    element: metadata,
    source: {},
    timestamp: new Date().toISOString(),
  };

  // Request source resolution
  requestSourceResolution(element);
  scheduleEventFallback(event);
}

function onOverlayKey(e) {
  if (e.key === "Escape") {
    disableInspectMode();
  }
}

// --- Selection Handler ---

function handleSelection() {
  const selection = window.getSelection();
  const selectedText = selection ? selection.toString().trim() : "";
  if (!selectedText) return;

  const anchorNode = selection.anchorNode;
  const element = anchorNode?.nodeType === 1 ? anchorNode : anchorNode?.parentElement;
  if (!element) return;

  const metadata = getElementMetadata(element);
  const event = {
    type: "selection",
    session_id: getCurrentSessionId(),
    url: window.location.href,
    selected_text: selectedText,
    element: metadata,
    source: {},
    timestamp: new Date().toISOString(),
  };

  requestSourceResolution(element);
  scheduleEventFallback(event);
}

// --- Session ID ---

function getCurrentSessionId() {
  // Try to detect session from URL port mapping
  const port = window.location.port;
  return `session-port-${port || "default"}`;
}

// --- Message Handlers ---

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "ACTIVATE_INSPECT") {
    enableInspectMode();
    sendResponse({ status: "ok" });
  } else if (message.type === "SEND_SELECTION") {
    handleSelection();
    sendResponse({ status: "ok" });
  } else if (message.type === "SET_SESSION_ID") {
    // Future: override session ID
    sendResponse({ status: "ok" });
  }
  return true;
});

// Inject element-source on load
injectElementSource();
