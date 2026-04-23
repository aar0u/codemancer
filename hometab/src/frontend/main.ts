import { Shortcut, Todo, SearchEngine } from '../types'

const API_BASE = ''

const state = {
  shortcuts: [] as Shortcut[],
  todos: [] as Todo[],
  searchEngines: [] as SearchEngine[],
  currentSearchEngine: null as SearchEngine | null,
  editingShortcutId: null as string | null,
  clockInterval: null as ReturnType<typeof setInterval> | null,
  searchDebounceTimer: null as ReturnType<typeof setTimeout> | null,
}

const toastContainer = document.getElementById('toast-container')!

type ToastType = 'success' | 'error' | 'info'

function showToast(message: string, type: ToastType = 'info', duration = 3000) {
  const toast = document.createElement('div')
  toast.className = `toast ${type}`
  toast.textContent = message
  toastContainer.appendChild(toast)
  
  requestAnimationFrame(() => {
    toast.classList.add('show')
  })
  
  setTimeout(() => {
    toast.classList.remove('show')
    setTimeout(() => toast.remove(), 300)
  }, duration)
}

function getAuthHeaders(): HeadersInit {
  const password = localStorage.getItem('hometab_auth')
  return {
    'Content-Type': 'application/json',
    ...(password ? { 'Authorization': `Bearer ${password}` } : {})
  }
}

function handleUnauthorized() {
  localStorage.removeItem('hometab_auth')
  location.reload()
}

async function fetchWithAuth(url: string, options: RequestInit = {}): Promise<Response> {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...getAuthHeaders(),
      ...options.headers
    }
  })
  
  if (response.status === 401) {
    handleUnauthorized()
    throw new Error('Unauthorized')
  }
  
  return response
}

function renderIcon(icon: string | undefined, options?: { name?: string; fallbackUrl?: string }): string {
  const { name = '', fallbackUrl } = options || {}
  
  if (icon) {
    const trimmed = icon.trim()
    const isSvg = trimmed.startsWith('<svg')
    if (isSvg) return icon
    
    const isUrl = /^(https?:)?\/\//.test(trimmed) || trimmed.startsWith('data:')
    if (isUrl) return `<img src="${icon}" alt="${name}">`
    
    return `<span class="icon-text">${icon.toUpperCase()}</span>`
  }
  
  if (fallbackUrl) {
    return `<img src="${fallbackUrl}" alt="${name}">`
  }
  
  const isCJK = /[\u4e00-\u9fff\u3040-\u30ff]/.test(name)
  const text = name.slice(0, isCJK ? 2 : 3).toUpperCase()
  return `<span class="icon-text">${text}</span>`
}

const passwordModal = document.getElementById('password-modal')!
const passwordForm = document.getElementById('password-form') as HTMLFormElement
const mainContent = document.getElementById('main-content')!
const passwordInput = document.getElementById('password-input') as HTMLInputElement
const confirmPasswordInput = document.getElementById('confirm-password-input') as HTMLInputElement
const confirmPasswordGroup = document.getElementById('confirm-password-group')!
const passwordSubmit = document.getElementById('password-submit')!
const errorMessage = document.getElementById('error-message')!
const modalTitle = document.getElementById('modal-title')!
const modalDescription = document.getElementById('modal-description')!

const background = document.getElementById('background') as HTMLElement
const timeEl = document.getElementById('time')!
const dateEl = document.getElementById('date')!
const shortcutsEl = document.getElementById('shortcuts')!
const todoItems = document.getElementById('todo-items')!
const todoInput = document.getElementById('todo-input') as HTMLInputElement
const addTodoBtn = document.getElementById('add-todo-btn')!
const todoCount = document.getElementById('todo-count')!
const todoHeader = document.querySelector('.todo-header')!
const todoContent = document.getElementById('todo-content') as HTMLElement

