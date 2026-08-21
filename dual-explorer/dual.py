#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "pillow",
# ]
# ///

import ctypes
import json
import os
import platform
import queue
import shutil
import stat
import subprocess
import sys
import threading
import tkinter as tk
from collections import deque, namedtuple
from datetime import datetime, timedelta
from tkinter import messagebox, ttk
from pathlib import Path

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

# Ensure win.py resolves next to this script, independent of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))

if platform.system() == "Windows":
    try:
        import win as native  # native OS integration + OLE drag-out (Windows only)
    except ImportError:
        native = None
else:
    native = None

# ── Theme ────────────────────────────────────────────────────────────────────

# Centralized widget sizing.
LAYOUT = {
    "window_width": 1600,
    "window_height": 900,
    "toolbar_button_width": 3,
    "size_column_width": 90,
    "mtime_column_width": 140,
    "filter_label_padx": 6,
    "filter_label_pady": 2,
    "filter_label_offset_x": -4,
    "filter_label_offset_y": 4,
    "search_entry_width": 50,
    "mtime_format": "%Y-%m-%d %H:%M",
    "preview_width": 760,
    "preview_height": 600,
    "drag_tooltip_offset_x": 14,
    "drag_tooltip_offset_y": 10,
}

BUSY_STATUS = "Busy with another file operation, try again shortly"
PREVIEW_MAX_BYTES = 200_000  # cap preview reads to keep UI responsive
IMAGE_PREVIEW_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".ico", ".tiff"}

# Timing constants (kept separate from layout constants).
STATUS_MESSAGE_MS = 4000  # status message lifetime
DIRTY_POLL_MS = 300  # watcher dirty-flag poll interval
DROP_POLL_MS = 200  # native drop-queue poll interval
WATCH_POLL_INTERVAL_S = 1.0  # fallback watcher interval
SEARCH_BATCH_SIZE = 200  # search results per UI batch
SEARCH_STEP_DELAY_MS = 1  # delay between _search_step() batches
PREVIEW_BINDTAG = "DualExplorerPreview"
PREVIEW_TEXT_PASSTHROUGH_KEYS = {"space", "Tab"}

# UI labels/icons.
ICONS = {
    "path_menu": "📁▾",
    "favorite": "⭐",
    "refresh": "⟳",
    "search": "🔍 Search",
    "folder": "📁",
    "file": "📄",
    "edit": "📝 Edit (F4)",
    "copy": "📋 Copy (F5)",
    "move": "➡ Move (F6)",
    "new_folder": "🆕 New Folder (F7)",
    "compare": "⇄ Compare",
    "delete": "🗑 Delete",
}

# Theme-specific ttk style overrides.
STYLE_OVERRIDES = {
    "clam": {
        "TButton": {"padding": (2, 1)},
    },
    "vista": {},
}

COLOR_SCHEME = {
    "pane_active": "#eaf4fb",
    "pane_inactive": "#f5f5f5",
    "status_info_bg": "#e0e0e0",
    "status_info_fg": "black",
    "status_success_bg": "#2e7d32",
    "status_success_fg": "white",
    "status_error_bg": "#c62828",
    "status_error_fg": "white",
    "filter_label_bg": "#333333",
    "filter_label_fg": "white",
    "tag_only_here": "#ffd6d6",
    "tag_diff": "#fff3b0",
    "tag_just_transferred": "#a5d6a7",
}
# ─────────────────────────────────────────────────────────────────────────────


def apply_theme(root, theme_name):
    style = ttk.Style(root)
    style.theme_use(theme_name)
    for style_name, options in STYLE_OVERRIDES.get(theme_name, {}).items():
        style.configure(style_name, **options)

    theme_bg = style.lookup("TFrame", "background")
    if theme_bg:
        COLOR_SCHEME["status_info_bg"] = theme_bg


def make_button(parent, text, command, side="left", width=None, padx=(6, 0)):
    kwargs = {"text": text, "command": command, "takefocus": 0}
    if width is not None:
        kwargs["width"] = width
    button = ttk.Button(parent, **kwargs)
    button.pack(side=side, padx=padx)
    return button


def add_bindtag_tree(root_widget, bindtag):
    """Insert `bindtag` right after each widget's own tag so it runs
    before class bindings (e.g. Text), recursively for a widget subtree."""

    stack = [root_widget]

    while stack:
        widget = stack.pop()

        try:
            tags = widget.bindtags()
        except tk.TclError:
            continue

        if bindtag not in tags:
            widget.bindtags((tags[0], bindtag, *tags[1:]))

        try:
            stack.extend(widget.winfo_children())
        except tk.TclError:
            continue


# Category tags map a predicate to a highlight color.
RECENT_DELTA = timedelta(days=2)

Category = namedtuple("Category", ["match", "color"])


def _ext(entry):
    return os.path.splitext(entry.name)[1].lower()


def _is_dir(entry):
    try:
        return entry.is_dir()
    except OSError:
        return False


def _mtime(entry):
    try:
        return datetime.fromtimestamp(entry.stat().st_mtime)
    except OSError:
        return None


CATEGORIES = {
    "cat_script": Category(
        match=lambda entry: not _is_dir(entry) and _ext(entry) in {
            ".py", ".sh", ".bash", ".js", ".ts", ".ps1", ".psm1", ".bat", ".cmd",
            ".rb", ".pl", ".php", ".go", ".rs", ".java", ".c", ".cpp", ".h",
            ".mjs", ".vbs", ".lua", ".sql"
        },
        color="#e1bee7",
    ),
    "cat_image": Category(
        match=lambda entry: not _is_dir(entry) and _ext(entry) in {
            ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff"
        },
        color="#ffe0b2",
    ),
    "cat_archive": Category(
        match=lambda entry: not _is_dir(entry) and _ext(entry) in {
            ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"
        },
        color="#d7ccc8",
    ),
    "cat_doc": Category(
        match=lambda entry: not _is_dir(entry) and _ext(entry) in {
            ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".md", ".txt"
        },
        color="#b2dfdb",
    ),
    "cat_recent": Category(
        match=lambda entry: _mtime(entry) is not None and datetime.now() - _mtime(entry) < RECENT_DELTA,
        color="#bbdefb",
    ),
}


def format_size(num_bytes):

    if num_bytes is None:
        return ""

    size = float(num_bytes)

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024

    return ""


def categorize(entry):
    return tuple(
        tag for tag, category in CATEGORIES.items()
        if category.match(entry)
    )

CONFIG_PATH = Path.home() / ".dual_explorer.json"


