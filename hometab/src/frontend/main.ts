import { Shortcut, Todo, SearchEngine } from '../types'

const API_BASE = ''

const ICONS = {
  edit: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>`,
  delete: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>`,
  copy: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`,
  menu: `<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="1.5"></circle><circle cx="12" cy="12" r="1.5"></circle><circle cx="12" cy="19" r="1.5"></circle></svg>`,
  link: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>`,
  checkbox: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"></polyline></svg>`,
  plus: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>`,
  loading: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10" stroke-dasharray="60" stroke-dashoffset="0"><animate attributeName="stroke-dashoffset" values="0;250" dur="1s" repeatCount="indefinite"/></circle></svg>`,
}

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
const dropdownContainer = document.getElementById('dropdown-container')!

type DropdownType = 'shortcut' | 'todo'

type ToastType = 'success' | 'error' | 'info'

function showDropdown(type: DropdownType, id: string, anchorEl: HTMLElement) {
  const existingDropdown = dropdownContainer.querySelector<HTMLElement>('.dropdown')
  const isSameDropdown =
    existingDropdown?.dataset.type === type && existingDropdown?.dataset.id === id

  closeDropdown()
  if (isSameDropdown) return
  
  const rect = anchorEl.getBoundingClientRect()
  const dropdown = document.createElement('div')
  dropdown.className = 'dropdown open'
  dropdown.dataset.type = type
  dropdown.dataset.id = id
  
  const createDropdownButton = (
    className: string,
    iconSvg: string,
    label: string,
    isDanger = false
  ): HTMLButtonElement => {
    const button = document.createElement('button')
    button.className = `dropdown-item ${className}${isDanger ? ' danger' : ''}`
    button.dataset.id = id
    button.appendChild(createSvgElement(iconSvg))

    const text = document.createElement('span')
    text.textContent = label
    button.appendChild(text)
    return button
  }

  if (type === 'shortcut') {
    dropdown.appendChild(createDropdownButton('edit-shortcut', ICONS.edit, 'Edit'))
    dropdown.appendChild(createDropdownButton('delete-shortcut', ICONS.delete, 'Delete', true))
  } else if (type === 'todo') {
    dropdown.appendChild(createDropdownButton('copy-todo', ICONS.copy, 'Copy'))
    dropdown.appendChild(createDropdownButton('delete-todo', ICONS.delete, 'Delete', true))
  }
  
  dropdown.style.position = 'fixed'
  dropdown.style.top = `${rect.bottom + 4}px`
  dropdown.style.right = `${window.innerWidth - rect.right}px`
  
  dropdownContainer.appendChild(dropdown)
  
  requestAnimationFrame(() => {
    const dropdownRect = dropdown.getBoundingClientRect()
    if (dropdownRect.bottom > window.innerHeight) {
      dropdown.style.top = `${rect.top - dropdownRect.height - 4}px`
    }
  })
}

function closeDropdown() {
  dropdownContainer.replaceChildren()
  const searchDropdown = document.getElementById('search-engine-dropdown')
  const searchBtn = document.getElementById('search-engine-btn')
  searchDropdown?.classList.remove('open')
  searchBtn?.classList.remove('active')
}

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
  return {
    'Content-Type': 'application/json',
  }
}

function handleUnauthorized() {
  location.reload()
}

