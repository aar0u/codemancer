#!/usr/bin/env python3
"""Generic log highlighter: colors by keyword/pattern, not a fixed format.

Usage:
    python3 tail /path/to/app.log      # follow a file (like tail -f)
    tail -f app.log | python3 tail     # read from stdin
    python3 tail --gui /path/to/app.log
    tail -f app.log | python3 tail --gui  # pipe into the GUI viewer
"""
import os
import queue
from collections import deque
import re
import sys
import threading
import time

try:
    import tkinter as tk
    from tkinter import filedialog, ttk
except ImportError:
    tk = None
    ttk = None
    filedialog = None


def _enable_windows_ansi():
    """cmd.exe needs VT processing enabled to render ANSI colors."""
    if sys.platform != "win32":
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32
    ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
    handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
    mode = ctypes.c_uint32()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)


_enable_windows_ansi()

RESET = "\033[0m"

# Piped stdin has no "last N lines" concept (there's no file to seek back
# into), so --gui shows everything it receives - capped here to bound memory.
STDIN_GUI_MAX_LINES = 50_000


def _hex_to_ansi_truecolor(hex_color: str) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return f"\033[38;2;{r};{g};{b}m"


# Nord palette, keyed by purpose rather than color name.
THEME_HEX = {
    "muted": "#4C566A",
    "logger": "#88C0D0",
    "quote": "#D08770",
    "error": "#BF616A",
    "warn": "#EBCB8B",
    "info": "#A3BE8C",
    "debug": "#81A1C1",
    "bracket0": "#5E81AC",
    "bracket1": "#B48EAD",
    "bracket2": "#8FBCBB",
}

# Symbolic color keys shared by both renderers: ANSI (CLI, truecolor) and Tk (--gui).
ANSI_COLORS = {key: _hex_to_ansi_truecolor(hex_color) for key, hex_color in THEME_HEX.items()}

BRACKET_PALETTE = [key for key in THEME_HEX if key.startswith("bracket")]

BRACKET_PAIRS = {"(": ")", "{": "}", "[": "]"}
BRACKET_CLOSERS = set(BRACKET_PAIRS.values())

LEVEL_COLOR_KEYS = {
    "FATAL": "error",
    "CRITICAL": "error",
    "SEVERE": "error",
    "ERROR": "error",
    "WARN":  "warn",
    "INFO":  "info",
    "DEBUG": "debug",
    "TRACE": "muted",
}

# Level keyword as a whole word, regardless of surrounding format.
LEVEL_RE = re.compile(
    r"\b(?P<level>FATAL|CRITICAL|ERROR|SEVERE|WARNING|WARN|INFO|DEBUG|TRACE)\b"
)

# Java/.NET style logger token: dot-separated segments, optional :line.
LOGGER_RE = re.compile(r"(?:^|(?<=[\s\[]))[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*){2,}(?::\d+)?\b")

ALERT_RE = re.compile(r"\b(failed|failure|exception|timeout|retry|panic|could not)\b", re.IGNORECASE)

# Timestamps: 2026-08-19 10:00:00.123 / 2026-08-19T10:00:00Z / 20260818 09:21:00,1402920
# / 20-Aug-2026 16:58:26:246 / 19/08/2026 10:00:00 / 08-19-26 10:00:00 (day/month order
# is ambiguous and irrelevant here - we're only highlighting, not parsing dates).
_DATE_YMD = r"\d{4}[-/]\d{2}[-/]\d{2}"
_DATE_NUMERIC = r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}"
_DATE_MONTH_NAME = r"\d{1,2}[-/ ][A-Za-z]{3,9}[-/ ]\d{2,4}"
_TIME = r"\d{2}:\d{2}:\d{2}(?:[.,:]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
TIMESTAMP_RE = re.compile(
    rf"\b(?:{_DATE_YMD}|{_DATE_NUMERIC}|{_DATE_MONTH_NAME})[ T]{_TIME}"
    rf"|\b\d{{8}} {_TIME}"
)


STACK_TRACE_RE = re.compile(
    r"^\s*(at |Caused by:|\.\.\. \d+ (more|common frames omitted)|Traceback \(most recent call last\)|File \"|panic:|goroutine )"
)