def load_config():

    try:
        return json.loads(CONFIG_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(config):

    try:
        CONFIG_PATH.write_text(json.dumps(config, indent=2))
    except OSError:
        pass


def dir_signature(path):

    signature = {}

    try:
        for entry in os.scandir(path):
            try:
                stat = entry.stat()
                signature[entry.name] = (
                    entry.is_dir(),
                    stat.st_size,
                    int(stat.st_mtime)
                )
            except OSError:
                pass
    except OSError:
        pass

    return signature


def walk_entries(root):

    # BFS surfaces shallow matches earlier than DFS.
    root_len = len(root.rstrip("\\/")) + 1
    queue_ = deque([root])

    while queue_:

        try:
            entries = os.scandir(queue_.popleft())
        except OSError:
            continue

        with entries:
            for entry in entries:

                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue

                # Skip reparse points to avoid recursive loops.
                if is_dir and not _is_reparse_point(entry):
                    queue_.append(entry.path)

                yield entry, entry.path[root_len:], is_dir


def _is_reparse_point(entry):
    try:
        return bool(entry.stat(follow_symlinks=False).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (OSError, AttributeError):
        return False


def open_in_editor(paths):

    if isinstance(paths, str):
        paths = [paths]

    args = " ".join(f'"{path}"' for path in paths)
    # Accepted risk: paths are treated as trusted on local machine; user is responsible for ensuring they are safe to open.
    subprocess.Popen(f'code {args}', shell=True)


class _PollingWatcher:
    """Fallback watcher: poll directory mtime and call on_change() on updates."""

    def __init__(self, path, on_change, interval=WATCH_POLL_INTERVAL_S):
        self._on_change = on_change
        self._stop_event = threading.Event()
        self._last_mtime = os.stat(path).st_mtime  # raises OSError if path is bad

        self._thread = threading.Thread(target=self._run, args=(path, interval), daemon=True)
        self._thread.start()

    def _run(self, path, interval):
        while not self._stop_event.wait(interval):
            try:
                mtime = os.stat(path).st_mtime
            except OSError:
                continue

            if mtime != self._last_mtime:
                self._last_mtime = mtime
                self._on_change()

    def stop(self):
        self._stop_event.set()
        self._thread.join(timeout=1)




class Favorites:

    def __init__(self, config, save):
        self.config = config
        self.save = save

    def get(self):
        return self.config.setdefault("favorites", [])

    def add(self, path):
        favorites = self.get()
        if path not in favorites:
            favorites.append(path)
            self.save()

    def remove(self, path):
        favorites = self.get()
        if path in favorites:
            favorites.remove(path)
            self.save()


class Preview:
    """Shared preview window, positioned over the non-active pane."""

    def __init__(self, root):
        self.root = root
        self.window = None
        self.text = None
        self.image_label = None
        self._photo = None  # keep a reference so Tk doesn't garbage-collect it
        self._image_path = None  # currently shown image, if any -- redrawn on resize
        self._preview_token = 0  # bumped per request; discards stale background decodes
        self._last_size = None  # (width, height) last rendered at; detects real resizes
        self.pane = None

    def toggle(self, pane):
        if self.window:
            self.close()
        elif pane.tree.focus():
            self._open(pane)
        return "break"

    @staticmethod
    def _position_over_other_pane(pane, width, height):
        # Center over the non-active tree; fall back to the active tree.
        target = pane.other.tree if pane.other else pane.tree
        x = target.winfo_rootx() + (target.winfo_width() - width) // 2
        y = target.winfo_rooty() + (target.winfo_height() - height) // 2
        return x, y

    def _open(self, pane):

        width, height = LAYOUT["preview_width"], LAYOUT["preview_height"]
        x, y = self._position_over_other_pane(pane, width, height)

        preview_win = tk.Toplevel(self.root)
        preview_win.geometry(f"{width}x{height}+{x}+{y}")
        # Keep preview above its owner window.
        preview_win.transient(self.root)
        preview_win.bind("<Configure>", self._on_resize)
        preview_win.protocol("WM_DELETE_WINDOW", self.close)
        # Flush geometry so first image thumbnail uses real window size.
        preview_win.update_idletasks()

        text_widget = tk.Text(preview_win, wrap="none")
        scrollbar = ttk.Scrollbar(preview_win, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)

        # Read-only but selectable/copyable.
        text_widget.bind("<Key>", self._block_edit)

        copy_menu = tk.Menu(text_widget, tearoff=0)
        copy_menu.add_command(label="Copy", command=lambda: text_widget.event_generate("<<Copy>>"))
        text_widget.bind("<Button-3>", lambda e: copy_menu.tk_popup(e.x_root, e.y_root))

        image_label = tk.Label(preview_win, bg="black")

        self.window = preview_win
        self.text = text_widget
        self.scrollbar = scrollbar
        self.image_label = image_label

        # Apply preview-level key routing to child widgets.
        add_bindtag_tree(preview_win, PREVIEW_BINDTAG)
        # Keep initial focus on the tree for Quick Look-style navigation.
        self.update(pane)

    @staticmethod
    def _block_edit(event):
        if event.state & 0x4:  # Control held -- let Ctrl+C/Ctrl+A etc. through
            return None
        if event.keysym in PREVIEW_TEXT_PASSTHROUGH_KEYS:
            # Let preview-level bindtag shortcuts handle these keys.
            return None
        if event.keysym in ("BackSpace", "Delete"):
            return "break"
        if event.char and event.char.isprintable():
            return "break"
        return None

    def update(self, pane):

        if not self.window:
            return

        self.pane = pane
        item = pane.tree.focus()
        path = pane.current_path if not item else os.path.join(pane.current_path, pane.get_name(item))
        name = os.path.basename(path) or path

        self.window.title(name)

        if ImageTk is not None and os.path.isfile(path) and os.path.splitext(path)[1].lower() in IMAGE_PREVIEW_EXTENSIONS:
            self._show_image(path)
            return

        self._show_content(path)

    def _show_content(self, path):
        self._image_path = None
        self.image_label.pack_forget()
        self._photo = None

        self.text.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", self._read_content(path))

    def _show_image(self, path):
        self._image_path = path
        self.text.pack_forget()
        self.scrollbar.pack_forget()
        self.image_label.pack(fill="both", expand=True)

        # Decode/resize off-thread; token drops stale results.
        self._preview_token += 1
        token = self._preview_token
        width = max(self.window.winfo_width(), 1)
        height = max(self.window.winfo_height(), 1)
        self._last_size = (width, height)

        def worker():
            try:
                with Image.open(path) as image:
                    if image.mode not in ("RGB", "RGBA"):
                        image = image.convert("RGBA")
                    image.thumbnail((width, height))
                    # Detach pixel data from the file handle before handoff.
                    image.load()
            except Exception as e:
                self.root.after(0, self._apply_image_result, token, None, str(e))
                return
            self.root.after(0, self._apply_image_result, token, image, None)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_image_result(self, token, image, error):
        # Drop stale decode results.
        if token != self._preview_token or not self.window:
            return

        if error:
            self._photo = None
            self.image_label.configure(image="", text=f"(cannot preview image: {error})", fg="white")
            return

        self._photo = ImageTk.PhotoImage(image)
        self.image_label.configure(image=self._photo, text="")

    def _on_resize(self, event):
        # <Configure> fires on move too; re-render only on size change.
        if event.widget is not self.window or not self._image_path:
            return
        if (event.width, event.height) == self._last_size:
            return
        self._show_image(self._image_path)

    @staticmethod
    def _read_content(path):

        if os.path.isdir(path):
            return "(folder -- no preview)"

        try:
            with open(path, "rb") as f:
                chunk = f.read(PREVIEW_MAX_BYTES + 1)
        except OSError as e:
            return f"(cannot read: {e})"

        if b"\0" in chunk:
            return "(binary file -- no preview)"

        truncated = len(chunk) > PREVIEW_MAX_BYTES
        text = chunk[:PREVIEW_MAX_BYTES].decode("utf-8", errors="replace")

        return text + "\n\n... (truncated)" if truncated else text

    def on_selection_changed(self, pane):
        # Update only from the pane currently driving the preview.
        if self.window and self.pane is pane:
            self.update(pane)

    def on_active_pane_changed(self, pane):
        # Repoint and reposition preview when active pane changes.
        if self.window:
            width, height = LAYOUT["preview_width"], LAYOUT["preview_height"]
            x, y = self._position_over_other_pane(pane, width, height)
            self.window.geometry(f"+{x}+{y}")
            self.update(pane)

    def close(self):
        if self.window:
            self.window.destroy()
            self.window = None
            self.text = None
            self.image_label = None
            self._photo = None
            self._image_path = None
            pane, self.pane = self.pane, None
            if pane:
                pane.tree.focus_set()


class ExplorerPane:

    def __init__(self, parent, start_path, on_change=None, favorites=None, on_focus=None, preview=None):

        self.on_change = on_change
        self.favorites = favorites
        self.on_focus = on_focus
        self.preview = preview
        self.other = None
        self.drag_item = None
        self.drag_names = []
        self.drag_tooltip = None
        self.drop_target = None
        self.name_to_item = {}
        self.all_items = []
        self.category_tags = {}
        self.filter_query = ""
        self.search_token = 0
        self.search_active = False
        self.sort_column = "name"
        self.sort_reverse = False
        self.watcher = None
        self.watch_path = None
        self.dirty = False
        self.busy = False
        self.drop_queue = queue.Queue()

        self.frame = ttk.Frame(parent)

        toolbar = ttk.Frame(self.frame)
        toolbar.pack(fill="x")

        self.path_var = tk.StringVar(value=start_path)

        make_button(
            toolbar,
            ICONS["path_menu"],
            self.show_path_menu,
            width=LAYOUT["toolbar_button_width"],
            padx=(1,1)
        )

        self.path_entry = ttk.Entry(
            toolbar,
            textvariable=self.path_var,
            takefocus=0
        )
        self.path_entry.pack(
            side="left",
            fill="x",
            expand=True
        )

        self.path_var.trace_add(
            "write",
            lambda *a: self.path_entry.update()
        )

        self.path_entry.bind(
            "<Return>",
            lambda e: self.load_path(
                self.path_var.get()
            )
        )

        make_button(
            toolbar,
            ICONS["favorite"],
            self.show_favorites_menu,
            width=LAYOUT["toolbar_button_width"],
            padx=(1,1)
        )

        make_button(
            toolbar,
            ICONS["refresh"],
            self.refresh,
            width=LAYOUT["toolbar_button_width"],
            padx=(0,1)
        )

        tree_frame = ttk.Frame(self.frame)
        tree_frame.pack(fill="both", expand=True)

        self.style_name = f"Dual{id(self)}.Treeview"

        self.style = ttk.Style()
        self.style.configure(self.style_name)
        self.set_active(False)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("size", "mtime"),
            show="tree headings",
            style=self.style_name,
            selectmode="extended"
        )

        self.tree.heading("#0", command=lambda: self.sort_by("name"))
        self.tree.heading("size", command=lambda: self.sort_by("size"))
        self.tree.heading("mtime", command=lambda: self.sort_by("mtime"))
        self.tree.column("size", width=LAYOUT["size_column_width"], anchor="e", stretch=False)
        self.tree.column("mtime", width=LAYOUT["mtime_column_width"], anchor="w", stretch=False)
        self._update_heading_arrows()

        self.tree.tag_configure("only_here", background=COLOR_SCHEME["tag_only_here"])
        self.tree.tag_configure("diff", background=COLOR_SCHEME["tag_diff"])
        self.tree.tag_configure("just_transferred", background=COLOR_SCHEME["tag_just_transferred"])

        for tag, category in CATEGORIES.items():
            self.tree.tag_configure(tag, background=category.color)

        scrollbar = ttk.Scrollbar(
            tree_frame,
            orient="vertical",
            command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(
            side="left",
            fill="both",
            expand=True
        )
        scrollbar.pack(side="right", fill="y")

        self.filter_label = tk.Label(
            tree_frame,
            bg=COLOR_SCHEME["filter_label_bg"],
            fg=COLOR_SCHEME["filter_label_fg"],
            padx=LAYOUT["filter_label_padx"],
            pady=LAYOUT["filter_label_pady"]
        )

        self.tree.bind("<ButtonPress-1>", self.on_drag_start, add="+")
        self.tree.bind("<ButtonPress-1>", self.activate_pane, add="+")
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<B1-Motion>", self.on_drag_motion, add="+")
        self.tree.bind("<ButtonRelease-1>", self.on_drag_release, add="+")
        self.tree.bind("<Button-3>", self.on_right_click)
        self.tree.bind("<Key>", self.on_type, add="+")
        self.tree.bind("<Left>", lambda e: self.go_up())
        self.tree.bind("<Right>", self.on_right_key)
        self.tree.bind("<Return>", lambda e: self.enter_selected())
        self.tree.bind("<Up>", self.on_arrow_key, add="+")
        self.tree.bind("<Down>", self.on_arrow_key, add="+")
        self.tree.bind("<space>", self.on_space)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.preview.on_selection_changed(self), add="+")
        self.tree.bind("<<TreeviewSelect>>", self.activate_pane, add="+")
        self.tree.bind("<FocusIn>", self.activate_pane)

        if native is not None:
            try:
                self.drop_target = native.register_drop_target(self.tree.winfo_id(), self._on_native_drop)
            except OSError as e:
                print(f"[dual] failed to register drop target: {e!r}")

        self.context_menu = tk.Menu(self.tree, tearoff=0)
        self.context_menu.add_command(label="New Folder (N)", underline=12, command=self.new_folder)
        self.context_menu.add_command(label="New File (F)", underline=10, command=self.new_file)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Copy Path (C)", underline=11, command=self.copy_path)
        self.context_menu.add_command(label="Open in Editor (E)", underline=16, command=self.open_in_editor)
        self.context_menu.add_command(label="Open Terminal Here (T)", underline=20, command=self.open_terminal_here)
        self.context_menu.add_command(label="Reveal in Explorer (R)", underline=20, command=self.reveal_in_explorer)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Rename (F2)", command=self.rename_selected)
        self.context_menu.add_command(label="Delete (D)", underline=8, command=self.delete_selected)

        self.status_var = tk.StringVar()
        self.status_after_id = None

        self.status_label = tk.Label(
            self.frame,
            textvariable=self.status_var,
            anchor="w",
            bg=COLOR_SCHEME["status_info_bg"],
            fg=COLOR_SCHEME["status_info_fg"]
        )
        self.status_label.pack(side="bottom", fill="x")

        self.current_path = ""
        self.load_path(start_path)
        self.tree.after(DIRTY_POLL_MS, self._poll_dirty)
        self.tree.after(DROP_POLL_MS, self._poll_drops)

    def refresh(self):

        # Preserve selection/filter across reload.
        selected_names = self.get_selected_names()
        focus_name = self.get_name(self.tree.focus()) if self.tree.focus() else None
        filter_query = self.filter_query

        self.load_path(self.current_path)

        if filter_query:
            self.filter_query = filter_query
            self.apply_filter()

        items = [self.name_to_item[n] for n in selected_names if n in self.name_to_item]

        if not items:
            return

        self.tree.selection_set(items)
        focus_item = self.name_to_item.get(focus_name)
        self.tree.focus(focus_item if focus_item in items else items[-1])
        self.tree.see(items[-1])

    def activate_pane(self, event=None):
        if self.on_focus:
            self.on_focus(self)

    def set_active(self, active):

        color = COLOR_SCHEME["pane_active"] if active else COLOR_SCHEME["pane_inactive"]

        self.style.configure(
            self.style_name,
            background=color,
            fieldbackground=color
        )

    def set_status(self, text, kind="info"):

        colors = {
            "info": (COLOR_SCHEME["status_info_bg"], COLOR_SCHEME["status_info_fg"]),
            "success": (COLOR_SCHEME["status_success_bg"], COLOR_SCHEME["status_success_fg"]),
            "error": (COLOR_SCHEME["status_error_bg"], COLOR_SCHEME["status_error_fg"]),
        }

        bg, fg = colors[kind]
        self.status_var.set(text)
        self.status_label.configure(bg=bg, fg=fg)

        if self.status_after_id:
            self.tree.after_cancel(self.status_after_id)

        self.status_after_id = self.tree.after(STATUS_MESSAGE_MS, self.clear_status)

    def clear_status(self):
        self.status_var.set("")
        self.status_label.configure(bg=COLOR_SCHEME["status_info_bg"], fg=COLOR_SCHEME["status_info_fg"])
        self.status_after_id = None

    def _sort_value(self, entry):
        if self.sort_column == "size":
            try:
                return entry.stat().st_size
            except OSError:
                return 0
        if self.sort_column == "mtime":
            try:
                return entry.stat().st_mtime
            except OSError:
                return 0
        return entry.name.lower()

    def _update_heading_arrows(self):
        labels = {"name": ("#0", "Name"), "size": ("size", "Size"), "mtime": ("mtime", "Modified")}
        arrow = " ▼" if self.sort_reverse else " ▲"

        for key, (col, text) in labels.items():
            self.tree.heading(col, text=text + arrow if key == self.sort_column else text)

    def sort_by(self, column):
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = True

        self._update_heading_arrows()
        self.load_path(self.current_path)

    def load_path(self, path):

        if self.busy:
            # Warn only for real navigation, not same-path watcher refreshes.
            if path != self.current_path:
                self.set_status(BUSY_STATUS, "error")
            return

        if not os.path.isdir(path):
            return

        self.search_token += 1
        self.search_active = False
        self.current_path = path
        self.path_var.set(path)
        self._start_watch(path)

        if self.on_change:
            self.on_change(path)

        self.tree.delete(
            *self.tree.get_children()
        )

        self.name_to_item = {}
        self.all_items = []
        self.category_tags = {}
        self._reset_filter()

        try:
            entries = list(os.scandir(path))
            dirs = [e for e in entries if _is_dir(e)]
            files = [e for e in entries if not _is_dir(e)]
            dirs.sort(key=self._sort_value, reverse=self.sort_reverse)
            files.sort(key=self._sort_value, reverse=self.sort_reverse)
            entries = dirs + files

            for entry in entries:

                is_dir = _is_dir(entry)
                icon = ICONS["folder"] if is_dir else ICONS["file"]

                try:
                    stat = entry.stat()
                    mtime_dt = datetime.fromtimestamp(stat.st_mtime)
                    mtime = mtime_dt.strftime(LAYOUT["mtime_format"])
                    size = "" if is_dir else format_size(stat.st_size)
                except OSError:
                    mtime_dt = None
                    mtime = ""
                    size = ""

                tags = categorize(entry)

                item = self.tree.insert(
                    "",
                    "end",
                    text=f"{icon} {entry.name}",
                    values=(size, mtime),
                    tags=tags
                )

                self.name_to_item[entry.name] = item
                self.category_tags[entry.name] = tags
                self.all_items.append(item)

        except PermissionError:
            pass

        if self.preview.window and self.preview.pane is self:
            self.preview.update(self)

    def _start_watch(self, path):
        """(Re)point watcher at path; prefer native watcher, fallback to polling."""

        if path == self.watch_path and self.watcher is not None:
            return

        self._stop_watch()
        self.watch_path = path

        watcher_cls = native.DirectoryWatcher if native is not None else _PollingWatcher

        try:
            self.watcher = watcher_cls(path, self._mark_dirty)
        except OSError:
            self.watcher = None

    def _stop_watch(self):
        if self.watcher is not None:
            self.watcher.stop()
            self.watcher = None

    def _mark_dirty(self):
        # Watcher thread: set a flag only; Tk updates happen on main thread.
        self.dirty = True

    def _poll_dirty(self):
        # Defer watcher-driven refresh while search/bulk ops are active.
        if self.dirty and not self.search_active and not self.busy:
            self.dirty = False
            self.refresh()

        self.tree.after(DIRTY_POLL_MS, self._poll_dirty)

    def get_name(self, item):
        return self.tree.item(item, "text")[2:]

    def _remove_rows(self, names):
        # Remove known-gone rows in place instead of full reload.
        for name in names:
            item = self.name_to_item.pop(name, None)
            if item is None:
                continue
            if item in self.all_items:
                self.all_items.remove(item)
            self.category_tags.pop(name, None)
            self.tree.delete(item)

    def highlight(self, names):

        items = [self.name_to_item[n] for n in names if n in self.name_to_item]

        if not items:
            return

        for item in items:
            self.tree.item(item, tags=("just_transferred",))

        self.tree.selection_set(items)
        self.tree.focus(items[-1])
        self.tree.see(items[-1])

    def on_space(self, event):
        # While actively filtering, space should type into the filter instead
        # of toggling the preview.
        if self.filter_query:
            return self.on_type(event)
        self.preview.toggle(self)
        return "break"

    def on_type(self, event):

        if event.keysym == "BackSpace":
            if self.filter_query:
                self.filter_query = self.filter_query[:-1]
                self.apply_filter()
            else:
                self.go_up()
        elif not event.char or not event.char.isprintable():
            return
        else:
            self.filter_query += event.char
            self.apply_filter()

        return "break"

    def apply_filter(self):

        if not self.filter_query:
            self.filter_label.place_forget()
            for index, item in enumerate(self.all_items):
                self.tree.reattach(item, "", index)
            focus = self.tree.focus()
            if focus:
                self.tree.selection_set(focus)
            return

        self.filter_label.configure(text=f"Filter: {self.filter_query}")
        self.filter_label.place(
            in_=self.tree,
            relx=1.0,
            rely=0.0,
            anchor="ne",
            x=LAYOUT["filter_label_offset_x"],
            y=LAYOUT["filter_label_offset_y"]
        )

        query_lower = self.filter_query.lower()
        visible_index = 0
        visible_items = []

        for item in self.all_items:
            if query_lower in self.get_name(item).lower():
                self.tree.reattach(item, "", visible_index)
                visible_index += 1
                visible_items.append(item)
            else:
                self.tree.detach(item)

        if not visible_items:
            self.tree.selection_set()
            return

        current = self.tree.focus()
        target = current if current in visible_items else visible_items[0]

        self.tree.selection_set(target)
        self.tree.focus(target)
        self.tree.see(target)

    def cancel_filter(self, event=None):

        if not self.filter_query:
            return None

        self._reset_filter()
        self.apply_filter()

        return "break"

    def _reset_filter(self):
        self.filter_query = ""
        self.filter_label.place_forget()

    def get_selected_names(self):
        return [self.get_name(item) for item in self.tree.selection()]

    def get_selected_paths(self):

        names = self.get_selected_names()

        if not names:
            return [self.current_path]

        return [os.path.join(self.current_path, name) for name in names]

    def go_up(self):

        if self.search_active:
            self.clear_search()
            return

        child = self.current_path
        parent = Path(child).parent

        self.load_path(str(parent))

        item = self.name_to_item.get(Path(child).name)

        if item:
            self.tree.selection_set(item)
            self.tree.focus(item)
            self.tree.see(item)

    def on_double_click(self, event):
        if not self.tree.identify_row(event.y):
            return
        self.enter_selected()

    def on_arrow_key(self, event):

        if self.tree.focus():
            return

        children = self.tree.get_children()

        if not children:
            return

        item = children[0]
        self.tree.selection_set(item)
        self.tree.focus(item)
        self.tree.see(item)

        return "break"

    def on_right_key(self, event):
        self.enter_selected(allow_open_files=False)
        return "break"

    def enter_selected(self, allow_open_files=True):

        selected_names = self.get_selected_names()
        item = self.tree.focus()

        if selected_names:
            selected_paths = [os.path.join(self.current_path, name) for name in selected_names]
        elif item:
            selected_paths = [os.path.join(self.current_path, self.get_name(item))]
        else:
            selected_paths = [self.current_path]

        if len(selected_paths) == 1 and os.path.isdir(selected_paths[0]):
            self.load_path(selected_paths[0])
            return

        if not allow_open_files:
            return

        files = [path for path in selected_paths if os.path.isfile(path)]

        if len(files) == len(selected_paths):
            if self._require_native("open_file"):
                for path in files:
                    native.open_file(path)

    def close(self):
        self._stop_watch()

        if self.drop_target is not None:
            try:
                self.drop_target.close()
            except Exception as e:
                print(f"[dual] failed to close drop target: {e!r}")
            self.drop_target = None

    def _require_native(self, method_name):
        """Return True if `native` is loaded and exposes `method_name`,
        otherwise report a status message and return False."""
        if native is not None and hasattr(native, method_name):
            return True

        self.set_status(f"Native OS integration unavailable: cannot {method_name}", "error")
        return False

    def _guard_busy(self, other=None):
        """Return True (and report status) if this pane, or optionally
        `other`, is busy with a background file operation."""
        if self.busy or (other is not None and other.busy):
            self.set_status(BUSY_STATUS, "error")
            return True
        return False

    def _guard_search_active(self, phrase, target=None):
        """Return True (and report status) if `target` (default self) is
        showing search results, where an action described by `phrase`
        (e.g. "rename in", "paste into") can't be performed."""
        if (target or self).search_active:
            self.set_status(f"Cannot {phrase} search results", "error")
            return True
        return False

    def _run_async(self, work, on_done):
        """Run `work()` on a background thread so slow filesystem ops don't
        freeze the UI; `on_done(result)` runs back on the main thread."""

        def runner():
            try:
                result = work()
            except Exception as e:  # broad on purpose -- surfaced via status
                result = e
            self.tree.after(0, on_done, result)

        threading.Thread(target=runner, daemon=True).start()

    def _run_bulk(self, work, action_label, on_result, other=None):
        """Run a bulk file operation via _run_async. On completion, clears
        busy flag(s) (self, and `other` if given) and either reports a
        background exception via set_status, or forwards the (items,
        errors) result tuple to `on_result(items, errors)`."""

        def done(result):
            self.busy = False
            if other is not None:
                other.busy = False

            if isinstance(result, Exception):
                self.set_status(f"{action_label} failed: {result}", "error")
                return

            on_result(*result)

        self._run_async(work, done)

    def _resolve_overwrite(self, dst_or_items, dst_for_item=None):
        """Main-thread-only overwrite resolution.

        - Single mode: _resolve_overwrite(dst) -> bool
        - Batch mode: _resolve_overwrite(items, dst_for_item) -> (approved_items, skipped_count)
        """

        if dst_for_item is None:
            dst = dst_or_items

            if not os.path.exists(dst):
                return True

            return messagebox.askyesnocancel(
                "Overwrite",
                f"\"{dst}\" already exists. Overwrite?",
            )

        items = dst_or_items
        approved_items = []

        for item in items:
            if self._resolve_overwrite(dst_for_item(item)):
                approved_items.append(item)

        return approved_items, len(items) - len(approved_items)

    def _prepare_bulk_copy(self, src_paths, dst_dir, move=False):
        """Main-thread-only prep shared by paste and cross-pane transfer:
        resolve overwrite conflicts and same-location duplicates.

        Same-location items skip the overwrite prompt entirely -- for move
        they're a no-op (kept out of the result), for copy they duplicate
        under a unique name (kept in, handled later by _bulk_copy).

        Returns (to_process, skipped_count).
        """

        def dst_for(src):
            return os.path.join(dst_dir, os.path.basename(src))

        same_path = [p for p in src_paths if os.path.abspath(p) == os.path.abspath(dst_for(p))]
        other_paths = [p for p in src_paths if p not in same_path]

        to_process, skipped = self._resolve_overwrite(other_paths, dst_for)

        if move:
            skipped += len(same_path)
        else:
            to_process += same_path

        return to_process, skipped

    def search(self, query):

        self.search_token += 1

        if not query:
            self.load_path(self.current_path)
            return

        self.search_active = True
        self.tree.delete(*self.tree.get_children())
        self.name_to_item = {}
        self.all_items = []
        self.category_tags = {}
        self._reset_filter()
        self.set_status("Searching...", "info")

        generator = walk_entries(self.current_path)
        self._search_step(query.lower(), generator, self.search_token)

    def clear_search(self):
        self.load_path(self.current_path)

    def _search_step(self, query_lower, generator, token):

        if token != self.search_token:
            return

        for count, (entry, rel, is_dir) in enumerate(generator, start=1):

            if query_lower in entry.name.lower():

                icon = ICONS["folder"] if is_dir else ICONS["file"]

                try:
                    stat = entry.stat()
                    mtime_dt = datetime.fromtimestamp(stat.st_mtime)
                    mtime = mtime_dt.strftime(LAYOUT["mtime_format"])
                    size = "" if is_dir else format_size(stat.st_size)
                except OSError:
                    mtime_dt = None
                    mtime = ""
                    size = ""

                tags = categorize(entry)

                item = self.tree.insert(
                    "", "end", text=f"{icon} {rel}", values=(size, mtime), tags=tags
                )
                self.name_to_item[rel] = item
                self.category_tags[rel] = tags
                self.all_items.append(item)

            if count >= SEARCH_BATCH_SIZE:
                self.set_status(f"Searching... {len(self.all_items)} found", "info")
                self.tree.after(SEARCH_STEP_DELAY_MS, self._search_step, query_lower, generator, token)
                return

        self.set_status(f"Search complete: {len(self.all_items)} result(s)", "success")

    def compare_with(self, other_signature):

        own_signature = dir_signature(self.current_path)

        for name, item in self.name_to_item.items():

            if name not in other_signature:
                self.tree.item(item, tags=("only_here",))
                continue

            own = own_signature.get(name)
            other = other_signature.get(name)

            if own and other and own[1:] != other[1:]:
                self.tree.item(item, tags=("diff",))

    def clear_compare_tags(self):
        for name, item in self.name_to_item.items():
            self.tree.item(item, tags=self.category_tags.get(name, ()))

    def clear_multi_selection(self):

        selection = self.tree.selection()

        if len(selection) <= 1:
            return

        focus = self.tree.focus()
        target = focus if focus in selection else selection[0]

        self.tree.selection_set(target)

    def clear_selection(self):

        if not self.tree.selection():
            return

        self.tree.selection_set(())

    def show_path_menu(self):

        menu = tk.Menu(self.tree, tearoff=0)

        current = Path(self.current_path).resolve()
        ancestors = [current, *current.parents]

        for folder in ancestors:
            menu.add_command(
                label=str(folder),
                command=lambda p=folder: self.load_path(str(p)),
                state="disabled" if folder == current else "normal"
            )

        toolbar = self.path_entry.master
        menu.post(
            toolbar.winfo_rootx(),
            toolbar.winfo_rooty() + toolbar.winfo_height()
        )

    def show_favorites_menu(self):

        menu = tk.Menu(self.tree, tearoff=0)
        favorites = self.favorites.get()

        for index, fav in enumerate(favorites):
            if index < 10:
                hint = str((index + 1) % 10)
                menu.add_command(
                    label=f"{hint}  {fav}",
                    underline=0,
                    command=lambda p=fav: self.load_path(p)
                )
            else:
                menu.add_command(
                    label=fav,
                    command=lambda p=fav: self.load_path(p)
                )

        if favorites:
            menu.add_separator()

        if self.current_path in favorites:
            menu.add_command(
                label="- Remove current folder",
                underline=2,
                command=lambda: self.favorites.remove(self.current_path)
            )
        else:
            menu.add_command(
                label="+ Add current folder",
                underline=2,
                command=lambda: self.favorites.add(self.current_path)
            )

        menu.post(
            self.tree.winfo_rootx(),
            self.tree.winfo_rooty()
        )

    def on_right_click(self, event):

        item = self.tree.identify_row(event.y)

        if item and item not in self.tree.selection():
            self.tree.selection_set(item)
            self.tree.focus(item)

        self.context_menu.post(event.x_root, event.y_root)

    def on_context_menu_key(self, event=None):

        item = self.tree.focus()
        bbox = self.tree.bbox(item) if item else None

        if bbox:
            x = self.tree.winfo_rootx() + bbox[0]
            y = self.tree.winfo_rooty() + bbox[1] + bbox[3]
        else:
            x = self.tree.winfo_rootx()
            y = self.tree.winfo_rooty()

        self.context_menu.post(x, y)

        return "break"

    def copy_path(self):
        paths = self.get_selected_paths()
        self.tree.clipboard_clear()
        self.tree.clipboard_append("\n".join(paths))

    def _on_native_drop(self, paths, x, y):
        # OLE drop callback may be off the Tk thread; queue work for main loop.
        self.drop_queue.put(paths)

    def _poll_drops(self):

        while True:
            try:
                paths = self.drop_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_dropped_paths(paths)

        self.tree.after(DROP_POLL_MS, self._poll_drops)

    def _handle_dropped_paths(self, paths):

        if self._guard_search_active("drop into"):
            return

        self._start_paste(paths)

    def copy_selected_to_clipboard(self):

        if not self._require_native("set_clipboard_files"):
            return

        paths = self.get_selected_paths()

        if not paths:
            return

        try:
            native.set_clipboard_files(paths)
        except OSError as e:
            self.set_status(f"Failed to copy to clipboard: {e}", "error")
            return

        summary = os.path.basename(paths[0]) if len(paths) == 1 else f"{len(paths)} items"
        self.set_status(f"Copied {summary} to clipboard", "success")

    def paste_from_clipboard(self):

        if self._guard_search_active("paste into"):
            return

        if not self._require_native("get_clipboard_files"):
            return

        try:
            paths = native.get_clipboard_files()
        except OSError as e:
            self.set_status(f"Failed to read clipboard: {e}", "error")
            return

        if not paths:
            return

        self._start_paste(paths)

    def _start_paste(self, paths):

        if self._guard_busy():
            return

        dst_dir = self.current_path
        to_copy, skipped = self._prepare_bulk_copy(paths, dst_dir)

        if not to_copy:
            self._report_paste([], [], skipped)
            return

        self.busy = True
        self.set_status("Copying...", "info")

        self._run_bulk(
            lambda: self._bulk_copy(to_copy, dst_dir),
            "Copy",
            lambda transferred, errors: self._report_paste(transferred, errors, skipped),
        )

    def _bulk_copy(self, src_paths, dst_dir, move=False):

        transferred = []
        errors = []

        for src in src_paths:
            name = os.path.basename(src)
            dst = os.path.join(dst_dir, name)

            # Copying onto the same location duplicates under a new name
            # instead of overwriting (matching Explorer/Finder); move never
            # reaches here for the same location -- transfer() treats that
            # case as a no-op.
            if not move and os.path.abspath(src) == os.path.abspath(dst):
                name = self._unique_name_in(dst_dir, name)
                dst = os.path.join(dst_dir, name)

            try:
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)

                if move:
                    if os.path.isdir(src):
                        shutil.rmtree(src)
                    else:
                        os.remove(src)

                transferred.append(name)
            except OSError as e:
                errors.append(f"{name}: {e}")

        return transferred, errors

    def _report_paste(self, transferred, errors, skipped):

        kind = "error" if errors else "success"

        if errors:
            self.set_status(f"Failed to paste: {'; '.join(errors)}", "error")

        if not transferred:
            if skipped and not errors:
                self.set_status(f"Skipped {skipped} item(s)", "info")
            return

        summary = transferred[0] if len(transferred) == 1 else f"{len(transferred)} items"

        if skipped:
            summary += f" ({skipped} skipped)"

        self.set_status(f"Pasted {summary}", kind)
        self.refresh()
        self.highlight(transferred)

    def open_in_editor(self):
        open_in_editor(self.get_selected_paths())

    def new_folder(self):
        self._create_and_rename("New folder", os.mkdir)

    def new_file(self):
        self._create_and_rename("New file.txt", lambda path: open(path, "x").close())

    def _create_and_rename(self, base_name, create):

        if self._guard_search_active("create in"):
            return

        if self._guard_busy():
            return

        name = self._unique_name_in(self.current_path, base_name)
        path = os.path.join(self.current_path, name)

        try:
            create(path)
        except OSError as e:
            self.set_status(f"Failed to create {name}: {e}", "error")
            return

        self.refresh()
        self.highlight([name])
        self._start_rename(name)

    @staticmethod
    def _unique_name_in(dir_path, base_name):

        stem, ext = os.path.splitext(base_name)
        candidate = base_name
        counter = 2

        while os.path.exists(os.path.join(dir_path, candidate)):
            candidate = f"{stem} ({counter}){ext}"
            counter += 1

        return candidate

    def rename_selected(self):

        if self._guard_search_active("rename in"):
            return

        if self._guard_busy():
            return

        item = self.tree.focus()

        if not item:
            return

        self._start_rename(self.get_name(item))

    def _start_rename(self, name):
        """Overlay an Entry on the tree row for `name` (Explorer-style inline
        rename): Enter/losing focus commits, Escape cancels and keeps the
        current name."""

        item = self.name_to_item.get(name)
        bbox = self.tree.bbox(item, column="#0") if item else None

        if not bbox:
            return

        x, y, width, height = bbox

        entry = ttk.Entry(self.tree)
        entry.insert(0, name)
        entry.place(x=x, y=y, width=width, height=height)
        entry.focus_set()

        stem, ext = os.path.splitext(name)

        if ext and not os.path.isdir(os.path.join(self.current_path, name)):
            entry.select_range(0, len(stem))
        else:
            entry.select_range(0, tk.END)

        entry.icursor(tk.END)

        # keyboard focus always returns to the tree once this entry is gone
        entry.bind("<Destroy>", lambda e: self.tree.focus_set())

        done = False

        def commit(event=None):
            nonlocal done
            if not done:
                done = True
                new_name = entry.get().strip()
                entry.destroy()
                if new_name and new_name != name:
                    self._rename(name, new_name)
            return "break"

        def cancel(event=None):
            nonlocal done
            done = True
            entry.destroy()
            return "break"

        entry.bind("<Return>", commit)
        entry.bind("<Escape>", cancel)
        entry.bind("<FocusOut>", commit)

    def _rename(self, old_name, new_name):

        old_path = os.path.join(self.current_path, old_name)
        new_path = os.path.join(self.current_path, new_name)

        # Use normcase so case-only renames work on Windows.
        if os.path.normcase(old_path) != os.path.normcase(new_path) and os.path.exists(new_path):
            self.set_status(f"\"{new_name}\" already exists", "error")
            return

        try:
            os.rename(old_path, new_path)
        except OSError as e:
            self.set_status(f"Failed to rename: {e}", "error")
            return

        self.set_status(f"Renamed to {new_name}", "success")
        self.refresh()
        self.highlight([new_name])

    def open_terminal_here(self):

        if not self._require_native("open_terminal"):
            return

        path = self.get_selected_paths()[0]

        if os.path.isfile(path):
            path = os.path.dirname(path)

        native.open_terminal(path)

    def reveal_in_explorer(self):
        if not self._require_native("reveal_in_explorer"):
            return

        native.reveal_in_explorer(self.get_selected_paths()[0])

    def _delete_path(self, path):
        """Prefer Recycle Bin via native integration; fallback to permanent delete."""

        if native is not None and hasattr(native, "recycle"):
            native.recycle([path])
        elif os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)

    def delete_selected(self):

        if self._guard_busy():
            return

        names = self.get_selected_names()
        deleting_self = not names

        # No selection means delete current folder.
        entries = (
            [(None, self.current_path)] if deleting_self
            else [(n, os.path.join(self.current_path, n)) for n in names]
        )

        prompt = (
            f"Delete \"{entries[0][1]}\"?"
            if len(entries) == 1
            else f"Delete {len(entries)} items?"
        )

        if not messagebox.askyesnocancel("Delete", prompt):
            return

        self.busy = True
        self.set_status("Deleting...", "info")

        self._run_bulk(
            lambda: self._delete_entries(entries),
            "Delete",
            lambda deleted, errors: self._report_delete(deleted, errors, deleting_self),
        )

    def _delete_entries(self, entries):

        deleted = []
        errors = []

        for name, path in entries:
            try:
                self._delete_path(path)
                deleted.append(name or os.path.basename(path))
            except OSError as e:
                errors.append(f"{os.path.basename(path)}: {e}")

        return deleted, errors

    def _report_delete(self, deleted, errors, deleting_self):

        if errors:
            messagebox.showerror("Delete failed", "\n".join(errors))
            self.set_status(f"Failed to delete: {'; '.join(errors)}", "error")

        if deleted:
            summary = deleted[0] if len(deleted) == 1 else f"{len(deleted)} items"
            self.set_status(f"Deleted {summary}", "success")

        if not deleting_self:
            self._remove_rows(deleted)
        elif not errors:
            self.go_up()

    def on_drag_start(self, event):
        self.drag_item = self.tree.identify_row(event.y)
        self.drag_names = []

        if not self.drag_item:
            return

        selection = self.tree.selection()

        if self.drag_item in selection and len(selection) > 1:
            self.drag_names = [self.get_name(i) for i in selection]
            # Keep existing multi-selection when drag starts on a selected row.
            self.activate_pane()
            self.tree.focus(self.drag_item)
            return "break"
        else:
            self.drag_names = [self.get_name(self.drag_item)]

    def on_drag_motion(self, event):

        if not self.drag_item:
            return

        self._show_drag_tooltip(event)

        if native is None:
            return

        # None means cursor left this Tk app (e.g., over Explorer/Notepad).
        outside = self.tree.winfo_containing(event.x_root, event.y_root) is None

        if not outside:
            return

        item = self.drag_item
        self.drag_item = None  # native drag now owns pointer flow
        self._hide_drag_tooltip()

        names = self.drag_names or [self.get_name(item)]
        paths = [os.path.join(self.current_path, name) for name in names]

        # Release Tk mouse capture before native DoDragDrop.
        ctypes.windll.user32.ReleaseCapture()

        try:
            effect = native.drag_files(paths)
        except OSError as e:
            print(f"[dual] native drag failed: {e!r}")
            self.set_status(f"Drag failed: {e}", "error")
            return

        summary = names[0] if len(names) == 1 else f"{len(names)} items"

        if effect == native.DROPEFFECT_MOVE:
            self.set_status(f"Moved {summary}", "success")
            self.refresh()
        elif effect != native.DROPEFFECT_NONE:
            # Some targets report COPY but only consume/open the file path.
            self.set_status(f"Dragged {summary}", "success")

    def _show_drag_tooltip(self, event):

        if self.drag_tooltip is None:
            names = self.drag_names

            if not names and self.drag_item:
                names = [self.get_name(self.drag_item)]

            text = names[0] if len(names) == 1 else f"{len(names)} items"

            tip = tk.Toplevel(self.tree)
            tip.overrideredirect(True)
            tip.attributes("-topmost", True)
            tk.Label(
                tip,
                text=text,
                bg=COLOR_SCHEME["filter_label_bg"],
                fg=COLOR_SCHEME["filter_label_fg"],
                padx=LAYOUT["filter_label_padx"],
                pady=LAYOUT["filter_label_pady"]
            ).pack()
            self.drag_tooltip = tip

        self.drag_tooltip.geometry(
            f"+{event.x_root + LAYOUT['drag_tooltip_offset_x']}"
            f"+{event.y_root + LAYOUT['drag_tooltip_offset_y']}"
        )

    def _hide_drag_tooltip(self):

        if self.drag_tooltip is not None:
            self.drag_tooltip.destroy()
            self.drag_tooltip = None

    def cancel_drag(self):
        """Clear drag state if gesture was interrupted and release event is missed."""
        self.drag_item = None
        self.drag_names = []
        self._hide_drag_tooltip()

    def on_drag_release(self, event):

        item = self.drag_item
        names = self.drag_names
        self.drag_item = None
        self.drag_names = []
        self._hide_drag_tooltip()

        if not item or not self.other:
            return

        target = self.tree.winfo_containing(event.x_root, event.y_root)

        if target is not self.other.tree:
            return

        if not names:
            names = [self.get_name(item)]

        self.transfer(names)

    def transfer_selected(self, move=False):

        names = self.get_selected_names()

        if not names:
            return

        self.transfer(names, move=move)

    def transfer(self, names, move=False):

        if not self.other:
            return

        if self._guard_search_active("copy/move into", target=self.other):
            return

        if self._guard_busy(other=self.other):
            return

        if isinstance(names, str):
            names = [names]

        # Snapshot paths in case either pane navigates during transfer.
        src_dir = self.current_path
        dst_dir = self.other.current_path
        src_paths = [os.path.join(src_dir, name) for name in names]

        to_transfer, skipped = self._prepare_bulk_copy(src_paths, dst_dir, move=move)

        if not to_transfer:
            self._report_transfer([], [], skipped, move)
            return

        self.busy = True
        self.other.busy = True
        self.set_status(f"{'Moving' if move else 'Copying'}...", "info")

        self._run_bulk(
            lambda: self._bulk_copy(to_transfer, dst_dir, move=move),
            "Move" if move else "Copy",
            lambda transferred, errors: self._report_transfer(transferred, errors, skipped, move),
            other=self.other,
        )

    def _report_transfer(self, transferred, errors, skipped, move):

        kind = "error" if errors else "success"

        if errors:
            self.set_status(f"Failed to {'move' if move else 'copy'}: {'; '.join(errors)}", "error")

        if not transferred:
            if skipped and not errors:
                self.set_status(f"Skipped {skipped} item(s)", "info")
            return

        verb = "Moved" if move else "Copied"
        summary = os.path.basename(transferred[0]) if len(transferred) == 1 else f"{len(transferred)} items"

        if skipped:
            summary += f" ({skipped} skipped)"

        message = f"{verb} {summary} to {self.other.current_path}"
        self.set_status(message, kind)

        dest_names = [os.path.basename(name) for name in transferred]
        self.other.refresh()
        self.other.highlight(dest_names)

        if move:
            self._remove_rows(transferred)


