export interface Shortcut {
  id: string
  name: string
  url: string
  icon?: string
}

export interface Todo {
  id: string
  text: string
  completed: boolean
}

export interface SearchEngine {
  id: string
  name: string
  url: string
  icon?: string
}

export interface AuthData {
  passwordHash: string
}

export interface UserData {
  shortcuts: Shortcut[]
  todos: Todo[]
  searchEngines: SearchEngine[]
}

export const DEFAULT_USER_ID = 'default'

export const KV_KEYS = {
  auth: (userId: string) => `auth:${userId}`,
  shortcuts: (userId: string) => `shortcuts:${userId}`,
  todos: (userId: string) => `todos:${userId}`,
  searchEngines: (userId: string) => `searchEngines:${userId}`,
  session: (token: string) => `session:${token}`,
  rateLimit: (ip: string, window: number) => `ratelimit:${ip}:${window}`,
}
