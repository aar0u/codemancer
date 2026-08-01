#!/usr/bin/env python3

import os
import re
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, ttk


class SimpleTailGUI:
    def __init__(self, root, log_file_path):
        self.root = root
        self.log_file_path = log_file_path
        self.max_lines = 1000
        self.last_position = 0
        self.last_ended_with_newline = True
        self.display_lines = []
        self.timer_id = None

        root.title("Tail GUI")
        root.geometry("800x600")

        controls = ttk.Frame(root, padding=8)
        controls.pack(fill=tk.X)

        ttk.Label(controls, text="Lines:").pack(side=tk.LEFT)
        self.line_count_input = ttk.Entry(controls, width=8)
        self.line_count_input.insert(0, str(self.max_lines))
        self.line_count_input.pack(side=tk.LEFT, padx=(4, 12))

        ttk.Label(controls, text="Highlight:").pack(side=tk.LEFT)
        self.keyword_input = ttk.Entry(controls, width=20)
        self.keyword_input.insert(0, "ERROR")
        self.keyword_input.pack(side=tk.LEFT, padx=4)

        ttk.Button(controls, text="Apply", command=self.apply_settings).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="Open file", command=self.open_file).pack(side=tk.LEFT, padx=4)

        self.log_display = tk.Text(root, wrap=tk.NONE, state=tk.DISABLED, font="TkFixedFont")
        self.log_display.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 0))

        self.h_scroll = ttk.Scrollbar(root, orient="horizontal", command=self.log_display.xview)
        self.h_scroll.pack(fill=tk.X, padx=8, pady=(0, 8))
        self.log_display.configure(xscrollcommand=self.h_scroll.set)

        self.highlight_font = tkfont.nametofont("TkFixedFont").copy()
        self.highlight_font.configure(weight="bold")
        self.log_display.tag_configure("highlight", foreground="#FF5733", font=self.highlight_font)

        self.line_count_input.bind("<Return>", self.apply_settings)
        self.keyword_input.bind("<Return>", self.apply_settings)
        self.update_log_content(force_reload=True)

    def open_file(self):
        file_path = filedialog.askopenfilename()
        if not file_path:
            return
        self.log_file_path = file_path
        self.last_position = 0
        self.display_lines = []
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

    @staticmethod
    def read_last_lines(file_path, num_lines, file_size):
        try:
            with open(file_path, "rb") as file:
                position = file_size
                chunks = []
                newline_count = 0

                while position > 0 and newline_count <= num_lines:
                    size = min(8192, position)
                    position -= size
                    file.seek(position)
                    chunk = file.read(size)
                    chunks.append(chunk)
                    newline_count += chunk.count(b"\n")

            content = b"".join(reversed(chunks))
            return content.decode("utf-8", errors="replace").replace("\0", "").splitlines()[-num_lines:], content.endswith(b"\n")
        except OSError as error:
            print(f"[GUI] Error reading last lines: {error}", file=sys.stderr)
            return [], True

    def update_log_content(self, force_reload=False):
        if self.log_display.tag_ranges("sel"):
            self.root.title("Tail GUI [PAUSED]")
            self.schedule_update()
            return

        self.root.title("Tail GUI")
        try:
            file_size = os.path.getsize(self.log_file_path)
            if force_reload or self.last_position == 0 or self.last_position > file_size:
                self.display_lines, self.last_ended_with_newline = self.read_last_lines(
                    self.log_file_path, self.max_lines, file_size
                )
                self.last_position = file_size
                new_lines_count = len(self.display_lines)
            else:
                with open(self.log_file_path, "rb") as file:
                    file.seek(self.last_position)
                    new_bytes = file.read()
                    self.last_position = file.tell()

                new_content = new_bytes.decode("utf-8", errors="replace").replace("\0", "")

                if not new_content:
                    self.schedule_update()
                    return

                new_lines = new_content.splitlines()
                new_lines_count = len(new_lines)
                if self.display_lines and not self.last_ended_with_newline:
                    self.display_lines[-1] += new_lines[0]
                    self.display_lines.extend(new_lines[1:])
                else:
                    self.display_lines.extend(new_lines)
                self.display_lines = self.display_lines[-self.max_lines:]
                self.last_ended_with_newline = new_bytes.endswith(b"\n")

            self.set_text("\n".join(self.display_lines))
            print(f"[GUI] Loaded: {new_lines_count} lines | Total: {len(self.display_lines)} lines")
        except OSError as error:
            self.set_text(f"Error reading file: {error}")
            print(f"[GUI] Error reading file: {error}", file=sys.stderr)
        finally:
            self.schedule_update()

    def set_text(self, text):
        self.log_display.configure(state=tk.NORMAL)
        self.log_display.delete("1.0", tk.END)
        self.log_display.insert("1.0", text)
        self.log_display.tag_remove("highlight", "1.0", tk.END)
        for keyword in filter(None, (item.strip() for item in self.keyword_input.get().split(","))):
            for match in re.finditer(re.escape(keyword), text, re.IGNORECASE):
                start = f"1.0+{match.start()}c"
                end = f"1.0+{match.end()}c"
                self.log_display.tag_add("highlight", start, end)
        self.log_display.see(tk.END)
        self.log_display.configure(state=tk.DISABLED)


if __name__ == "__main__":
    root = tk.Tk()
    SimpleTailGUI(root, sys.argv[1] if len(sys.argv) > 1 else "sample.log")
    root.mainloop()
