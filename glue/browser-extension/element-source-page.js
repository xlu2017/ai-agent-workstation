/**
 * Page-context script that uses element-source to resolve DOM elements.
 * This runs in the MAIN world (page context) to access React fibers.
 * Injected by the content script.
 *
 * When loaded, it listens for __UI_BRIDGE_RESOLVE_SOURCE messages
 * and responds with __UI_BRIDGE_SOURCE_RESULT.
 */

(function() {
  // element-source exposes resolveElementInfo on window when loaded as global
  // Wait for it to be available
  function waitForElementSource(callback, retries) {
    if (retries <= 0) {
      callback(null);
      return;
    }
    if (window.ElementSource && window.ElementSource.resolveElementInfo) {
      callback(window.ElementSource);
      return;
    }
    setTimeout(() => waitForElementSource(callback, retries - 1), 50);
  }

  window.addEventListener("message", async (event) => {
    if (event.source !== window) return;
    if (event.data?.type !== "__UI_BRIDGE_RESOLVE_SOURCE") return;

    const selector = event.data.selector;
    if (!selector) return;

    let element;
    try {
      element = document.querySelector(selector);
    } catch (e) {
      element = null;
    }

    if (!element) {
      window.postMessage({
        type: "__UI_BRIDGE_SOURCE_RESULT",
        payload: { framework: "", componentName: null, source: null, stack: [] },
      }, "*");
      return;
    }

    waitForElementSource(async (lib) => {
      if (!lib) {
        // Fallback: try to read React fiber directly
        const result = fallbackResolve(element);
        window.postMessage({ type: "__UI_BRIDGE_SOURCE_RESULT", payload: result }, "*");
        return;
      }

      try {
        const info = await lib.resolveElementInfo(element);
        window.postMessage({
          type: "__UI_BRIDGE_SOURCE_RESULT",
          payload: {
            framework: detectFramework(),
            componentName: info.componentName,
            source: info.source,
            stack: info.stack || [],
          },
        }, "*");
      } catch (err) {
        const result = fallbackResolve(element);
        window.postMessage({ type: "__UI_BRIDGE_SOURCE_RESULT", payload: result }, "*");
      }
    }, 10);
  });

  function fallbackResolve(element) {
    // Try React fiber directly
    const fiberKey = Object.keys(element).find(k => k.startsWith("__reactFiber$") || k.startsWith("__reactInternalInstance$"));
    if (fiberKey) {
      const fiber = element[fiberKey];
      const source = fiber?._debugSource;
      const name = getComponentName(fiber);
      return {
        framework: "react",
        componentName: name,
        source: source ? { filePath: source.fileName, lineNumber: source.lineNumber, columnNumber: source.columnNumber, componentName: name } : null,
        stack: [],
      };
    }

    // Try Vue
    if (element.__vue_app__ || element.__vueParentComponent) {
      return { framework: "vue", componentName: null, source: null, stack: [] };
    }

    return { framework: "", componentName: null, source: null, stack: [] };
  }

  function getComponentName(fiber) {
    if (!fiber) return null;
    let current = fiber;
    while (current) {
      if (current.type && typeof current.type === "function") {
        return current.type.displayName || current.type.name || null;
      }
      if (current.type && typeof current.type === "object" && current.type.render) {
        return current.type.render.displayName || current.type.render.name || null;
      }
      current = current.return;
    }
    return null;
  }

  function detectFramework() {
    if (document.querySelector("[data-reactroot]") || document.getElementById("__next")) return "react";
    if (window.__VUE_DEVTOOLS_GLOBAL_HOOK__) return "vue";
    if (document.querySelector("[data-svelte-h]")) return "svelte";
    return "";
  }
})();
