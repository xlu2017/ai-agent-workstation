const MENU_ID = 'jg-select-component-for-agent-edit';
const DEFAULT_SETTINGS = {
  controlPlaneUrl: 'http://127.0.0.1:9877',
  sessionId: '',
  autoInferSessionId: true,
};

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: MENU_ID,
    title: 'Select component for agent edit',
    contexts: ['page', 'frame', 'selection', 'editable'],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== MENU_ID || !tab?.id) return;
  chrome.tabs.sendMessage(tab.id, { type: 'JG_START_REGION_SELECT' });
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === 'JG_GET_SETTINGS') {
    chrome.storage.sync.get(DEFAULT_SETTINGS, (settings) => sendResponse(settings));
    return true;
  }

  if (message?.type === 'JG_CAPTURE_VISIBLE_TAB') {
    chrome.tabs.captureVisibleTab(sender.tab?.windowId, { format: 'png' }, (dataUrl) => {
      if (chrome.runtime.lastError) {
        sendResponse({ ok: false, error: chrome.runtime.lastError.message });
        return;
      }
      sendResponse({ ok: true, dataUrl });
    });
    return true;
  }

  if (message?.type === 'JG_SUBMIT_REGION_EDIT') {
    submitRegionEdit(message.payload).then(sendResponse).catch((error) => {
      sendResponse({ ok: false, error: String(error?.message || error) });
    });
    return true;
  }
});

async function getSettings() {
  return await chrome.storage.sync.get(DEFAULT_SETTINGS);
}

function inferSessionId(payload, settings) {
  if (payload.sessionId) return payload.sessionId;
  if (settings.sessionId) return settings.sessionId;
  if (!settings.autoInferSessionId) return '';
  const url = payload.page?.url || '';
  const match = url.match(/\/session\/([^/?#]+)/);
  return match ? decodeURIComponent(match[1]) : '';
}

function buildInstruction(payload, ambientEventId) {
  const selected = payload.selection || {};
  const elements = Array.isArray(selected.elements) ? selected.elements : [];
  const lines = [];
  lines.push('Browser-selected frontend edit request.');
  lines.push('');
  lines.push(`User request: ${payload.prompt}`);
  lines.push(`Page: ${payload.page?.title || ''} ${payload.page?.url || ''}`.trim());
  lines.push(`Selection mode: ${selected.mode || 'drag_region'}`);
  if (selected.bounds) lines.push(`Region bounds: ${JSON.stringify(selected.bounds)}`);
  if (ambientEventId) lines.push(`Ambient evidence id: ${ambientEventId}`);
  lines.push('');
  if (elements.length) {
    lines.push('Selected DOM/component targets:');
    for (const element of elements.slice(0, 20)) {
      lines.push(`- selector=${element.selector || ''}; tag=${element.tagName || ''}; text=${truncate(element.text || '', 160)}; framework=${element.framework || 'unknown'}; source=${element.sourceHint || ''}`);
    }
  } else {
    lines.push('No identifiable DOM/component targets were selected. Use the screenshot fallback evidence and region bounds to locate the intended UI area.');
  }
  return lines.filter(Boolean).join('\n');
}

async function submitRegionEdit(payload) {
  const settings = await getSettings();
  const controlPlaneUrl = String(settings.controlPlaneUrl || DEFAULT_SETTINGS.controlPlaneUrl).replace(/\/$/, '');
  const sessionId = inferSessionId(payload, settings);
  if (!sessionId) return { ok: false, error: 'No session id configured or inferable from the page URL.' };

  const ambientEvent = {
    event_type: payload.selection?.elements?.length ? 'browser.element_selected' : 'screenshot.fallback_captured',
    session_id: sessionId,
    source: payload.selection?.elements?.length ? 'browser' : 'screenshot_fallback',
    actor: 'user',
    confidence: payload.selection?.elements?.length ? 0.9 : 0.45,
    payload: {
      page: payload.page,
      selection: payload.selection,
      screenshot_fallback: payload.screenshotFallback || null,
      source: 'chrome_extension.region_prompt',
    },
  };

  let ambientEventId = '';
  try {
    const ambientRes = await fetch(`${controlPlaneUrl}/api/sessions/${encodeURIComponent(sessionId)}/ambient/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ambientEvent),
    });
    if (ambientRes.ok) {
      const ambientJson = await ambientRes.json();
      ambientEventId = ambientJson?.event?.event_id || '';
    }
  } catch (_) {
    // The chat submit remains useful even if the ambient router is not mounted yet.
  }

  const instruction = buildInstruction(payload, ambientEventId);
  const chatRes = await fetch(`${controlPlaneUrl}/api/sessions/${encodeURIComponent(sessionId)}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ instruction, execution_mode: 'finite' }),
  });
  const chatJson = await chatRes.json().catch(() => ({}));
  if (!chatRes.ok) {
    return { ok: false, error: chatJson?.error || chatRes.statusText, sessionId, ambientEventId };
  }
  return { ok: true, sessionId, ambientEventId, chat: chatJson };
}

function truncate(value, max) {
  return value.length > max ? value.slice(0, max - 1) + '…' : value;
}
