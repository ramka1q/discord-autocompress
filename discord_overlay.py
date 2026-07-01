#!/usr/bin/env python3
"""
Discord Overlay Auto-Compress (v2 — тригер на Ctrl+V у Discord)
==============================================================
Прихована фонова програма. Коли ти тиснеш Ctrl+V у Discord, щоб вставити відео, і
воно більше за ліміт — програма перехоплює вставку, показує гарне вікно БЕЗ РАМОК у
стилі Discord, стискає відео й сама вставляє вже маленький файл у Discord.

  python discord_overlay.py            -> фоновий режим (прихований)
  python discord_overlay.py --settings -> вікно налаштувань

Чому лише Ctrl+V, а не drag&drop: при перетягуванні мишкою файл потрапляє напряму в
Discord повз буфер обміну, тож сторонній програмі його шлях недоступний. Ctrl+V
працює, бо файл лежить у буфері.

Потрібен ffmpeg у PATH. Решта — стандартна бібліотека Python 3.8+ (Windows).
"""
import ctypes
import json
import os
import queue
import sys
import tempfile
import threading
from ctypes import wintypes

import tkinter as tk

import dc_core

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".discord_overlay.json")

# ---- кольори Discord ----
C_BG, C_BG2, C_DARK = "#313338", "#2b2d31", "#1e1f22"
C_BLURPLE, C_BLURPLE_H = "#5865f2", "#4752c4"
C_TEXT, C_MUTED, C_GREEN = "#f2f3f5", "#b5bac1", "#23a55a"
C_RED = "#ed4245"
C_KEY = "#010203"
FONT = "Segoe UI"

# --------------------------------------------------------------------------- #
#  WinAPI
# --------------------------------------------------------------------------- #
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

CF_HDROP, GHND = 15, 0x0042
WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
VK_CONTROL, VK_V = 0x11, 0x56
KEYEVENTF_KEYUP = 0x0002
LLKHF_INJECTED = 0x10

user32.GetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p
user32.GetForegroundWindow.restype = ctypes.c_void_p
user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.CallNextHookEx.restype = ctypes.c_long
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.GetMessageW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
user32.IsIconic.argtypes = [ctypes.c_void_p]
user32.IsIconic.restype = ctypes.c_int
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
user32.IsWindowVisible.restype = ctypes.c_int
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GetModuleHandleW.restype = ctypes.c_void_p
shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
shell32.DragQueryFileW.restype = ctypes.c_uint

LowLevelKeyboardProc = ctypes.CFUNCTYPE(
    ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, LowLevelKeyboardProc,
                                     ctypes.c_void_p, wintypes.DWORD]


class DROPFILES(ctypes.Structure):
    _fields_ = [("pFiles", wintypes.DWORD), ("pt_x", wintypes.LONG),
                ("pt_y", wintypes.LONG), ("fNC", wintypes.BOOL), ("fWide", wintypes.BOOL)]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p)]


def foreground_title() -> tuple:
    hwnd = user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return hwnd, buf.value


def clipboard_files() -> list:
    files = []
    if not user32.OpenClipboard(None):
        return files
    try:
        h = user32.GetClipboardData(CF_HDROP)
        if h:
            count = shell32.DragQueryFileW(h, 0xFFFFFFFF, None, 0)
            for i in range(count):
                length = shell32.DragQueryFileW(h, i, None, 0)
                b = ctypes.create_unicode_buffer(length + 1)
                shell32.DragQueryFileW(h, i, b, length + 1)
                files.append(b.value)
    finally:
        user32.CloseClipboard()
    return files


def set_clipboard_files(paths: list) -> bool:
    offset = ctypes.sizeof(DROPFILES)
    data = ("".join(p + "\0" for p in paths) + "\0").encode("utf-16-le")
    h = kernel32.GlobalAlloc(GHND, offset + len(data))
    if not h:
        return False
    ptr = kernel32.GlobalLock(h)
    df = DROPFILES.from_address(ptr)
    df.pFiles = offset
    df.fWide = True
    ctypes.memmove(ptr + offset, data, len(data))
    kernel32.GlobalUnlock(h)
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_HDROP, h)
    finally:
        user32.CloseClipboard()
    return True


def send_ctrl_v():
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_V, 0, 0, 0)
    user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