def _ranges_overlap(start: int, end: int, ranges) -> bool:
    for r_start, r_end in ranges:
        if start < r_end and end > r_start:
            return True
    return False


class _PairScanner:
    """Escape-aware scan for quotes and () {} [] pairs; depth cycles
    through BRACKET_PALETTE, mismatches flagged red.
    """

    def __init__(self, text: str):
        self.text = text
        self.n = len(text)
        self.pair_spans = []
        self.quote_ranges = []
        self.bracket_stack = []  # entries: (open_char, open_idx, depth)
        self.in_quote = None
        self.quote_start = -1

    def scan(self):
        i = 0
        while i < self.n:
            i = self._step(i)
        for _, open_idx, _ in self.bracket_stack:
            self.pair_spans.append((open_idx, open_idx + 1, "error", 15))
        return self.pair_spans, self.quote_ranges

    def _step(self, i: int) -> int:
        ch = self.text[i]
        if ch == "\\" and i + 1 < self.n:
            return i + 2
        if self.in_quote:
            return self._close_quote_if_matching(i, ch)
        if ch in ("'", '"'):
            self.in_quote = ch
            self.quote_start = i
            return i + 1
        if ch in BRACKET_PAIRS:
            self.bracket_stack.append((ch, i, len(self.bracket_stack)))
            return i + 1
        if ch in BRACKET_CLOSERS:
            self._close_bracket(i, ch)
            return i + 1
        return i + 1

    def _close_quote_if_matching(self, i: int, ch: str) -> int:
        if ch == self.in_quote:
            self.quote_ranges.append((self.quote_start, i + 1))
            self.pair_spans.append((self.quote_start, self.quote_start + 1, "quote", 60))
            self.pair_spans.append((i, i + 1, "quote", 60))
            self.in_quote = None
        return i + 1

    def _close_bracket(self, i: int, ch: str) -> None:
        if self.bracket_stack and BRACKET_PAIRS[self.bracket_stack[-1][0]] == ch:
            _, open_idx, depth = self.bracket_stack.pop()
            color = BRACKET_PALETTE[depth % len(BRACKET_PALETTE)]
            self.pair_spans.append((open_idx, open_idx + 1, color, 15))
            self.pair_spans.append((i, i + 1, color, 15))
        else:
            self.pair_spans.append((i, i + 1, "error", 15))


def _add_regex_spans(raw, spans, pattern, span_color, priority, *, count=0, skip_ranges=None, color_for_match=None):
    matched = 0
    for m in pattern.finditer(raw):
        start, end = m.span()
        if skip_ranges and _ranges_overlap(start, end, skip_ranges):
            continue
        current_color = color_for_match(m) if color_for_match else span_color
        if current_color:
            spans.append((start, end, current_color, priority))
        matched += 1
        if count and matched >= count:
            break


def _level_color_for_match(m) -> str:
    level = m.group("level").upper()
    return LEVEL_COLOR_KEYS.get("WARN" if level == "WARNING" else level, "")


def compute_spans(raw: str):
    """Returns [(start, end, color_key, priority)] for a line; shared by
    the CLI (ANSI) and --gui (Tk) renderers.
    """
    if STACK_TRACE_RE.match(raw):
        return [(0, len(raw), "muted", 100)]

    pair_spans, quote_ranges = _PairScanner(raw).scan()
    spans = list(pair_spans)

    _add_regex_spans(raw, spans, LOGGER_RE, "logger", 20, count=1, skip_ranges=quote_ranges)
    _add_regex_spans(raw, spans, ALERT_RE, "error", 30)
    _add_regex_spans(raw, spans, TIMESTAMP_RE, "muted", 40)
    _add_regex_spans(raw, spans, LEVEL_RE, None, 50, count=1, color_for_match=_level_color_for_match)

    return spans


def _resolve_line_styles(raw_len: int, spans):
    """Merge spans by priority into a per-index color-key array."""
    style_by_index = [None] * raw_len
    priority_by_index = [-1] * raw_len
    for start, end, color_key, priority in spans:
        start = max(0, min(start, raw_len))
        end = max(0, min(end, raw_len))
        for i in range(start, end):
            if priority >= priority_by_index[i]:
                priority_by_index[i] = priority
                style_by_index[i] = color_key
    return style_by_index


