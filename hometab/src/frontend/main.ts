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

const API_BASE = ''

let shortcuts: Shortcut[] = []
let todos: Todo[] = []
let editingShortcutId: string | null = null

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

function getTodayKey() {
  const now = new Date()
  return `${now.getFullYear()}-${now.getMonth() + 1}-${now.getDate()}`
}

async function setDynamicBackground(forceRefresh = false) {
  const todayKey = getTodayKey()
  const cached = localStorage.getItem('hometab_bg')
  
  if (!forceRefresh && cached) {
    const { date, imageId } = JSON.parse(cached)
    if (date === todayKey && imageId) {
      const width = window.innerWidth
      const height = Math.round(window.innerHeight * 1.2)
      background.style.backgroundImage = `url(https://picsum.photos/id/${imageId}/${width}/${height})`
      return
    }
  }
  
  const width = window.innerWidth
  const height = Math.round(window.innerHeight * 1.2)
  
  try {
    const res = await fetch(`https://picsum.photos/${width}/${height}`)
    const imageId = res.url.match(/\/id\/(\d+)\//)?.[1] || null
    
    const blob = await res.blob()
    const blobUrl = URL.createObjectURL(blob)
    background.style.backgroundImage = `url(${blobUrl})`
    
    if (imageId) {
      localStorage.setItem('hometab_bg', JSON.stringify({ date: todayKey, imageId }))
    }
  } catch {
    background.style.backgroundImage = `url(https://picsum.photos/${width}/${height})`
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

function closeAllDropdowns() {
  document.querySelectorAll('.shortcut-dropdown.open').forEach(dropdown => {
    dropdown.classList.remove('open')
  })
}

function renderShortcuts() {
  shortcutsEl.innerHTML = ''
  
  shortcuts.forEach(shortcut => {
    const icon = shortcut.icon
    const isSvg = icon?.trim().startsWith('<svg')
    const fallbackUrl = getFaviconUrl(shortcut.url)
    
    let iconHtml = ''
    if (isSvg && icon) {
      iconHtml = icon
    } else if (icon) {
      iconHtml = `<img src="${icon}" alt="${shortcut.name}" onerror="this.style.display='none';this.nextElementSibling.classList.remove('hidden')">`
    } else if (fallbackUrl) {
      iconHtml = `<img src="${fallbackUrl}" alt="${shortcut.name}" onerror="this.style.display='none';this.nextElementSibling.classList.remove('hidden')">`
    }
    
    const div = document.createElement('div')
    div.className = 'shortcut'
    div.draggable = true
    div.dataset.id = shortcut.id
    div.innerHTML = `
      <a href="${shortcut.url}" rel="noreferrer">
        <div class="shortcut-icon">
          ${iconHtml}
          <svg class="default-icon ${iconHtml ? 'hidden' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="2" y1="12" x2="22" y2="12"></line>
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
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
      <div class="shortcut-dropdown" data-id="${shortcut.id}">
        <button class="dropdown-item edit" data-id="${shortcut.id}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
          </svg>
          <span>Edit</span>
        </button>
        <button class="dropdown-item delete" data-id="${shortcut.id}">
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
  addBtn.addEventListener('click', () => openShortcutModal())
  shortcutsEl.appendChild(addBtn)
  
  document.querySelectorAll('.shortcut-menu-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation()
      const id = (btn as HTMLElement).dataset.id!
      const dropdown = document.querySelector(`.shortcut-dropdown[data-id="${id}"]`)
      const isOpen = dropdown?.classList.contains('open')
      closeAllDropdowns()
      if (!isOpen && dropdown) {
        dropdown.classList.add('open')
      }
    })
  })
  
  document.querySelectorAll('.dropdown-item.edit').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation()
      closeAllDropdowns()
      const id = (btn as HTMLElement).dataset.id!
      const shortcut = shortcuts.find(s => s.id === id)
      if (shortcut) openShortcutModal(shortcut)
    })
  })
  
  document.querySelectorAll('.dropdown-item.delete').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation()
      closeAllDropdowns()
      const id = (btn as HTMLElement).dataset.id!
      await deleteShortcut(id)
    })
  })
  
  setupDragAndDrop()
}

let draggedId: string | null = null

function setupDragAndDrop() {
  const items = shortcutsEl.querySelectorAll('.shortcut')
  
  items.forEach(item => {
    item.addEventListener('dragstart', (e) => {
      draggedId = (item as HTMLElement).dataset.id!
      item.classList.add('dragging')
      ;(e as DragEvent).dataTransfer!.effectAllowed = 'move'
    })
    
    item.addEventListener('dragend', () => {
      item.classList.remove('dragging')
      document.querySelectorAll('.shortcut.drag-over').forEach(el => el.classList.remove('drag-over'))
      draggedId = null
    })
    
    item.addEventListener('dragover', (e) => {
      e.preventDefault()
      ;(e as DragEvent).dataTransfer!.dropEffect = 'move'
      document.querySelectorAll('.shortcut.drag-over').forEach(el => el.classList.remove('drag-over'))
      if ((item as HTMLElement).dataset.id !== draggedId) {
        item.classList.add('drag-over')
      }
    })
    
    item.addEventListener('dragleave', () => {
      item.classList.remove('drag-over')
    })
    
    item.addEventListener('drop', async (e) => {
      e.preventDefault()
      item.classList.remove('drag-over')
      const targetId = (item as HTMLElement).dataset.id!
      if (draggedId && draggedId !== targetId) {
        await reorderShortcuts(draggedId, targetId)
      }
    })
  })
}

async function reorderShortcuts(draggedId: string, targetId: string) {
  const draggedIndex = shortcuts.findIndex(s => s.id === draggedId)
  const targetIndex = shortcuts.findIndex(s => s.id === targetId)
  
  if (draggedIndex === -1 || targetIndex === -1) return
  
  const [dragged] = shortcuts.splice(draggedIndex, 1)
  shortcuts.splice(targetIndex, 0, dragged)
  
  await fetch(`${API_BASE}/api/shortcuts/reorder`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ shortcuts })
  })
  
  renderShortcuts()
}

document.addEventListener('click', (e) => {
  const target = e.target as HTMLElement
  if (!target.closest('.shortcut-menu-btn') && !target.closest('.shortcut-dropdown')) {
    closeAllDropdowns()
  }
})

function renderTodos() {
  todoItems.innerHTML = ''
  
  if (todos.length === 0) {
    todoItems.innerHTML = '<p style="text-align:center;color:rgba(255,255,255,0.5);font-size:0.875rem;padding:1rem;">No tasks yet. Add one above!</p>'
  } else {
    todos.forEach(todo => {
      const div = document.createElement('div')
      div.className = 'todo-item'
      div.innerHTML = `
        <div class="checkbox ${todo.completed ? 'checked' : ''}" data-id="${todo.id}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
        </div>
        <span class="text ${todo.completed ? 'completed' : ''}">${todo.text}</span>
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
  
  const completedCount = todos.filter(t => t.completed).length
  todoCount.textContent = `${completedCount}/${todos.length} done`
  
  document.querySelectorAll('.todo-item .checkbox').forEach(checkbox => {
    checkbox.addEventListener('click', async () => {
      const id = (checkbox as HTMLElement).dataset.id!
      const todo = todos.find(t => t.id === id)
      if (todo) {
        await toggleTodo(id, !todo.completed)
      }
    })
  })
  
  document.querySelectorAll('.todo-item .delete-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = (btn as HTMLElement).dataset.id!
      await deleteTodo(id)
    })
  })
}

function openShortcutModal(shortcut?: Shortcut) {
  if (shortcut) {
    editingShortcutId = shortcut.id
    shortcutModalTitle.textContent = 'Edit Shortcut'
    shortcutNameInput.value = shortcut.name
    shortcutUrlInput.value = shortcut.url
    shortcutIconInput.value = shortcut.icon || ''
  } else {
    editingShortcutId = null
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
  editingShortcutId = null
}

async function saveShortcut() {
  const name = shortcutNameInput.value.trim()
  let url = shortcutUrlInput.value.trim()
  const icon = shortcutIconInput.value.trim() || undefined
  
  if (!name || !url) return
  
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    url = `https://${url}`
  }
  
  if (editingShortcutId) {
    await fetch(`${API_BASE}/api/shortcuts/${editingShortcutId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, url, icon })
    })
  } else {
    await fetch(`${API_BASE}/api/shortcuts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: Date.now().toString(), name, url, icon })
    })
  }
  
  closeShortcutModal()
  await loadData()
}

