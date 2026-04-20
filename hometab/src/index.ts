import { Hono, Context, MiddlewareHandler } from 'hono'
import { cors } from 'hono/cors'
import defaults from './defaults.json'
import { Shortcut, Todo, SearchEngine, UserData, DEFAULT_USER_ID } from './types'

type Bindings = {
  KV_BINDING: KVNamespace
  ASSETS: Fetcher
}

const app = new Hono<{ Bindings: Bindings }>()

app.use('/*', cors())

type RateLimitOptions = {
  windowMs: number
  max: number
  message?: string
}

function rateLimit(options: RateLimitOptions): MiddlewareHandler<{ Bindings: Bindings }> {
  const { windowMs, max, message = 'Too many requests, please try again later.' } = options
  
  return async (c, next) => {
    const ip = c.req.header('CF-Connecting-IP') || 
               c.req.header('X-Forwarded-For')?.split(',')[0]?.trim() || 
               'unknown'
    const key = `ratelimit:${ip}:${Math.floor(Date.now() / windowMs)}`
    
    const kv = c.env.KV_BINDING
    const current = await kv.get(key)
    const count = current ? parseInt(current, 10) : 0
    
    if (count >= max) {
      return c.json({ error: message }, 429)
    }
    
    await kv.put(key, String(count + 1), { expirationTtl: Math.ceil(windowMs / 1000) })
    await next()
  }
}

const SESSION_TTL = 7 * 24 * 60 * 60

async function hashPassword(password: string): Promise<string> {
  const encoder = new TextEncoder()
  const data = encoder.encode(password)
  const hashBuffer = await crypto.subtle.digest('SHA-256', data)
  const hashArray = Array.from(new Uint8Array(hashBuffer))
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
}

function generateToken(): string {
  const bytes = new Uint8Array(32)
  crypto.getRandomValues(bytes)
  return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('')
}

async function createSession(kv: KVNamespace, userId: string): Promise<string> {
  const token = generateToken()
  await kv.put(`session:${token}`, userId, { expirationTtl: SESSION_TTL })
  return token
}

async function validateAndRefreshSession(kv: KVNamespace, token: string): Promise<string | null> {
  const userId = await kv.get(`session:${token}`)
  if (userId) {
    await kv.put(`session:${token}`, userId, { expirationTtl: SESSION_TTL })
  }
  return userId
}

async function deleteSession(kv: KVNamespace, token: string): Promise<void> {
  await kv.delete(`session:${token}`)
}

async function getUserData(kv: KVNamespace, userId: string): Promise<UserData | null> {
  const data = await kv.get(`user:${userId}`)
  return data ? JSON.parse(data) : null
}

async function setUserData(kv: KVNamespace, userId: string, data: UserData): Promise<void> {
  await kv.put(`user:${userId}`, JSON.stringify(data))
}

async function withUserData(
  c: Context<{ Bindings: Bindings }>,
  handler: (userData: UserData) => Promise<Response>
): Promise<Response> {
  const userData = await getUserData(c.env.KV_BINDING, DEFAULT_USER_ID)
  if (!userData) {
    return c.json({ error: 'User not found' }, 404)
  }
  return handler(userData)
}

async function verifyAuth(c: Context<{ Bindings: Bindings }>): Promise<boolean> {
  const authHeader = c.req.header('Authorization')
  if (!authHeader) return false
  
  const token = authHeader.replace('Bearer ', '')
  const userId = await validateAndRefreshSession(c.env.KV_BINDING, token)
  return userId === DEFAULT_USER_ID
}

app.use('/api/shortcuts/*', async (c, next) => {
  if (!(await verifyAuth(c))) {
    return c.json({ error: 'Unauthorized' }, 401)
  }
  await next()
})

app.use('/api/todos/*', async (c, next) => {
  if (!(await verifyAuth(c))) {
    return c.json({ error: 'Unauthorized' }, 401)
  }
  await next()
})

app.post('/api/auth/setup', rateLimit({ windowMs: 60 * 60 * 1000, max: 3, message: 'Too many setup attempts. Try again in 1 hour.' }), async (c) => {
  const { password } = await c.req.json()
  
  if (!password || typeof password !== 'string') {
    return c.json({ error: 'Password is required' }, 400)
  }
  
  const existing = await getUserData(c.env.KV_BINDING, DEFAULT_USER_ID)
  if (existing) {
    return c.json({ error: 'Password already set' }, 400)
  }
  
  const passwordHash = await hashPassword(password)
  const userData: UserData = {
    passwordHash,
    shortcuts: defaults.shortcuts as Shortcut[],
    todos: defaults.todos as Todo[],
    searchEngines: defaults.searchEngines as SearchEngine[]
  }
  
  await setUserData(c.env.KV_BINDING, DEFAULT_USER_ID, userData)
  
  const token = await createSession(c.env.KV_BINDING, DEFAULT_USER_ID)
  return c.json({ success: true, token })
})