const shortcutModal = document.getElementById('shortcut-modal')!
const shortcutForm = document.getElementById('shortcut-form') as HTMLFormElement
const shortcutNameInput = document.getElementById('shortcut-name-input') as HTMLInputElement
const shortcutUrlInput = document.getElementById('shortcut-url-input') as HTMLInputElement
const shortcutIconInput = document.getElementById('shortcut-icon-input') as HTMLInputElement
const shortcutCancel = document.getElementById('shortcut-cancel')!
const shortcutModalTitle = document.getElementById('shortcut-modal-title')!

const searchInput = document.getElementById('search-input') as HTMLInputElement
const searchBtn = document.getElementById('search-btn')!
const searchEngineBtn = document.getElementById('search-engine-btn')!
const searchEngineDropdown = document.getElementById('search-engine-dropdown')!
const searchEngineList = document.getElementById('search-engine-list')!
const currentEngineIcon = document.getElementById('current-engine-icon')!

async function setDynamicBackground(forceRefresh = false) {
  const now = new Date()
  const todayKey = `${now.getFullYear()}-${now.getMonth() + 1}-${now.getDate()}`
  const cached = localStorage.getItem('hometab_bg')
  
  if (!forceRefresh && cached) {
    const { date, imageUrl } = JSON.parse(cached)
    if (date === todayKey && imageUrl) {
      background.style.backgroundImage = `url(${imageUrl})`
      return
    }
  }
  
  const width = window.innerWidth
  const height = Math.round(window.innerHeight * 1.2)
  const res = await fetch(`https://picsum.photos/${width}/${height}`)
  
  if (res.url) {
    localStorage.setItem('hometab_bg', JSON.stringify({ date: todayKey, imageUrl: res.url }))
    background.style.backgroundImage = `url(${res.url})`
  }
}

function updateClock() {
  const now = new Date()
  const timeStr = now.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: true
  })
  const dateStr = now.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric'
  })
  timeEl.textContent = timeStr
  dateEl.textContent = dateStr
}

function getFaviconUrl(url: string): string | null {
  try {
    const domain = new URL(url).hostname
    return `https://www.google.com/s2/favicons?domain=${domain}&sz=64`
  } catch {
    return null
  }
}

const URL_REGEX = /^(https?:\/\/)?[a-zA-Z0-9\u4e00-\u9fa5\-]+(\.[a-zA-Z0-9\u4e00-\u9fa5\-]+)+(:\d+)?(\/[^\s]*)?$/i

function normalizeUrl(input: string): string | null {
  const url = input.trim()
  if (!url) return null
  
  if (!URL_REGEX.test(url)) {
    return null
  }
  
  const hasProtocol = url.startsWith('http://') || url.startsWith('https://')
  const normalizedUrl = hasProtocol ? url : `https://${url}`
  
  try {
    new URL(normalizedUrl)
    return normalizedUrl
  } catch {
    return null
  }
}

function closeAllDropdowns() {
  document.querySelectorAll('.dropdown.open').forEach(dropdown => {
    dropdown.classList.remove('open')
  })
}

let shortcutsEventsInitialized = false

