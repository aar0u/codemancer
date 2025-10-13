import os, sys
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

def load_names():
    try:
        with open("names.txt", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load list:\n{e}")
        sys.exit(1)

names = load_names()

class CheckboxListApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Huddle Helper")
        self.geometry("220x400")
        self.resizable(False, False)
        self.x_states = {}  # Track X state for each checkbox
        self.checkboxes = {}

        # Main frame
        main_frame = tk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True)

        max_text_width = 0
        row_height = 0
        font = ("Segoe UI", 11)
        for name in names:
            self.create_checkbox_row(main_frame, name)
            temp_label = tk.Label(main_frame, text=name, font=font)
            temp_label.update_idletasks()
            text_width = temp_label.winfo_reqwidth()
            max_text_width = max(max_text_width, text_width)
            if row_height == 0:
                row_height = temp_label.winfo_reqheight() + 4  # 4 for pady
            temp_label.destroy()
        self.update_idletasks()
        min_width = 180
        min_height = 400
 
        desired_width = max(min_width, max_text_width + 60) # checkbox and margins padding
        desired_height = max(min_height, len(names) * row_height + 60)  # top/bottom padding
        self.geometry(f"{desired_width}x{desired_height}")
        self.minsize(min_width, min_height)
        self.center_window()

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def create_checkbox_row(self, parent, name):
        row = tk.Frame(parent)
        row.pack(fill=tk.X, padx=8, pady=2)
        var = tk.BooleanVar()
        cb = tk.Checkbutton(row, text=name, variable=var, font=("Segoe UI", 11), anchor="w")
        cb.pack(side=tk.LEFT, fill=tk.X, expand=True)
        cb.bind("<Button-3>", lambda e, n=name, c=cb, v=var: self.handle_right_click(n, c, v))
        cb.bind("<Button-1>", lambda e, n=name, c=cb, v=var: self.handle_left_click(n, c, v))
        self.x_states[name] = False
        self.checkboxes[name] = (cb, var)

    def handle_left_click(self, name, cb, var):
        var.set(not var.get())
        self.x_states[name] = False
        cb.config(text=name, fg="black")

    def handle_right_click(self, name, cb, var):
        self.x_states[name] = not self.x_states[name]
        if self.x_states[name]:
            var.set(False)
            cb.config(text=f"{name}  ✗", fg="red")
        else:
            cb.config(text=name, fg="black")

if __name__ == "__main__":
    # Find icon path for both script and exe
    if getattr(sys, 'frozen', False):
        icon_path = os.path.join(sys._MEIPASS, "meeting.ico")
    else:
        icon_path = os.path.abspath("meeting.ico")
    root = CheckboxListApp()
    try:
        root.iconbitmap(icon_path)
    except Exception:
        pass
    root.mainloop()
