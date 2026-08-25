export interface Shortcut {
  id: string
  name: string
  url: string
  icon?: string
}

export interface Note {
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
  notes: Note[]
  searchEngines: SearchEngine[]
}

export interface TabsRecord {
  machineId: string
  content: string
  updatedAt: string
}

export const DEFAULT_USER_ID = 'default'

export const KV_KEYS = {
  auth: (userId: string) => `auth:${userId}`,
  shortcuts: (userId: string) => `shortcuts:${userId}`,
  notes: (userId: string) => `notes:${userId}`,
  searchEngines: (userId: string) => `searchEngines:${userId}`,
  tabs: (userId: string, machineId: string) => `tabs:${userId}:${machineId}`,
  session: (token: string) => `session:${token}`,
  rateLimit: (ip: string, window: number) => `ratelimit:${ip}:${window}`,
  trash: (userId: string, type: 'shortcuts' | 'notes', id: string) => `trash:${userId}:${type}:${id}`,
}