function setupShortcutsEventDelegation() {
  if (shortcutsEventsInitialized) return
  shortcutsEventsInitialized = true

  shortcutsEl.addEventListener('click', (e) => {
    const target = e.target as HTMLElement
    
    if (target.closest('.add-shortcut')) {
      openShortcutModal()
      return
    }
    
    if (target.closest('.shortcut-menu-btn')) {
      e.stopPropagation()
      const btn = target.closest('.shortcut-menu-btn') as HTMLElement
      const id = btn.dataset.id!
      const dropdown = document.querySelector(`.shortcut-dropdown[data-id="${id}"]`)
      const isOpen = dropdown?.classList.contains('open')
      closeAllDropdowns()
      if (!isOpen && dropdown) {
        dropdown.classList.add('open')
      }
      return
    }
    
    if (target.closest('.dropdown-item.edit')) {
      e.stopPropagation()
      closeAllDropdowns()
      const btn = target.closest('.dropdown-item.edit') as HTMLElement
      const id = btn.dataset.id!
      const shortcut = state.shortcuts.find(s => s.id === id)
      if (shortcut) openShortcutModal(shortcut)
      return
    }
    
    if (target.closest('.delete-shortcut')) {
      e.stopPropagation()
      closeAllDropdowns()
      const btn = target.closest('.delete-shortcut') as HTMLElement
      const id = btn.dataset.id!
      deleteShortcut(id)
      return
    }
    
    const link = target.closest('.shortcut a') as HTMLElement
    if (link) {
      const shortcut = link.closest('.shortcut')
      const icon = shortcut?.querySelector('.shortcut-icon')
      const img = icon?.querySelector('img')
      const svgIcon = icon?.querySelector('svg:not(.loading-icon)')
      const defaultIconSpan = icon?.querySelector('span:not(.hidden)')
      const loadingIcon = icon?.querySelector('.loading-icon')
      
      if (img) img.classList.add('hidden')
      if (svgIcon) svgIcon.classList.add('hidden')
      if (defaultIconSpan) defaultIconSpan.classList.add('hidden')
      if (loadingIcon) loadingIcon.classList.remove('hidden')
      shortcut?.classList.add('loading')
    }
  })
  
  setupDragAndDrop()
}

function renderShortcuts() {
  shortcutsEl.innerHTML = ''
  
  state.shortcuts.forEach(shortcut => {
    const iconHtml = renderIcon(shortcut.icon, {
      name: shortcut.name,
      fallbackUrl: getFaviconUrl(shortcut.url) || undefined
    })
    
    const div = document.createElement('div')
    div.className = 'shortcut'
    div.draggable = true
    div.dataset.id = shortcut.id
    div.innerHTML = `
      <a href="${shortcut.url}" rel="noreferrer">
        <div class="shortcut-icon">
          ${iconHtml}
          <svg class="loading-icon hidden" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10" stroke-dasharray="60" stroke-dashoffset="0">
              <animate attributeName="stroke-dashoffset" values="0;250" dur="1s" repeatCount="indefinite"/>
            </circle>
          </svg>
        </div>
        <span class="shortcut-name">${shortcut.name}</span>
      </a>
      <button class="shortcut-menu-btn" data-id="${shortcut.id}" aria-label="Menu">
        <svg viewBox="0 0 24 24" fill="currentColor">
          <circle cx="12" cy="5" r="1.5"></circle>
          <circle cx="12" cy="12" r="1.5"></circle>
          <circle cx="12" cy="19" r="1.5"></circle>
        </svg>
      </button>
      <div class="dropdown shortcut-dropdown" data-id="${shortcut.id}">
        <button class="dropdown-item edit" data-id="${shortcut.id}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
          </svg>
          <span>Edit</span>
        </button>
        <button class="dropdown-item danger delete-shortcut" data-id="${shortcut.id}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
          <span>Delete</span>
        </button>
      </div>
    `
    shortcutsEl.appendChild(div)
  })
  
  const addBtn = document.createElement('div')
  addBtn.className = 'add-shortcut'
  addBtn.innerHTML = `
    <div class="shortcut-icon">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="12" y1="5" x2="12" y2="19"></line>
        <line x1="5" y1="12" x2="19" y2="12"></line>
      </svg>
    </div>
    <span class="shortcut-name">Add</span>
  `
  shortcutsEl.appendChild(addBtn)
  
  setupShortcutsEventDelegation()
}

let draggedId: string | null = null
let dragDropInitialized = false

