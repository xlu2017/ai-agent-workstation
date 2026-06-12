(() => {
  chrome.runtime.onMessage.addListener((message) => {
    if (!message || message.type !== 'JG_START_REGION_SELECT') return;
    const marker = document.createElement('div');
    marker.className = 'jg-region-help';
    marker.textContent = 'Drag selection scaffold active';
    document.documentElement.appendChild(marker);
    setTimeout(() => marker.remove(), 1500);
  });
})();
