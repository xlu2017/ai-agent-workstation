const JG_HISTORY_KEY = 'jgRegionEditHistory';
const JG_HISTORY_LIMIT = 40;

async function jgReadHistory() {
  const result = await chrome.storage.local.get({ [JG_HISTORY_KEY]: [] });
  return Array.isArray(result[JG_HISTORY_KEY]) ? result[JG_HISTORY_KEY] : [];
}

async function jgWriteHistory(history) {
  const trimmed = history.slice(0, JG_HISTORY_LIMIT);
  await chrome.storage.local.set({ [JG_HISTORY_KEY]: trimmed });
  return trimmed;
}

async function jgRecordRegionEdit(entry) {
  const history = await jgReadHistory();
  const item = {
    id: entry.id || `region_${Date.now()}`,
    createdAt: entry.createdAt || new Date().toISOString(),
    sessionId: entry.sessionId || '',
    page: entry.page || {},
    selection: sanitizeSelectionForHistory(entry.selection || {}),
    prompt: entry.prompt || '',
    ambientEventId: entry.ambientEventId || '',
    taskId: entry.taskId || '',
    status: entry.status || 'submitted',
  };
  return await jgWriteHistory([item, ...history.filter((candidate) => candidate.id !== item.id)]);
}

async function jgClearRegionHistory() {
  await chrome.storage.local.set({ [JG_HISTORY_KEY]: [] });
}

function sanitizeSelectionForHistory(selection) {
  const elements = Array.isArray(selection.elements) ? selection.elements : [];
  return {
    mode: selection.mode || 'drag_region',
    bounds: selection.bounds || null,
    viewport: selection.viewport || null,
    elements: elements.slice(0, 30).map((element) => ({
      tagName: element.tagName || '',
      selector: element.selector || '',
      text: truncateForHistory(element.text || '', 240),
      role: element.role || '',
      testId: element.testId || '',
      id: element.id || '',
      framework: element.framework || 'unknown',
      componentName: element.componentName || '',
      sourceHint: element.sourceHint || '',
      bounds: element.bounds || null,
    })),
    visualFallback: selection.visualFallback ? {
      available: !!selection.visualFallback.available,
      kind: selection.visualFallback.kind || '',
      bounds: selection.visualFallback.bounds || null,
      evidenceId: selection.visualFallback.evidenceId || '',
    } : null,
  };
}

function truncateForHistory(value, max) {
  const text = String(value || '');
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

globalThis.jgRegionHistory = {
  read: jgReadHistory,
  record: jgRecordRegionEdit,
  clear: jgClearRegionHistory,
};