async function fetchWithAuth(url: string, options: RequestInit = {}): Promise<Response> {
  const response = await fetch(url, {
    ...options,
    credentials: 'include',
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

function createSvgElement(svg: string): HTMLElement {
  const template = document.createElement('template')
  template.innerHTML = svg.trim()
  const element = template.content.firstElementChild
  return (element as HTMLElement) || document.createElement('span')
}

function renderIcon(icon: string | undefined, options?: { name?: string; fallbackUrl?: string }): HTMLElement {
  const { name = '', fallbackUrl } = options || {}

  const textIcon = (value: string) => {
    const span = document.createElement('span')
    span.className = 'icon-text'
    span.textContent = value
    return span
  }

  if (icon) {
    const trimmed = icon.trim()

    const isSvg = trimmed.startsWith('<svg')
    if (isSvg) {
      const svgEl = createSvgElement(trimmed)
      if (svgEl.tagName.toLowerCase() === 'svg') {
        return svgEl
      }
    }

    const isUrl = /^(https?:)?\/\//.test(trimmed) || trimmed.startsWith('data:')
    if (isUrl) {
      const img = document.createElement('img')
      img.src = icon
      img.alt = name
      return img
    }

    return textIcon(icon.toUpperCase())
  }

  if (fallbackUrl) {
    const img = document.createElement('img')
    img.src = fallbackUrl
    img.alt = name
    return img
  }

  const isCJK = /[\u4e00-\u9fff\u3040-\u30ff]/.test(name)
  const text = name.slice(0, isCJK ? 2 : 3).toUpperCase()
  return textIcon(text)
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
      showDropdown('shortcut', id, btn)
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
  shortcutsEl.replaceChildren()
  
  state.shortcuts.forEach(shortcut => {
    const iconEl = renderIcon(shortcut.icon, {
      name: shortcut.name,
      fallbackUrl: getFaviconUrl(shortcut.url) || undefined
    })

    const div = document.createElement('div')
    div.className = 'shortcut'
    div.draggable = true
    div.dataset.id = shortcut.id

    const link = document.createElement('a')
    link.href = shortcut.url
    link.rel = 'noreferrer'

    const shortcutIcon = document.createElement('div')
    shortcutIcon.className = 'shortcut-icon'
    shortcutIcon.appendChild(iconEl)
    const loadingIcon = createSvgElement(ICONS.loading)
    loadingIcon.classList.add('loading-icon', 'hidden')
    shortcutIcon.appendChild(loadingIcon)
    link.appendChild(shortcutIcon)

    const nameSpan = document.createElement('span')
    nameSpan.className = 'shortcut-name'
    nameSpan.textContent = shortcut.name
    link.appendChild(nameSpan)

    const menuBtn = document.createElement('button')
    menuBtn.className = 'shortcut-menu-btn'
    menuBtn.dataset.id = shortcut.id
    menuBtn.setAttribute('aria-label', 'Menu')
    menuBtn.appendChild(createSvgElement(ICONS.menu))

    div.appendChild(link)
    div.appendChild(menuBtn)
    shortcutsEl.appendChild(div)
  })

  const addBtn = document.createElement('div')
  addBtn.className = 'add-shortcut'
  const addIcon = document.createElement('div')
  addIcon.className = 'shortcut-icon'
  addIcon.appendChild(createSvgElement(ICONS.plus))

  const addText = document.createElement('span')
  addText.className = 'shortcut-name'
  addText.textContent = 'Add'
  addBtn.appendChild(addIcon)
  addBtn.appendChild(addText)
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
  
  if (target.closest('.edit-shortcut')) {
    const btn = target.closest('.edit-shortcut') as HTMLElement
    const id = btn.dataset.id!
    const shortcut = state.shortcuts.find(s => s.id === id)
    if (shortcut) openShortcutModal(shortcut)
    closeDropdown()
    return
  }
  
  if (target.closest('.delete-shortcut')) {
    const btn = target.closest('.delete-shortcut') as HTMLElement
    const id = btn.dataset.id!
    deleteShortcut(id)
    closeDropdown()
    return
  }
  
  if (target.closest('.copy-todo')) {
    const btn = target.closest('.copy-todo') as HTMLElement
    const id = btn.dataset.id!
    const todo = state.todos.find(t => t.id === id)
    if (todo) {
      navigator.clipboard.writeText(todo.text)
      showToast('Copied to clipboard', 'success')
    }
    closeDropdown()
    return
  }
  
  if (target.closest('.delete-todo')) {
    const btn = target.closest('.delete-todo') as HTMLElement
    const id = btn.dataset.id!
    deleteTodo(id)
    closeDropdown()
    return
  }
  
  if (!target.closest('.shortcut-menu-btn') && !target.closest('.todo-menu-btn') &&
      !target.closest('#dropdown-container') && !target.closest('.search-engine-btn') &&
      !target.closest('#search-engine-dropdown')) {
    closeDropdown()
  }
})

function renderTodos() {
  todoItems.replaceChildren()
  
  if (state.todos.length === 0) {
    const empty = document.createElement('p')
    empty.style.textAlign = 'center'
    empty.style.color = 'rgba(255,255,255,0.5)'
    empty.style.fontSize = '0.875rem'
    empty.style.padding = '1rem'
    empty.textContent = 'No tasks yet. Add one above!'
    todoItems.appendChild(empty)
  } else {
    state.todos.forEach(todo => {
      const div = document.createElement('div')
      div.className = 'todo-item'

      const checkbox = document.createElement('div')
      checkbox.className = `checkbox ${todo.completed ? 'checked' : ''}`
      checkbox.dataset.id = todo.id
      checkbox.appendChild(createSvgElement(ICONS.checkbox))

      const text = document.createElement('span')
      text.className = `text ${todo.completed ? 'completed' : ''}`
      text.dataset.id = todo.id
      text.textContent = todo.text

      const normalizedUrl = normalizeUrl(todo.text)
      let linkBtn: HTMLAnchorElement | null = null
      if (normalizedUrl) {
        linkBtn = document.createElement('a')
        linkBtn.href = normalizedUrl
        linkBtn.target = '_blank'
        linkBtn.rel = 'noopener noreferrer'
        linkBtn.className = 'link-btn'
        linkBtn.title = 'Open link'
        linkBtn.appendChild(createSvgElement(ICONS.link))
      }

      const menuBtn = document.createElement('button')
      menuBtn.className = 'todo-menu-btn'
      menuBtn.dataset.id = todo.id
      menuBtn.setAttribute('aria-label', 'Menu')
      menuBtn.appendChild(createSvgElement(ICONS.menu))

      div.appendChild(checkbox)
      div.appendChild(text)
      if (linkBtn) div.appendChild(linkBtn)
      div.appendChild(menuBtn)
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
    
    const menuBtn = target.closest('.todo-menu-btn')
    if (menuBtn) {
      const btn = menuBtn as HTMLElement
      const id = btn.dataset.id!
      showDropdown('todo', id, btn)
      return
    }
  })
  
  todoItems.addEventListener('dblclick', (e) => {
    const target = e.target as HTMLElement
    const textEl = target.closest('.text')
    if (textEl && !textEl.classList.contains('editing')) {
      startEditTodo((textEl as HTMLElement).dataset.id!)
    }
  })
}

function startEditTodo(id: string) {
  const todo = state.todos.find(t => t.id === id)
  if (!todo) return
  
  const textEl = todoItems.querySelector(`.text[data-id="${id}"]`)
  if (!textEl) return
  
  const input = document.createElement('input')
  input.type = 'text'
  input.className = 'todo-edit-input'
  input.value = todo.text
  
  textEl.classList.add('editing')
  textEl.replaceChildren(input)
  input.focus()
  input.select()
  
  const saveEdit = async () => {
    const newText = input.value.trim()
    if (newText && newText !== todo.text) {
      await updateTodoText(id, newText)
    } else {
      renderTodos()
    }
  }
  
  input.addEventListener('blur', saveEdit)
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      input.blur()
    }
    if (e.key === 'Escape') {
      renderTodos()
    }
  })
}

