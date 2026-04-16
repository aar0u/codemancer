import { Hono } from 'hono'
import { cors } from 'hono/cors'
import defaults from './defaults.json'

type Bindings = {
  KV_BINDING: KVNamespace
  ASSETS: Fetcher
}

interface Shortcut {
  id: string
  name: string
  url: string
  icon?: string
}

interface Todo {
  id: string
  text: string
  completed: boolean
}

interface UserData {
  passwordHash: string
  shortcuts: Shortcut[]
  todos: Todo[]
}

const app = new Hono<{ Bindings: Bindings }>()

app.use('/*', cors())

async function hashPassword(password: string): Promise<string> {
  const encoder = new TextEncoder()
  const data = encoder.encode(password)
  const hashBuffer = await crypto.subtle.digest('SHA-256', data)
  const hashArray = Array.from(new Uint8Array(hashBuffer))
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
}

async function getUserData(kv: KVNamespace, userId: string): Promise<UserData | null> {
  const data = await kv.get(`user:${userId}`)
  return data ? JSON.parse(data) : null
}

async function setUserData(kv: KVNamespace, userId: string, data: UserData): Promise<void> {
  await kv.put(`user:${userId}`, JSON.stringify(data))
}

app.post('/api/auth/setup', async (c) => {
  const { password } = await c.req.json()
  const userId = 'default'
  
  const existing = await getUserData(c.env.KV_BINDING, userId)
  if (existing) {
    return c.json({ error: 'Password already set' }, 400)
  }
  
  const passwordHash = await hashPassword(password)
  const userData: UserData = {
    passwordHash,
    shortcuts: defaults.shortcuts as Shortcut[],
    todos: defaults.todos as Todo[]
  }
  
  await setUserData(c.env.KV_BINDING, userId, userData)
  return c.json({ success: true })
})

app.post('/api/auth/verify', async (c) => {
  const { password } = await c.req.json()
  const userId = 'default'
  
  const userData = await getUserData(c.env.KV_BINDING, userId)
  if (!userData) {
    return c.json({ error: 'User not found' }, 404)
  }
  
  const passwordHash = await hashPassword(password)
  if (passwordHash !== userData.passwordHash) {
    return c.json({ error: 'Invalid password' }, 401)
  }
  
  return c.json({ success: true })
})

app.get('/api/auth/check', async (c) => {
  const userId = 'default'
  const userData = await getUserData(c.env.KV_BINDING, userId)
  return c.json({ hasPassword: !!userData })
})

app.get('/api/shortcuts', async (c) => {
  const userId = 'default'
  const userData = await getUserData(c.env.KV_BINDING, userId)
  return c.json({ shortcuts: userData?.shortcuts || [] })
})

app.post('/api/shortcuts', async (c) => {
  const userId = 'default'
  const shortcut: Shortcut = await c.req.json()
  
  const userData = await getUserData(c.env.KV_BINDING, userId)
  if (!userData) {
    return c.json({ error: 'User not found' }, 404)
  }
  
  userData.shortcuts.push(shortcut)
  await setUserData(c.env.KV_BINDING, userId, userData)
  
  return c.json({ success: true, shortcut })
})

app.put('/api/shortcuts/reorder', async (c) => {
  const userId = 'default'
  const { shortcuts } = await c.req.json()
  
  const userData = await getUserData(c.env.KV_BINDING, userId)
  if (!userData) {
    return c.json({ error: 'User not found' }, 404)
  }
  
  userData.shortcuts = shortcuts
  await setUserData(c.env.KV_BINDING, userId, userData)
  
  return c.json({ success: true })
})

app.put('/api/shortcuts/:id', async (c) => {
  const userId = 'default'
  const id = c.req.param('id')
  const updates: Partial<Shortcut> = await c.req.json()
  
  const userData = await getUserData(c.env.KV_BINDING, userId)
  if (!userData) {
    return c.json({ error: 'User not found' }, 404)
  }
  
  const index = userData.shortcuts.findIndex(s => s.id === id)
  if (index === -1) {
    return c.json({ error: 'Shortcut not found' }, 404)
  }
  
  userData.shortcuts[index] = { ...userData.shortcuts[index], ...updates }
  await setUserData(c.env.KV_BINDING, userId, userData)
  
  return c.json({ success: true, shortcut: userData.shortcuts[index] })
})

app.delete('/api/shortcuts/:id', async (c) => {
  const userId = 'default'
  const id = c.req.param('id')
  
  const userData = await getUserData(c.env.KV_BINDING, userId)
  if (!userData) {
    return c.json({ error: 'User not found' }, 404)
  }
  
  userData.shortcuts = userData.shortcuts.filter(s => s.id !== id)
  await setUserData(c.env.KV_BINDING, userId, userData)
  
  return c.json({ success: true })
})

app.get('/api/todos', async (c) => {
  const userId = 'default'
  const userData = await getUserData(c.env.KV_BINDING, userId)
  return c.json({ todos: userData?.todos || [] })
})

app.post('/api/todos', async (c) => {
  const userId = 'default'
  const todo: Todo = await c.req.json()
  
  const userData = await getUserData(c.env.KV_BINDING, userId)
  if (!userData) {
    return c.json({ error: 'User not found' }, 404)
  }
  
  userData.todos.push(todo)
  await setUserData(c.env.KV_BINDING, userId, userData)
  
  return c.json({ success: true, todo })
})

app.put('/api/todos/:id', async (c) => {
  const userId = 'default'
  const id = c.req.param('id')
  const updates: Partial<Todo> = await c.req.json()
  
  const userData = await getUserData(c.env.KV_BINDING, userId)
  if (!userData) {
    return c.json({ error: 'User not found' }, 404)
  }
  
  const index = userData.todos.findIndex(t => t.id === id)
  if (index === -1) {
    return c.json({ error: 'Todo not found' }, 404)
  }
  
  userData.todos[index] = { ...userData.todos[index], ...updates }
  await setUserData(c.env.KV_BINDING, userId, userData)
  
  return c.json({ success: true, todo: userData.todos[index] })
})

app.delete('/api/todos/:id', async (c) => {
  const userId = 'default'
  const id = c.req.param('id')
  
  const userData = await getUserData(c.env.KV_BINDING, userId)
  if (!userData) {
    return c.json({ error: 'User not found' }, 404)
  }
  
  userData.todos = userData.todos.filter(t => t.id !== id)
  await setUserData(c.env.KV_BINDING, userId, userData)
  
  return c.json({ success: true })
})

export default app