function setupDragAndDrop() {
  if (dragDropInitialized) return
  dragDropInitialized = true
  
  shortcutsEl.addEventListener('dragstart', (e) => {
    const item = (e.target as HTMLElement).closest('.shortcut') as HTMLElement | null
    if (!item) return
    draggedId = item.dataset.id!
    item.classList.add('dragging')
    ;(e as DragEvent).dataTransfer!.effectAllowed = 'move'
  })
  
  shortcutsEl.addEventListener('dragend', (e) => {
    const item = (e.target as HTMLElement).closest('.shortcut') as HTMLElement | null
    if (item) item.classList.remove('dragging')
    document.querySelectorAll('.shortcut.drag-over').forEach(el => el.classList.remove('drag-over'))
    draggedId = null
  })
  
  shortcutsEl.addEventListener('dragover', (e) => {
    e.preventDefault()
    const item = (e.target as HTMLElement).closest('.shortcut') as HTMLElement | null
    if (!item) return
    ;(e as DragEvent).dataTransfer!.dropEffect = 'move'
    document.querySelectorAll('.shortcut.drag-over').forEach(el => el.classList.remove('drag-over'))
    if (item.dataset.id !== draggedId) {
      item.classList.add('drag-over')
    }
  })
  
  shortcutsEl.addEventListener('dragleave', (e) => {
    const item = (e.target as HTMLElement).closest('.shortcut') as HTMLElement | null
    if (item) item.classList.remove('drag-over')
  })
  
  shortcutsEl.addEventListener('drop', async (e) => {
    e.preventDefault()
    const item = (e.target as HTMLElement).closest('.shortcut') as HTMLElement | null
    if (!item) return
    item.classList.remove('drag-over')
    const targetId = item.dataset.id!
    if (draggedId && draggedId !== targetId) {
      await reorderShortcuts(draggedId, targetId)
    }
  })
}

async function reorderShortcuts(draggedId: string, targetId: string) {
  const draggedIndex = state.shortcuts.findIndex(s => s.id === draggedId)
  const targetIndex = state.shortcuts.findIndex(s => s.id === targetId)
  
  if (draggedIndex === -1 || targetIndex === -1) return
  
  const draggedEl = document.querySelector(`.shortcut[data-id="${draggedId}"]`)
  draggedEl?.classList.add('saving')
  
  const newShortcuts = [...state.shortcuts]
  const [dragged] = newShortcuts.splice(draggedIndex, 1)
  newShortcuts.splice(targetIndex, 0, dragged)
  
  try {
    await fetchWithAuth(`${API_BASE}/api/shortcuts/reorder`, {
      method: 'PUT',
      body: JSON.stringify({ shortcuts: newShortcuts })
    })
    state.shortcuts = newShortcuts
    renderShortcuts()
  } catch (error) {
    console.error('Failed to reorder shortcuts:', error)
    showToast('Failed to reorder shortcuts', 'error')
  }
}

document.addEventListener('click', (e) => {
  const target = e.target as HTMLElement
  if (!target.closest('.shortcut-menu-btn') && !target.closest('.shortcut-dropdown')) {
    closeAllDropdowns()
  }
})

function renderTodos() {
  todoItems.innerHTML = ''
  
  if (state.todos.length === 0) {
    todoItems.innerHTML = '<p style="text-align:center;color:rgba(255,255,255,0.5);font-size:0.875rem;padding:1rem;">No tasks yet. Add one above!</p>'
  } else {
    state.todos.forEach(todo => {
      const div = document.createElement('div')
      div.className = 'todo-item'
      
      const normalizedUrl = normalizeUrl(todo.text)
      const textHtml = normalizedUrl
        ? `<a href="${normalizedUrl}" target="_blank" rel="noopener noreferrer" class="text ${todo.completed ? 'completed' : ''}">${todo.text}</a>`
        : `<span class="text ${todo.completed ? 'completed' : ''}">${todo.text}</span>`
      
      div.innerHTML = `
        <div class="checkbox ${todo.completed ? 'checked' : ''}" data-id="${todo.id}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
        </div>
        ${textHtml}
        <button class="delete-btn" data-id="${todo.id}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6"></polyline>
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
          </svg>
        </button>
      `
      todoItems.appendChild(div)
    })
  }
  
  const completedCount = state.todos.filter(t => t.completed).length
  todoCount.textContent = `${completedCount}/${state.todos.length}`
  
  setupTodosEventDelegation()
}

