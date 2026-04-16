(function() {
  const API_BASE = '';
  let storageMode = localStorage.getItem('storageMode') || 'local';

  const _originalLoadTasks = globalThis.loadTasks;
  const _originalSaveTasks = globalThis.saveTasks;

  function injectStyles() {
    document.head.insertAdjacentHTML('beforeend', `
      <style>
        .storage-toggle{display:flex;align-items:center;gap:.75rem;margin-top:1rem;padding-top:1rem;border-top:1px solid #e0e0e0;font-size:.8rem;color:#666}
        .storage-toggle span{font-weight:500}
        .storage-toggle label{display:flex;align-items:center;gap:.25rem;cursor:pointer;padding:.25rem .5rem;border-radius:4px;transition:background .2s}
        .storage-toggle label:hover{background:#f0f0f0}
        .storage-toggle input{display:none}
        .storage-toggle label.active{background:#e3f2fd;color:var(--primary-color);font-weight:500}
        .storage-status{padding:2px 6px;border-radius:4px;font-size:.7rem;background:#e3f2fd;color:var(--primary-color)}
        .storage-status.error{background:#ffebee;color:#c62828}
        .storage-status.connected{background:#e8f5e9;color:#2e7d32}
      </style>
    `);
  }

  function injectToggleUI() {
    const hint = document.querySelector('.shortcut-hint');
    if (!hint) return;

    hint.insertAdjacentHTML('beforeend', `
      <div class="storage-toggle">
        <span>Storage:</span>
        <label id="storage-local" class="${storageMode === 'local' ? 'active' : ''}">
          <input type="radio" name="storage" value="local" ${storageMode === 'local' ? 'checked' : ''}>
          Local
        </label>
        <label id="storage-api" class="${storageMode === 'api' ? 'active' : ''}">
          <input type="radio" name="storage" value="api" ${storageMode === 'api' ? 'checked' : ''}>
          API
        </label>
        <span class="storage-status" id="storage-status"></span>
      </div>
    `);

    hint.querySelectorAll('input[name="storage"]').forEach(radio => {
      radio.addEventListener('change', async (e) => {
        storageMode = e.target.value;
        localStorage.setItem('storageMode', storageMode);
        document.getElementById('storage-local').classList.toggle('active', storageMode === 'local');
        document.getElementById('storage-api').classList.toggle('active', storageMode === 'api');
        if (storageMode === 'api') checkHealth();
        else updateStatus('', '');
        await loadTasks();
      });
    });
  }

  function updateStatus(type, msg) {
    const el = document.getElementById('storage-status');
    if (!el) return;
    el.textContent = msg;
    el.className = 'storage-status' + (type ? ` ${type}` : '');
  }

  async function checkHealth() {
    try {
      const res = await fetch(`${API_BASE}/api/health`);
      if (!res.ok) {
        updateStatus('error', 'Error');
        return;
      }
      const data = await res.json();
      updateStatus(data.status === 'ok' ? 'connected' : 'error', data.status === 'ok' ? 'Online' : 'Error');
    } catch {
      updateStatus('error', 'Offline');
    }
  }

  async function apiLoad() {
    const res = await fetch(`${API_BASE}/api/tasks`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    updateStatus('connected', 'Online');
    return data.data;
  }

  async function apiSave(data) {
    const res = await fetch(`${API_BASE}/api/tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }
    const result = await res.json();
    if (!result.success) throw new Error(result.error);
    updateStatus('connected', 'Saved');
  }

  globalThis.loadTasks = async function() {
    if (storageMode === 'api') {
      try {
        tasks = await apiLoad();
      } catch (e) {
        console.error('API load failed:', e);
        updateStatus('error', 'Error');
        alert(`Failed to connect to API: ${e.message}. Switching to Local.`);
        storageMode = 'local';
        localStorage.setItem('storageMode', 'local');
        document.getElementById('storage-local').classList.add('active');
        document.getElementById('storage-api').classList.remove('active');
        if (_originalLoadTasks) {
          _originalLoadTasks();
        } else {
          tasks = JSON.parse(localStorage.getItem('tasks') || '[]');
        }
      }
    } else {
      if (_originalLoadTasks) {
        _originalLoadTasks();
      } else {
        tasks = JSON.parse(localStorage.getItem('tasks') || '[]');
      }
    }
    renderTasks();
  };

  globalThis.saveTasks = async function() {
    if (storageMode === 'api') {
      try {
        await apiSave(tasks);
      } catch (e) {
        console.error('API save failed:', e);
        updateStatus('error', 'Save Failed');
        alert(`Save failed: ${e.message}\n\nYour changes are NOT saved. Closing this page will lose your data.\n\nPlease try again or switch to Local storage.`);
      }
    } else {
      if (_originalSaveTasks) {
        _originalSaveTasks();
      } else {
        localStorage.setItem('tasks', JSON.stringify(tasks));
      }
    }
  };

  function init() {
    injectStyles();
    injectToggleUI();
    if (storageMode === 'api') checkHealth();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
