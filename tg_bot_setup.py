"""
Claude Bridge — Desktop App.

Full chat client + Telegram bot manager + settings.
Dark theme, image support, real-time tool display.

Usage:
  py D:/Life/tg_bot_setup.py
"""

import json
import sys
import os
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
from datetime import datetime
import threading
import time

if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).parent

CONFIG_PATH = APP_DIR / "tg_bot_v2_config.json"
STATE_PATH = APP_DIR / "tg_bot_v2_state.json"
BOT_SCRIPT = APP_DIR / "tg_claude_bot.py"
LOG_PATH = APP_DIR / "tg_bot_v2.log"
CHAT_LOG = APP_DIR / "chat_history.jsonl"
STOP_SIGNAL = APP_DIR / "tg_bot_stop_signal"

DEFAULT_CONFIG = {
    "bot_token": "",
    "allowed_users": [],
    "python_path": sys.executable,
    "claude_path": "claude",
    "work_dir": ".",
    "model": "claude-opus-4-6",
    "permission_mode": "bypassPermissions",
    "effort": "high",
    "max_turns": None,
    "max_budget_usd": None,
    "history_size": 20,
    "progress_interval": 10,
    "system_prompt": "",
    "allowed_tools": [],
    "disallowed_tools": [],
    "autostart": False,
}

# --- Dark Theme Colors ---
C = {
    "bg": "#1e1e1e",
    "bg2": "#252526",
    "bg3": "#2d2d2d",
    "bg_input": "#3c3c3c",
    "fg": "#cccccc",
    "fg2": "#969696",
    "fg_dim": "#666666",
    "accent": "#0078d4",
    "accent2": "#264f78",
    "green": "#4ec9b0",
    "blue": "#569cd6",
    "yellow": "#dcdcaa",
    "orange": "#ce9178",
    "red": "#f44747",
    "border": "#404040",
    "user_bg": "#0e4a6e",
    "claude_bg": "#2d2d2d",
}

MODELS = [
    ("Opus 4.6", "claude-opus-4-6"),
    ("Sonnet 4.6", "claude-sonnet-4-6"),
    ("Haiku 4.5", "claude-haiku-4-5-20251001"),
]

PERMISSIONS = [
    ("Bypass all", "bypassPermissions"),
    ("Auto-edit", "acceptEdits"),
    ("Ask first", "default"),
    ("Plan only", "plan"),
]

EFFORTS = [("Max", "max"), ("High", "high"), ("Medium", "medium"), ("Low", "low")]


def load_config():
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def load_state():
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"session_id": None, "msg_counter": 0, "history": {}}


def save_state(st):
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(st, f, indent=2, ensure_ascii=False)


# =====================================================
#  DARK THEME SETUP
# =====================================================

