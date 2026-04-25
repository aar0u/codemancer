import { Hono, Context, MiddlewareHandler } from 'hono'
import { cors } from 'hono/cors'
import { deleteCookie, getCookie, setCookie } from 'hono/cookie'
import {
  Shortcut,
  Todo,
  SearchEngine,
  AuthData,
  UserData,
  DEFAULT_USER_ID,
  KV_KEYS,
} from './types'

type Bindings = {
  KV_BINDING: KVNamespace
  ASSETS: Fetcher
}

type Variables = {
  userId: string
}

const app = new Hono<{ Bindings: Bindings; Variables: Variables }>()

app.use('/*', cors())

type RateLimitOptions = {
  windowMs: number
  max: number
  message?: string
}

const AUTH_COOKIE_NAME = 'hometab_auth'

function getCookieSecurity(c: Context<{ Bindings: Bindings; Variables: Variables }>) {
  const forwardedProto = c.req.header('X-Forwarded-Proto')
  const isHttps = c.req.url.startsWith('https://') || forwardedProto === 'https'
  return {
    secure: isHttps,
    sameSite: 'Lax' as const,
  }
}

function rateLimit(options: RateLimitOptions): MiddlewareHandler<{ Bindings: Bindings; Variables: Variables }> {
  const { windowMs, max, message = 'Too many requests, please try again later.' } = options

  return async (c, next) => {
    const ip =
      c.req.header('CF-Connecting-IP') ||
      c.req.header('X-Forwarded-For')?.split(',')[0]?.trim() ||
      'unknown'
    const key = KV_KEYS.rateLimit(ip, Math.floor(Date.now() / windowMs))
    const ttlSeconds = Math.max(60, Math.ceil(windowMs / 1000))

    const kv = c.env.KV_BINDING
    const current = await kv.get(key)
    const count = Number.parseInt(current || '0', 10)

    // NOTE: KV increment here is not atomic. Under high concurrency, a small over-allow window may happen.
    // We accept this trade-off for simplicity and document the risk in README.
    if (count >= max) {
      return c.json({ error: message }, 429)
    }

    await kv.put(key, String(count + 1), { expirationTtl: ttlSeconds })
    await next()
  }
}

const SESSION_TTL = 7 * 24 * 60 * 60

async function hashPassword(password: string): Promise<string> {
  const encoder = new TextEncoder()
  const data = encoder.encode(password)
  const hashBuffer = await crypto.subtle.digest('SHA-256', data)
  const hashArray = Array.from(new Uint8Array(hashBuffer))
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('')
}

function generateToken(): string {
  const bytes = new Uint8Array(32)
  crypto.getRandomValues(bytes)
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
}

async function createSession(kv: KVNamespace, userId: string): Promise<string> {
  const token = generateToken()
  await kv.put(KV_KEYS.session(token), userId, { expirationTtl: SESSION_TTL })
  return token
}

async function validateAndRefreshSession(
  kv: KVNamespace,
  token: string
): Promise<string | null> {
  const data = await kv.getWithMetadata<{ lastRefresh: number }>(KV_KEYS.session(token))
  
  if (data.value) {
    const now = Date.now()
    const lastRefresh = data.metadata?.lastRefresh || 0
    const oneDayMs = 24 * 60 * 60 * 1000
    
    if (now - lastRefresh > oneDayMs) {
      await kv.put(KV_KEYS.session(token), data.value, { 
        expirationTtl: SESSION_TTL,
        metadata: { lastRefresh: now }
      })
    }
  }
  return data.value
}

async function deleteSession(kv: KVNamespace, token: string): Promise<void> {
  await kv.delete(KV_KEYS.session(token))
}

async function getAuthData(kv: KVNamespace, userId: string): Promise<AuthData | null> {
  const data = await kv.get(KV_KEYS.auth(userId))
  return data ? JSON.parse(data) : null
}

async function setAuthData(kv: KVNamespace, userId: string, data: AuthData): Promise<void> {
  await kv.put(KV_KEYS.auth(userId), JSON.stringify(data))
}

async function getShortcuts(kv: KVNamespace, userId: string): Promise<Shortcut[]> {
  const data = await kv.get(KV_KEYS.shortcuts(userId))
  return data ? JSON.parse(data) : []
}

