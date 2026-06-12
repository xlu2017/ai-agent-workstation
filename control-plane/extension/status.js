function jgToast(message) {
  const old = document.querySelector('.jg-status-toast');
  if (old) old.remove();
  const node = document.createElement('div');
  node.className = 'jg-status-toast';
  node.textContent = message;
  document.documentElement.appendChild(node);
  setTimeout(() => node.remove(), 3500);
}

globalThis.jgStatus = { toast: jgToast };
