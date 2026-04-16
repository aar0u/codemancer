# Action Board - Task List SPA

A modern, Material Design-inspired single page app for managing tasks (to-do list).

---

## Features

- Task data stored in localStorage (optionally switchable to REST API).
- Easy export/import of all tasks as JSON.
- Modern UI, summary list view, expandable rows.

---

## Data Model

Each task contains:
- `id`: unique identifier
- `createdTime`: ISO string, set on creation
- `content`: task description
- `tags`: array of strings
- `endTime`: ISO string, set when ended (not user-editable)

---

## UI/UX

- **Main Actions:**  
  - New Task (`Ctrl+K`)
  - Export Tasks
  - Import Tasks

- **Task List View:**  
  - Shows summary, created date (`yyyy-mm-dd hh:mm`)
  - Ended tasks show end date, gray out, move to bottom
  - Click row to expand for editing

- **Row Actions:**  
  - Delete
  - End (move to bottom, gray out, show end time)
  - Undo End

- **Input Area:**  
  - Expands automatically to fit content
  - Save button (`Ctrl+Enter`)

---

## Keyboard Shortcuts

- `Ctrl+K`: New Task
- `Ctrl+Enter`: Save Task
- `↑` / `K`: Navigate up
- `↓` / `J`: Navigate down
- `→` / `L`: Expand/collapse selected row
- `Esc`: Collapse expanded row

---

## Technical Notes

- Date format: `yyyy-mm-dd hh:mm`
- End time is set only by clicking "End", not manually.
- When displaying end time, always show start time as well.
- All logic and UI are contained in a single HTML file (see `task.html`).