async function updateTodoText(id: string, text: string) {
  try {
    await fetchWithAuth(`${API_BASE}/api/todos/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ text })
    })
    const todo = state.todos.find(t => t.id === id)
    if (todo) {
      todo.text = text
      renderTodos()
    }
  } catch (error) {
    console.error('Failed to update todo:', error)
    showToast('Failed to update task', 'error')
    renderTodos()
  }
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
  
  try {
    await fetchWithAuth(`${API_BASE}/api/todos/${id}`, { method: 'DELETE' })
    state.todos = state.todos.filter(t => t.id !== id)
    renderTodos()
  } catch (error) {
    console.error('Failed to delete todo:', error)
    showToast('Failed to delete task', 'error')
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

async function setupPassword(password: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/auth/setup`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password })
    })
    return res.ok
  } catch (error) {
    console.error('Failed to setup password:', error)
    return false
  }
}

async function verifyPassword(password: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/auth/verify`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password })
    })
    return res.ok
  } catch (error) {
    console.error('Failed to verify password:', error)
    return false
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
    
    const success = await setupPassword(password)
    if (success) {
      showMainContent()
    } else {
      showError('Failed to set password')
    }
  } else {
    const success = await verifyPassword(password)
    if (success) {
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
  try {
    const res = await fetch(`${API_BASE}/api/auth/check`, { credentials: 'include' })
    if (res.ok) {
      const data = await res.json()
      if ((data as { isValid?: boolean }).isValid) {
        showMainContent()
        return
      }
    }
  } catch (error) {
    console.error('Auth check failed:', error)
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

  currentEngineIcon.replaceChildren(renderIcon(state.currentSearchEngine.icon, { name: state.currentSearchEngine.name }))

  searchEngineList.replaceChildren()
  state.searchEngines.forEach(engine => {
    const btn = document.createElement('button')
    btn.className = `dropdown-item search-engine-item${engine.id === state.currentSearchEngine?.id ? ' selected' : ''}`

    btn.appendChild(renderIcon(engine.icon, { name: engine.name }))
    const text = document.createElement('span')
    text.textContent = engine.name
    btn.appendChild(text)
    btn.addEventListener('click', () => selectSearchEngine(engine))
    searchEngineList.appendChild(btn)
  })
}

function selectSearchEngine(engine: SearchEngine) {
  state.currentSearchEngine = engine
  localStorage.setItem('hometab_search_engine', engine.id)
  renderSearchEngines()
  closeDropdown()
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
  closeDropdown()
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
