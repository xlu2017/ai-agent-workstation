function jgConfidence(selection) {
  const elements = Array.isArray(selection && selection.elements) ? selection.elements : [];
  if (!elements.length) return { score: 0.25, level: 'low', reasons: ['fallback only'] };
  let score = 0.35;
  const reasons = [];
  if (elements.some((element) => element.sourceHint || element.sourceFile)) { score += 0.35; reasons.push('source hint present'); }
  if (elements.some((element) => element.framework && element.framework !== 'unknown')) { score += 0.15; reasons.push('framework hint present'); }
  if (elements.some((element) => element.testId || element.id)) { score += 0.1; reasons.push('stable identifier present'); }
  if (elements.some((element) => element.selector)) { score += 0.05; reasons.push('selector present'); }
  score = Math.max(0, Math.min(1, score));
  return { score, level: score >= 0.75 ? 'high' : score >= 0.45 ? 'medium' : 'low', reasons };
}

function jgConfidenceSummary(selection) {
  const elements = Array.isArray(selection && selection.elements) ? selection.elements : [];
  const first = elements[0] || {};
  return { confidence: jgConfidence(selection), targetCount: elements.length, firstSelector: first.selector || '', firstFramework: first.framework || 'unknown', firstComponent: first.componentName || '' };
}

globalThis.jgConfidence = { score: jgConfidence, summary: jgConfidenceSummary };
