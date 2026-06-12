type CapabilityVisibility = 'render' | 'disabled' | 'omit'

type UiCapability = {
  key: string
  label: string
  area: string
  enabled: boolean
  visibility: CapabilityVisibility
  reason: string
  intent: string
}

type UiCapabilitiesResponse = {
  capabilities: UiCapability[]
}

type CapabilityRule = {
  key: string
  selectors: string[]
  fallback: UiCapability
}

const CONTROL_API = window.location.port === '5173'
  ? `${window.location.protocol}//${window.location.hostname}:9877/api`
  : '/api'

function endpoint(path: string): string {
  return `${CONTROL_API}${path.startsWith('/') ? path : `/${path}`}`
}

function fallbackCapability(key: string, label: string, area: string, reason: string): UiCapability {
  return {
    key,
    label,
    area,
    enabled: false,
    visibility: 'omit',
    reason,
    intent: 'Temporary DOM guard fallback used only until GET /api/ui/capabilities responds.',
  }
}

const RULES: CapabilityRule[] = [
  {
    key: 'workspace.invite_members',
    selectors: ['.ws-dropdown-header-actions .ws-btn-sm[aria-label="Invite members"]'],
    fallback: fallbackCapability('workspace.invite_members', 'Invite members', 'workspace', 'No invite-members endpoint exists yet.'),
  },
  {
    key: 'workspace.create',
    selectors: ['.ws-dropdown-footer .ws-footer-btn[aria-label="Create new workspace"]'],
    fallback: fallbackCapability('workspace.create', 'Create workspace', 'workspace', 'No workspace creation endpoint exists yet.'),
  },
  {
    key: 'auth.logout',
    selectors: ['.ws-dropdown-footer .ws-footer-btn.ws-logout'],
    fallback: fallbackCapability('auth.logout', 'Log out', 'workspace', 'No logout endpoint exists yet.'),
  },
  {
    key: 'sidebar.ask',
    selectors: ['.sidebar-primary-nav .sidebar-nav-item[aria-label="Ask"]', '.sidebar-collapsed-nav .sidebar-icon-btn[aria-label="Ask"]'],
    fallback: fallbackCapability('sidebar.ask', 'Ask', 'sidebar', 'No distinct ask route exists yet.'),
  },
  {
    key: 'sidebar.knowledge',
    selectors: ['.sidebar-primary-nav .sidebar-nav-item[aria-label="Knowledge"]', '.sidebar-collapsed-nav .sidebar-icon-btn[aria-label="Knowledge"]'],
    fallback: fallbackCapability('sidebar.knowledge', 'Knowledge', 'sidebar', 'Knowledge is not wired as a specific sidebar surface yet.'),
  },
  {
    key: 'sidebar.review',
    selectors: ['.sidebar-primary-nav .sidebar-nav-item[aria-label="Review"]', '.sidebar-collapsed-nav .sidebar-icon-btn[aria-label="Review"]'],
    fallback: fallbackCapability('sidebar.review', 'Review', 'sidebar', 'No review route exists yet.'),
  },
  {
    key: 'sidebar.automations',
    selectors: ['.sidebar-primary-nav .sidebar-nav-item[aria-label="Automations"]', '.sidebar-collapsed-nav .sidebar-icon-btn[aria-label="Automations"]'],
    fallback: fallbackCapability('sidebar.automations', 'Automations', 'sidebar', 'No automation scheduler route exists yet.'),
  },
  {
    key: 'recent.placeholder_actions',
    selectors: ['.recent-menu-actions'],
    fallback: fallbackCapability('recent.placeholder_actions', 'Recent menu placeholder actions', 'sidebar', 'Recent menu actions are informational only.'),
  },
  {
    key: 'help.open',
    selectors: ['.sidebar-footer .sidebar-icon-btn[aria-label="Help"]'],
    fallback: fallbackCapability('help.open', 'Help', 'sidebar', 'No help route or documentation panel exists yet.'),
  },
  {
    key: 'session.decision.submit',
    selectors: ['.as-decision-options'],
    fallback: fallbackCapability('session.decision.submit', 'Submit decision answer', 'session', 'No decision submission endpoint exists yet.'),
  },
  {
    key: 'session.artifact_tab.create',
    selectors: ['.as-tab-add'],
    fallback: fallbackCapability('session.artifact_tab.create', 'Create artifact tab', 'session', 'No artifact tab creation endpoint exists yet.'),
  },
  {
    key: 'session.review_actions',
    selectors: ['.as-review-actions'],
    fallback: fallbackCapability('session.review_actions', 'Review actions', 'session', 'No review-action endpoint exists yet.'),
  },
]

function toMap(capabilities: UiCapability[]): Record<string, UiCapability> {
  return capabilities.reduce<Record<string, UiCapability>>((acc, capability) => {
    acc[capability.key] = capability
    return acc
  }, {})
}

function shouldRender(capability: UiCapability): boolean {
  return capability.enabled && capability.visibility === 'render'
}

function shouldDisable(capability: UiCapability): boolean {
  return !capability.enabled || capability.visibility === 'disabled'
}

function applyCapabilityToElement(element: Element, capability: UiCapability) {
  if (shouldRender(capability)) {
    element.removeAttribute('hidden')
    element.removeAttribute('aria-hidden')
    if (element instanceof HTMLButtonElement) {
      element.disabled = false
      element.title = capability.intent
    }
    return
  }

  if (capability.visibility === 'disabled' && element instanceof HTMLButtonElement) {
    element.removeAttribute('hidden')
    element.removeAttribute('aria-hidden')
    element.disabled = true
    element.title = capability.reason
    return
  }

  element.setAttribute('hidden', 'true')
  element.setAttribute('aria-hidden', 'true')
  if (element instanceof HTMLElement) {
    element.dataset.capabilityGuard = capability.key
    element.title = capability.reason
  }
}

function collapseEmptyContainers() {
  document.querySelectorAll('.ws-dropdown-footer').forEach(footer => {
    const visibleChildren = Array.from(footer.children).filter(child => !child.hasAttribute('hidden'))
    if (visibleChildren.length === 0) {
      footer.setAttribute('hidden', 'true')
      footer.setAttribute('aria-hidden', 'true')
    } else {
      footer.removeAttribute('hidden')
      footer.removeAttribute('aria-hidden')
    }
  })
}

function applyCapabilities(capabilities: Record<string, UiCapability>) {
  for (const rule of RULES) {
    const capability = capabilities[rule.key] || rule.fallback
    for (const selector of rule.selectors) {
      document.querySelectorAll(selector).forEach(element => applyCapabilityToElement(element, capability))
    }
  }
  collapseEmptyContainers()
}

async function loadCapabilities(): Promise<Record<string, UiCapability>> {
  try {
    const response = await fetch(endpoint('/ui/capabilities'))
    if (!response.ok) throw new Error(await response.text() || `${response.status} ${response.statusText}`)
    const data = await response.json() as UiCapabilitiesResponse
    return toMap(data.capabilities || [])
  } catch {
    return toMap(RULES.map(rule => rule.fallback))
  }
}

export function installCapabilityDomGuard() {
  let latest: Record<string, UiCapability> | null = null
  let scheduled = false

  function scheduleApply() {
    if (!latest || scheduled) return
    scheduled = true
    requestAnimationFrame(() => {
      scheduled = false
      if (latest) applyCapabilities(latest)
    })
  }

  loadCapabilities().then(capabilities => {
    latest = capabilities
    applyCapabilities(capabilities)
  })

  const observer = new MutationObserver(scheduleApply)
  observer.observe(document.documentElement, { childList: true, subtree: true })
}

installCapabilityDomGuard()