async function deleteShortcut(id: string) {
  await fetch(`${API_BASE}/api/shortcuts/${id}`, { method: 'DELETE' })
  await loadData()
}

async function addTodo() {
  const text = todoInput.value.trim()
  if (!text) return
  
  await fetch(`${API_BASE}/api/todos`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: Date.now().toString(), text, completed: false })
  })
  
  todoInput.value = ''
  await loadData()
}

async function toggleTodo(id: string, completed: boolean) {
  await fetch(`${API_BASE}/api/todos/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ completed })
  })
  await loadData()
}

async function deleteTodo(id: string) {
  await fetch(`${API_BASE}/api/todos/${id}`, { method: 'DELETE' })
  await loadData()
}

async function checkPasswordExists(): Promise<boolean> {
  const res = await fetch(`${API_BASE}/api/auth/check`)
  const data = await res.json()
  return (data as { hasPassword: boolean }).hasPassword
}

async function setupPassword(password: string): Promise<boolean> {
  const res = await fetch(`${API_BASE}/api/auth/setup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password })
  })
  return res.ok
}

async function verifyPassword(password: string): Promise<boolean> {
  const res = await fetch(`${API_BASE}/api/auth/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password })
  })
  return res.ok
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
      localStorage.setItem('hometab_auth', password)
      showMainContent()
    } else {
      showError('Failed to set password')
    }
  } else {
    const success = await verifyPassword(password)
    if (success) {
      localStorage.setItem('hometab_auth', password)
      showMainContent()
    } else {
      showError('Invalid password')
    }
  }
}

async function showMainContent() {
  passwordModal.classList.add('hidden')
  mainContent.classList.remove('hidden')
  await loadData()
  await setDynamicBackground()
  updateClock()
  setInterval(updateClock, 1000)
}

async function loadData() {
  const [shortcutsRes, todosRes] = await Promise.all([
    fetch(`${API_BASE}/api/shortcuts`),
    fetch(`${API_BASE}/api/todos`)
  ])
  
  const shortcutsData = await shortcutsRes.json()
  const todosData = await todosRes.json()
  
  shortcuts = (shortcutsData as { shortcuts: Shortcut[] }).shortcuts || []
  todos = (todosData as { todos: Todo[] }).todos || []
  
  renderShortcuts()
  renderTodos()
}

async function init() {
  const storedPassword = localStorage.getItem('hometab_auth')
  
  if (storedPassword) {
    const success = await verifyPassword(storedPassword)
    if (success) {
      showMainContent()
      return
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

init()
