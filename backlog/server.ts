import { Hono } from 'hono'
import { cors } from 'hono/cors'
import { serveStatic } from 'hono/bun'
import { writeFileSync, readFileSync, existsSync, mkdirSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const app = new Hono()
const DATA_DIR = join(__dirname, 'data')
const DB_FILE = join(DATA_DIR, 'tasks.json')

function ensureDataDir() {
  if (!existsSync(DATA_DIR)) {
    mkdirSync(DATA_DIR, { recursive: true })
  }
}

function readTasks(): any[] {
  ensureDataDir()
  if (!existsSync(DB_FILE)) {
    return []
  }
  try {
    const content = readFileSync(DB_FILE, 'utf-8')
    return JSON.parse(content)
  } catch {
    return []
  }
}

function writeTasks(tasks: any[]): void {
  ensureDataDir()
  writeFileSync(DB_FILE, JSON.stringify(tasks, null, 2), 'utf-8')
}

app.use('/*', cors(), serveStatic({ root: './public' }))

app.get('/api/tasks', (c) => {
  const tasks = readTasks()
  return c.json({ success: true, data: tasks })
})

app.post('/api/tasks', async (c) => {
  try {
    const body = await c.req.json()
    if (!Array.isArray(body)) {
      return c.json({ success: false, error: 'Invalid data format' }, 400)
    }
    writeTasks(body)
    return c.json({ success: true })
  } catch (error) {
    return c.json({ success: false, error: 'Failed to save tasks' }, 500)
  }
})

app.get('/api/health', (c) => {
  return c.json({ status: 'ok', timestamp: new Date().toISOString() })
})

console.log('🚀 Running on Bun...')
console.log('📡 Server starting at http://localhost:8080')

export default {
  port: 8080,
  fetch: app.fetch,
}
