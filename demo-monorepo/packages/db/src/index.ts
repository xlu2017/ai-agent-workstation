import Database from 'better-sqlite3'
import { type Task, generateId } from '@taskflow/shared'
import { join } from 'path'

const DB_PATH = process.env.DB_PATH || join(process.cwd(), 'taskflow.db')

class TaskflowDB {
  private db: Database.Database

  constructor() {
    this.db = new Database(DB_PATH)
    this.migrate()
  }

  private migrate() {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        completed INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
      );
      CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
      );
    `)
  }

  getAllTasks(): Task[] {
    return this.db.prepare('SELECT * FROM tasks ORDER BY created_at DESC').all().map(this.rowToTask)
  }

  getTask(id: string): Task | null {
    const row = this.db.prepare('SELECT * FROM tasks WHERE id = ?').get(id) as any
    return row ? this.rowToTask(row) : null
  }

  createTask(data: { title: string; description?: string }): Task {
    const id = generateId()
    const now = new Date().toISOString()
    this.db.prepare(
      'INSERT INTO tasks (id, title, description, completed, created_at, updated_at) VALUES (?, ?, ?, 0, ?, ?)'
    ).run(id, data.title, data.description || '', now, now)
    return this.getTask(id)!
  }

  updateTask(id: string, data: Partial<Task>): Task {
    const now = new Date().toISOString()
    if (data.completed !== undefined) {
      this.db.prepare('UPDATE tasks SET completed = ?, updated_at = ? WHERE id = ?')
        .run(data.completed ? 1 : 0, now, id)
    }
    if (data.title !== undefined) {
      this.db.prepare('UPDATE tasks SET title = ?, updated_at = ? WHERE id = ?')
        .run(data.title, now, id)
    }
    if (data.description !== undefined) {
      this.db.prepare('UPDATE tasks SET description = ?, updated_at = ? WHERE id = ?')
        .run(data.description, now, id)
    }
    return this.getTask(id)!
  }

  deleteTask(id: string): void {
    this.db.prepare('DELETE FROM tasks WHERE id = ?').run(id)
  }

  getSettings(): Record<string, any> {
    const rows = this.db.prepare('SELECT * FROM settings').all() as any[]
    const settings: Record<string, any> = { theme: 'light', notifications: true, autoSave: false }
    for (const row of rows) {
      try { settings[row.key] = JSON.parse(row.value) } catch { settings[row.key] = row.value }
    }
    return settings
  }

  updateSettings(data: Record<string, any>): Record<string, any> {
    const stmt = this.db.prepare('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)')
    for (const [key, value] of Object.entries(data)) {
      if (value !== undefined) stmt.run(key, JSON.stringify(value))
    }
    return this.getSettings()
  }

  private rowToTask(row: any): Task {
    return {
      id: row.id,
      title: row.title,
      description: row.description,
      completed: Boolean(row.completed),
      createdAt: row.created_at,
      updatedAt: row.updated_at,
    }
  }
}

export const db = new TaskflowDB()