let todosEventsInitialized = false

function setupTodosEventDelegation() {
  if (todosEventsInitialized) return
  todosEventsInitialized = true

  todoItems.addEventListener('click', async (e) => {
    const target = e.target as HTMLElement
    
    const checkbox = target.closest('.checkbox')
    if (checkbox) {
      const id = (checkbox as HTMLElement).dataset.id!
      const todo = state.todos.find(t => t.id === id)
      if (todo) await toggleTodo(id, !todo.completed)
      return
    }
    
    const deleteBtn = target.closest('.delete-btn')
    if (deleteBtn) {
      await deleteTodo((deleteBtn as HTMLElement).dataset.id!)
    }
  })
}

function openShortcutModal(shortcut?: Shortcut) {
  if (shortcut) {
    state.editingShortcutId = shortcut.id
    shortcutModalTitle.textContent = 'Edit Shortcut'
    shortcutNameInput.value = shortcut.name
    shortcutUrlInput.value = shortcut.url
    shortcutIconInput.value = shortcut.icon || ''
  } else {
    state.editingShortcutId = null
    shortcutModalTitle.textContent = 'Add Shortcut'
    shortcutNameInput.value = ''
    shortcutUrlInput.value = ''
    shortcutIconInput.value = ''
  }
  shortcutModal.classList.remove('hidden')
  shortcutNameInput.focus()
}

function closeShortcutModal() {
  shortcutModal.classList.add('hidden')
  state.editingShortcutId = null
}

async function saveShortcut() {
  const name = shortcutNameInput.value.trim()
  const urlInput = shortcutUrlInput.value.trim()
  const icon = shortcutIconInput.value.trim() || undefined
  
  if (!name || !urlInput) return
  
  const url = normalizeUrl(urlInput)
  if (!url) {
    showToast('Please enter a valid URL', 'error')
    return
  }
  
  const saveBtn = document.getElementById('shortcut-save') as HTMLButtonElement
  saveBtn.disabled = true
  saveBtn.textContent = 'Saving...'
  
  try {
    if (state.editingShortcutId) {
      await fetchWithAuth(`${API_BASE}/api/shortcuts/${state.editingShortcutId}`, {
        method: 'PUT',
        body: JSON.stringify({ name, url, icon })
      })
      const index = state.shortcuts.findIndex(s => s.id === state.editingShortcutId)
      if (index !== -1) {
        state.shortcuts[index] = { ...state.shortcuts[index], name, url, icon }
      }
    } else {
      const newShortcut: Shortcut = { id: Date.now().toString(), name, url, icon }
      await fetchWithAuth(`${API_BASE}/api/shortcuts`, {
        method: 'POST',
        body: JSON.stringify(newShortcut)
      })
      state.shortcuts.push(newShortcut)
    }
    
    renderShortcuts()
    closeShortcutModal()
  } catch (error) {
    console.error('Failed to save shortcut:', error)
    showToast('Failed to save shortcut', 'error')
  } finally {
    saveBtn.disabled = false
    saveBtn.textContent = 'Save'
  }
}

async function deleteShortcut(id: string) {
  const shortcutEl = document.querySelector(`.shortcut[data-id="${id}"]`)
  shortcutEl?.classList.add('saving')
  
  try {
    await fetchWithAuth(`${API_BASE}/api/shortcuts/${id}`, { method: 'DELETE' })
    state.shortcuts = state.shortcuts.filter(s => s.id !== id)
    renderShortcuts()
  } catch (error) {
    console.error('Failed to delete shortcut:', error)
    showToast('Failed to delete shortcut', 'error')
  }
}