class DualExplorer:

    def __init__(self, root):

        self.root = root

        root.title("Dual Explorer")

        self.config = load_config()
        apply_theme(root, self.config.get("theme", "vista"))

        width, height = LAYOUT["window_width"], LAYOUT["window_height"]
        x = (root.winfo_screenwidth() - width) // 2
        y = 20

        root.geometry(f"{width}x{height}+{x}+{y}")

        root.bind_all("<Escape>", lambda e: self.handle_escape())
        root.bind_all("<Delete>", lambda e: self.delete_active(e))
        root.bind_all("<F2>", lambda e: self.rename_active(e))
        root.bind_all("<F4>", lambda e: self.edit_active(e))
        root.bind_all("<F5>", lambda e: self.transfer_active(event=e))
        root.bind_all("<F6>", lambda e: self.transfer_active(move=True, event=e))
        root.bind_all("<F7>", lambda e: self.new_folder_active(e))
        root.bind_all("<Shift-F10>", lambda e: self.context_menu_active(e))
        root.bind_all("<Alt-F4>", self.close)
        root.bind_all("<Control-w>", self.close)
        root.bind_all("<Control-l>", lambda e: self.focus_active_address())
        root.bind_all("<Control-f>", lambda e: self.focus_search())
        root.bind_all("<Control-d>", lambda e: self.favorites_active())
        root.bind_all("<Control-c>", lambda e: self.copy_active_to_clipboard(e))
        root.bind_all("<Control-v>", lambda e: self.paste_active_from_clipboard(e))
        root.bind_all("<Control-g>", lambda e: self.open_terminal_active(e))
        root.bind_all("<Control-n>", lambda e: self.new_folder_active(e))
        root.bind_all("<Control-backslash>", lambda e: self.path_menu_active())
        root.bind("<Deactivate>", lambda e: self.cancel_drags())

        root.bind_class(PREVIEW_BINDTAG, "<Tab>", lambda e: self.switch_active_pane())
        root.bind_class(PREVIEW_BINDTAG, "<space>", lambda e: self.preview.close() or "break")

        self.favorites = Favorites(self.config, self.save_config)
        self.preview = Preview(root)

        top_toolbar = ttk.Frame(root, padding=(6, 6))
        top_toolbar.pack(fill="x")

        self.search_var = tk.StringVar()

        make_button(
            top_toolbar,
            ICONS["search"],
            self.run_search,
            side="right"
        )

        search_entry = ttk.Entry(
            top_toolbar,
            textvariable=self.search_var,
            width=LAYOUT["search_entry_width"],
            takefocus=0
        )
        search_entry.pack(side="right")
        search_entry.bind("<Return>", lambda e: self.run_search())

        self.search_var.trace_add(
            "write",
            lambda *a: search_entry.update()
        )

        self.search_entry = search_entry

        bottom_toolbar = ttk.Frame(root, padding=(6, 6))
        bottom_toolbar.pack(side="bottom", fill="x")

        make_button(
            bottom_toolbar,
            ICONS["edit"],
            self.edit_active
        )

        make_button(
            bottom_toolbar,
            ICONS["copy"],
            lambda: self.transfer_active()
        )

        make_button(
            bottom_toolbar,
            ICONS["move"],
            lambda: self.transfer_active(move=True)
        )

        make_button(
            bottom_toolbar,
            ICONS["new_folder"],
            self.new_folder_active
        )

        make_button(
            bottom_toolbar,
            ICONS["delete"],
            self.delete_active,
        )

        make_button(
            bottom_toolbar,
            ICONS["compare"],
            self.compare
        )

        self.active_pane = None

        paned = ttk.PanedWindow(
            root,
            orient="horizontal"
        )

        paned.pack(
            fill="both",
            expand=True
        )

        self.left = ExplorerPane(
            paned,
            self.config.get(
                "left",
                os.environ.get("OneDrive", str(Path.home()))
            ),
            on_change=lambda p: self.remember("left", p),
            favorites=self.favorites,
            on_focus=self.set_active_pane,
            preview=self.preview
        )

        self.right = ExplorerPane(
            paned,
            self.config.get(
                "right",
                str(Path.home())
            ),
            on_change=lambda p: self.remember("right", p),
            favorites=self.favorites,
            on_focus=self.set_active_pane,
            preview=self.preview
        )

        self.left.other = self.right
        self.right.other = self.left

        paned.add(self.left.frame, weight=1)
        paned.add(self.right.frame, weight=1)

        self.right.tree.focus_set()
        self.set_active_pane(self.right)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def set_active_pane(self, pane):
        self.active_pane = pane
        self.left.set_active(pane is self.left)
        self.right.set_active(pane is self.right)
        self.preview.on_active_pane_changed(pane)

    def run_search(self):
        if self.active_pane:
            self.active_pane.search(self.search_var.get())

    def edit_active(self, event=None):
        if event is not None and self._focus_outside_trees(event):
            return None
        if self.active_pane:
            self.active_pane.open_in_editor()
        return "break"

    def new_folder_active(self, event=None):
        if event is not None and self._focus_outside_trees(event):
            return None
        if self.active_pane:
            self.active_pane.new_folder()
        return "break"

    def rename_active(self, event=None):
        if event is not None and self._focus_outside_trees(event):
            return None
        if self.active_pane:
            self.active_pane.rename_selected()
        return "break"

    def transfer_active(self, move=False, event=None):
        if event is not None and self._focus_outside_trees(event):
            return None
        if self.active_pane:
            self.active_pane.transfer_selected(move=move)
        return "break"

    def favorites_active(self):
        if self.active_pane:
            self.active_pane.show_favorites_menu()

    def path_menu_active(self):
        if self.active_pane:
            self.active_pane.show_path_menu()

    def _focus_outside_trees(self, event):
        # Limit pane shortcuts to tree widgets; keep normal behavior elsewhere.
        return event.widget not in (self.left.tree, self.right.tree)

    def delete_active(self, event=None):
        if event is not None and self._focus_outside_trees(event):
            return None
        if self.active_pane:
            self.active_pane.delete_selected()
        return "break"

    def copy_active_to_clipboard(self, event=None):
        if event is not None and self._focus_outside_trees(event):
            return None
        if self.active_pane:
            self.active_pane.copy_selected_to_clipboard()
        return "break"

    def paste_active_from_clipboard(self, event=None):
        if event is not None and self._focus_outside_trees(event):
            return None
        if self.active_pane:
            self.active_pane.paste_from_clipboard()
        return "break"

    def open_terminal_active(self, event=None):
        if event is not None and self._focus_outside_trees(event):
            return None
        if self.active_pane:
            self.active_pane.open_terminal_here()
        return "break"

    def context_menu_active(self, event=None):
        if event is not None and self._focus_outside_trees(event):
            return None
        if self.active_pane:
            self.active_pane.on_context_menu_key()
        return "break"

    def switch_active_pane(self):
        # Bound on preview bindtag so Tab still toggles panes from preview widgets.
        other = self.left if self.active_pane is self.right else self.right
        other.tree.focus_set()
        self.set_active_pane(other)
        return "break"


    def cancel_drags(self):
        self.left.cancel_drag()
        self.right.cancel_drag()

    def close(self, event=None):
        self.cancel_drags()
        self.preview.close()
        self.left.close()
        self.right.close()
        self.root.destroy()
        return "break"

    def focus_search(self):
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, tk.END)
        return "break"

    def focus_active_address(self):
        if self.active_pane:
            self.active_pane.path_entry.focus_set()
            self.active_pane.path_entry.selection_range(0, tk.END)
        return "break"

    def handle_escape(self):

        # Cancel one active layer per Esc press.
        pane = self.active_pane

        if pane is None:
            return

        if self.preview.window:
            self.preview.close()
            return

        if pane.filter_query:
            pane.cancel_filter()
            return

        if pane.search_active:
            pane.clear_search()
            self.search_var.set("")
            return

        if len(pane.tree.selection()) > 1:
            pane.clear_multi_selection()
            return

        if pane.tree.selection():
            pane.clear_selection()
            return

        self.left.clear_compare_tags()
        self.right.clear_compare_tags()

    def remember(self, side, path):

        # Ignore same-path refresh callbacks; persist only real navigation.
        if self.config.get(side) == path:
            return

        self.config[side] = path
        save_config(self.config)

        pane = getattr(self, side, None)

        if pane is not None and pane is self.active_pane:
            self.search_var.set("")

    def save_config(self):
        save_config(self.config)

    def compare(self):
        left_sig = dir_signature(self.left.current_path)
        right_sig = dir_signature(self.right.current_path)
        self.left.compare_with(right_sig)
        self.right.compare_with(left_sig)


root = tk.Tk()
root.withdraw()  # avoid unsized flash during startup

app = DualExplorer(root)

root.deiconify()
root.lift()

if native is None:
    print("[dual] win.py not available: native OS integration disabled "
          "(Open Terminal, Reveal in Explorer, clipboard files, drag-out will not work)")
    messagebox.showwarning(
        "Limited functionality",
        "win.py could not be loaded, so native OS integration is unavailable:\n"
        "Open Terminal, Reveal in Explorer, clipboard files (Ctrl+C/V), and drag-out to other apps will not work."
    )

# Restore tree focus after deiconify/warning dialog.
if app.active_pane:
    app.active_pane.tree.focus_force()

root.mainloop()
