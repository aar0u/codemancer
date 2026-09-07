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
STDIN_GUI_MAX_LINES = 5_000

# CLI output must stay near the live end of a busy log. Keep a small newest-only
# buffer and emit at most this many lines per update; terminal rendering is slow.
CLI_PENDING_MAX_LINES = 1_000
CLI_BATCH_MAX_LINES = 200
MAX_INCREMENTAL_READ_BYTES = 64 * 1024
SEARCH_DEBOUNCE_MS = 250
# Full-buffer search rescans are chunked by wall-clock time (not match count)
# so a common keyword on a large, tag-heavy buffer can't block the UI in one
# long call; the inter-chunk delay leaves Tk room to service input.
SEARCH_SCAN_CHUNK_BUDGET_S = 0.015
SEARCH_SCAN_CHUNK_DELAY_MS = 10
# Not just a scan-time bound: once search_hit tags number in the thousands,
# Tk's Text widget gets dramatically slower at EVERYTHING (scroll measured at
# ~1000x, not just search) for as long as those tags stay applied - so this
# has to stay small, not just "large but finite".
SEARCH_MAX_MATCHES = 200


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


def read_appended_lines(path: str, position: int, max_lines: int):
    """Return bounded appended lines without making a busy tail catch up forever."""
    file_size = os.path.getsize(path)
    if file_size - position > MAX_INCREMENTAL_READ_BYTES:
        lines, position = read_tail_lines(path, max_lines)
        return lines, position, False, True
    with open(path, "rb") as f:
        f.seek(position - 1)
        continues_previous_line = f.read(1) != b"\n"
        f.seek(position)
        lines = deque(maxlen=max_lines)
        skipped = 0
        for raw_line in f:
            for line in raw_line.decode("utf-8", errors="replace").replace("\0", "").splitlines():
                skipped += len(lines) == lines.maxlen
                lines.append(line)
        return list(lines), f.tell(), continues_previous_line and not skipped, skipped


def _print_cli_lines(lines, skipped=0):
    if skipped:
        print(f"[tail-viewer skipped {skipped} stale lines]")
    color = not skipped and len(lines) < CLI_BATCH_MAX_LINES
    for line in lines:
        print(highlight(line) if color else line)


def follow(path: str, num_lines: int = 10):
    lines, position = read_tail_lines(path, num_lines)
    _print_cli_lines(lines)
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
                _print_cli_lines(lines)
            elif stat.st_size > position:
                lines, position, _continues, skipped = read_appended_lines(path, position, CLI_BATCH_MAX_LINES)
                _print_cli_lines(lines, skipped)
            marker = read_marker(path, position)
        except OSError:
            pass
        time.sleep(0.3)


