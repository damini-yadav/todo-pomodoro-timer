import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.font import Font
from datetime import datetime, timedelta
import json
import os
import platform
import threading
import time
import winsound  # Only works on Windows for sound
# For cross-platform sound, external libs are needed, but we'll keep offline & minimal.

APP_DATA_FILE = "todo_pomodoro_data.json"
AUDIO_PREF_FILE = "audio_pref.json"

class PomodoroApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("ToDo + Pomodoro Timer")
        self.geometry("600x500")
        self.minsize(550, 450)
        self.style = ttk.Style(self)
        self._set_theme("light")

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Data holders
        self.tasks = []
        self.timer_running = False
        self.timer_thread = None
        self.remaining_seconds = 0
        self.current_timer_mode = "Work"  # Work, Short Break, Long Break

        self.audio_file = None
        self.audio_permanent = False

        # Fonts & Icons (use emojis for icons for simplicity)
        self.font_heading = Font(family="Segoe UI", size=14, weight="bold")
        self.font_normal = Font(family="Segoe UI", size=11)
        self.font_small = Font(family="Segoe UI", size=9)

        # UI Vars
        self.dark_mode = tk.BooleanVar(value=False)
        self.custom_work_mins = tk.IntVar(value=25)
        self.custom_short_break_mins = tk.IntVar(value=5)
        self.custom_long_break_mins = tk.IntVar(value=15)
        self.pomodoro_count = 0
        self.pomodoro_target = tk.IntVar(value=4)

        self.task_title_var = tk.StringVar()
        self.task_detail_var = tk.StringVar()
        self.task_due_var = tk.StringVar()
        self.task_priority_var = tk.StringVar(value="Medium")

        self.timer_display_var = tk.StringVar(value="00:00")

        # Load saved data if any
        self.load_data()
        self.load_audio_pref()

        # UI Build
        self._build_audio_select_overlay()

    def _set_theme(self, mode):
        # Simple light/dark style setup
        if mode == "dark":
            bg = "#222222"
            fg = "#EEEEEE"
            self.style.configure("TFrame", background=bg)
            self.style.configure("TLabel", background=bg, foreground=fg)
            self.style.configure("TButton", background="#444444", foreground=fg)
            self.configure(background=bg)
        else:
            bg = "#f0f0f0"
            fg = "#222222"
            self.style.configure("TFrame", background=bg)
            self.style.configure("TLabel", background=bg, foreground=fg)
            self.style.configure("TButton", background="#ddd", foreground=fg)
            self.configure(background=bg)

    def _build_audio_select_overlay(self):
        # Overlay Frame for first-time or audio file selection
        self.overlay = ttk.Frame(self, padding=20)
        self.overlay.place(relx=0.5, rely=0.5, anchor="center")

        label = ttk.Label(self.overlay, text="Select Timer Sound (WAV format recommended):", font=self.font_heading)
        label.pack(pady=(0,10))

        self.audio_path_var = tk.StringVar(value=self.audio_file if self.audio_file else "")

        audio_entry = ttk.Entry(self.overlay, textvariable=self.audio_path_var, width=40, font=self.font_normal)
        audio_entry.pack(side="left", padx=(0,10))

        browse_btn = ttk.Button(self.overlay, text="Browse", command=self.browse_audio)
        browse_btn.pack(side="left")

        self.perm_sound_var = tk.BooleanVar(value=self.audio_permanent)
        perm_check = ttk.Checkbutton(self.overlay, text="Set as permanent sound", variable=self.perm_sound_var)
        perm_check.pack(pady=15)

        proceed_btn = ttk.Button(self.overlay, text="Proceed", command=self._on_audio_selected)
        proceed_btn.pack(pady=5)

        help_label = ttk.Label(self.overlay, text="(WAV audio recommended for offline playback)", font=self.font_small, foreground="gray")
        help_label.pack()

    def browse_audio(self):
        filetypes = [("WAV files", "*.wav"), ("All files", "*.*")]
        filename = filedialog.askopenfilename(title="Select Timer Sound File", filetypes=filetypes)
        if filename:
            self.audio_path_var.set(filename)

    def _on_audio_selected(self):
        path = self.audio_path_var.get()
        if not path or not os.path.isfile(path):
            messagebox.showerror("Invalid File", "Please select a valid audio file.")
            return
        self.audio_file = path
        self.audio_permanent = self.perm_sound_var.get()

        if self.audio_permanent:
            self.save_audio_pref()

        self.overlay.destroy()
        self._build_main_ui()

    def _build_main_ui(self):
        # Main frame layout:
        # Top center timer
        # Left todo list
        # Right controls + task details + settings + dark mode toggle

        self.main_frame = ttk.Frame(self, padding=10)
        self.main_frame.pack(fill="both", expand=True)

        # TIMER display top center
        timer_frame = ttk.Frame(self.main_frame)
        timer_frame.pack(fill="x", pady=(0,10))
        timer_label = ttk.Label(timer_frame, text="Pomodoro Timer", font=self.font_heading)
        timer_label.pack()

        self.timer_display = ttk.Label(timer_frame, textvariable=self.timer_display_var, font=Font(family="Segoe UI", size=48, weight="bold"))
        self.timer_display.pack()

        # Timer mode display & buttons
        mode_frame = ttk.Frame(timer_frame)
        mode_frame.pack(pady=5)

        self.mode_label_var = tk.StringVar(value=f"Mode: {self.current_timer_mode}")
        mode_label = ttk.Label(mode_frame, textvariable=self.mode_label_var, font=self.font_normal)
        mode_label.pack(side="left", padx=(0,15))

        # Timer controls
        btn_start = ttk.Button(mode_frame, text="▶ Start", command=self.start_timer)
        btn_start.pack(side="left", padx=5)
        btn_pause = ttk.Button(mode_frame, text="⏸ Pause", command=self.pause_timer)
        btn_pause.pack(side="left", padx=5)
        btn_reset = ttk.Button(mode_frame, text="⟲ Reset", command=self.reset_timer)
        btn_reset.pack(side="left", padx=5)

        # MAIN content split: Left todo, right details + settings
        content_frame = ttk.Frame(self.main_frame)
        content_frame.pack(fill="both", expand=True)

        # LEFT - ToDo list
        todo_frame = ttk.Frame(content_frame, relief="solid", borderwidth=1, padding=10)
        todo_frame.pack(side="left", fill="both", expand=True, padx=(0,10))

        todo_heading = ttk.Label(todo_frame, text="Your Tasks", font=self.font_heading)
        todo_heading.pack(anchor="w")

        self.tasks_tree = ttk.Treeview(todo_frame, columns=("Detail", "Due", "Priority", "Done"), show="headings", selectmode="browse")
        self.tasks_tree.pack(fill="both", expand=True, pady=5)
        self.tasks_tree.heading("Detail", text="Details")
        self.tasks_tree.heading("Due", text="Due Date")
        self.tasks_tree.heading("Priority", text="Priority")
        self.tasks_tree.heading("Done", text="Done")

        self.tasks_tree.column("Detail", width=150)
        self.tasks_tree.column("Due", width=80)
        self.tasks_tree.column("Priority", width=60, anchor="center")
        self.tasks_tree.column("Done", width=40, anchor="center")

        self.tasks_tree.bind("<Delete>", self.delete_selected_task)
        self.tasks_tree.bind("<Double-1>", self.edit_selected_task)

        self.refresh_task_list()

        # Buttons below tasks list
        btn_frame = ttk.Frame(todo_frame)
        btn_frame.pack(fill="x")

        add_btn = ttk.Button(btn_frame, text="＋ Add Task", command=self.open_task_editor)
        add_btn.pack(side="left", padx=2, pady=5)
        del_btn = ttk.Button(btn_frame, text="🗑 Delete Task", command=self.delete_selected_task)
        del_btn.pack(side="left", padx=2, pady=5)
        done_btn = ttk.Button(btn_frame, text="✔ Mark Done", command=self.mark_task_done)
        done_btn.pack(side="left", padx=2, pady=5)

        # RIGHT - Task Details and Settings Tabs
        right_notebook = ttk.Notebook(content_frame)
        right_notebook.pack(side="right", fill="both", expand=True)

        # Task editor tab
        self.task_editor_frame = ttk.Frame(right_notebook, padding=10)
        right_notebook.add(self.task_editor_frame, text="Task Details")

        ttk.Label(self.task_editor_frame, text="Title:", font=self.font_normal).grid(row=0, column=0, sticky="w", pady=3)
        self.entry_task_title = ttk.Entry(self.task_editor_frame, textvariable=self.task_title_var)
        self.entry_task_title.grid(row=0, column=1, sticky="ew", pady=3)

        ttk.Label(self.task_editor_frame, text="Details:", font=self.font_normal).grid(row=1, column=0, sticky="nw", pady=3)
        self.entry_task_detail = tk.Text(self.task_editor_frame, height=4, width=30, font=self.font_normal)
        self.entry_task_detail.grid(row=1, column=1, sticky="ew", pady=3)

        ttk.Label(self.task_editor_frame, text="Due Date (YYYY-MM-DD):", font=self.font_normal).grid(row=2, column=0, sticky="w", pady=3)
        self.entry_task_due = ttk.Entry(self.task_editor_frame, textvariable=self.task_due_var)
        self.entry_task_due.grid(row=2, column=1, sticky="ew", pady=3)

        ttk.Label(self.task_editor_frame, text="Priority:", font=self.font_normal).grid(row=3, column=0, sticky="w", pady=3)
        self.priority_cb = ttk.Combobox(self.task_editor_frame, values=["High", "Medium", "Low"], state="readonly", textvariable=self.task_priority_var)
        self.priority_cb.grid(row=3, column=1, sticky="ew", pady=3)

        # Save/Cancel buttons
        btn_task_save = ttk.Button(self.task_editor_frame, text="Save Task", command=self.save_task)
        btn_task_save.grid(row=4, column=0, pady=10)
        btn_task_cancel = ttk.Button(self.task_editor_frame, text="Clear", command=self.clear_task_editor)
        btn_task_cancel.grid(row=4, column=1, pady=10)

        self.task_editor_frame.columnconfigure(1, weight=1)

        # Settings Tab
        settings_frame = ttk.Frame(right_notebook, padding=10)
        right_notebook.add(settings_frame, text="Settings")

        # Custom timers
        ttk.Label(settings_frame, text="Work Duration (minutes):", font=self.font_normal).grid(row=0, column=0, sticky="w", pady=5)
        work_spin = ttk.Spinbox(settings_frame, from_=1, to=180, textvariable=self.custom_work_mins, width=5)
        work_spin.grid(row=0, column=1, sticky="w")

        ttk.Label(settings_frame, text="Short Break Duration (minutes):", font=self.font_normal).grid(row=1, column=0, sticky="w", pady=5)
        short_break_spin = ttk.Spinbox(settings_frame, from_=1, to=60, textvariable=self.custom_short_break_mins, width=5)
        short_break_spin.grid(row=1, column=1, sticky="w")

        ttk.Label(settings_frame, text="Long Break Duration (minutes):", font=self.font_normal).grid(row=2, column=0, sticky="w", pady=5)
        long_break_spin = ttk.Spinbox(settings_frame, from_=1, to=120, textvariable=self.custom_long_break_mins, width=5)
        long_break_spin.grid(row=2, column=1, sticky="w")

        # Pomodoro target before long break
        ttk.Label(settings_frame, text="Pomodoros before Long Break:", font=self.font_normal).grid(row=3, column=0, sticky="w", pady=5)
        pomodoro_target_spin = ttk.Spinbox(settings_frame, from_=1, to=10, textvariable=self.pomodoro_target, width=5)
        pomodoro_target_spin.grid(row=3, column=1, sticky="w")

        # Dark mode toggle
        dark_check = ttk.Checkbutton(settings_frame, text="Dark Mode", variable=self.dark_mode, command=self.toggle_dark_mode)
        dark_check.grid(row=4, column=0, columnspan=2, pady=10)

        # Audio change
        audio_btn = ttk.Button(settings_frame, text="Change Timer Sound", command=self.change_audio_sound)
        audio_btn.grid(row=5, column=0, columnspan=2, pady=10)

        for i in range(6):
            settings_frame.rowconfigure(i, weight=0)
        settings_frame.columnconfigure(1, weight=1)

        # Keyboard shortcuts
        self.bind_all("<space>", self.toggle_timer_keyboard)
        self.bind_all("<Control-n>", lambda e: self.open_task_editor())
        self.bind_all("<Control-d>", lambda e: self.delete_selected_task())

    # ===== TASKS handling =====
    def refresh_task_list(self):
        self.tasks_tree.delete(*self.tasks_tree.get_children())
        for idx, task in enumerate(self.tasks):
            done_mark = "✔" if task.get("done", False) else ""
            due_str = task.get("due", "")
            priority = task.get("priority", "Medium")
            self.tasks_tree.insert("", "end", iid=str(idx), values=(
                task.get("details", "")[:30] + ("..." if len(task.get("details", ""))>30 else ""),
                due_str,
                priority,
                done_mark
            ))

    def open_task_editor(self):
        self.clear_task_editor()
        self.task_title_var.set("")
        self.task_detail_var.set("")
        self.task_due_var.set("")
        self.task_priority_var.set("Medium")
        # Switch to Task Details tab if notebook present
        try:
            nb = self.task_editor_frame.master
            nb.select(self.task_editor_frame)
        except Exception:
            pass

    def clear_task_editor(self):
        self.task_title_var.set("")
        self.entry_task_detail.delete("1.0", tk.END)
        self.task_due_var.set("")
        self.task_priority_var.set("Medium")

    def save_task(self):
        title = self.task_title_var.get().strip()
        detail = self.entry_task_detail.get("1.0", tk.END).strip()
        due = self.task_due_var.get().strip()
        priority = self.task_priority_var.get()

        if not title:
            messagebox.showwarning("Missing Title", "Task must have a title.")
            return

        if due:
            try:
                datetime.strptime(due, "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Invalid Date", "Due Date must be in YYYY-MM-DD format.")
                return

        # Check if editing existing task
        selected = self.tasks_tree.selection()
        if selected:
            idx = int(selected[0])
            self.tasks[idx] = {
                "title": title,
                "details": detail,
                "due": due,
                "priority": priority,
                "done": self.tasks[idx].get("done", False)
            }
        else:
            self.tasks.append({
                "title": title,
                "details": detail,
                "due": due,
                "priority": priority,
                "done": False
            })

        self.save_data()
        self.refresh_task_list()
        self.clear_task_editor()

    def delete_selected_task(self, event=None):
        selected = self.tasks_tree.selection()
        if not selected:
            return
        idx = int(selected[0])
        confirm = messagebox.askyesno("Delete Task", f"Delete task: {self.tasks[idx].get('title', '')}?")
        if confirm:
            self.tasks.pop(idx)
            self.save_data()
            self.refresh_task_list()

    def mark_task_done(self):
        selected = self.tasks_tree.selection()
        if not selected:
            return
        idx = int(selected[0])
        self.tasks[idx]["done"] = True
        self.save_data()
        self.refresh_task_list()

    def edit_selected_task(self, event=None):
        selected = self.tasks_tree.selection()
        if not selected:
            return
        idx = int(selected[0])
        task = self.tasks[idx]
        self.task_title_var.set(task.get("title", ""))
        self.entry_task_detail.delete("1.0", tk.END)
        self.entry_task_detail.insert(tk.END, task.get("details", ""))
        self.task_due_var.set(task.get("due", ""))
        self.task_priority_var.set(task.get("priority", "Medium"))
        try:
            nb = self.task_editor_frame.master
            nb.select(self.task_editor_frame)
        except Exception:
            pass

    # ===== TIMER functions =====
    def start_timer(self):
        if self.timer_running:
            return
        if self.remaining_seconds == 0:
            self._set_timer_by_mode()

        self.timer_running = True
        self.update_timer_display()
        self.timer_thread = threading.Thread(target=self._timer_countdown, daemon=True)
        self.timer_thread.start()

    def pause_timer(self):
        self.timer_running = False

    def reset_timer(self):
        self.timer_running = False
        self.remaining_seconds = 0
        self.update_timer_display()

    def toggle_timer_keyboard(self, event=None):
        if self.timer_running:
            self.pause_timer()
        else:
            self.start_timer()

    def _set_timer_by_mode(self):
        if self.current_timer_mode == "Work":
            self.remaining_seconds = self.custom_work_mins.get() * 60
        elif self.current_timer_mode == "Short Break":
            self.remaining_seconds = self.custom_short_break_mins.get() * 60
        elif self.current_timer_mode == "Long Break":
            self.remaining_seconds = self.custom_long_break_mins.get() * 60

    def _timer_countdown(self):
        while self.timer_running and self.remaining_seconds > 0:
            time.sleep(1)
            if not self.timer_running:
                break
            self.remaining_seconds -= 1
            self.update_timer_display()

        if self.remaining_seconds == 0 and self.timer_running:
            self.timer_running = False
            self._play_sound()
            self._switch_timer_mode()

    def update_timer_display(self):
        mins, secs = divmod(self.remaining_seconds, 60)
        self.timer_display_var.set(f"{mins:02d}:{secs:02d}")

    def _switch_timer_mode(self):
        # Switch between work and break modes automatically
        if self.current_timer_mode == "Work":
            self.pomodoro_count += 1
            if self.pomodoro_count % self.pomodoro_target.get() == 0:
                self.current_timer_mode = "Long Break"
            else:
                self.current_timer_mode = "Short Break"
        else:
            self.current_timer_mode = "Work"
        self.mode_label_var.set(f"Mode: {self.current_timer_mode}")
        self._set_timer_by_mode()
        self.update_timer_display()
        # Auto-start next session?
        # Comment next line if you want manual start
        self.start_timer()

    def _play_sound(self):
        if self.audio_file and os.path.isfile(self.audio_file):
            try:
                # Windows sound play
                if platform.system() == "Windows":
                    winsound.PlaySound(self.audio_file, winsound.SND_FILENAME)
                else:
                    # Non-Windows systems: skip sound for now
                    pass
            except Exception:
                pass

    # ===== Dark mode toggle =====
    def toggle_dark_mode(self):
        if self.dark_mode.get():
            self._set_theme("dark")
        else:
            self._set_theme("light")

    # ===== Data persistence =====
    def load_data(self):
        if os.path.isfile(APP_DATA_FILE):
            try:
                with open(APP_DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.tasks = data.get("tasks", [])
                    self.custom_work_mins.set(data.get("work_mins", 25))
                    self.custom_short_break_mins.set(data.get("short_break_mins", 5))
                    self.custom_long_break_mins.set(data.get("long_break_mins", 15))
                    self.pomodoro_target.set(data.get("pomodoro_target", 4))
            except Exception:
                self.tasks = []

    def save_data(self):
        data = {
            "tasks": self.tasks,
            "work_mins": self.custom_work_mins.get(),
            "short_break_mins": self.custom_short_break_mins.get(),
            "long_break_mins": self.custom_long_break_mins.get(),
            "pomodoro_target": self.pomodoro_target.get()
        }
        try:
            with open(APP_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass

    def load_audio_pref(self):
        if os.path.isfile(AUDIO_PREF_FILE):
            try:
                with open(AUDIO_PREF_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.audio_file = data.get("audio_file")
                    self.audio_permanent = data.get("permanent", False)
            except Exception:
                self.audio_file = None
                self.audio_permanent = False

    def save_audio_pref(self):
        data = {
            "audio_file": self.audio_file,
            "permanent": self.audio_permanent
        }
        try:
            with open(AUDIO_PREF_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass

    def change_audio_sound(self):
        # Open overlay again
        self._build_audio_select_overlay()

    def on_close(self):
        # Save data before exit
        self.save_data()
        self.destroy()

if __name__ == "__main__":
    app = PomodoroApp()
    if app.audio_file and app.audio_permanent:
        app.overlay.destroy()
        app._build_main_ui()
    app.mainloop()