async function addTodo() {
  const text = todoInput.value.trim()
  if (!text) return
  
  const newTodo: Todo = { id: Date.now().toString(), text, completed: false }
  
  const addBtn = document.getElementById('add-todo-btn') as HTMLButtonElement
  addBtn.disabled = true
  
  try {
    await fetchWithAuth(`${API_BASE}/api/todos`, {
      method: 'POST',
      body: JSON.stringify(newTodo)
    })
    state.todos.push(newTodo)
    todoInput.value = ''
    renderTodos()
  } catch (error) {
    console.error('Failed to add todo:', error)
    showToast('Failed to add task', 'error')
  } finally {
    addBtn.disabled = false
  }
}

async function toggleTodo(id: string, completed: boolean) {
  const checkbox = document.querySelector(`.checkbox[data-id="${id}"]`)
  checkbox?.classList.add('loading')
  
  try {
    await fetchWithAuth(`${API_BASE}/api/todos/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ completed })
    })
    const todo = state.todos.find(t => t.id === id)
    if (todo) {
      todo.completed = completed
      renderTodos()
    }
  } catch (error) {
    console.error('Failed to toggle todo:', error)
    showToast('Failed to update task', 'error')
    checkbox?.classList.remove('loading')
  }
}

async function deleteTodo(id: string) {
  const todoItem = document.querySelector(`.todo-item:has(.checkbox[data-id="${id}"])`)
  const deleteBtn = todoItem?.querySelector('.delete-btn')
  deleteBtn?.classList.add('loading')
  
  try {
    await fetchWithAuth(`${API_BASE}/api/todos/${id}`, { method: 'DELETE' })
    state.todos = state.todos.filter(t => t.id !== id)
    renderTodos()
  } catch (error) {
    console.error('Failed to delete todo:', error)
    showToast('Failed to delete task', 'error')
    deleteBtn?.classList.remove('loading')
  }
}

async function checkPasswordExists(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/auth/check`)
    const data = await res.json()
    return (data as { hasPassword: boolean }).hasPassword
  } catch (error) {
    console.error('Failed to check password:', error)
    return false
  }
}

async function setupPassword(password: string): Promise<string | null> {
  try {
    const res = await fetch(`${API_BASE}/api/auth/setup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password })
    })
    if (!res.ok) return null
    const data = await res.json()
    return (data as { token?: string }).token || null
  } catch (error) {
    console.error('Failed to setup password:', error)
    return null
  }
}

async function verifyPassword(password: string): Promise<string | null> {
  try {
    const res = await fetch(`${API_BASE}/api/auth/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password })
    })
    if (!res.ok) return null
    const data = await res.json()
    return (data as { token?: string }).token || null
  } catch (error) {
    console.error('Failed to verify password:', error)
    return null
  }
}

function showError(message: string) {
  errorMessage.textContent = message
  errorMessage.classList.remove('hidden')
}

function hideError() {
  errorMessage.classList.add('hidden')
}

async function handlePasswordSubmit() {
  hideError()
  const password = passwordInput.value
  
  if (!password) {
    showError('Please enter a password')
    return
  }
  
  const hasPassword = await checkPasswordExists()
  
  if (!hasPassword) {
    const confirmPassword = confirmPasswordInput.value
    if (!confirmPassword) {
      showError('Please confirm your password')
      return
    }
    if (password !== confirmPassword) {
      showError('Passwords do not match')
      return
    }
    
    const token = await setupPassword(password)
    if (token) {
      localStorage.setItem('hometab_auth', token)
      showMainContent()
    } else {
      showError('Failed to set password')
    }
  } else {
    const token = await verifyPassword(password)
    if (token) {
      localStorage.setItem('hometab_auth', token)
      showMainContent()
    } else {
      showError('Invalid password')
    }
  }
}

function loadCachedData(): boolean {
  const cached = localStorage.getItem('hometab_data')
  if (!cached) return false
  try {
    renderAll(JSON.parse(cached))
    return true
  } catch {
    return false
  }
}