def read_stdin():
    pending = deque(maxlen=CLI_PENDING_MAX_LINES)
    condition = threading.Condition()
    closed = False
    skipped = 0

    def reader():
        nonlocal closed, skipped
        for line in sys.stdin:
            with condition:
                if len(pending) == pending.maxlen:
                    skipped += 1
                pending.append(line.rstrip("\n"))
                condition.notify()
        with condition:
            closed = True
            condition.notify()

    threading.Thread(target=reader, daemon=True).start()
    while True:
        with condition:
            while not pending and not closed:
                condition.wait()
            if not pending and closed:
                return
            batch_skipped, skipped = skipped, 0
            while len(pending) > CLI_BATCH_MAX_LINES:
                pending.popleft()
                batch_skipped += 1
            lines = list(pending)
            pending.clear()
        _print_cli_lines(lines, batch_skipped)


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
        self.search_timer_id = None
        self.search_scan_timer_id = None
        self._search_scan_query = None
        self._search_scan_on_complete = None
        self._search_scan_match_count = 0
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
            # Stdin is unseekable, so re-reading or changing the buffer cap doesn't apply.
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
        self.resume_button = ttk.Button(controls, text="Resume", command=self.resume_tail, state=tk.DISABLED)
        self.resume_button.pack(side=tk.LEFT, padx=(12, 0))

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
            self._stdin_queue = queue.Queue(maxsize=CLI_PENDING_MAX_LINES)
            self._stdin_dropped = 0
            self._stdin_dropped_lock = threading.Lock()
            self._stdin_closed = False
            threading.Thread(target=self._read_stdin, daemon=True).start()
            self._poll_stdin_queue()
        else:
            self.refresh(force_reload=True)

    def _read_stdin(self):
        """Runs on a background thread; the Tk main loop can't block on stdin."""
        drop_streak = 0
        for line in sys.stdin:
            try:
                self._stdin_queue.put_nowait(line.rstrip("\n"))
                drop_streak = 0
            except queue.Full:
                try:
                    self._stdin_queue.get_nowait()
                except queue.Empty:
                    pass
                else:
                    with self._stdin_dropped_lock:
                        self._stdin_dropped += 1
                self._stdin_queue.put_nowait(line.rstrip("\n"))
                # A never-blocking loop this tight starves the Tk thread of the
                # GIL under a heavy flood (worst on Windows); sleep() forces a
                # real handoff.
                drop_streak += 1
                if drop_streak % 500 == 0:
                    time.sleep(0.001)
        # Independent of the sentinel below, which only surfaces once drained -
        # doesn't happen while paused, but "closed" should still show then.
        self._stdin_closed = True
        while True:
            try:
                self._stdin_queue.put_nowait(None)  # sentinel: stdin closed
                return
            except queue.Full:
                try:
                    self._stdin_queue.get_nowait()
                except queue.Empty:
                    pass

    def _base_title(self):
        if not self.stdin_mode:
            return "Tail GUI"
        return "Tail GUI (stdin closed)" if self._stdin_closed else "Tail GUI (stdin)"

    def _scrolled_away_from_bottom(self):
        # bbox is exact; a yview() fraction threshold isn't (.see(tk.END) can land short of 1.0).
        return self.log_display.bbox(f"{tk.END}-1c") is None

    def _poll_stdin_queue(self):
        if self.log_display.tag_ranges("sel") or self._scrolled_away_from_bottom():
            self.resume_button.configure(state=tk.NORMAL)
            self.root.title(self._base_title())
            self.root.after(200, self._poll_stdin_queue)
            return
        self.resume_button.configure(state=tk.DISABLED)
        lines = []
        closed = False
        with self._stdin_dropped_lock:
            dropped = self._stdin_dropped
            self._stdin_dropped = 0
        try:
            while self._stdin_queue.qsize() > CLI_BATCH_MAX_LINES:
                self._stdin_queue.get_nowait()
                dropped += 1
            while len(lines) < CLI_BATCH_MAX_LINES:
                item = self._stdin_queue.get_nowait()
                if item is None:
                    closed = True
                    break
                lines.append(item)
        except queue.Empty:
            pass
        if lines:
            # Dropped lines were never shown, so the buffer isn't stale - keep appending, don't wipe it.
            self.append_lines(lines)
        title = "Tail GUI (stdin closed)" if closed else "Tail GUI (stdin)"
        if dropped:
            title += f" [skipped {dropped}]"
        self.root.title(title)
        if not closed:
            self.root.after(200, self._poll_stdin_queue)

    def resume_tail(self):
        """Snap back to the bottom and clear any selection, resuming tail-follow."""
        self.log_display.tag_remove("sel", "1.0", tk.END)
        self.log_display.see(tk.END)

    def toggle_wrap(self):
        if self.wrap_var.get():
            self.log_display.configure(wrap=tk.WORD)
            self.h_scroll.pack_forget()
        else:
            self.log_display.configure(wrap=tk.NONE)
            self.h_scroll.pack(fill=tk.X, padx=8, pady=(0, 8))

    def _cancel_scheduled_search(self):
        if self.search_timer_id is not None:
            self.root.after_cancel(self.search_timer_id)
            self.search_timer_id = None

    def _on_search_text_changed(self, event=None):
        # Ignore Return here - find_next/find_prev already handle it.
        if event is not None and event.keysym == "Return":
            return
        self._cancel_scheduled_search()
        self.search_timer_id = self.root.after(SEARCH_DEBOUNCE_MS, self._run_scheduled_search)

    def _run_scheduled_search(self):
        self.search_timer_id = None
        self._update_search_matches()

    def _search_hit_ranges(self):
        """Live match list read straight from tags - no separate Python list to
        keep in sync, and edits (inserts/trims) update tags for free."""
        ranges = self.log_display.tag_ranges("search_hit")
        return [(str(ranges[i]), str(ranges[i + 1])) for i in range(0, len(ranges), 2)]

    def _find_and_tag_hits(self, start, end, query):
        while True:
            pos = self.log_display.search(query, start, end, nocase=True)
            if not pos:
                break
            match_end = f"{pos}+{len(query)}c"
            self.log_display.tag_add("search_hit", pos, match_end)
            start = match_end

    def _match_count_label(self, count):
        return f"{SEARCH_MAX_MATCHES}+" if count >= SEARCH_MAX_MATCHES else str(count)

    def _match_status_text(self, count):
        return f"{self._match_count_label(count)} matches" if count else "no matches"

    def _add_incremental_search_hits(self, start_index):
        """Scan only newly-inserted text instead of rescanning the whole
        buffer - keeps the search responsive while lines keep arriving."""
        query = self.search_input.get()
        if not query:
            return
        matches = self._search_hit_ranges()
        if len(matches) < SEARCH_MAX_MATCHES:
            self._find_and_tag_hits(start_index, tk.END, query)
            matches = self._search_hit_ranges()
        if self.search_match_idx >= 0 and not self.log_display.tag_ranges("search_current"):
            self.search_match_idx = -1
        if self.search_match_idx >= 0:
            self.search_status.configure(text=f"{self.search_match_idx + 1}/{self._match_count_label(len(matches))} matches")
        else:
            self.search_status.configure(text=self._match_status_text(len(matches)))

    def _cancel_search_scan(self):
        if self.search_scan_timer_id is not None:
            self.root.after_cancel(self.search_scan_timer_id)
            self.search_scan_timer_id = None
        if self._search_scan_query is not None:
            self.log_display.mark_unset("_search_scan_pos")
            self.log_display.mark_unset("_search_scan_end")
            self._search_scan_query = None
            self._search_scan_on_complete = None

    def _start_full_search_scan(self, on_complete):
        """Rebuilds search_hit tags for the whole buffer, a time-budgeted
        chunk at a time (see SEARCH_SCAN_CHUNK_BUDGET_S) instead of in one
        blocking call."""
        self._cancel_search_scan()
        self.log_display.tag_remove("search_hit", "1.0", tk.END)
        self.log_display.tag_remove("search_current", "1.0", tk.END)
        self.search_match_idx = -1
        query = self.search_input.get()
        if not query:
            self.search_status.configure(text="")
            return
        self.search_status.configure(text="searching…")
        # Marks (not plain index strings) auto-adjust if lines get trimmed
        # mid-scan. _search_scan_end snapshots the buffer's current end with
        # left gravity, so it stays put as new lines keep arriving - unlike
        # tk.END (re-evaluated live), which would let a busy incoming stream
        # keep the scan chasing a moving target indefinitely.
        self.log_display.mark_set("_search_scan_pos", "1.0")
        self.log_display.mark_set("_search_scan_end", "end-1c")
        self.log_display.mark_gravity("_search_scan_end", tk.LEFT)
        self._search_scan_query = query
        self._search_scan_on_complete = on_complete
        self._search_scan_match_count = 0
        self._run_search_scan_chunk()

    def _finish_search_scan(self):
        self.log_display.mark_unset("_search_scan_pos")
        self.log_display.mark_unset("_search_scan_end")
        self._search_scan_query = None
        self.search_scan_timer_id = None
        on_complete = self._search_scan_on_complete
        self._search_scan_on_complete = None
        on_complete()

    def _run_search_scan_chunk(self):
        query = self._search_scan_query
        deadline = time.monotonic() + SEARCH_SCAN_CHUNK_BUDGET_S
        while time.monotonic() < deadline:
            if self._search_scan_match_count >= SEARCH_MAX_MATCHES:
                self._finish_search_scan()
                return
            pos = self.log_display.index("_search_scan_pos")
            end = self.log_display.index("_search_scan_end")
            found = self.log_display.search(query, pos, end, nocase=True)
            if not found:
                self._finish_search_scan()
                return
            match_end = f"{found}+{len(query)}c"
            self.log_display.tag_add("search_hit", found, match_end)
            self.log_display.mark_set("_search_scan_pos", match_end)
            self._search_scan_match_count += 1
        self.search_scan_timer_id = self.root.after(SEARCH_SCAN_CHUNK_DELAY_MS, self._run_search_scan_chunk)

    def _report_match_count(self, preserve_idx=-1):
        matches = self._search_hit_ranges()
        if preserve_idx >= 0 and matches:
            self._goto_match(min(preserve_idx, len(matches) - 1))
        else:
            self.search_status.configure(text=self._match_status_text(len(matches)))

    def _update_search_matches(self, preserve_current=False):
        previous_match_idx = self.search_match_idx if preserve_current else -1
        self._start_full_search_scan(lambda: self._report_match_count(previous_match_idx))

    def _goto_match(self, idx):
        matches = self._search_hit_ranges()
        if not matches:
            # Reached via find_next/find_prev after a scan that found nothing -
            # without this, the status would stay stuck on "searching..." forever.
            self.search_status.configure(text=self._match_status_text(0))
            return
        idx = idx % len(matches)
        self.search_match_idx = idx
        self.log_display.tag_remove("search_current", "1.0", tk.END)
        pos, end = matches[idx]
        self.log_display.tag_add("search_current", pos, end)
        self.log_display.see(pos)
        self.search_status.configure(text=f"{idx + 1}/{self._match_count_label(len(matches))} matches")

    def find_next(self, _event=None):
        pending_search = self.search_timer_id is not None
        self._cancel_scheduled_search()
        if pending_search or self._search_scan_query is not None or not self._search_hit_ranges():
            self._start_full_search_scan(lambda: self._goto_match(self.search_match_idx + 1))
        else:
            self._goto_match(self.search_match_idx + 1)

    def find_prev(self, _event=None):
        pending_search = self.search_timer_id is not None
        self._cancel_scheduled_search()
        if pending_search or self._search_scan_query is not None or not self._search_hit_ranges():
            self._start_full_search_scan(lambda: self._goto_match(self.search_match_idx - 1))
        else:
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
        lines, self.last_position, continues_previous_line, dropped = read_appended_lines(
            self.log_file_path, self.last_position, CLI_BATCH_MAX_LINES
        )
        if dropped is True:
            # Jumped far ahead - prior buffer is now a discontinuous gap, so start over.
            self.set_lines(lines)
        elif lines:
            # A bounded in-window skip; history is still contiguous, so keep appending.
            self.append_lines(lines, continues_previous_line)

    def update_log_content(self, force_reload=False):
        # Selection always pauses; scrolled-away-from-bottom only pauses passive tail-follow.
        if self.log_display.tag_ranges("sel") or (not force_reload and self._scrolled_away_from_bottom()):
            self.resume_button.configure(state=tk.NORMAL)
            self.root.title(self._base_title())
            self.schedule_update()
            return
        self.resume_button.configure(state=tk.DISABLED)
        self.root.title(self._base_title())
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

    def render_lines(self, lines):
        # Bulk-insert all lines in one Tcl call, then tag colors as a separate pass.
        # With wrap=word, each individual insert() forces Tk to re-run line-wrap
        # layout; N single-line inserts measured ~10x slower than one N-line insert.
        if not lines:
            return
        start_line = int(self.log_display.index(f"{tk.END}-1c").split(".")[0])
        self.log_display.insert(tk.END, "\n".join(lines) + "\n")
        for offset, raw_line in enumerate(lines):
            line_index = f"{start_line + offset}.0"
            for start, end, color_key, _priority in compute_spans(raw_line):
                self.log_display.tag_add(color_key, f"{line_index}+{start}c", f"{line_index}+{end}c")

    def set_lines(self, lines):
        self.log_display.configure(state=tk.NORMAL)
        self.log_display.delete("1.0", tk.END)
        self.render_lines(lines)
        self.log_display.see(tk.END)
        self.log_display.configure(state=tk.DISABLED)
        self._update_search_matches(preserve_current=True)

    def append_lines(self, lines, continues_previous_line=False):
        self.log_display.configure(state=tk.NORMAL)
        rendered_count = 0
        if continues_previous_line and lines:
            line_start = self.log_display.index(f"{tk.END}-2l linestart")
            previous_line = self.log_display.get(line_start, f"{tk.END}-1c")
            self.log_display.delete(line_start, tk.END)
            self.render_line(previous_line + lines[0])
            rendered_count += 1
            lines = lines[1:]
        self.render_lines(lines)
        rendered_count += len(lines)
        total_lines = int(self.log_display.index(f"{tk.END}-1c").split(".")[0]) - 1
        if total_lines > self.max_lines:
            self.log_display.delete("1.0", f"{total_lines - self.max_lines + 1}.0")
            total_lines = self.max_lines
        self.log_display.see(tk.END)
        self.log_display.configure(state=tk.DISABLED)
        # Only newly (re-)rendered lines can contain new matches - rescan just that tail.
        scan_start_line = max(1, total_lines - rendered_count + 1)
        self._add_incremental_search_hits(f"{scan_start_line}.0")


def run_gui(path, num_lines, stdin_mode=False):
    if tk is None:
        raise RuntimeError("tkinter is not available in this environment")
    if sys.platform == "win32":
        # Windows' default ~15.6ms timer tick means Tk's after()-based polling
        # (search scan chunks, stdin drain) can silently double in latency
        # whenever some other process on the system stops holding a
        # higher-resolution timer. Request 1ms resolution for this process's
        # own lifetime so our scheduling doesn't depend on ambient state.
        try:
            import ctypes
            ctypes.windll.winmm.timeBeginPeriod(1)
        except (AttributeError, OSError):
            pass
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