def apply_dark_theme(root):
    root.configure(bg=C["bg"])

    style = ttk.Style()
    style.theme_use("clam")

    style.configure(".", background=C["bg"], foreground=C["fg"], fieldbackground=C["bg_input"],
                    bordercolor=C["border"], troughcolor=C["bg2"], selectbackground=C["accent2"],
                    selectforeground=C["fg"], font=("Segoe UI", 10))

    style.configure("TFrame", background=C["bg"])
    style.configure("TLabel", background=C["bg"], foreground=C["fg"])
    style.configure("TButton", background=C["bg3"], foreground=C["fg"], borderwidth=1, relief="flat", padding=(10, 4))
    style.map("TButton", background=[("active", C["accent"]), ("pressed", C["accent2"])])

    style.configure("Accent.TButton", background=C["accent"], foreground="white", font=("Segoe UI", 10, "bold"))
    style.map("Accent.TButton", background=[("active", "#1a8fe6"), ("pressed", C["accent2"])])

    style.configure("Danger.TButton", background="#5a1d1d", foreground=C["red"])
    style.map("Danger.TButton", background=[("active", "#7a2d2d")])

    style.configure("TNotebook", background=C["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", background=C["bg2"], foreground=C["fg2"], padding=(16, 6),
                    font=("Segoe UI", 10))
    style.map("TNotebook.Tab", background=[("selected", C["bg"]), ("active", C["bg3"])],
              foreground=[("selected", C["fg"]), ("active", C["fg"])])

    style.configure("TLabelframe", background=C["bg"], foreground=C["fg2"], bordercolor=C["border"])
    style.configure("TLabelframe.Label", background=C["bg"], foreground=C["fg2"],
                    font=("Segoe UI", 9, "bold"))

    style.configure("TEntry", fieldbackground=C["bg_input"], foreground=C["fg"], insertcolor=C["fg"],
                    bordercolor=C["border"])

    style.configure("TCombobox", fieldbackground=C["bg_input"], foreground=C["fg"],
                    selectbackground=C["accent2"], bordercolor=C["border"])
    style.map("TCombobox", fieldbackground=[("readonly", C["bg_input"])],
              selectbackground=[("readonly", C["accent2"])])

    style.configure("TCheckbutton", background=C["bg"], foreground=C["fg"])
    style.map("TCheckbutton", background=[("active", C["bg"])])

    style.configure("TRadiobutton", background=C["bg"], foreground=C["fg"])
    style.map("TRadiobutton", background=[("active", C["bg"])])

    style.configure("TSeparator", background=C["border"])

    style.configure("TScrollbar", background=C["bg2"], troughcolor=C["bg"], bordercolor=C["bg"],
                    arrowcolor=C["fg2"])

    style.configure("Status.TLabel", background=C["bg2"], foreground=C["fg2"], font=("Segoe UI", 9))
    style.configure("Running.TLabel", background=C["bg"], foreground=C["green"], font=("Segoe UI", 10, "bold"))
    style.configure("Stopped.TLabel", background=C["bg"], foreground=C["fg_dim"], font=("Segoe UI", 10))
    style.configure("Title.TLabel", font=("Segoe UI", 11, "bold"))
    style.configure("Dim.TLabel", foreground=C["fg_dim"], font=("Segoe UI", 9))


# =====================================================
#  MAIN APP
# =====================================================

class App:
    def __init__(self, root):
        self.root = root
        root.title("Claude Bridge")
        root.geometry("800x700")
        root.minsize(700, 550)

        apply_dark_theme(root)

        self.config = load_config()
        self.bot_process = None
        self.log_running = False
        self.chat_proc = None
        self.chat_busy = False
        self.attached_image = None
        self.chat_log_pos = 0
        self.chat_log_monitoring = True

        # Notebook
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        # Tabs
        self._build_chat_tab()
        self._build_bot_tab()
        self._build_settings_tab()
        self._build_log_tab()

        # Status bar
        self._build_statusbar()

        # Auto-detect running bot
        self._detect_running_bot()

        # Start chat log monitor
        self._init_chat_log_pos()
        self._monitor_chat_log()

        # Global hotkeys by keycode — works on ANY keyboard layout (Russian, etc.)
        self.root.bind("<Key>", self._on_key_global)

    # =====================================================
    #  CHAT TAB
    # =====================================================

    def _build_chat_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  Chat  ")

        # Top bar
        topbar = tk.Frame(tab, bg=C["bg2"], height=36)
        topbar.pack(fill=tk.X)
        topbar.pack_propagate(False)

        tk.Label(topbar, text="Claude Bridge", font=("Segoe UI", 10, "bold"),
                 bg=C["bg2"], fg=C["green"]).pack(side=tk.LEFT, padx=10)

        self.chat_model_var = tk.StringVar(value=self.config.get("model", "claude-opus-4-6"))
        model_menu = ttk.Combobox(topbar, textvariable=self.chat_model_var,
                                   values=[m[1] for m in MODELS], width=22, state="readonly")
        model_menu.pack(side=tk.LEFT, padx=5, pady=4)

        self.chat_effort_var = tk.StringVar(value=self.config.get("effort", "high"))
        effort_menu = ttk.Combobox(topbar, textvariable=self.chat_effort_var,
                                    values=[e[1] for e in EFFORTS], width=8, state="readonly")
        effort_menu.pack(side=tk.LEFT, padx=5, pady=4)

        self.chat_stop_btn = tk.Button(topbar, text="Stop", font=("Segoe UI", 9),
                                        bg="#5a1d1d", fg=C["red"], relief="flat", padx=10,
                                        command=self._chat_stop, state=tk.DISABLED)
        self.chat_stop_btn.pack(side=tk.RIGHT, padx=5, pady=4)

        tk.Button(topbar, text="New Chat", font=("Segoe UI", 9),
                  bg=C["bg3"], fg=C["fg"], relief="flat", padx=10,
                  command=self._chat_new).pack(side=tk.RIGHT, padx=2, pady=4)

        # Chat display
        chat_frame = tk.Frame(tab, bg=C["bg"])
        chat_frame.pack(fill=tk.BOTH, expand=True)

        self.chat_display = tk.Text(
            chat_frame, wrap=tk.WORD, font=("Consolas", 10),
            state=tk.DISABLED, bg=C["bg"], fg=C["fg"],
            insertbackground=C["fg"], selectbackground=C["accent2"],
            padx=12, pady=8, spacing1=1, spacing3=1,
            borderwidth=0, highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(chat_frame, command=self.chat_display.yview)
        self.chat_display.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat_display.pack(fill=tk.BOTH, expand=True)

        # Tags
        self.chat_display.tag_configure("user_name", foreground=C["blue"], font=("Segoe UI", 10, "bold"))
        self.chat_display.tag_configure("user_text", foreground=C["fg"], font=("Consolas", 10))
        self.chat_display.tag_configure("claude_name", foreground=C["green"], font=("Segoe UI", 10, "bold"))
        self.chat_display.tag_configure("claude_text", foreground=C["fg"], font=("Consolas", 10))
        self.chat_display.tag_configure("tool", foreground=C["fg_dim"], font=("Consolas", 9))
        self.chat_display.tag_configure("error", foreground=C["red"], font=("Consolas", 10))
        self.chat_display.tag_configure("system", foreground=C["fg_dim"], font=("Segoe UI", 9, "italic"))
        self.chat_display.tag_configure("img", foreground=C["yellow"], font=("Consolas", 9))
        self.chat_display.tag_configure("separator", foreground=C["border"])
        self.chat_display.tag_configure("end_marker", foreground=C["green"], font=("Segoe UI", 10, "bold"))

        # Input area
        input_outer = tk.Frame(tab, bg=C["border"], padx=1, pady=1)
        input_outer.pack(fill=tk.X, padx=10, pady=(0, 10))

        input_frame = tk.Frame(input_outer, bg=C["bg_input"])
        input_frame.pack(fill=tk.X)

        # Attachment bar (hidden by default)
        self.attach_bar = tk.Frame(input_frame, bg=C["bg3"])
        self.attach_label = tk.Label(self.attach_bar, text="", bg=C["bg3"], fg=C["yellow"],
                                      font=("Consolas", 9))
        self.attach_label.pack(side=tk.LEFT, padx=8, pady=2)
        tk.Button(self.attach_bar, text="✕", bg=C["bg3"], fg=C["red"], relief="flat",
                  font=("Consolas", 9), command=self._remove_attachment).pack(side=tk.RIGHT, padx=5)

        # Input row
        input_row = tk.Frame(input_frame, bg=C["bg_input"])
        input_row.pack(fill=tk.X)

        tk.Button(input_row, text="📎", font=("Segoe UI", 12), bg=C["bg_input"], fg=C["fg2"],
                  relief="flat", command=self._attach_image, cursor="hand2").pack(side=tk.LEFT, padx=(4, 0))

        self.chat_input = tk.Text(
            input_row, height=2, wrap=tk.WORD, font=("Consolas", 10),
            bg=C["bg_input"], fg=C["fg"], insertbackground=C["fg"],
            borderwidth=0, highlightthickness=0, padx=4, pady=6,
        )
        self.chat_input.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.chat_input.bind("<Return>", self._on_enter)
        self.chat_input.bind("<Shift-Return>", lambda e: None)

        self.stop_inline_btn = tk.Button(input_row, text="■", font=("Segoe UI", 14),
                                          bg="#5a1d1d", fg=C["red"], relief="flat", width=3,
                                          command=self._chat_stop, cursor="hand2")

        self.send_btn = tk.Button(input_row, text="➤", font=("Segoe UI", 14),
                                   bg=C["accent"], fg="white", relief="flat", width=3,
                                   command=self._chat_send, cursor="hand2")
        self.send_btn.pack(side=tk.RIGHT, padx=2, pady=2)

    def _on_enter(self, event):
        if not (event.state & 1):  # not Shift
            self._chat_send()
            return "break"

    def _on_key_global(self, event):
        if not (event.state & 4):
            return
        KC = {65: "a", 67: "c", 86: "v", 88: "x", 90: "z"}
        key = KC.get(event.keycode)
        if not key:
            return
        latin = event.keysym and len(event.keysym) == 1 and event.keysym.lower() == key
        if latin and key in ("c", "x", "z", "v"):
            return
        if key == "v":
            return self._on_paste(event)
        w = event.widget
        if isinstance(w, tk.Text):
            if key == "a":
                w.tag_add(tk.SEL, "1.0", tk.END)
                w.mark_set(tk.INSERT, tk.END)
                return "break"
            elif key == "c":
                w.event_generate("<<Copy>>")
                return "break"
            elif key == "x":
                w.event_generate("<<Cut>>")
                return "break"
            elif key == "z":
                try:
                    w.edit_undo()
                except tk.TclError:
                    pass
                return "break"
        elif isinstance(w, (ttk.Entry, tk.Entry)):
            if key == "a":
                w.select_range(0, tk.END)
                w.icursor(tk.END)
                return "break"
            elif key == "c":
                w.event_generate("<<Copy>>")
                return "break"
            elif key == "x":
                w.event_generate("<<Cut>>")
                return "break"
            elif key == "z":
                return "break"

    def _on_paste(self, event):
        debug = []
        paste_dir = APP_DIR / "paste_images"
        paste_dir.mkdir(exist_ok=True)
        filename = f"paste_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = paste_dir / filename

        # Method 1: PIL in current process
        try:
            from PIL import ImageGrab
            debug.append("PIL imported OK")
            img = ImageGrab.grabclipboard()
            debug.append(f"grabclipboard={type(img).__name__}")
            if img is not None and hasattr(img, 'save'):
                img.save(str(path), "PNG")
                self.attached_image = str(path)
                self.attach_label.config(text=f"📎 {filename}")
                self.attach_bar.pack(fill=tk.X, before=self.chat_input.master)
                self._status(f"Image attached: {filename}")
                self._debug_log(debug + ["PIL SAVE OK"])
                return "break"
        except Exception as e:
            debug.append(f"PIL error: {e}")

        # Method 2: ctypes CF_DIB
        try:
            import ctypes, struct
            u32 = ctypes.windll.user32
            k32 = ctypes.windll.kernel32
            CF_DIB = 8
            avail = u32.IsClipboardFormatAvailable(CF_DIB)
            debug.append(f"CF_DIB avail={avail}")

            # Enumerate all formats
            fmts = []
            if u32.OpenClipboard(0):
                fmt = 0
                for _ in range(50):
                    fmt = u32.EnumClipboardFormats(fmt)
                    if fmt == 0:
                        break
                    fmts.append(fmt)
                u32.CloseClipboard()
            debug.append(f"formats={fmts}")

            if avail and u32.OpenClipboard(0):
                h = u32.GetClipboardData(CF_DIB)
                debug.append(f"handle={h}")
                if h:
                    k32.GlobalLock.restype = ctypes.c_void_p
                    k32.GlobalSize.restype = ctypes.c_size_t
                    ptr = k32.GlobalLock(h)
                    size = k32.GlobalSize(h)
                    debug.append(f"ptr={ptr} size={size}")
                    if ptr and size:
                        raw = bytes((ctypes.c_char * size).from_address(ptr))
                        k32.GlobalUnlock(h)
                        u32.CloseClipboard()
                        hdr_size = struct.unpack_from('<I', raw, 0)[0]
                        bmp_path = str(path).replace('.png', '.bmp')
                        file_size = 14 + len(raw)
                        bmp_hdr = struct.pack('<2sIHHI', b'BM', file_size, 0, 0, 14 + hdr_size)
                        with open(bmp_path, 'wb') as f:
                            f.write(bmp_hdr)
                            f.write(raw)
                        self.attached_image = bmp_path
                        fname = Path(bmp_path).name
                        self.attach_label.config(text=f"📎 {fname}")
                        self.attach_bar.pack(fill=tk.X, before=self.chat_input.master)
                        self._status(f"Image attached: {fname}")
                        self._debug_log(debug + ["CTYPES SAVE OK"])
                        return "break"
                    else:
                        k32.GlobalUnlock(h)
                u32.CloseClipboard()
        except Exception as e:
            debug.append(f"ctypes error: {e}")

        # Method 3: external script
        clip_script = APP_DIR / "clip_image.py"
        python = self.config.get("python_path") or "python"
        debug.append(f"trying script: {clip_script.exists()}, python={python}")

        def _run_clip():
            try:
                r = subprocess.run(
                    [python, str(clip_script), str(path)],
                    capture_output=True, text=True, timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                debug.append(f"script rc={r.returncode} out={r.stdout.strip()[:80]} err={r.stderr.strip()[:80]}")
                saved = r.stdout.strip()
                if r.returncode == 0 and saved and Path(saved).exists():
                    self.root.after(0, self._finish_paste, saved, Path(saved).name)
                    self.root.after(0, self._debug_log, debug + ["SCRIPT OK"])
                else:
                    self.root.after(0, self._paste_text_fallback)
                    self.root.after(0, self._debug_log, debug + ["SCRIPT FAILED"])
            except Exception as e:
                debug.append(f"script error: {e}")
                self.root.after(0, self._paste_text_fallback)
                self.root.after(0, self._debug_log, debug + ["SCRIPT EXCEPTION"])

        self._status("Pasting image...")
        threading.Thread(target=_run_clip, daemon=True).start()
        return "break"

    def _debug_log(self, lines):
        log_path = APP_DIR / "paste_debug.log"
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"\n--- {datetime.now().isoformat()} ---\n")
            for line in lines:
                f.write(f"  {line}\n")

    def _finish_paste(self, path, filename):
        self.attached_image = path
        self.attach_label.config(text=f"📎 {filename}")
        self.attach_bar.pack(fill=tk.X, before=self.chat_input.master)
        self._status(f"Image attached: {filename}")

    def _paste_text_fallback(self):
        try:
            text = self.root.clipboard_get()
            self.chat_input.insert(tk.INSERT, text)
        except tk.TclError:
            pass
        self._status("Ready")

    def _chat_append(self, text, tag="claude_text"):
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, text, tag)
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)

    def _chat_clear(self):
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.delete("1.0", tk.END)
        self.chat_display.config(state=tk.DISABLED)

    def _attach_image(self):
        path = filedialog.askopenfilename(
            title="Attach Image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("All", "*.*")],
        )
        if path:
            self.attached_image = path
            self.attach_label.config(text=f"📎 {Path(path).name}")
            self.attach_bar.pack(fill=tk.X, before=self.chat_input.master)

    def _remove_attachment(self):
        self.attached_image = None
        self.attach_bar.pack_forget()

    def _chat_new(self):
        st = load_state()
        st["session_id"] = None
        save_state(st)
        self._chat_clear()
        self._chat_append("New session started\n", "system")
        self._status("Session reset")

    def _chat_stop(self):
        if self.chat_proc:
            try:
                self.chat_proc.kill()
            except Exception:
                pass
            self._chat_append("\n🛑 Stopped\n", "error")
        else:
            STOP_SIGNAL.touch()
            self._chat_append("\n🛑 Stop signal sent to bot\n", "error")
        self.chat_busy = False
        self._toggle_chat_ui(False)

    def _toggle_chat_ui(self, busy):
        self.chat_busy = busy
        if busy:
            self.send_btn.pack_forget()
            self.stop_inline_btn.pack(side=tk.RIGHT, padx=2, pady=2)
        else:
            self.stop_inline_btn.pack_forget()
            self.send_btn.pack(side=tk.RIGHT, padx=2, pady=2)
        self.chat_stop_btn.config(state=tk.NORMAL if busy else tk.DISABLED)

    def _chat_send(self):
        if self.chat_busy:
            return

        text = self.chat_input.get("1.0", tk.END).strip()
        if not text and not self.attached_image:
            return

        self.chat_input.delete("1.0", tk.END)

        # Display user message
        self._chat_append("━" * 50 + "\n", "separator")
        self._chat_append("You\n", "user_name")
        if self.attached_image:
            self._chat_append(f"📎 {Path(self.attached_image).name}\n", "img")
        if text:
            self._chat_append(f"{text}\n", "user_text")

        # Build prompt
        prompt = text
        if self.attached_image:
            img_note = f"[Image: {self.attached_image} — use Read tool to view]"
            prompt = f"{img_note}\n{text}" if text else img_note
            self._remove_attachment()

        self._write_chat_log("user_message", {"text": text, "user": "You (GUI)"})
        self._chat_append("\n", "claude_text")
        self._chat_append("Claude\n", "claude_name")
        self._toggle_chat_ui(True)
        self._status("Working...")

        thread = threading.Thread(target=self._run_claude, args=(prompt,), daemon=True)
        thread.start()

    def _write_chat_log(self, event_type, data):
        entry = {
            "ts": datetime.now().isoformat(),
            "source": "gui",
            "type": event_type,
            "data": data,
        }
        try:
            with open(CHAT_LOG, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _init_chat_log_pos(self):
        if CHAT_LOG.exists():
            self.chat_log_pos = CHAT_LOG.stat().st_size
        else:
            self.chat_log_pos = 0

    def _monitor_chat_log(self):
        if not self.chat_log_monitoring:
            return
        try:
            if CHAT_LOG.exists():
                size = CHAT_LOG.stat().st_size
                if size > self.chat_log_pos:
                    with open(CHAT_LOG, 'r', encoding='utf-8') as f:
                        f.seek(self.chat_log_pos)
                        new_data = f.read()
                        self.chat_log_pos = f.tell()
                    for line in new_data.strip().split("\n"):
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if entry.get("source") == "gui":
                            continue
                        self._render_chat_entry(entry)
        except Exception:
            pass
        self.root.after(500, self._monitor_chat_log)

    def _render_chat_entry(self, entry):
        etype = entry.get("type", "")
        data = entry.get("data", {})
        source = entry.get("source", "?")

        if etype == "user_message":
            self._chat_append("━" * 50 + "\n", "separator")
            user = data.get("user", source)
            self._chat_append(f"{user} (Telegram)\n", "user_name")
            self._chat_append(f"{data.get('text', '')}\n", "user_text")
            self._chat_append("\n", "claude_text")
            self._chat_append("Claude\n", "claude_name")
        elif etype == "tool":
            self._chat_append(f"  {data.get('desc', '?')}\n", "tool")
        elif etype == "text":
            self._chat_append(f"{data.get('text', '')}\n", "claude_text")
        elif etype == "result":
            self._chat_append(f"{data.get('text', '')}\n", "claude_text")
        elif etype == "end":
            self._chat_append("КОНЕЦ\n", "end_marker")
        elif etype == "stopped":
            self._chat_append(f"🛑 Stopped by {data.get('by', '?')}\n", "error")

    def _run_claude(self, prompt):
        cfg = self.config
        st = load_state()
        session_id = st.get("session_id")

        cmd = [
            cfg.get("claude_path", "claude"), "-p",
            "--output-format", "stream-json", "--verbose",
            "--model", self.chat_model_var.get(),
            "--permission-mode", cfg.get("permission_mode", "bypassPermissions"),
            "--effort", self.chat_effort_var.get(),
        ]
        if session_id:
            cmd.extend(["--resume", session_id])

        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        work_dir = cfg.get("work_dir", ".")

        last_sent_text = ""

        proc = None
        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', errors='replace', cwd=work_dir, env=env,
                creationflags=flags,
            )
            self.chat_proc = proc
            proc.stdin.write(prompt)
            proc.stdin.close()

            final_text = ""
            new_session = session_id

            for raw_line in proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type", "")

                if etype == "result":
                    new_session = event.get("session_id", session_id)
                    final_text = event.get("result", "")

                elif etype == "assistant":
                    msg = event.get("message", {})
                    if not isinstance(msg, dict):
                        continue
                    for block in msg.get("content", []):
                        btype = block.get("type")
                        if btype == "tool_use":
                            desc = self._tool_desc(block.get("name", "?"), block.get("input", {}))
                            self._write_chat_log("tool", {"desc": desc})
                            self.root.after(0, self._chat_append, f"  {desc}\n", "tool")
                        elif btype == "text" and block.get("text", "").strip():
                            txt = block["text"].strip()
                            if len(txt) > 3:
                                last_sent_text = txt
                                self._write_chat_log("text", {"text": txt})
                                self.root.after(0, self._chat_append, f"{txt}\n", "claude_text")

            proc.wait()

            # Save session
            if new_session:
                st["session_id"] = new_session
                save_state(st)

            # Final result (only if different from streamed text)
            if final_text and final_text.strip() != last_sent_text.strip():
                self._write_chat_log("result", {"text": final_text})
                self.root.after(0, self._chat_append, f"{final_text}\n", "claude_text")

            self._write_chat_log("end", {})
            self.root.after(0, self._chat_append, "КОНЕЦ\n", "end_marker")
            self.root.after(0, self._status, "Done")

        except Exception as e:
            self.root.after(0, self._chat_append, f"\n❌ {e}\n", "error")
            self.root.after(0, self._status, f"Error: {e}")

        finally:
            if self.chat_proc is proc:
                self.chat_proc = None
            self.root.after(0, self._toggle_chat_ui, False)

    def _tool_desc(self, name, inp):
        if not isinstance(inp, dict):
            inp = {}
        m = {
            "Read": lambda: f"📖 Read {Path(inp.get('file_path', '?')).name}",
            "Edit": lambda: f"✏️ Edit {Path(inp.get('file_path', '?')).name}",
            "Write": lambda: f"📝 Write {Path(inp.get('file_path', '?')).name}",
            "Bash": lambda: f"💻 {(inp.get('description') or inp.get('command', '?'))[:60]}",
            "Glob": lambda: f"🔍 Glob {inp.get('pattern', '?')}",
            "Grep": lambda: f"🔎 Grep {inp.get('pattern', '?')[:40]}",
            "WebSearch": lambda: f"🌐 {inp.get('query', '?')[:40]}",
            "WebFetch": lambda: f"📥 {inp.get('url', '?')[:50]}",
            "Agent": lambda: f"🤖 {inp.get('description', '?')[:40]}",
        }
        fn = m.get(name)
        return fn() if fn else f"🔧 {name}"

    # =====================================================
    #  BOT TAB
    # =====================================================

    def _build_bot_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  Telegram Bot  ")

        # Status
        sf = ttk.LabelFrame(tab, text="Bot Status", padding=12)
        sf.pack(fill=tk.X, padx=15, pady=(15, 5))

        row1 = ttk.Frame(sf)
        row1.pack(fill=tk.X)
        self.bot_status_label = ttk.Label(row1, text="Stopped", style="Stopped.TLabel")
        self.bot_status_label.pack(side=tk.LEFT)
        self.bot_pid_label = ttk.Label(row1, text="", style="Dim.TLabel")
        self.bot_pid_label.pack(side=tk.LEFT, padx=20)
        self.bot_session_label = ttk.Label(row1, text="", style="Dim.TLabel")
        self.bot_session_label.pack(side=tk.LEFT)

        row2 = ttk.Frame(sf)
        row2.pack(fill=tk.X, pady=(10, 0))
        self.start_btn = ttk.Button(row2, text="Start Bot", command=self._start_bot, style="Accent.TButton")
        self.start_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.stop_btn = ttk.Button(row2, text="Stop Bot", command=self._stop_bot, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(row2, text="Restart", command=self._restart_bot).pack(side=tk.LEFT, padx=5)
        ttk.Button(row2, text="Reset Session", command=self._reset_session).pack(side=tk.RIGHT)

        # Telegram config
        tf = ttk.LabelFrame(tab, text="Telegram", padding=12)
        tf.pack(fill=tk.X, padx=15, pady=5)

        r1 = ttk.Frame(tf)
        r1.pack(fill=tk.X, pady=3)
        ttk.Label(r1, text="Bot Token:", width=14).pack(side=tk.LEFT)
        self.token_var = tk.StringVar(value=self.config.get("bot_token", ""))
        self.token_entry = ttk.Entry(r1, textvariable=self.token_var, show="*")
        self.token_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.show_token_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(r1, text="Show", variable=self.show_token_var,
                         command=lambda: self.token_entry.config(show="" if self.show_token_var.get() else "*")
                         ).pack(side=tk.LEFT, padx=5)

        r2 = ttk.Frame(tf)
        r2.pack(fill=tk.X, pady=3)
        ttk.Label(r2, text="Allowed Users:", width=14).pack(side=tk.LEFT)
        users_str = ", ".join(str(u) for u in self.config.get("allowed_users", []))
        self.users_var = tk.StringVar(value=users_str)
        ttk.Entry(r2, textvariable=self.users_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(r2, text="IDs, comma-sep", style="Dim.TLabel").pack(side=tk.LEFT, padx=5)

        # Autostart
        af = ttk.LabelFrame(tab, text="Autostart", padding=12)
        af.pack(fill=tk.X, padx=15, pady=5)
        self.autostart_var = tk.BooleanVar(value=self.config.get("autostart", False))
        ttk.Checkbutton(af, text="Start bot with Windows", variable=self.autostart_var).pack(anchor=tk.W)
        ttk.Button(af, text="Install Autostart", command=self._setup_autostart).pack(anchor=tk.W, pady=(5, 0))

    # =====================================================
    #  SETTINGS TAB
    # =====================================================

    def _build_settings_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  Settings  ")

        # Scrollable
        canvas = tk.Canvas(tab, bg=C["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(fill=tk.BOTH, expand=True)

        # Bind mousewheel
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        parent = scroll_frame

        # Claude Code
        cf = ttk.LabelFrame(parent, text="Claude Bridge", padding=12)
        cf.pack(fill=tk.X, padx=15, pady=(15, 5))

        r0 = ttk.Frame(cf)
        r0.pack(fill=tk.X, pady=3)
        ttk.Label(r0, text="Python Path:", width=14).pack(side=tk.LEFT)
        self.python_var = tk.StringVar(value=self.config.get("python_path", sys.executable))
        ttk.Entry(r0, textvariable=self.python_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(r0, text="...", width=3,
                   command=lambda: self._browse_file(self.python_var, "Python", [("Exe", "*.exe")])).pack(side=tk.LEFT, padx=2)

        r1 = ttk.Frame(cf)
        r1.pack(fill=tk.X, pady=3)
        ttk.Label(r1, text="CLI Path:", width=14).pack(side=tk.LEFT)
        self.cli_var = tk.StringVar(value=self.config.get("claude_path", ""))
        ttk.Entry(r1, textvariable=self.cli_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(r1, text="...", width=3,
                   command=lambda: self._browse_file(self.cli_var, "Claude CLI", [("Exe", "*.cmd *.exe")])).pack(side=tk.LEFT, padx=2)

        r2 = ttk.Frame(cf)
        r2.pack(fill=tk.X, pady=3)
        ttk.Label(r2, text="Work Directory:", width=14).pack(side=tk.LEFT)
        self.workdir_var = tk.StringVar(value=self.config.get("work_dir", ""))
        ttk.Entry(r2, textvariable=self.workdir_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(r2, text="...", width=3,
                   command=lambda: self._browse_dir(self.workdir_var)).pack(side=tk.LEFT, padx=2)

        # Model / Mode / Effort
        mf = ttk.LabelFrame(parent, text="Model & Mode", padding=12)
        mf.pack(fill=tk.X, padx=15, pady=5)

        r3 = ttk.Frame(mf)
        r3.pack(fill=tk.X, pady=3)
        ttk.Label(r3, text="Model:", width=14).pack(side=tk.LEFT)
        self.model_var = tk.StringVar(value=self.config.get("model", "claude-opus-4-6"))
        for label, val in MODELS:
            ttk.Radiobutton(r3, text=label, variable=self.model_var, value=val).pack(side=tk.LEFT, padx=(0, 15))

        r4 = ttk.Frame(mf)
        r4.pack(fill=tk.X, pady=3)
        ttk.Label(r4, text="Mode:", width=14).pack(side=tk.LEFT)
        self.perm_var = tk.StringVar(value=self.config.get("permission_mode", "bypassPermissions"))
        for label, val in PERMISSIONS:
            ttk.Radiobutton(r4, text=label, variable=self.perm_var, value=val).pack(side=tk.LEFT, padx=(0, 15))

        r5 = ttk.Frame(mf)
        r5.pack(fill=tk.X, pady=3)
        ttk.Label(r5, text="Effort:", width=14).pack(side=tk.LEFT)
        self.effort_var = tk.StringVar(value=self.config.get("effort", "high"))
        for label, val in EFFORTS:
            ttk.Radiobutton(r5, text=label, variable=self.effort_var, value=val).pack(side=tk.LEFT, padx=(0, 15))

        # System Prompt
        pf = ttk.LabelFrame(parent, text="System Prompt (optional)", padding=12)
        pf.pack(fill=tk.X, padx=15, pady=5)
        self.prompt_text = tk.Text(pf, height=3, wrap=tk.WORD, font=("Consolas", 9),
                                    bg=C["bg_input"], fg=C["fg"], insertbackground=C["fg"],
                                    borderwidth=1, highlightthickness=0)
        self.prompt_text.pack(fill=tk.X)
        self.prompt_text.insert("1.0", self.config.get("system_prompt", ""))

        # Tool restrictions
        tf = ttk.LabelFrame(parent, text="Tool Restrictions", padding=12)
        tf.pack(fill=tk.X, padx=15, pady=5)

        r6 = ttk.Frame(tf)
        r6.pack(fill=tk.X, pady=3)
        ttk.Label(r6, text="Allowed:", width=14).pack(side=tk.LEFT)
        self.allowed_tools_var = tk.StringVar(value=", ".join(self.config.get("allowed_tools", [])))
        ttk.Entry(r6, textvariable=self.allowed_tools_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        r7 = ttk.Frame(tf)
        r7.pack(fill=tk.X, pady=3)
        ttk.Label(r7, text="Disallowed:", width=14).pack(side=tk.LEFT)
        self.disallowed_tools_var = tk.StringVar(value=", ".join(self.config.get("disallowed_tools", [])))
        ttk.Entry(r7, textvariable=self.disallowed_tools_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Label(tf, text="Read, Edit, Write, Bash, Glob, Grep, Agent, WebSearch...", style="Dim.TLabel").pack(anchor=tk.W, pady=(3, 0))

        # Limits
        lf = ttk.LabelFrame(parent, text="Limits", padding=12)
        lf.pack(fill=tk.X, padx=15, pady=5)

        r8 = ttk.Frame(lf)
        r8.pack(fill=tk.X, pady=3)
        ttk.Label(r8, text="Max Turns:", width=14).pack(side=tk.LEFT)
        mt = self.config.get("max_turns")
        self.turns_var = tk.StringVar(value=str(mt) if mt else "")
        ttk.Entry(r8, textvariable=self.turns_var, width=10).pack(side=tk.LEFT)
        ttk.Label(r8, text="empty = unlimited", style="Dim.TLabel").pack(side=tk.LEFT, padx=10)

        r9 = ttk.Frame(lf)
        r9.pack(fill=tk.X, pady=3)
        ttk.Label(r9, text="History Size:", width=14).pack(side=tk.LEFT)
        self.hist_var = tk.StringVar(value=str(self.config.get("history_size", 20)))
        ttk.Entry(r9, textvariable=self.hist_var, width=10).pack(side=tk.LEFT)

        r10 = ttk.Frame(lf)
        r10.pack(fill=tk.X, pady=3)
        ttk.Label(r10, text="Progress Interval:", width=14).pack(side=tk.LEFT)
        self.interval_var = tk.StringVar(value=str(self.config.get("progress_interval", 10)))
        ttk.Entry(r10, textvariable=self.interval_var, width=10).pack(side=tk.LEFT)
        ttk.Label(r10, text="seconds", style="Dim.TLabel").pack(side=tk.LEFT, padx=10)

        # Save button
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=15, pady=15)
        ttk.Button(btn_frame, text="Save Settings", command=self._save_settings, style="Accent.TButton").pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Save & Restart Bot", command=self._save_and_restart).pack(side=tk.LEFT, padx=10)

        # Paths
        info = ttk.LabelFrame(parent, text="File Paths", padding=12)
        info.pack(fill=tk.X, padx=15, pady=(0, 15))
        for p in [f"Config:  {CONFIG_PATH}", f"State:   {STATE_PATH}", f"Bot:     {BOT_SCRIPT}", f"Log:     {LOG_PATH}"]:
            ttk.Label(info, text=p, font=("Consolas", 8), style="Dim.TLabel").pack(anchor=tk.W)

    # =====================================================
    #  LOG TAB
    # =====================================================

    def _build_log_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  Log  ")

        self.log_text = tk.Text(
            tab, wrap=tk.WORD, font=("Consolas", 9), state=tk.DISABLED,
            bg=C["bg"], fg=C["fg2"], insertbackground=C["fg"],
            borderwidth=0, highlightthickness=0, padx=8, pady=8,
        )
        scrollbar = ttk.Scrollbar(tab, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        btn_row = ttk.Frame(tab)
        btn_row.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(btn_row, text="Clear", command=self._clear_log).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Open File",
                   command=lambda: os.startfile(str(LOG_PATH)) if LOG_PATH.exists() else None).pack(side=tk.LEFT, padx=5)

    # =====================================================
    #  STATUS BAR
    # =====================================================

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=C["bg2"], height=24)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)

        self.statusbar_label = tk.Label(bar, text="Ready", bg=C["bg2"], fg=C["fg2"],
                                         font=("Segoe UI", 9), anchor=tk.W)
        self.statusbar_label.pack(side=tk.LEFT, padx=10)

        self.statusbar_right = tk.Label(bar, text="", bg=C["bg2"], fg=C["fg_dim"],
                                         font=("Segoe UI", 9), anchor=tk.E)
        self.statusbar_right.pack(side=tk.RIGHT, padx=10)

    def _status(self, text):
        self.statusbar_label.config(text=text)

    # =====================================================
    #  ACTIONS
    # =====================================================

    def _browse_file(self, var, title, filetypes):
        path = filedialog.askopenfilename(title=title, filetypes=filetypes + [("All", "*.*")])
        if path:
            var.set(path)

    def _browse_dir(self, var):
        path = filedialog.askdirectory()
        if path:
            var.set(path)

    def _build_config_dict(self):
        users = []
        for u in self.users_var.get().split(","):
            u = u.strip()
            if u.isdigit():
                users.append(int(u))

        mt = self.turns_var.get().strip()
        prompt = self.prompt_text.get("1.0", tk.END).strip()

        def parse_list(s):
            return [x.strip() for x in s.split(",") if x.strip()] if s.strip() else []

        return {
            "bot_token": self.token_var.get().strip(),
            "allowed_users": users,
            "python_path": self.python_var.get().strip(),
            "claude_path": self.cli_var.get().strip(),
            "work_dir": self.workdir_var.get().strip(),
            "model": self.model_var.get(),
            "permission_mode": self.perm_var.get(),
            "effort": self.effort_var.get(),
            "max_turns": int(mt) if mt.isdigit() else None,
            "history_size": int(self.hist_var.get()) if self.hist_var.get().isdigit() else 20,
            "progress_interval": int(self.interval_var.get()) if self.interval_var.get().isdigit() else 10,
            "system_prompt": prompt,
            "allowed_tools": parse_list(self.allowed_tools_var.get()),
            "disallowed_tools": parse_list(self.disallowed_tools_var.get()),
            "autostart": self.autostart_var.get(),
        }

    def _save_settings(self):
        cfg = self._build_config_dict()
        if not cfg["bot_token"]:
            messagebox.showwarning("Error", "Bot Token required!")
            return False
        save_config(cfg)
        self.config = cfg
        self._status(f"Settings saved ({datetime.now().strftime('%H:%M:%S')})")
        return True

    def _save_and_restart(self):
        if self._save_settings():
            self._restart_bot()

    # --- Bot control ---

    def _start_bot(self):
        if not self._save_settings():
            return
        try:
            env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
            python = self.config.get("python_path") or sys.executable
            flags = 0
            if sys.platform == "win32":
                flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            self.bot_process = subprocess.Popen(
                [python, "-u", str(BOT_SCRIPT), "--config", str(CONFIG_PATH)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace', env=env,
                creationflags=flags,
            )
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.bot_status_label.config(text=f"Running (PID {self.bot_process.pid})", style="Running.TLabel")
            self.bot_pid_label.config(text=f"PID: {self.bot_process.pid}")
            self._status(f"Bot started (PID {self.bot_process.pid})")

            self.log_running = True
            threading.Thread(target=self._read_bot_log, daemon=True).start()
            self._poll_bot()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _stop_bot(self):
        self.log_running = False
        if self.bot_process:
            try:
                self.bot_process.terminate()
                self.bot_process.wait(timeout=5)
            except Exception:
                try:
                    self.bot_process.kill()
                except Exception:
                    pass
            self.bot_process = None
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.bot_status_label.config(text="Stopped", style="Stopped.TLabel")
        self.bot_pid_label.config(text="")
        self._status("Bot stopped")

    def _restart_bot(self):
        self._stop_bot()
        self.root.after(500, self._start_bot)

    def _reset_session(self):
        st = load_state()
        st["session_id"] = None
        save_state(st)
        self.bot_session_label.config(text="Session: new")
        self._status("Session reset")

    def _poll_bot(self):
        if self.bot_process:
            ret = self.bot_process.poll()
            if ret is not None:
                self.start_btn.config(state=tk.NORMAL)
                self.stop_btn.config(state=tk.DISABLED)
                self.bot_status_label.config(text=f"Exited ({ret})", style="Stopped.TLabel")
                self.bot_process = None
            else:
                # Update session info
                st = load_state()
                sid = st.get("session_id", "")
                cnt = st.get("msg_counter", 0)
                sid_short = (sid[:12] + "...") if sid and len(sid) > 12 else (sid or "new")
                self.bot_session_label.config(text=f"Session: {sid_short} | Msgs: {cnt}")
                self.root.after(3000, self._poll_bot)

    def _read_bot_log(self):
        try:
            log_file = open(LOG_PATH, 'a', encoding='utf-8')
        except Exception:
            log_file = None

        while self.log_running and self.bot_process and self.bot_process.stdout:
            try:
                line = self.bot_process.stdout.readline()
                if not line:
                    break
                line = line.rstrip()
                if log_file:
                    log_file.write(f"{datetime.now().strftime('%H:%M:%S')} {line}\n")
                    log_file.flush()
                self.root.after(0, self._append_log, line)
            except Exception:
                break

        if log_file:
            log_file.close()

    def _append_log(self, line):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, line + "\n")
        self.log_text.see(tk.END)
        count = int(self.log_text.index('end-1c').split('.')[0])
        if count > 500:
            self.log_text.delete("1.0", f"{count - 500}.0")
        self.log_text.config(state=tk.DISABLED)

    def _clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _setup_autostart(self):
        startup = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup"
        vbs = startup / "tg_claude_bot_v2.vbs"
        content = f'Set s = CreateObject("WScript.Shell")\ns.Run "pythonw -u ""{BOT_SCRIPT}"" --config ""{CONFIG_PATH}""", 0, False\n'
        try:
            vbs.write_text(content)
            messagebox.showinfo("Done", f"Autostart created:\n{vbs}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _detect_running_bot(self):
        found = False
        try:
            import psutil
            for proc in psutil.process_iter(['pid', 'cmdline']):
                cmdline = proc.info.get('cmdline') or []
                if any('tg_claude_bot.py' in str(c) for c in cmdline):
                    self.bot_status_label.config(text=f"Running externally (PID {proc.pid})", style="Running.TLabel")
                    self.bot_pid_label.config(text=f"PID: {proc.pid}")
                    self.stop_btn.config(state=tk.NORMAL)
                    self.start_btn.config(state=tk.DISABLED)
                    found = True
                    return
        except ImportError:
            pass

        if not found and self.config.get("bot_token") and BOT_SCRIPT.exists():
            self._start_bot()


# =====================================================
#  MAIN
# =====================================================

def main():
    root = tk.Tk()

    # Icon (optional)
    try:
        root.iconbitmap(default="")
    except Exception:
        pass

    app = App(root)

    # Center on screen
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (w // 2)
    y = (root.winfo_screenheight() // 2) - (h // 2)
    root.geometry(f"+{x}+{y}")

    root.mainloop()


if __name__ == '__main__':
    main()