def _render_ansi(raw: str, style_by_index) -> str:
    out = []
    current = None
    for i, ch in enumerate(raw):
        target = style_by_index[i]
        if target != current:
            if current is not None:
                out.append(RESET)
            if target is not None:
                out.append(ANSI_COLORS[target])
            current = target
        out.append(ch)

    if current is not None:
        out.append(RESET)

    return "".join(out)


def highlight(line: str) -> str:
    raw = line.rstrip("\n")
    spans = compute_spans(raw)
    if not spans:
        return raw

    style_by_index = _resolve_line_styles(len(raw), spans)
    return _render_ansi(raw, style_by_index)


def read_tail_lines(path: str, num_lines: int):
    """Read the last num_lines without loading the whole file. Returns (lines, file_size)."""
    file_size = os.path.getsize(path)
    with open(path, "rb") as f:
        position = file_size
        chunks = []
        newline_count = 0
        while position > 0 and newline_count <= num_lines:
            size = min(8192, position)
            position -= size
            f.seek(position)
            chunk = f.read(size)
            chunks.append(chunk)
            newline_count += chunk.count(b"\n")

    content = b"".join(reversed(chunks))
    lines = content.decode("utf-8", errors="replace").replace("\0", "").splitlines()[-num_lines:]
    return lines, file_size


def read_marker(path: str, position: int) -> bytes:
    with open(path, "rb") as f:
        f.seek(max(0, position - 64))
        return f.read(min(64, position))


def follow(path: str, num_lines: int = 10):
    lines, position = read_tail_lines(path, num_lines)
    for line in lines:
        print(highlight(line))
    stat = os.stat(path)
    file_id = stat.st_dev, stat.st_ino
    marker = read_marker(path, position)
    while True:
        try:
            stat = os.stat(path)
            rotated = ((stat.st_dev, stat.st_ino) != file_id or stat.st_size < position
                       or stat.st_size >= position and read_marker(path, position) != marker)
            if rotated:
                lines, position = read_tail_lines(path, num_lines)
                file_id = stat.st_dev, stat.st_ino
                for line in lines:
                    print(highlight(line))
            elif stat.st_size > position:
                with open(path, "rb") as f:
                    f.seek(position)
                    for raw_line in f:
                        for line in raw_line.decode("utf-8", errors="replace").replace("\0", "").splitlines():
                            print(highlight(line))
                    position = f.tell()
            marker = read_marker(path, position)
        except OSError:
            pass
        time.sleep(0.3)


def read_stdin():
    for line in sys.stdin:
        print(highlight(line))


def parse_args(argv):
    """tail-style flags: -f/-F/--follow (no-op), -n/--lines N, --gui."""
    path = None
    num_lines = 10
    gui = False
    skip_next = False
    for arg in argv:
        if skip_next:
            num_lines = int(arg)
            skip_next = False
            continue
        if arg == "--gui":
            gui = True
            continue
        if arg in ("-f", "--follow", "-F"):
            continue
        if arg in ("-n", "--lines"):
            skip_next = True
            continue
        if arg.startswith("-n"):
            num_lines = int(arg[2:])
            continue
        if arg.startswith("--lines="):
            num_lines = int(arg.split("=", 1)[1])
            continue
        if arg.startswith("-"):
            raise ValueError(f"Unknown option: {arg}")
        path = arg
    if skip_next:
        raise ValueError("-n/--lines requires a value")
    if num_lines <= 0:
        raise ValueError("lines must be positive")
    return path, num_lines, gui