function renderAll(data: { shortcuts?: Shortcut[]; todos?: Todo[]; searchEngines?: SearchEngine[] }) {
  state.shortcuts = data.shortcuts || []
  state.todos = data.todos || []
  state.searchEngines = data.searchEngines || []
  
  const savedEngineId = localStorage.getItem('hometab_search_engine')
  state.currentSearchEngine = state.searchEngines.find(e => e.id === savedEngineId) || state.searchEngines[0]
  
  renderShortcuts()
  renderTodos()
  renderSearchEngines()
}

async function showMainContent() {
  passwordModal.classList.add('hidden')
  mainContent.classList.remove('hidden')
  
  updateClock()
  if (state.clockInterval) clearInterval(state.clockInterval)
  state.clockInterval = setInterval(updateClock, 1000)
  
  const cachedBg = localStorage.getItem('hometab_bg')
  if (cachedBg) {
    try {
      const { imageUrl } = JSON.parse(cachedBg)
      if (imageUrl) background.style.backgroundImage = `url(${imageUrl})`
    } catch {}
  }
  
  loadCachedData()
  
  await Promise.all([loadData(), setDynamicBackground()])
}

async function loadData() {
  try {
    const res = await fetchWithAuth(`${API_BASE}/api/data`)
    if (!res.ok) throw new Error('Failed to load data')
    
    const data = await res.json() as { shortcuts?: Shortcut[]; todos?: Todo[]; searchEngines?: SearchEngine[] }
    localStorage.setItem('hometab_data', JSON.stringify(data))
    renderAll(data)
  } catch (error) {
    console.error('Failed to load data:', error)
  }
}

async function init() {
  const storedToken = localStorage.getItem('hometab_auth')
  
  if (storedToken) {
    try {
      const res = await fetch(`${API_BASE}/api/auth/check`, {
        headers: { 'Authorization': `Bearer ${storedToken}` }
      })
      if (res.ok) {
        const data = await res.json()
        if ((data as { isValid?: boolean }).isValid) {
          showMainContent()
          return
        }
        // Token is invalid, remove it
        localStorage.removeItem('hometab_auth')
      }
      // If res.ok is false (e.g., 500), don't remove token - server error
    } catch (error) {
      // Don't remove token on network error or abort
      // User may be offline or page was refreshed quickly
      console.error('Auth check failed:', error)
    }
  }
  
  const hasPassword = await checkPasswordExists()
  
  if (!hasPassword) {
    modalTitle.textContent = 'Welcome'
    modalDescription.textContent = 'Set your password to protect your data'
    confirmPasswordGroup.classList.remove('hidden')
    passwordSubmit.textContent = 'Get Started'
  } else {
    modalTitle.textContent = 'Welcome Back'
    modalDescription.textContent = 'Enter your password to continue'
    confirmPasswordGroup.classList.add('hidden')
    passwordSubmit.textContent = 'Continue'
  }
  
  passwordModal.classList.remove('hidden')
}

function renderSearchEngines() {
  if (!state.currentSearchEngine) return
  
  currentEngineIcon.innerHTML = renderIcon(state.currentSearchEngine.icon, { name: state.currentSearchEngine.name })
  
  searchEngineList.innerHTML = ''
  state.searchEngines.forEach(engine => {
    const btn = document.createElement('button')
    btn.className = `dropdown-item search-engine-item${engine.id === state.currentSearchEngine?.id ? ' selected' : ''}`
    btn.innerHTML = `
      ${renderIcon(engine.icon, { name: engine.name })}
      <span>${engine.name}</span>
    `
    btn.addEventListener('click', () => selectSearchEngine(engine))
    searchEngineList.appendChild(btn)
  })
}

function selectSearchEngine(engine: SearchEngine) {
  state.currentSearchEngine = engine
  localStorage.setItem('hometab_search_engine', engine.id)
  renderSearchEngines()
  closeAllDropdowns()
  searchEngineBtn.classList.remove('active')
  searchInput.focus()
}

