function jgSourceHintForElement(element) {
  if (!element) return emptySourceHint();
  const direct = directSourceHint(element);
  if (direct.confidence > 0) return direct;
  const mapped = mappedSourceHint(element);
  if (mapped.confidence > 0) return mapped;
  const framework = frameworkHint(element);
  return { ...framework, sourceFile: '', sourceLine: null };
}

function emptySourceHint() {
  return { framework: 'unknown', componentName: '', sourceFile: '', sourceLine: null, confidence: 0 };
}

function directSourceHint(element) {
  const file = element.getAttribute('data-jg-source-file') || element.getAttribute('data-source-file') || '';
  const line = element.getAttribute('data-jg-source-line') || element.getAttribute('data-source-line') || '';
  const component = element.getAttribute('data-jg-component') || element.getAttribute('data-component') || '';
  if (!file && !component) return emptySourceHint();
  return {
    framework: element.getAttribute('data-jg-framework') || 'annotated',
    componentName: component,
    sourceFile: file,
    sourceLine: line ? Number(line) : null,
    confidence: file ? 0.95 : 0.75,
  };
}

function mappedSourceHint(element) {
  const map = globalThis.__JG_COMPONENT_SOURCE_MAP__;
  if (!map || typeof map !== 'object') return emptySourceHint();
  const testId = element.getAttribute('data-testid') || element.getAttribute('data-test') || '';
  const id = element.id || '';
  const key = testId || id;
  if (!key || !map[key]) return emptySourceHint();
  const entry = map[key];
  return {
    framework: entry.framework || 'mapped',
    componentName: entry.componentName || '',
    sourceFile: entry.sourceFile || '',
    sourceLine: entry.sourceLine || null,
    confidence: 0.9,
  };
}

function frameworkHint(element) {
  for (const key of Object.keys(element)) {
    if (key.indexOf('__reactFiber$') === 0 || key.indexOf('__reactInternalInstance$') === 0) {
      return { framework: 'react', componentName: reactComponentName(element[key]), confidence: 0.55 };
    }
  }
  if (element.__vueParentComponent) {
    return { framework: 'vue', componentName: element.__vueParentComponent.type && element.__vueParentComponent.type.name || '', confidence: 0.55 };
  }
  if (element.__ngContext__) return { framework: 'angular', componentName: '', confidence: 0.4 };
  return emptySourceHint();
}

function reactComponentName(fiber) {
  let cursor = fiber;
  for (let i = 0; cursor && i < 10; i += 1) {
    const type = cursor.elementType || cursor.type;
    if (typeof type === 'function' && type.name) return type.name;
    if (type && type.displayName) return type.displayName;
    cursor = cursor.return;
  }
  return '';
}

globalThis.jgSourceHints = { forElement: jgSourceHintForElement };