async function setShortcuts(kv: KVNamespace, userId: string, shortcuts: Shortcut[]): Promise<void> {
  await kv.put(KV_KEYS.shortcuts(userId), JSON.stringify(shortcuts))
}

async function getTodos(kv: KVNamespace, userId: string): Promise<Todo[]> {
  const data = await kv.get(KV_KEYS.todos(userId))
  return data ? JSON.parse(data) : []
}

async function setTodos(kv: KVNamespace, userId: string, todos: Todo[]): Promise<void> {
  await kv.put(KV_KEYS.todos(userId), JSON.stringify(todos))
}

async function getSearchEngines(kv: KVNamespace, userId: string): Promise<SearchEngine[]> {
  const data = await kv.get(KV_KEYS.searchEngines(userId))
  return data ? JSON.parse(data) : []
}

async function setSearchEngines(
  kv: KVNamespace,
  userId: string,
  searchEngines: SearchEngine[]
): Promise<void> {
  await kv.put(KV_KEYS.searchEngines(userId), JSON.stringify(searchEngines))
}

async function getUserData(kv: KVNamespace, userId: string): Promise<UserData> {
  const [shortcuts, todos, searchEngines] = await Promise.all([
    getShortcuts(kv, userId),
    getTodos(kv, userId),
    getSearchEngines(kv, userId),
  ])
  return { shortcuts, todos, searchEngines }
}

async function verifyAuth(
  c: Context<{ Bindings: Bindings; Variables: Variables }>
): Promise<{ valid: boolean; userId: string | null }> {
  const cookieToken = getCookie(c, AUTH_COOKIE_NAME)
  const authHeader = c.req.header('Authorization')
  const bearerToken = authHeader?.replace('Bearer ', '').trim()
  const token = cookieToken || bearerToken
  if (!token) return { valid: false, userId: null }

  const userId = await validateAndRefreshSession(c.env.KV_BINDING, token)
  return { valid: userId !== null, userId }
}

const authMiddleware: MiddlewareHandler<{ Bindings: Bindings; Variables: Variables }> = async (c, next) => {
  const { valid, userId } = await verifyAuth(c)
  if (!valid || !userId) {
    return c.json({ error: 'Unauthorized' }, 401)
  }
  c.set('userId', userId)
  await next()
}

app.use('/api/shortcuts/*', authMiddleware)
app.use('/api/todos/*', authMiddleware)
app.use('/api/data', authMiddleware)

app.post(
  '/api/auth/setup',
  rateLimit({
    windowMs: 60 * 60 * 1000,
    max: 3,
    message: 'Too many setup attempts. Try again in 1 hour.',
  }),
  async (c) => {
    const { password } = await c.req.json()

    if (!password || typeof password !== 'string') {
      return c.json({ error: 'Password is required' }, 400)
    }

    const existing = await getAuthData(c.env.KV_BINDING, DEFAULT_USER_ID)
    if (existing) {
      return c.json({ error: 'Password already set' }, 400)
    }

    const passwordHash = await hashPassword(password)
    const kv = c.env.KV_BINDING
    
    await Promise.all([
      setAuthData(kv, DEFAULT_USER_ID, { passwordHash }),
      getShortcuts(kv, DEFAULT_USER_ID).then((s) => {
        if (s.length === 0) setShortcuts(kv, DEFAULT_USER_ID, [])
      }),
      getTodos(kv, DEFAULT_USER_ID).then((t) => {
        if (t.length === 0) setTodos(kv, DEFAULT_USER_ID, [])
      }),
      getSearchEngines(kv, DEFAULT_USER_ID).then((e) => {
        if (e.length === 0) setSearchEngines(kv, DEFAULT_USER_ID, [])
      }),
    ])

    const token = await createSession(kv, DEFAULT_USER_ID)
    setCookie(c, AUTH_COOKIE_NAME, token, {
      httpOnly: true,
      path: '/',
      maxAge: SESSION_TTL,
      ...getCookieSecurity(c),
    })

    return c.json({ success: true })
  }
)