function performSearch() {
  const query = searchInput.value.trim()
  if (!query || !state.currentSearchEngine) return
  
  searchBtn.classList.add('loading')
  searchInput.disabled = true
  
  const searchUrl = state.currentSearchEngine.url.replace('%s', encodeURIComponent(query))
  window.open(searchUrl, '_self')
}

function toggleSearchEngineDropdown() {
  const isOpen = searchEngineDropdown.classList.contains('open')
  closeAllDropdowns()
  if (!isOpen) {
    searchEngineDropdown.classList.add('open')
    searchEngineBtn.classList.add('active')
  }
}

passwordForm.addEventListener('submit', (e) => {
  e.preventDefault()
  handlePasswordSubmit()
})

shortcutForm.addEventListener('submit', (e) => {
  e.preventDefault()
  saveShortcut()
})

shortcutCancel.addEventListener('click', closeShortcutModal)

addTodoBtn.addEventListener('click', addTodo)
todoInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') addTodo()
})

todoHeader.addEventListener('click', () => {
  todoContent.classList.toggle('hidden')
})

document.getElementById('refresh-bg')!.addEventListener('click', () => {
  setDynamicBackground(true)
})

searchEngineBtn.addEventListener('click', (e) => {
  e.stopPropagation()
  toggleSearchEngineDropdown()
})

searchBtn.addEventListener('click', performSearch)

searchInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    if (state.searchDebounceTimer) clearTimeout(state.searchDebounceTimer)
    state.searchDebounceTimer = setTimeout(performSearch, 150)
  }
  
  if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
    e.preventDefault()
    const engines = state.searchEngines
    if (engines.length === 0) return
    
    const currentIndex = engines.findIndex(e => e.id === state.currentSearchEngine?.id)
    let newIndex: number
    
    if (e.key === 'ArrowUp') {
      newIndex = currentIndex <= 0 ? engines.length - 1 : currentIndex - 1
    } else {
      newIndex = currentIndex >= engines.length - 1 ? 0 : currentIndex + 1
    }
    
    selectSearchEngine(engines[newIndex])
  }
})

document.addEventListener('click', (e) => {
  if (!searchEngineDropdown.contains(e.target as Node) && !searchEngineBtn.contains(e.target as Node)) {
    searchEngineDropdown.classList.remove('open')
    searchEngineBtn.classList.remove('active')
  }
})

function resetLoadingStates() {
  document.querySelectorAll('.shortcut.loading').forEach(shortcut => {
    shortcut.classList.remove('loading')
    const icon = shortcut.querySelector('.shortcut-icon')
    const img = icon?.querySelector('img')
    const svgIcon = icon?.querySelector('svg:not(.loading-icon)')
    const defaultIconSpan = icon?.querySelector('span.hidden')
    const loadingIcon = icon?.querySelector('.loading-icon')
    
    if (img) img.classList.remove('hidden')
    if (svgIcon) svgIcon.classList.remove('hidden')
    if (defaultIconSpan) defaultIconSpan.classList.remove('hidden')
    if (loadingIcon) loadingIcon.classList.add('hidden')
  })
  
  searchBtn.classList.remove('loading')
  searchInput.disabled = false
}

window.addEventListener('pageshow', (e) => {
  if (e.persisted) {
    resetLoadingStates()
  }
})

document.addEventListener('keydown', (e) => {
  if (e.key === '/') {
    const activeElement = document.activeElement
    const isInputFocused = activeElement && (
      activeElement.tagName === 'INPUT' ||
      activeElement.tagName === 'TEXTAREA' ||
      activeElement.tagName === 'SELECT' ||
      (activeElement as HTMLElement).isContentEditable
    )
    
    if (!isInputFocused) {
      e.preventDefault()
      searchInput.focus()
      searchInput.select()
    }
  }
  
  if (e.key === 'Escape') {
    if (!shortcutModal.classList.contains('hidden')) {
      closeShortcutModal()
    }
  }
})

init()