app.post('/api/auth/verify', rateLimit({ windowMs: 15 * 60 * 1000, max: 5, message: 'Too many login attempts. Try again in 15 minutes.' }), async (c) => {
  const { password } = await c.req.json()
  
  if (!password || typeof password !== 'string') {
    return c.json({ error: 'Password is required' }, 400)
  }
  
  const userData = await getUserData(c.env.KV_BINDING, DEFAULT_USER_ID)
  if (!userData) {
    return c.json({ error: 'User not found' }, 404)
  }
  
  const passwordHash = await hashPassword(password)
  if (passwordHash !== userData.passwordHash) {
    return c.json({ error: 'Invalid password' }, 401)
  }
  
  const token = await createSession(c.env.KV_BINDING, DEFAULT_USER_ID)
  return c.json({ success: true, token })
})

app.post('/api/auth/logout', async (c) => {
  const authHeader = c.req.header('Authorization')
  if (authHeader) {
    const token = authHeader.replace('Bearer ', '')
    await deleteSession(c.env.KV_BINDING, token)
  }
  return c.json({ success: true })
})

app.get('/api/auth/check', async (c) => {
  const userData = await getUserData(c.env.KV_BINDING, DEFAULT_USER_ID)
  const hasPassword = !!userData
  
  const authHeader = c.req.header('Authorization')
  let isValid = false
  if (authHeader) {
    const token = authHeader.replace('Bearer ', '')
    const userId = await validateAndRefreshSession(c.env.KV_BINDING, token)
    isValid = userId === DEFAULT_USER_ID
  }
  
  return c.json({ hasPassword, isValid })
})

app.get('/api/data', async (c) => {
  const userData = await getUserData(c.env.KV_BINDING, DEFAULT_USER_ID)
  const { passwordHash, ...data } = userData || { passwordHash: '' }
  return c.json(data)
})

app.post('/api/shortcuts', async (c) => {
  const shortcut: Shortcut = await c.req.json()
  
  return withUserData(c, async (userData) => {
    userData.shortcuts.push(shortcut)
    await setUserData(c.env.KV_BINDING, DEFAULT_USER_ID, userData)
    return c.json({ success: true, shortcut })
  })
})

app.put('/api/shortcuts/reorder', async (c) => {
  const { shortcuts } = await c.req.json()
  
  return withUserData(c, async (userData) => {
    userData.shortcuts = shortcuts
    await setUserData(c.env.KV_BINDING, DEFAULT_USER_ID, userData)
    return c.json({ success: true })
  })
})

app.put('/api/shortcuts/:id', async (c) => {
  const id = c.req.param('id')
  const updates: Partial<Shortcut> = await c.req.json()
  
  return withUserData(c, async (userData) => {
    const index = userData.shortcuts.findIndex(s => s.id === id)
    if (index === -1) {
      return c.json({ error: 'Shortcut not found' }, 404)
    }
    
    userData.shortcuts[index] = { ...userData.shortcuts[index], ...updates }
    await setUserData(c.env.KV_BINDING, DEFAULT_USER_ID, userData)
    
    return c.json({ success: true, shortcut: userData.shortcuts[index] })
  })
})

app.delete('/api/shortcuts/:id', async (c) => {
  const id = c.req.param('id')
  
  return withUserData(c, async (userData) => {
    userData.shortcuts = userData.shortcuts.filter(s => s.id !== id)
    await setUserData(c.env.KV_BINDING, DEFAULT_USER_ID, userData)
    return c.json({ success: true })
  })
})

app.post('/api/todos', async (c) => {
  const todo: Todo = await c.req.json()
  
  return withUserData(c, async (userData) => {
    userData.todos.push(todo)
    await setUserData(c.env.KV_BINDING, DEFAULT_USER_ID, userData)
    return c.json({ success: true, todo })
  })
})

app.put('/api/todos/:id', async (c) => {
  const id = c.req.param('id')
  const updates: Partial<Todo> = await c.req.json()
  
  return withUserData(c, async (userData) => {
    const index = userData.todos.findIndex(t => t.id === id)
    if (index === -1) {
      return c.json({ error: 'Todo not found' }, 404)
    }
    
    userData.todos[index] = { ...userData.todos[index], ...updates }
    await setUserData(c.env.KV_BINDING, DEFAULT_USER_ID, userData)
    
    return c.json({ success: true, todo: userData.todos[index] })
  })
})

app.delete('/api/todos/:id', async (c) => {
  const id = c.req.param('id')
  
  return withUserData(c, async (userData) => {
    userData.todos = userData.todos.filter(t => t.id !== id)
    await setUserData(c.env.KV_BINDING, DEFAULT_USER_ID, userData)
    return c.json({ success: true })
  })
})

export default app
