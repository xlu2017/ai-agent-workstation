(() => {
  let overlay = null;
  let box = null;
  let start = null;
  let region = null;
  let targets = [];

  chrome.runtime.onMessage.addListener((message) => {
    if (message && message.type === 'JG_START_REGION_SELECT') beginSelection();
  });

  function beginSelection() {
    cleanup();
    overlay = document.createElement('div');
    overlay.className = 'jg-region-overlay';
    overlay.innerHTML = '<div class="jg-region-help">Drag to select UI. Release to confirm.</div>';
    document.documentElement.appendChild(overlay);
    window.addEventListener('pointerdown', onPointerDown, true);
    window.addEventListener('keydown', onKeyDown, true);
  }

  function onPointerDown(event) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    start = { x: event.clientX, y: event.clientY };
    box = document.createElement('div');
    box.className = 'jg-region-box';
    overlay.appendChild(box);
    window.addEventListener('pointermove', onPointerMove, true);
    window.addEventListener('pointerup', onPointerUp, true);
  }

  function onPointerMove(event) {
    if (!box || !start) return;
    event.preventDefault();
    region = toRect(start.x, start.y, event.clientX, event.clientY);
    draw(box, region);
  }

  function onPointerUp(event) {
    event.preventDefault();
    event.stopPropagation();
    window.removeEventListener('pointermove', onPointerMove, true);
    window.removeEventListener('pointerup', onPointerUp, true);
    region = toRect(start.x, start.y, event.clientX, event.clientY);
    if (region.width < 8 || region.height < 8) return cleanup();
    targets = findTargets(region);
    highlightTargets(targets);
    showConfirm();
  }

  function onKeyDown(event) {
    if (event.key === 'Escape') cleanup();
  }

  function showConfirm() {
    const panel = document.createElement('div');
    panel.className = 'jg-region-confirm';
    const title = targets.length ? targets.length + ' target(s) selected' : 'No DOM target found';
    const body = targets.length ? 'Confirm selected region.' : 'Confirm screenshot fallback for this region.';
    panel.innerHTML = '<strong>' + title + '</strong><span>' + body + '</span><div><button data-jg="cancel">Cancel</button><button data-jg="ok">Confirm</button></div>';
    document.documentElement.appendChild(panel);
    place(panel, region);
    panel.querySelector('[data-jg="cancel"]').onclick = cleanup;
    panel.querySelector('[data-jg="ok"]').onclick = () => { panel.remove(); showPromptPanel(); };
  }

  function showPromptPanel() {
    const panel = document.createElement('div');
    panel.className = 'jg-prompt-dialog';
    const meta = targets.length ? 'DOM context attached' : 'Screenshot fallback will be attached';
    panel.innerHTML = '<strong>Ask agent to edit selected UI</strong><textarea placeholder="Describe the change. Enter sends, Shift+Enter newline."></textarea><small>' + meta + '</small><div><button data-jg="cancel">Cancel</button><button data-jg="send">Send</button></div>';
    document.documentElement.appendChild(panel);
    place(panel, region);
    const textarea = panel.querySelector('textarea');
    const send = () => submitSelection(textarea.value, panel);
    panel.querySelector('[data-jg="cancel"]').onclick = cleanup;
    panel.querySelector('[data-jg="send"]').onclick = send;
    textarea.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); send(); }
    });
    textarea.focus();
  }

  async function submitSelection(value, panel) {
    const text = String(value || '').trim();
    if (!text) return;
    panel.classList.add('jg-busy');
    const fallback = targets.length ? null : await requestFallbackImage();
    const payload = {
      sessionId: inferSessionId(),
      prompt: text,
      page: { url: location.href, title: document.title },
      selection: { mode: 'drag_region', bounds: region, elements: targets.map(describeTarget) },
      screenshotFallback: fallback,
    };
    chrome.runtime.sendMessage({ type: 'JG_SUBMIT_REGION_EDIT', payload }, (response) => {
      panel.classList.remove('jg-busy');
      if (!response || !response.ok) {
        const note = panel.querySelector('small');
        if (note) note.textContent = response && response.error ? response.error : 'Submit failed';
        panel.classList.add('jg-error');
        return;
      }
      panel.innerHTML = '<strong>Sent to session</strong><small>' + (response.sessionId || '') + '</small>';
      setTimeout(cleanup, 1200);
    });
  }

  async function requestFallbackImage() {
    const result = await chrome.runtime.sendMessage({ type: 'JG_CAPTURE_VISIBLE_TAB' });
    return { available: !!(result && result.ok), kind: 'visible_tab_png', dataUrl: result && result.ok ? result.dataUrl : '', bounds: region };
  }

  function findTargets(r) {
    return Array.from(document.body.querySelectorAll('*')).filter((el) => {
      if (el.closest('.jg-region-overlay,.jg-region-confirm,.jg-prompt-dialog')) return false;
      const b = el.getBoundingClientRect();
      if (b.width < 4 || b.height < 4) return false;
      if (!intersects(r, b)) return false;
      return useful(el);
    }).slice(0, 30);
  }

  function useful(el) {
    const tag = el.tagName.toLowerCase();
    if (['html', 'body', 'script', 'style', 'head', 'meta', 'link'].includes(tag)) return false;
    return el.id || el.getAttribute('data-testid') || el.getAttribute('data-test') || el.getAttribute('role') || el.children.length === 0 || el.matches('button,a,input,textarea,select,label,form,section,article,nav,header,main,footer,[class]');
  }

  function describeTarget(el) {
    const b = el.getBoundingClientRect();
    return { tagName: el.tagName.toLowerCase(), selector: selectorFor(el), text: String(el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 500), role: el.getAttribute('role') || '', testId: el.getAttribute('data-testid') || el.getAttribute('data-test') || '', id: el.id || '', className: typeof el.className === 'string' ? el.className : '', bounds: { x: b.left, y: b.top, width: b.width, height: b.height }, framework: frameworkName(el) };
  }

  function frameworkName(el) {
    for (const key of Object.keys(el)) if (key.indexOf('__reactFiber$') === 0 || key.indexOf('__reactInternalInstance$') === 0) return 'react';
    if (el.__vueParentComponent) return 'vue';
    if (el.__ngContext__) return 'angular';
    return 'unknown';
  }

  function selectorFor(el) {
    if (el.id) return '#' + CSS.escape(el.id);
    const testId = el.getAttribute('data-testid') || el.getAttribute('data-test');
    if (testId) return '[data-testid="' + String(testId).replace(/"/g, '\\"') + '"]';
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && parts.length < 5) { parts.unshift(cur.tagName.toLowerCase()); cur = cur.parentElement; }
    return parts.join(' > ');
  }

  function highlightTargets(elements) { elements.forEach((el) => { const b = el.getBoundingClientRect(); const mark = document.createElement('div'); mark.className = 'jg-element-highlight'; draw(mark, { x: b.left, y: b.top, width: b.width, height: b.height }); overlay.appendChild(mark); }); }
  function toRect(x1, y1, x2, y2) { return { x: Math.min(x1, x2), y: Math.min(y1, y2), width: Math.abs(x2 - x1), height: Math.abs(y2 - y1) }; }
  function draw(node, r) { node.style.left = r.x + 'px'; node.style.top = r.y + 'px'; node.style.width = r.width + 'px'; node.style.height = r.height + 'px'; }
  function intersects(a, b) { return !(b.left > a.x + a.width || b.right < a.x || b.top > a.y + a.height || b.bottom < a.y); }
  function place(node, r) { node.style.left = Math.max(12, Math.min(innerWidth - 360, r.x)) + 'px'; node.style.top = Math.max(12, Math.min(innerHeight - 190, r.y + r.height + 12)) + 'px'; }
  function inferSessionId() { const m = location.href.match(/\/session\/([^/?#]+)/); return m ? decodeURIComponent(m[1]) : ''; }
  function cleanup() { window.removeEventListener('pointerdown', onPointerDown, true); window.removeEventListener('pointermove', onPointerMove, true); window.removeEventListener('pointerup', onPointerUp, true); window.removeEventListener('keydown', onKeyDown, true); document.querySelectorAll('.jg-region-overlay,.jg-region-confirm,.jg-prompt-dialog').forEach((n) => n.remove()); overlay = null; box = null; start = null; region = null; targets = []; }
})();
