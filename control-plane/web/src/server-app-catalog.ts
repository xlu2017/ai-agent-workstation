export type ServerAppLaunchMode = 'desktop_control' | 'remote_desktop_only'

export interface ServerAppEntry {
  id: string
  name: string
  description: string
  category: string
  popularity: number
  keywords: string[]
  launchPrompt: string
  preferredCommands: string[]
  launchMode: ServerAppLaunchMode
}

export const POPULAR_SERVER_APPS: ServerAppEntry[] = [
  {
    id: 'terminal',
    name: 'Terminal',
    description: 'Open an interactive shell on the visible desktop.',
    category: 'System',
    popularity: 100,
    keywords: ['terminal', 'shell', 'bash', 'command', 'console', 'xterm'],
    launchPrompt: 'Open a terminal on the remote desktop.',
    preferredCommands: ['xfce4-terminal', 'x-terminal-emulator', 'xterm'],
    launchMode: 'desktop_control',
  },
  {
    id: 'browser',
    name: 'Web Browser',
    description: 'Open the default graphical browser in the remote desktop.',
    category: 'Web',
    popularity: 96,
    keywords: ['browser', 'web', 'chrome', 'chromium', 'firefox', 'internet'],
    launchPrompt: 'Open the web browser on the remote desktop.',
    preferredCommands: ['google-chrome', 'chromium', 'chromium-browser', 'firefox', 'xdg-open'],
    launchMode: 'desktop_control',
  },
  {
    id: 'file-manager',
    name: 'File Manager',
    description: 'Browse repositories and workstation files visually.',
    category: 'System',
    popularity: 94,
    keywords: ['files', 'file manager', 'folder', 'directory', 'thunar', 'nautilus'],
    launchPrompt: 'Open the file manager at /opt/workstation/repos on the remote desktop.',
    preferredCommands: ['thunar', 'nautilus', 'xdg-open'],
    launchMode: 'desktop_control',
  },
  {
    id: 'code-editor',
    name: 'Code Editor',
    description: 'Open a graphical editor for repository inspection and edits.',
    category: 'Development',
    popularity: 88,
    keywords: ['code', 'editor', 'vscode', 'visual studio code', 'cursor', 'zed'],
    launchPrompt: 'Open the graphical code editor on the remote desktop.',
    preferredCommands: ['code', 'codium', 'cursor', 'zed'],
    launchMode: 'desktop_control',
  },
  {
    id: 'system-monitor',
    name: 'System Monitor',
    description: 'Inspect CPU, memory, and process activity on the server desktop.',
    category: 'System',
    popularity: 76,
    keywords: ['system monitor', 'processes', 'cpu', 'memory', 'task manager'],
    launchPrompt: 'Open the system monitor on the remote desktop.',
    preferredCommands: ['xfce4-taskmanager', 'gnome-system-monitor', 'htop'],
    launchMode: 'desktop_control',
  },
  {
    id: 'screenshot',
    name: 'Screenshot Tool',
    description: 'Open the desktop screenshot utility for manual capture.',
    category: 'Utilities',
    popularity: 72,
    keywords: ['screenshot', 'screen capture', 'image capture'],
    launchPrompt: 'Open the screenshot tool on the remote desktop.',
    preferredCommands: ['xfce4-screenshooter', 'gnome-screenshot'],
    launchMode: 'desktop_control',
  },
  {
    id: 'settings',
    name: 'Settings',
    description: 'Open desktop settings and display/input configuration.',
    category: 'System',
    popularity: 68,
    keywords: ['settings', 'preferences', 'display', 'keyboard', 'mouse'],
    launchPrompt: 'Open desktop settings on the remote desktop.',
    preferredCommands: ['xfce4-settings-manager', 'gnome-control-center'],
    launchMode: 'desktop_control',
  },
  {
    id: 'remote-desktop',
    name: 'Remote Desktop',
    description: 'Open a plain Guacamole remote desktop tab without launching a specific app.',
    category: 'Access',
    popularity: 65,
    keywords: ['remote desktop', 'rdp', 'guacamole', 'desktop', 'vnc'],
    launchPrompt: 'Open the remote desktop.',
    preferredCommands: [],
    launchMode: 'remote_desktop_only',
  },
]

export function searchServerApps(query: string, apps: ServerAppEntry[] = POPULAR_SERVER_APPS): ServerAppEntry[] {
  const q = query.trim().toLowerCase()
  const scored = apps.map(app => {
    const haystack = [app.name, app.description, app.category, ...app.keywords, ...app.preferredCommands].join(' ').toLowerCase()
    let score = app.popularity
    if (q) {
      if (app.name.toLowerCase().includes(q)) score += 120
      if (app.keywords.some(keyword => keyword.toLowerCase().includes(q))) score += 80
      if (haystack.includes(q)) score += 40
      if (!haystack.includes(q)) score -= 200
    }
    return { app, score }
  })
  return scored.filter(item => item.score > -100).sort((a, b) => b.score - a.score).map(item => item.app)
}