# --------------------------------------------------------------------------- #
#  Конфіг
# --------------------------------------------------------------------------- #
def load_config() -> dict:
    cfg = {"target_mb": 10, "audio_kbps": 128, "auto_scale": True,
           "block_paste": True, "auto_paste": True}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
#  Оверлей у стилі Discord
# --------------------------------------------------------------------------- #
def _rr_pts(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


class Overlay(tk.Toplevel):
    W, H = 480, 348

    def __init__(self, master, file_path, size_mb, cfg, discord_hwnd, on_close, watcher=None):
        super().__init__(master)
        self.file_path, self.size_mb, self.cfg = file_path, size_mb, cfg
        self.discord_hwnd, self.on_close, self.watcher = discord_hwnd, on_close, watcher
        self.cancel = {"flag": False}

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-transparentcolor", C_KEY)
        except tk.TclError:
            pass
        self.configure(bg=C_KEY)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{self.W}x{self.H}+{(sw - self.W) // 2}+{int(sh * 0.30)}")

        self.canvas = tk.Canvas(self, width=self.W, height=self.H, bg=C_KEY, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_polygon(_rr_pts(2, 2, self.W - 2, self.H - 2, 22),
                                   smooth=True, fill=C_BG, outline="")
        self.canvas.create_polygon(_rr_pts(2, 2, self.W - 2, 8, 22),
                                   smooth=True, fill=C_BLURPLE, outline="")
        self.canvas.bind("<Button-1>", lambda e: setattr(self, "_d", (e.x, e.y)))
        self.canvas.bind("<B1-Motion>", self._drag)

        self._widgets = []
        self._show_offer()

        # оверлей живе «поверх Discord»: ховаємо його, коли Discord згорнули або
        # прикрили іншим вікном, і показуємо знову, коли Discord знову активний
        self._alive = True
        self._visible = True
        self._suspend_vis = False
        self._vis_after = self.after(400, self._visibility_tick)

    def _own_hwnd(self):
        try:
            return int(self.winfo_id())
        except Exception:
            return 0

    def _visibility_tick(self):
        self._vis_after = None
        if not self._alive:
            return
        if self._suspend_vis:  # відкрито редактор обрізки — не втручаємось
            self._vis_after = self.after(300, self._visibility_tick)
            return
        try:
            fg, title = foreground_title()
            own = self._own_hwnd()
            # показуємо, лише коли активне вікно — Discord (або сам наш оверлей)
            show = ("discord" in title.lower()) or (own and fg == own)
            if self.discord_hwnd and user32.IsIconic(self.discord_hwnd):
                show = False  # Discord згорнутий
            if show and not self._visible:
                self.deiconify()
                self.attributes("-topmost", True)
                self._visible = True
            elif not show and self._visible:
                self.withdraw()
                self._visible = False
        except Exception:
            pass
        if self._alive:
            self._vis_after = self.after(300, self._visibility_tick)

    def _clear(self):
        for w in self._widgets:
            w.destroy()
        self._widgets.clear()
        self.canvas.delete("dyn")

    def _place(self, w, x, y, anchor="center"):
        self.canvas.create_window(x, y, window=w, anchor=anchor, tags="dyn")
        self._widgets.append(w)

    def _label(self, text, size, color, bold=False):
        return tk.Label(self.canvas, text=text, bg=C_BG, fg=color,
                        font=(FONT, size, "bold" if bold else "normal"))

    def _button(self, text, cmd, primary=True):
        bg, hover = (C_BLURPLE, C_BLURPLE_H) if primary else (C_BG2, C_DARK)
        b = tk.Button(self.canvas, text=text, command=cmd, bg=bg, fg=C_TEXT,
                      activebackground=hover, activeforeground=C_TEXT, relief="flat",
                      font=(FONT, 11, "bold"), bd=0, padx=18, pady=9, cursor="hand2")
        b.bind("<Enter>", lambda e: b.config(bg=hover))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

    def _show_offer(self):
        self._clear()
        name = os.path.basename(self.file_path)
        if len(name) > 42:
            name = name[:39] + "…"
        self._place(self._label("🎬", 30, C_TEXT), self.W // 2, 40)
        self._place(self._label("Це відео завелике для Discord", 14, C_TEXT, bold=True), self.W // 2, 78)
        self._place(self._label(name, 10, C_MUTED), self.W // 2, 100)
        self._place(self._label(f"{self.size_mb:.1f} МБ  →  ≈{self.cfg['target_mb']} МБ",
                                11, C_BLURPLE, bold=True), self.W // 2, 124)
        self._place(self._button("Стиснути і вставити  ▶", self._start), self.W // 2, 164)
        self._place(self._button("Поділити на частини  ⧉",
                                 lambda: self._start_split(balanced=False), primary=False),
                    self.W // 2, 204)
        self._place(self._button("Стиснути і поділити  ⚖",
                                 lambda: self._start_split(balanced=True), primary=False),
                    self.W // 2, 244)
        self._place(self._button("Обрізати момент ✂", self._open_trim, primary=False),
                    self.W // 2 - 8, 292, "e")
        self._place(self._button("Закрити", self._close, primary=False), self.W // 2 + 8, 292, "w")

    def _show_progress(self, title="Стискаю відео…"):
        self._clear()
        self._place(self._label(title, 14, C_TEXT, bold=True), self.W // 2, 64)
        self.sub = self._label("", 10, C_MUTED)
        self._place(self.sub, self.W // 2, 88)
        self.pct = self._label("0%", 26, C_BLURPLE, bold=True)
        self._place(self.pct, self.W // 2, 124)
        self.bx1, self.bx2, self.by = 70, self.W - 70, 165
        self.canvas.create_polygon(_rr_pts(self.bx1, self.by, self.bx2, self.by + 12, 6),
                                   smooth=True, fill=C_DARK, outline="", tags="dyn")
        self.fill = self.canvas.create_polygon(_rr_pts(self.bx1, self.by, self.bx1 + 1, self.by + 12, 6),
                                               smooth=True, fill=C_BLURPLE, outline="", tags="dyn")
        self._place(self._button("Скасувати", lambda: self.cancel.update(flag=True), primary=False),
                    self.W // 2, 210)

    def _show_done(self, final_mb, fits, pasted):
        self._clear()
        col = C_GREEN if fits else "#faa61a"
        self._place(self._label("✓", 40, col, bold=True), self.W // 2, 62)
        self._place(self._label("Готово!", 15, C_TEXT, bold=True), self.W // 2, 106)
        self._place(self._label(f"{final_mb:.2f} МБ", 11, C_MUTED), self.W // 2, 130)
        msg = "Вставлено в Discord ✓" if pasted else "У буфері — натисни Ctrl+V у Discord"
        self._place(self._label(msg, 12, C_BLURPLE, bold=True), self.W // 2, 158)
        self._place(self._button("Готово", self._close), self.W // 2, 206)
        self.after(5000, self._close)

    def _show_error(self, msg, allow_split=True, allow_trim=True):
        self._clear()
        self._place(self._label("⚠", 30, "#faa61a", bold=True), self.W // 2, 40)
        self._place(self._label("Не вдалося стиснути", 14, C_TEXT, bold=True), self.W // 2, 78)
        lines = msg.split("\n")
        for i, line in enumerate(lines):
            self._place(self._label(line, 10, C_MUTED), self.W // 2, 102 + i * 17)
        # для довгих відео: поділ на частини (якісний) або «стиснути і поділити» (менше файлів)
        y = 196
        if allow_split:
            self._place(self._button("Поділити на частини  ⧉",
                                     lambda: self._start_split(balanced=False)), self.W // 2, y)
            self._place(self._button("Стиснути і поділити  ⚖",
                                     lambda: self._start_split(balanced=True), primary=False),
                        self.W // 2, y + 40)
            y += 80
        if allow_trim:
            self._place(self._button("Обрізати момент ✂", self._open_trim, primary=False),
                        self.W // 2 - 8, y + 8, "e")
            self._place(self._button("Закрити", self._close, primary=False), self.W // 2 + 8, y + 8, "w")
        else:
            self._place(self._button("Закрити", self._close, primary=False), self.W // 2, y + 8)

    def _open_trim(self):
        try:
            info = dc_core.ffprobe_info(self.file_path)
        except Exception:
            return self._show_error("Не вдалося прочитати відео.", allow_split=False, allow_trim=False)
        self._suspend_vis = True   # редактор має «Discord» у заголовку — не смикаємо оверлей
        self.withdraw()
        self._visible = False
        try:
            from editor import VideoEditor
            VideoEditor(self.master, self.file_path, info, self.cfg, self.discord_hwnd,
                        self.watcher, on_close=self._close)
        except Exception as e:
            self._suspend_vis = False
            self.deiconify()
            self._visible = True
            self._show_error(f"Редактор недоступний:\n{str(e)[:60]}", allow_trim=False)

    def _start(self):
        try:
            info = dc_core.ffprobe_info(self.file_path)
        except Exception:
            return self._show_error("Не вдалося прочитати відео.\nМожливо, файл пошкоджений.",
                                    allow_split=False, allow_trim=False)
        target = float(self.cfg["target_mb"])
        # перевірка здійсненності: навіть якщо ВЕСЬ бюджет віддати відео — чи вистачить?
        best = dc_core.calc_video_kbps(info["duration"], target, 0, False)
        if not best or best < 50:
            mins = info["duration"] / 60
            return self._show_error(
                f"Відео завелике для {target:g} МБ ({mins:.0f} хв).\n"
                f"Підвищ ліміт у Налаштуваннях (Nitro)\nабо спершу обріж відео коротше.")
        scale = (dc_core.pick_auto_scale(info, target, self.cfg["audio_kbps"])
                 if self.cfg.get("auto_scale", True) else 0)
        out_path = dc_core.output_name(self.file_path, target)
        self._show_progress()

        def worker():
            ok, msg, mb = dc_core.compress(self.file_path, out_path, target, scale,
                                           self.cfg["audio_kbps"], info,
                                           progress_cb=lambda p: self.after(0, lambda: self._set(p)),
                                           should_cancel=lambda: self.cancel["flag"])
            self.after(0, lambda: self._after(ok, out_path, mb, target, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _set(self, pct):
        try:
            self.pct.config(text=f"{int(pct)}%")
            w = self.bx1 + (self.bx2 - self.bx1) * pct / 100
            self.canvas.coords(self.fill, *_rr_pts(self.bx1, self.by, max(self.bx1 + 1, w), self.by + 12, 6))
        except tk.TclError:
            pass

    def _after(self, ok, out_path, final_mb, target, msg=""):
        if not ok or self.cancel["flag"]:
            if os.path.exists(out_path):
                try: os.remove(out_path)
                except OSError: pass
            if self.cancel["flag"]:
                return self._close()
            return self._show_error(msg or "Не вдалося стиснути відео.")
        self._set(100)  # довести смужку до кінця
        try:
            set_clipboard_files([out_path])
            if self.watcher:
                self.watcher.mark_self_clipboard()
        except Exception:
            pass
        pasted = False
        if self.cfg.get("auto_paste", True) and self.discord_hwnd:
            try:
                user32.SetForegroundWindow(self.discord_hwnd)
                self.after(180, send_ctrl_v)
                pasted = True
            except Exception:
                pasted = False
        self._show_done(final_mb, final_mb <= target, pasted)

    # ---- розділення довгого відео на кілька частин ----
    def _set_part(self, i, n):
        try:
            self.sub.config(text=f"частина {i} з {n}")
        except (tk.TclError, AttributeError):
            pass

    def _start_split(self, balanced=False):
        try:
            info = dc_core.ffprobe_info(self.file_path)
        except Exception:
            return self._show_error("Не вдалося прочитати відео.", allow_split=False, allow_trim=False)
        target = float(self.cfg["target_mb"])
        # balanced=True -> «стиснути і поділити»: менше частин, зате кожна стискається сильніше
        n_parts = (dc_core.plan_parts_balanced(info["duration"], target, self.cfg["audio_kbps"],
                                               info["has_audio"]) if balanced else None)
        self.cancel["flag"] = False
        self._show_progress(title="Стискаю і ділю…" if balanced else "Ділю на частини…")

        def worker():
            ok, msg, outs = dc_core.split_compress(
                self.file_path, target, self.cfg.get("auto_scale", True),
                self.cfg["audio_kbps"], info,
                progress_cb=lambda p: self.after(0, lambda: self._set(p)),
                should_cancel=lambda: self.cancel["flag"],
                part_cb=lambda i, n: self.after(0, lambda: self._set_part(i, n)),
                n_parts=n_parts)
            self.after(0, lambda: self._after_split(ok, outs, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _after_split(self, ok, outs, msg=""):
        if self.cancel["flag"]:
            for p in outs:
                try: os.remove(p)
                except OSError: pass
            return self._close()
        if not ok or not outs:
            return self._show_error(msg or "Не вдалося розділити відео.", allow_trim=False)
        self._set(100)
        try:
            set_clipboard_files(outs)
            if self.watcher:
                self.watcher.mark_self_clipboard()
        except Exception:
            pass
        # авто-вставка лише якщо частин не більше за ліміт Discord (10 вкладень за раз)
        pasted = False
        if self.cfg.get("auto_paste", True) and self.discord_hwnd and len(outs) <= 10:
            try:
                user32.SetForegroundWindow(self.discord_hwnd)
                self.after(180, send_ctrl_v)
                pasted = True
            except Exception:
                pasted = False
        self._show_done_split(len(outs), pasted)

    def _show_done_split(self, n, pasted):
        self._clear()
        self._place(self._label("✓", 38, C_GREEN, bold=True), self.W // 2, 54)
        self._place(self._label(f"Готово — {n} частин", 15, C_TEXT, bold=True), self.W // 2, 98)
        if pasted:
            msg = "Вставлено в Discord ✓"
        elif n > 10:
            msg = "Усі в буфері · Ctrl+V (Discord бере до 10 за раз)"
        else:
            msg = "Усі в буфері — натисни Ctrl+V у Discord"
        self._place(self._label(msg, 11, C_BLURPLE, bold=True), self.W // 2, 128)
        self._place(self._label("Файли поруч з оригіналом: …_part1, _part2 …", 9, C_MUTED),
                    self.W // 2, 152)
        self._place(self._button("Готово", self._close), self.W // 2, 200)
        self.after(9000, self._close)

    def _close(self):
        self._alive = False
        if getattr(self, "_vis_after", None):
            try:
                self.after_cancel(self._vis_after)
            except Exception:
                pass
        try:
            self.destroy()
        finally:
            if self.on_close:
                self.on_close()

    def _drag(self, e):
        self.geometry(f"+{self.winfo_x() + e.x - self._d[0]}+{self.winfo_y() + e.y - self._d[1]}")


# --------------------------------------------------------------------------- #
#  Вікно-тример: кадрове прев'ю + повзунки + обрізка під ліміт
# --------------------------------------------------------------------------- #
def _fmt_time(t):
    t = max(0, int(t))
    return f"{t // 60}:{t % 60:02d}"


class TrimWindow(tk.Toplevel):
    def __init__(self, master, file_path, info, cfg, discord_hwnd, watcher, on_close):
        super().__init__(master)
        self.file_path, self.info, self.cfg = file_path, info, cfg
        self.discord_hwnd, self.watcher, self.on_close = discord_hwnd, watcher, on_close
        self.dur = max(0.1, info["duration"])
        self.cancel = {"flag": False}
        self.busy = False
        self._preview_after = None
        self._frame_idx = 0
        self._tmpdir = tempfile.mkdtemp(prefix="dovl_")
        self._frames = [os.path.join(self._tmpdir, "a.png"), os.path.join(self._tmpdir, "b.png")]
        self._img = None

        self.title("Обрізати відео — Discord Auto-Compress")
        self.configure(bg=C_BG)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._close)

        target = float(cfg["target_mb"])
        audio = cfg["audio_kbps"]
        self.max_good = dc_core.max_seconds(target, audio, 800)   # гарна якість
        self.max_min = dc_core.max_seconds(target, audio, 150)    # мінімум

        self._build()
        self.start_var.set(0.0)
        self.end_var.set(min(self.dur, max(1.0, self.max_good)))
        self._update_info()
        self._schedule_preview(0.0)

    def _build(self):
        pad = {"bg": C_BG, "fg": C_TEXT}
        tk.Label(self, text="✂  Обери момент для Discord", font=(FONT, 13, "bold"),
                 **pad).pack(pady=(12, 6))

        self.preview_lbl = tk.Label(self, text="завантаження кадру…", bg=C_DARK,
                                    fg=C_MUTED, width=54, height=12)
        self.preview_lbl.pack(padx=14)
        self.time_lbl = tk.Label(self, text="0:00", font=(FONT, 10), bg=C_BG, fg=C_MUTED)
        self.time_lbl.pack(pady=(4, 8))

        def mkscale(label, var, cb):
            row = tk.Frame(self, bg=C_BG); row.pack(fill="x", padx=18)
            tk.Label(row, text=label, width=8, anchor="w", font=(FONT, 10), bg=C_BG,
                     fg=C_TEXT).pack(side="left")
            res = 1.0 if self.dur > 600 else 0.1
            s = tk.Scale(row, from_=0, to=self.dur, orient="horizontal", resolution=res,
                         variable=var, command=cb, showvalue=False, length=380,
                         bg=C_BG, fg=C_TEXT, troughcolor=C_DARK, highlightthickness=0,
                         activebackground=C_BLURPLE, sliderrelief="flat", bd=0)
            s.pack(side="left", fill="x", expand=True, padx=6)
            return s

        self.start_var = tk.DoubleVar()
        self.end_var = tk.DoubleVar()
        mkscale("Початок", self.start_var, self._on_start)
        mkscale("Кінець", self.end_var, self._on_end)

        self.info_lbl = tk.Label(self, text="", font=(FONT, 11, "bold"), bg=C_BG, fg=C_TEXT)
        self.info_lbl.pack(pady=(10, 2))
        self.hint_lbl = tk.Label(
            self, font=(FONT, 9), bg=C_BG, fg=C_MUTED,
            text=f"Макс для {self.cfg['target_mb']:g} МБ: ~{_fmt_time(self.max_good)} (гарно) · "
                 f"~{_fmt_time(self.max_min)} (мінімум)")
        self.hint_lbl.pack()

        btns = tk.Frame(self, bg=C_BG); btns.pack(pady=12)

        def mkbtn(parent, text, cmd, primary=True):
            bg, hov = (C_BLURPLE, C_BLURPLE_H) if primary else (C_BG2, C_DARK)
            b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=C_TEXT,
                          activebackground=hov, activeforeground=C_TEXT, relief="flat",
                          font=(FONT, 11, "bold"), bd=0, padx=18, pady=9, cursor="hand2")
            b.bind("<Enter>", lambda e: b.config(bg=hov))
            b.bind("<Leave>", lambda e: b.config(bg=bg))
            return b

        self.trim_btn = mkbtn(btns, "Обрізати і вставити  ▶", self._start_trim)
        self.trim_btn.pack(side="left", padx=6)
        mkbtn(btns, "Скасувати", self._close, primary=False).pack(side="left", padx=6)

    # ---- повзунки ----
    def _on_start(self, _v):
        if self.start_var.get() >= self.end_var.get():
            self.end_var.set(min(self.dur, self.start_var.get() + (1.0 if self.dur > 600 else 0.1)))
        self._update_info()
        self._schedule_preview(self.start_var.get())

    def _on_end(self, _v):
        if self.end_var.get() <= self.start_var.get():
            self.start_var.set(max(0, self.end_var.get() - (1.0 if self.dur > 600 else 0.1)))
        self._update_info()
        self._schedule_preview(self.end_var.get())

    def _update_info(self):
        if self.busy:
            return
        s, e = self.start_var.get(), self.end_var.get()
        d = e - s
        if d <= 0:
            self.info_lbl.config(text="Кінець має бути після початку", fg=C_RED)
            self.trim_btn.config(state="disabled")
            return
        v = dc_core.calc_video_kbps(d, float(self.cfg["target_mb"]),
                                    self.cfg["audio_kbps"], self.info["has_audio"]) or 0
        if v >= 600:
            col, tag = C_GREEN, "✓ гарна якість"
        elif v >= 150:
            col, tag = "#faa61a", "⚠ норм якість"
        elif v >= 50:
            col, tag = "#faa61a", "⚠ слабка якість"
        else:
            col, tag = C_RED, "✗ задовгий шматок"
        self.info_lbl.config(text=f"Вибрано {d:.1f} с · відео ~{v} kbps · {tag}", fg=col)
        self.trim_btn.config(state=("normal" if v >= 50 else "disabled"))

    # ---- прев'ю кадру ----
    def _schedule_preview(self, t):
        self._pending_t = t
        if self._preview_after:
            try: self.after_cancel(self._preview_after)
            except Exception: pass
        self._preview_after = self.after(130, self._run_preview)

    def _run_preview(self):
        t = self._pending_t
        self._frame_idx ^= 1
        png = self._frames[self._frame_idx]

        def work():
            if dc_core.extract_frame(self.file_path, t, png, width=380):
                self.after(0, lambda: self._set_image(png, t))
        threading.Thread(target=work, daemon=True).start()

    def _set_image(self, png, t):
        try:
            img = tk.PhotoImage(file=png)
            self._img = img
            self.preview_lbl.config(image=img, text="")
            self.time_lbl.config(text=_fmt_time(t))
        except tk.TclError:
            pass

    # ---- обрізка + стиснення ----
    def _start_trim(self):
        s, e = self.start_var.get(), self.end_var.get()
        d = e - s
        if d <= 0:
            return
        self.busy = True
        self.trim_btn.config(state="disabled")
        target = float(self.cfg["target_mb"])
        scale = (dc_core.pick_auto_scale(self.info, target, self.cfg["audio_kbps"])
                 if self.cfg.get("auto_scale", True) else 0)
        out_path = dc_core.output_name(self.file_path, target)

        def worker():
            ok, msg, mb = dc_core.compress(
                self.file_path, out_path, target, scale, self.cfg["audio_kbps"], self.info,
                progress_cb=lambda p: self.after(0, lambda: self.info_lbl.config(
                    text=f"Стискаю… {int(p)}%", fg=C_BLURPLE)),
                should_cancel=lambda: self.cancel["flag"], start=s, dur=d)
            self.after(0, lambda: self._done(ok, out_path, mb, target, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, ok, out_path, mb, target, msg):
        if not ok:
            if os.path.exists(out_path):
                try: os.remove(out_path)
                except OSError: pass
            self.busy = False
            self.info_lbl.config(text=msg or "Не вдалося стиснути", fg=C_RED)
            self.trim_btn.config(state="normal")
            return
        try:
            set_clipboard_files([out_path])
            if self.watcher:
                self.watcher.mark_self_clipboard()
        except Exception:
            pass
        pasted = ""
        if self.cfg.get("auto_paste", True) and self.discord_hwnd:
            try:
                user32.SetForegroundWindow(self.discord_hwnd)
                self.after(180, send_ctrl_v)
                pasted = " · вставлено в Discord"
            except Exception:
                pasted = ""
        self.info_lbl.config(text=f"Готово ✓ {mb:.2f} МБ{pasted}", fg=C_GREEN)
        self.after(2500, self._close)

    def _close(self):
        self.cancel["flag"] = True
        try:
            import shutil
            shutil.rmtree(self._tmpdir, ignore_errors=True)
        except Exception:
            pass
        try:
            self.destroy()
        finally:
            if self.on_close:
                self.on_close()


# --------------------------------------------------------------------------- #
#  Фон: перехоплення Ctrl+V у Discord
# --------------------------------------------------------------------------- #
def _autoupdate_bg():
    """Тихо перевіряє оновлення на GitHub (лише в друга — за маркером .autoupdate)."""
    try:
        import update
        update.auto()
    except Exception:
        pass


class Watcher:
    def __init__(self):
        self.cfg = load_config()
        threading.Thread(target=_autoupdate_bg, daemon=True).start()
        self.root = tk.Tk()
        self.root.withdraw()
        self.q = queue.Queue()
        self.overlay_open = False
        self.last_seq_self = 0
        self._cooldown_until = 0
        threading.Thread(target=self._hook_thread, daemon=True).start()
        self.root.after(120, self._poll_queue)

    def mark_self_clipboard(self):
        # ми самі поклали файл — стартуємо коротку «паузу», щоб не зреагувати на свою ж вставку
        self._cooldown_until = kernel32.GetTickCount() + 1500

    # ---- перевірка: чи треба перехопити цю вставку ----
    def _should_intercept(self):
        hwnd, title = foreground_title()
        if "discord" not in title.lower():
            return None
        limit = self.cfg["target_mb"] * 1024 * 1024
        for path in clipboard_files():
            if os.path.splitext(path)[1].lower() not in dc_core.VIDEO_EXT:
                continue
            if "_discord_" in os.path.basename(path) or not os.path.isfile(path):
                continue
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if size > limit:
                return (hwnd, path, size)
        return None

    # ---- LL keyboard hook ----
    def _ll_proc(self, nCode, wParam, lParam):
        try:
            if nCode == 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if (kb.vkCode == VK_V and not (kb.flags & LLKHF_INJECTED)
                        and (user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)):
                    now = kernel32.GetTickCount()
                    if now >= self._cooldown_until and not self.overlay_open:
                        hit = self._should_intercept()
                        if hit:
                            self._cooldown_until = now + 1500
                            self.q.put(hit)
                            if self.cfg.get("block_paste", True):
                                return 1  # зʼїдаємо Ctrl+V, щоб Discord не лаявся
        except Exception:
            pass
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _hook_thread(self):
        self._proc = LowLevelKeyboardProc(self._ll_proc)
        self._hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    # ---- черга подій -> головний потік Tk ----
    def _poll_queue(self):
        try:
            while not self.overlay_open:
                hwnd, path, size = self.q.get_nowait()
                self.overlay_open = True
                Overlay(self.root, path, size / 1024 / 1024, self.cfg, hwnd,
                        on_close=self._closed, watcher=self)
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    def _closed(self):
        self.overlay_open = False

    def run(self):
        self.root.mainloop()


# --------------------------------------------------------------------------- #
#  Налаштування
# --------------------------------------------------------------------------- #
def settings_window():
    cfg = load_config()
    root = tk.Tk()
    root.title("Налаштування Auto-Compress")
    root.geometry("400x380")
    root.configure(bg=C_BG)

    def L(t, **kw):
        return tk.Label(root, text=t, bg=C_BG, fg=C_TEXT, **kw)

    L("Ідеальний розмір (ліміт Discord)", font=(FONT, 11, "bold")).pack(pady=(16, 6))
    target = tk.IntVar(value=cfg["target_mb"])
    for t, mb in (("10 МБ (без Nitro)", 10), ("25 МБ", 25),
                  ("50 МБ (Nitro Basic)", 50), ("500 МБ (Nitro)", 500)):
        tk.Radiobutton(root, text=t, variable=target, value=mb, bg=C_BG, fg=C_TEXT,
                       selectcolor=C_DARK, activebackground=C_BG, activeforeground=C_TEXT,
                       font=(FONT, 10)).pack(anchor="w", padx=46)

    auto = tk.BooleanVar(value=cfg.get("auto_scale", True))
    block = tk.BooleanVar(value=cfg.get("block_paste", True))
    paste = tk.BooleanVar(value=cfg.get("auto_paste", True))

    def C(t, v):
        tk.Checkbutton(root, text=t, variable=v, bg=C_BG, fg=C_TEXT, selectcolor=C_DARK,
                       activebackground=C_BG, activeforeground=C_TEXT,
                       font=(FONT, 10)).pack(anchor="w", padx=46)
    C("Авто-підбір роздільності", auto)
    C("Блокувати «завелику» вставку в Discord", block)
    C("Сам вставляти стиснутий файл у Discord", paste)

    arow = tk.Frame(root, bg=C_BG); arow.pack(anchor="w", padx=46, pady=6)
    tk.Label(arow, text="Аудіо kbps:", bg=C_BG, fg=C_TEXT, font=(FONT, 10)).pack(side="left")
    audio = tk.IntVar(value=cfg.get("audio_kbps", 128))
    tk.Spinbox(arow, from_=0, to=320, increment=32, width=6, textvariable=audio).pack(side="left", padx=6)

    def save():
        save_config({"target_mb": target.get(), "audio_kbps": audio.get(),
                     "auto_scale": auto.get(), "block_paste": block.get(),
                     "auto_paste": paste.get()})
        root.destroy()

    tk.Button(root, text="Зберегти", command=save, bg=C_BLURPLE, fg=C_TEXT,
              activebackground=C_BLURPLE_H, relief="flat", font=(FONT, 11, "bold"),
              padx=20, pady=8, cursor="hand2").pack(pady=14)
    root.mainloop()


if __name__ == "__main__":
    if "--settings" in sys.argv:
        settings_window()
    else:
        Watcher().run()
