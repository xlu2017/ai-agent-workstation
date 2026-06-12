function jgRegisterAnchor(key, metadata) {
  if (!globalThis.__JG_COMPONENT_SOURCE_MAP__) globalThis.__JG_COMPONENT_SOURCE_MAP__ = {};
  globalThis.__JG_COMPONENT_SOURCE_MAP__[key] = {
    framework: metadata.framework || 'unknown',
    componentName: metadata.componentName || '',
    sourceFile: metadata.sourceFile || '',
    sourceLine: metadata.sourceLine || null,
  };
}

function jgAnchorAttributes(key, metadata) {
  jgRegisterAnchor(key, metadata || {});
  return {
    'data-testid': key,
    'data-jg-component': metadata && metadata.componentName || '',
    'data-jg-source-file': metadata && metadata.sourceFile || '',
    'data-jg-source-line': metadata && metadata.sourceLine || '',
    'data-jg-framework': metadata && metadata.framework || '',
  };
}

globalThis.jgAnchors = { register: jgRegisterAnchor, attributes: jgAnchorAttributes };
