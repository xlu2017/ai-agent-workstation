const defaults = { controlPlaneUrl: 'http://127.0.0.1:9877', sessionId: '', autoInferSessionId: true };

document.addEventListener('DOMContentLoaded', () => {
  chrome.storage.sync.get(defaults, (settings) => {
    const url = document.getElementById('controlPlaneUrl');
    const session = document.getElementById('sessionId');
    const infer = document.getElementById('autoInferSessionId');
    if (url) url.value = settings.controlPlaneUrl || defaults.controlPlaneUrl;
    if (session) session.value = settings.sessionId || '';
    if (infer) infer.checked = settings.autoInferSessionId !== false;
  });
  const save = document.getElementById('save');
  if (save) save.addEventListener('click', () => {
    chrome.storage.sync.set({
      controlPlaneUrl: document.getElementById('controlPlaneUrl')?.value || defaults.controlPlaneUrl,
      sessionId: document.getElementById('sessionId')?.value || '',
      autoInferSessionId: !!document.getElementById('autoInferSessionId')?.checked,
    }, () => {
      const status = document.getElementById('status');
      if (status) status.textContent = ' Saved';
    });
  });
});