class TailGUI:
    def __init__(self, root, log_file_path, max_lines, stdin_mode=False):
        self.root = root
        self.log_file_path = log_file_path
        self.stdin_mode = stdin_mode
        self.max_lines = STDIN_GUI_MAX_LINES if stdin_mode else max_lines
        self.last_position = 0
        self.last_file_id = None
        self.last_marker = None
        self.timer_id = None
        self.search_matches = []
        self.search_match_idx = -1

        root.title("Tail GUI")
        root.geometry("1000x600")

        controls = ttk.Frame(root, padding=8)
        controls.pack(fill=tk.X)
        self.open_file_button = ttk.Button(controls, text="Open file", command=self.open_file)
        self.open_file_button.pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(controls, text="Lines:").pack(side=tk.LEFT)
        self.line_count_input = ttk.Entry(controls, width=8)
        self.line_count_input.insert(0, str(self.max_lines))
        self.line_count_input.pack(side=tk.LEFT, padx=(4, 12))
        if stdin_mode:
            # Stdin is unseekable and already fully consumed by the reader
            # thread, so re-reading a file or changing the buffer cap live
            # doesn't apply here.
            self.open_file_button.configure(state=tk.DISABLED)
            self.line_count_input.configure(state=tk.DISABLED)

        self.wrap_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="Wrap", variable=self.wrap_var, command=self.toggle_wrap).pack(
            side=tk.LEFT, padx=(0, 12)
        )

        ttk.Label(controls, text="Search:").pack(side=tk.LEFT, padx=(0, 4))
        self.search_input = ttk.Entry(controls, width=20)
        self.search_input.pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Prev", command=self.find_prev).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls, text="Next", command=self.find_next).pack(side=tk.LEFT, padx=2)
        self.search_status = ttk.Label(controls, text="")
        self.search_status.pack(side=tk.LEFT, padx=(4, 0))

        text_frame = ttk.Frame(root)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 0))

        self.log_display = tk.Text(text_frame, wrap=tk.NONE, state=tk.DISABLED, font="TkFixedFont", bg="#1e1e1e", fg="#d4d4d4")
        self.log_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for key, color in THEME_HEX.items():
            self.log_display.tag_configure(key, foreground=color)
        self.log_display.tag_configure("search_hit", background="#5a5a00")
        self.log_display.tag_configure("search_current", background="#c07800", foreground="#000000")

        self.v_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.log_display.yview)
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_display.configure(yscrollcommand=self.v_scroll.set)

        self.h_scroll = ttk.Scrollbar(root, orient="horizontal", command=self.log_display.xview)
        self.h_scroll.pack(fill=tk.X, padx=8, pady=(0, 8))
        self.log_display.configure(xscrollcommand=self.h_scroll.set)

        self.line_count_input.bind("<Return>", self.apply_settings)
        self.line_count_input.bind("<FocusOut>", self.apply_settings)
        self.search_input.bind("<Return>", self.find_next)
        self.search_input.bind("<Shift-Return>", self.find_prev)
        self.search_input.bind("<KeyRelease>", self._on_search_text_changed)
        if stdin_mode:
            self._stdin_queue = queue.Queue(maxsize=STDIN_GUI_MAX_LINES)
            threading.Thread(target=self._read_stdin, daemon=True).start()
            self._poll_stdin_queue()
        else:
            self.refresh(force_reload=True)

    def _read_stdin(self):
        """Runs on a background thread; the Tk main loop can't block on stdin."""
        for line in sys.stdin:
            self._stdin_queue.put(line.rstrip("\n"))
        self._stdin_queue.put(None)  # sentinel: stdin closed

    def _poll_stdin_queue(self):
        if self.log_display.tag_ranges("sel"):
            self.root.title("Tail GUI [PAUSED]")
            self.root.after(200, self._poll_stdin_queue)
            return
        lines = []
        closed = False
        try:
            while True:
                item = self._stdin_queue.get_nowait()
                if item is None:
                    closed = True
                    break
                lines.append(item)
        except queue.Empty:
            pass
        if lines:
            self.append_lines(lines)
        self.root.title("Tail GUI (stdin closed)" if closed else "Tail GUI (stdin)")
        if not closed:
            self.root.after(200, self._poll_stdin_queue)

    def toggle_wrap(self):
        if self.wrap_var.get():
            self.log_display.configure(wrap=tk.WORD)
            self.h_scroll.pack_forget()
        else:
            self.log_display.configure(wrap=tk.NONE)
            self.h_scroll.pack(fill=tk.X, padx=8, pady=(0, 8))

    def _on_search_text_changed(self, event=None):
        # Ignore Return here - find_next/find_prev already handle it, and
        # KeyRelease also fires for Return, which would reset the position.
        if event is not None and event.keysym == "Return":
            return
        self._update_search_matches()

    def _update_search_matches(self, preserve_current=False):
        previous_match_idx = self.search_match_idx if preserve_current else -1
        self.log_display.tag_remove("search_hit", "1.0", tk.END)
        self.log_display.tag_remove("search_current", "1.0", tk.END)
        self.search_matches = []
        self.search_match_idx = -1
        query = self.search_input.get()
        if not query:
            self.search_status.configure(text="")
            return
        start = "1.0"
        while True:
            pos = self.log_display.search(query, start, tk.END, nocase=True)
            if not pos:
                break
            end = f"{pos}+{len(query)}c"
            self.search_matches.append((pos, end))
            self.log_display.tag_add("search_hit", pos, end)
            start = end
        if previous_match_idx >= 0 and self.search_matches:
            self._goto_match(min(previous_match_idx, len(self.search_matches) - 1))
        else:
            self.search_status.configure(
                text=f"{len(self.search_matches)} matches" if self.search_matches else "no matches"
            )

    def _goto_match(self, idx):
        if not self.search_matches:
            return
        idx = idx % len(self.search_matches)
        self.search_match_idx = idx
        self.log_display.tag_remove("search_current", "1.0", tk.END)
        pos, end = self.search_matches[idx]
        self.log_display.tag_add("search_current", pos, end)
        self.log_display.see(pos)
        self.search_status.configure(text=f"{idx + 1}/{len(self.search_matches)} matches")

    def find_next(self, _event=None):
        if not self.search_matches:
            self._update_search_matches()
        if self.search_matches:
            self._goto_match(self.search_match_idx + 1)

    def find_prev(self, _event=None):
        if not self.search_matches:
            self._update_search_matches()
        if self.search_matches:
            self._goto_match(self.search_match_idx - 1)

    def open_file(self):
        file_path = filedialog.askopenfilename()
        if not file_path:
            return
        self.log_file_path = file_path
        self.last_position = 0
        self.last_file_id = None
        self.last_marker = None
        self.refresh(force_reload=True)

    def apply_settings(self, _event=None):
        try:
            max_lines = int(self.line_count_input.get())
            if max_lines <= 0:
                raise ValueError
        except ValueError:
            self.line_count_input.delete(0, tk.END)
            self.line_count_input.insert(0, str(self.max_lines))
            return
        self.max_lines = max_lines
        self.refresh(force_reload=True)

    def refresh(self, force_reload=False):
        if self.timer_id is not None:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None
        self.update_log_content(force_reload)

    def schedule_update(self):
        if self.timer_id is None:
            self.timer_id = self.root.after(500, self.run_scheduled_update)

    def run_scheduled_update(self):
        self.timer_id = None
        self.update_log_content()

    def _reload_from_scratch(self):
        lines, self.last_position = read_tail_lines(self.log_file_path, self.max_lines)
        self.set_lines(lines)

    def _append_new_bytes(self):
        with open(self.log_file_path, "rb") as f:
            f.seek(self.last_position - 1)
            continues_previous_line = f.read(1) != b"\n"
            f.seek(self.last_position)
            lines = deque(maxlen=self.max_lines)
            dropped_lines = False
            for raw_line in f:
                for line in raw_line.decode("utf-8", errors="replace").replace("\0", "").splitlines():
                    dropped_lines |= len(lines) == lines.maxlen
                    lines.append(line)
            self.last_position = f.tell()
        if lines:
            self.append_lines(list(lines), continues_previous_line and not dropped_lines)

    def update_log_content(self, force_reload=False):
        if self.log_display.tag_ranges("sel"):
            self.root.title("Tail GUI [PAUSED]")
            self.schedule_update()
            return
        self.root.title("Tail GUI")
        try:
            stat = os.stat(self.log_file_path)
            file_id = stat.st_dev, stat.st_ino
            needs_reload = (force_reload or self.last_position == 0 or self.last_position > stat.st_size
                            or self.last_file_id is not None and self.last_file_id != file_id
                            or self.last_marker is not None and stat.st_size >= self.last_position
                            and read_marker(self.log_file_path, self.last_position) != self.last_marker)
            if needs_reload:
                self._reload_from_scratch()
            elif self.last_position < stat.st_size:
                self._append_new_bytes()
            self.last_file_id = file_id
            self.last_marker = read_marker(self.log_file_path, self.last_position)
        except OSError as error:
            self.set_lines([f"Error reading file: {error}"])
        finally:
            self.schedule_update()

    def render_line(self, raw_line):
        self.log_display.insert(tk.END, raw_line + "\n")
        line_index = self.log_display.index(f"{tk.END}-2l")
        for start, end, color_key, _priority in compute_spans(raw_line):
            self.log_display.tag_add(color_key, f"{line_index}+{start}c", f"{line_index}+{end}c")

    def _display_lines(self, lines, *, clear):
        self.log_display.configure(state=tk.NORMAL)
        if clear:
            self.log_display.delete("1.0", tk.END)
        for line in lines:
            self.render_line(line)
        if not clear:
            total_lines = int(self.log_display.index(f"{tk.END}-1c").split(".")[0]) - 1
            if total_lines > self.max_lines:
                self.log_display.delete("1.0", f"{total_lines - self.max_lines + 1}.0")
        self.log_display.see(tk.END)
        self.log_display.configure(state=tk.DISABLED)
        self._update_search_matches(preserve_current=True)

    def set_lines(self, lines):
        self._display_lines(lines, clear=True)

    def append_lines(self, lines, continues_previous_line=False):
        self.log_display.configure(state=tk.NORMAL)
        if continues_previous_line and lines:
            line_start = self.log_display.index(f"{tk.END}-2l linestart")
            previous_line = self.log_display.get(line_start, f"{tk.END}-1c")
            self.log_display.delete(line_start, tk.END)
            self.render_line(previous_line + lines[0])
            lines = lines[1:]
        for line in lines:
            self.render_line(line)
        total_lines = int(self.log_display.index(f"{tk.END}-1c").split(".")[0]) - 1
        if total_lines > self.max_lines:
            self.log_display.delete("1.0", f"{total_lines - self.max_lines + 1}.0")
        self.log_display.see(tk.END)
        self.log_display.configure(state=tk.DISABLED)
        self._update_search_matches(preserve_current=True)


