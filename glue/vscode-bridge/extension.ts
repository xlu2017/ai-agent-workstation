import * as vscode from 'vscode';
import * as http from 'http';

const BRIDGE_URL = 'http://localhost:9876';
let debounceTimer: NodeJS.Timeout | undefined;

interface EditorContext {
  type: 'editor_focus';
  session_id: string;
  file: string;
  language: string;
  selection: {
    text: string;
    startLine: number;
    startColumn: number;
    endLine: number;
    endColumn: number;
  };
  cursor: {
    line: number;
    column: number;
  };
  visibleRange: {
    startLine: number;
    endLine: number;
  };
  diagnostics: Array<{
    severity: string;
    message: string;
    line: number;
    column: number;
    source: string;
  }>;
  symbolAtCursor: string;
  gitBranch: string;
  workspaceRoot: string;
  timestamp: string;
}

const getSessionId = (): string => {
  return process.env.WORKSTATION_SESSION_ID || 'default';
};

const getGitBranch = async (workspaceRoot: string): Promise<string> => {
  try {
    const gitExtension = vscode.extensions.getExtension('vscode.git');
    if (gitExtension) {
      const git = gitExtension.exports.getAPI(1);
      const repo = git.repositories[0];
      if (repo) {
        return repo.state.HEAD?.name || '';
      }
    }
  } catch {
    // Fall through
  }
  return '';
};

const getSymbolAtCursor = async (
  document: vscode.TextDocument,
  position: vscode.Position
): Promise<string> => {
  try {
    const wordRange = document.getWordRangeAtPosition(position);
    if (wordRange) {
      return document.getText(wordRange);
    }
  } catch {
    // Fall through
  }
  return '';
};

const getDiagnostics = (document: vscode.TextDocument) => {
  const diagnostics = vscode.languages.getDiagnostics(document.uri);
  return diagnostics.slice(0, 10).map(diag => ({
    severity: vscode.DiagnosticSeverity[diag.severity],
    message: diag.message,
    line: diag.range.start.line + 1,
    column: diag.range.start.character + 1,
    source: diag.source || '',
  }));
};

const sendToBridge = (context: EditorContext): void => {
  const body = JSON.stringify(context);
  const url = new URL('/editor-context', BRIDGE_URL);

  const req = http.request(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(body),
    },
  });

  req.on('error', () => {
    // Bridge not running — silently ignore
  });

  req.write(body);
  req.end();
};

const captureAndSend = async (): Promise<void> => {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return;

  const document = editor.document;
  const selection = editor.selection;
  const visibleRanges = editor.visibleRanges;

  const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
  const relativePath = vscode.workspace.asRelativePath(document.uri);

  const context: EditorContext = {
    type: 'editor_focus',
    session_id: getSessionId(),
    file: relativePath,
    language: document.languageId,
    selection: {
      text: document.getText(selection),
      startLine: selection.start.line + 1,
      startColumn: selection.start.character + 1,
      endLine: selection.end.line + 1,
      endColumn: selection.end.character + 1,
    },
    cursor: {
      line: selection.active.line + 1,
      column: selection.active.character + 1,
    },
    visibleRange: {
      startLine: visibleRanges[0]?.start.line + 1 || 1,
      endLine: visibleRanges[0]?.end.line + 1 || 1,
    },
    diagnostics: getDiagnostics(document),
    symbolAtCursor: await getSymbolAtCursor(document, selection.active),
    gitBranch: await getGitBranch(workspaceRoot),
    workspaceRoot,
    timestamp: new Date().toISOString(),
  };

  sendToBridge(context);
};

const debouncedCapture = (): void => {
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
  debounceTimer = setTimeout(captureAndSend, 300);
};

export const activate = (extensionContext: vscode.ExtensionContext): void => {
  // Track selection changes
  extensionContext.subscriptions.push(
    vscode.window.onDidChangeTextEditorSelection(debouncedCapture)
  );

  // Track active editor changes
  extensionContext.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor(debouncedCapture)
  );

  // Track visible range changes (scrolling)
  extensionContext.subscriptions.push(
    vscode.window.onDidChangeTextEditorVisibleRanges(debouncedCapture)
  );

  // Manual command: send current focus explicitly
  extensionContext.subscriptions.push(
    vscode.commands.registerCommand('workstation.sendEditorContext', captureAndSend)
  );

  console.log('Workstation Editor Bridge activated');
};

export const deactivate = (): void => {
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
};