app.post(
  '/api/auth/verify',
  rateLimit({
    windowMs: 15 * 60 * 1000,
    max: 5,
    message: 'Too many login attempts. Try again in 15 minutes.',
  }),
  async (c) => {
    const { password } = await c.req.json()

    if (!password || typeof password !== 'string') {
      return c.json({ error: 'Password is required' }, 400)
    }

    const authData = await getAuthData(c.env.KV_BINDING, DEFAULT_USER_ID)
    if (!authData) {
      return c.json({ error: 'User not found' }, 404)
    }

    const passwordHash = await hashPassword(password)
    if (passwordHash !== authData.passwordHash) {
      return c.json({ error: 'Invalid password' }, 401)
    }

    const token = await createSession(c.env.KV_BINDING, DEFAULT_USER_ID)
    setCookie(c, AUTH_COOKIE_NAME, token, {
      httpOnly: true,
      path: '/',
      maxAge: SESSION_TTL,
      ...getCookieSecurity(c),
    })

    return c.json({ success: true })
  }
)

app.post('/api/auth/logout', async (c) => {
  const token = getCookie(c, AUTH_COOKIE_NAME)
  if (token) {
    await deleteSession(c.env.KV_BINDING, token)
  }
  deleteCookie(c, AUTH_COOKIE_NAME, { path: '/' })
  return c.json({ success: true })
})

app.get('/api/auth/check', async (c) => {
  const authData = await getAuthData(c.env.KV_BINDING, DEFAULT_USER_ID)
  const hasPassword = !!authData

  const { valid: isValid } = await verifyAuth(c)

  return c.json({ hasPassword, isValid })
})

app.get('/api/data', async (c) => {
  const data = await getUserData(c.env.KV_BINDING, c.get('userId'))
  return c.json(data)
})

app.post('/api/shortcuts', async (c) => {
  const shortcut: Shortcut = await c.req.json()
  const kv = c.env.KV_BINDING
  const userId = c.get('userId')

  const shortcuts = await getShortcuts(kv, userId)
  shortcuts.push(shortcut)
  await setShortcuts(kv, userId, shortcuts)

  return c.json({ success: true, shortcut })
})

app.put('/api/shortcuts/reorder', async (c) => {
  const { shortcuts } = await c.req.json()
  await setShortcuts(c.env.KV_BINDING, c.get('userId'), shortcuts)
  return c.json({ success: true })
})

app.put('/api/shortcuts/:id', async (c) => {
  const id = c.req.param('id')
  const updates: Partial<Shortcut> = await c.req.json()
  const kv = c.env.KV_BINDING
  const userId = c.get('userId')

  const shortcuts = await getShortcuts(kv, userId)
  const index = shortcuts.findIndex((s) => s.id === id)
  if (index === -1) {
    return c.json({ error: 'Shortcut not found' }, 404)
  }

  shortcuts[index] = { ...shortcuts[index], ...updates }
  await setShortcuts(kv, userId, shortcuts)

  return c.json({ success: true, shortcut: shortcuts[index] })
})

app.delete('/api/shortcuts/:id', async (c) => {
  const id = c.req.param('id')
  const kv = c.env.KV_BINDING
  const userId = c.get('userId')

  const shortcuts = await getShortcuts(kv, userId)
  const filtered = shortcuts.filter((s) => s.id !== id)
  await setShortcuts(kv, userId, filtered)

  return c.json({ success: true })
})

app.post('/api/todos', async (c) => {
  const todo: Todo = await c.req.json()
  const kv = c.env.KV_BINDING
  const userId = c.get('userId')

  const todos = await getTodos(kv, userId)
  todos.push(todo)
  await setTodos(kv, userId, todos)

  return c.json({ success: true, todo })
})

app.put('/api/todos/:id', async (c) => {
  const id = c.req.param('id')
  const updates: Partial<Todo> = await c.req.json()
  const kv = c.env.KV_BINDING
  const userId = c.get('userId')

  const todos = await getTodos(kv, userId)
  const index = todos.findIndex((t) => t.id === id)
  if (index === -1) {
    return c.json({ error: 'Todo not found' }, 404)
  }

  todos[index] = { ...todos[index], ...updates }
  await setTodos(kv, userId, todos)

  return c.json({ success: true, todo: todos[index] })
})

app.delete('/api/todos/:id', async (c) => {
  const id = c.req.param('id')
  const kv = c.env.KV_BINDING
  const userId = c.get('userId')

  const todos = await getTodos(kv, userId)
  const filtered = todos.filter((t) => t.id !== id)
  await setTodos(kv, userId, filtered)

  return c.json({ success: true })
})

export default app
