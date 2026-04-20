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

export interface UserData {
  passwordHash: string
  shortcuts: Shortcut[]
  todos: Todo[]
}

export const DEFAULT_USER_ID = 'default'