def run_gui(path, num_lines, stdin_mode=False):
    if tk is None:
        raise RuntimeError("tkinter is not available in this environment")
    root = tk.Tk()
    TailGUI(root, path or "sample.log", num_lines, stdin_mode=stdin_mode)
    root.mainloop()


USAGE = f"""Generic log highlighter (colors by keyword/pattern, not a fixed format).

Usage:
  python3 tail /path/to/app.log        Follow a file (like tail -f)
  tail -f app.log | python3 tail       Read from a pipe
  python3 tail --gui /path/to/app.log  Open the Tkinter viewer

Options:
  -f, --follow, -F     No-op (this tool always follows)
  -n N, --lines=N      Number of initial lines to print (default 10)
  --gui                Launch the GUI instead of the CLI. Reads a file if given,
                       otherwise piped stdin (buffers up to {STDIN_GUI_MAX_LINES}
                       lines to bound memory; the Lines field is unused there).
"""


if __name__ == "__main__":
    try:
        file_path, lines_to_show, gui_mode = parse_args(sys.argv[1:])
        if gui_mode:
            run_gui(file_path, lines_to_show, stdin_mode=not file_path and not sys.stdin.isatty())
        # If input is piped, process stdin stream first (e.g. grep ... | tail).
        elif not sys.stdin.isatty() and not file_path:
            read_stdin()
        elif file_path:
            follow(file_path, lines_to_show)
        elif sys.stdin.isatty():
            # No file, no pipe, no --gui: nothing to read - show usage instead
            # of silently blocking on interactive stdin.
            print(USAGE)
    except KeyboardInterrupt:
        pass
    except ValueError as error:
        print(error, file=sys.stderr)
        raise SystemExit(2)
