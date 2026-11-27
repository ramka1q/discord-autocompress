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
import threading
import time
from ctypes import wintypes

import tkinter as tk

import dc_core
import themes
import ui
import media
import i18n
import jokes
import stats

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".discord_overlay.json")
FREE_LIMIT_MB = 20

# ---- кольори теми (заповнюються apply_theme; імена лишаються C_* для сумісності) ----
C_BG, C_BG2, C_DARK = "#313338", "#2b2d31", "#1e1f22"
C_BLURPLE, C_BLURPLE_H = "#5865f2", "#4752c4"
C_TEXT, C_MUTED, C_GREEN = "#f2f3f5", "#b5bac1", "#23a55a"
C_RED = "#ed4245"
C_WARN = "#faa61a"
C_KEY = "#010203"
FONT = themes.FONT
LANG = "en"
THEME = "mono"


def apply_theme(name: str):
    """Перемикає глобальні кольори overlay на палітру теми (нові вікна беруть нові кольори)."""
    global C_BG, C_BG2, C_DARK, C_BLURPLE, C_BLURPLE_H, C_TEXT, C_MUTED, C_GREEN, C_RED, C_WARN
    global THEME
    THEME = name if name in themes.THEMES else themes.DEFAULT
    p = themes.palette(name)
    C_BG, C_BG2, C_DARK = p["bg"], p["panel"], p["dark"]
    C_BLURPLE, C_BLURPLE_H = p["accent"], p["accent_h"]
    C_TEXT, C_MUTED, C_GREEN = p["text"], p["muted"], p["green"]
    C_RED = p["red"]
    C_WARN = p.get("warn", "#faa61a")


def L(key, **kw):
    """Коротко: переклад рядка overlay поточною мовою."""
    return i18n.tr(LANG, key, **kw)


SOUND_WAV = os.path.join(os.path.expanduser("~"), ".discord_done_sound.wav")


def play_done_sound(cfg):
    """Звук після стиснення (async, ctypes -> онлайн). Свій .wav, якщо заданий,
    інакше — системний звук Windows."""
    if not cfg.get("sound_done", True):
        return
    try:
        f = cfg.get("sound_file", "")
        if f and os.path.isfile(f):
            # SND_FILENAME(0x20000) | SND_ASYNC(0x1) | SND_NODEFAULT(0x2)
            ctypes.windll.winmm.PlaySoundW(ctypes.c_wchar_p(f), None, 0x00020003)
        else:
            # SND_ALIAS(0x10000) | SND_ASYNC(0x1) | SND_NODEFAULT(0x2) — звук Windows
            ctypes.windll.winmm.PlaySoundW(ctypes.c_wchar_p("SystemAsterisk"), None, 0x00010003)
    except Exception:
        pass

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
VK_MENU, VK_E = 0x12, 0x45          # Alt, E — Ctrl+Alt+E відкриває «Мої монтажі»
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
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
# УВАГА: НЕ задаємо argtypes для GetCursorPos — user32 спільний для всіх модулів,
# а трей (tray.py) кличе GetCursorPos зі СВОЄЮ структурою POINT. Жорсткий argtypes
# ламав меню трею. Без argtypes ctypes приймає byref будь-якої POINT-структури.
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
    cfg = {"target_mb": FREE_LIMIT_MB, "free_limit_mb": FREE_LIMIT_MB,
           "audio_kbps": 128, "auto_scale": True,
           "block_paste": True, "auto_paste": True,
           "lang": "en", "theme": "mono",   # перший запуск (нема конфіга) -> англійська
           "compress_video": True, "compress_images": True, "compress_audio": True,
           "keep_local": "ask", "offer_shrink": True, "sound_done": True,
           "sound_file": "", "notify_done": True,
           "encoder": "auto", "encoder_best": "", "gpu_seen": False}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            saved = json.load(f)
        # Migrate users who had the old free-tier preset selected.  Remembering
        # the free limit separately makes the same migration safe next time
        # Discord changes it, while preserving 25/50/500 MB choices.
        previous_free = saved.get("free_limit_mb", 10)
        if saved.get("target_mb", previous_free) == previous_free and previous_free < FREE_LIMIT_MB:
            saved["target_mb"] = FREE_LIMIT_MB
        if saved.get("free_limit_mb") != FREE_LIMIT_MB:
            saved["free_limit_mb"] = FREE_LIMIT_MB
        cfg.update(saved)
        save_config(cfg)
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
#  Оверлей
# --------------------------------------------------------------------------- #
def _rr_pts(x1, y1, x2, y2, r):
    return ui.rr_pts(x1, y1, x2, y2, r)


def _fmt_dur(sec):
    sec = max(0, int(round(sec)))
    if sec >= 3600:
        return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"
    return f"{sec // 60}:{sec % 60:02d}"


def _palette():
    """Поточна палітра оверлея (глобальні C_* + градієнт/картка з теми)."""
    p = themes.palette(THEME)
    return dict(p, bg=C_BG, panel=C_BG2, dark=C_DARK, accent=C_BLURPLE, accent_h=C_BLURPLE_H,
                text=C_TEXT, muted=C_MUTED, green=C_GREEN, red=C_RED, warn=C_WARN)


class Overlay(tk.Toplevel):
    """Вікно без рамок поверх Discord: пропозиція -> прогрес -> «Готово».
    Усе намальовано на одному Canvas (заокруглена картка з прозорими кутами)."""
    W = 460
    MARGIN = 34          # відступ кнопок від країв картки
    BTN_H = 42
    HEAD = 46            # висота «шапки» з логотипом і хрестиком

    def __init__(self, master, file_path, size_mb, cfg, discord_hwnd, on_close,
                 watcher=None, kind="video"):
        super().__init__(master)
        self.file_path, self.size_mb, self.cfg = file_path, size_mb, cfg
        self.discord_hwnd, self.on_close, self.watcher = discord_hwnd, on_close, watcher
        self.kind = kind                 # "video" | "image" | "audio" | "shrink"
        self.out_path = None             # шлях стиснутого файла (для «лишити/видалити»)
        self.cancel = {"flag": False}
        self.P = _palette()
        self.H = 452
        self._closed = False
        self._timers = {}                # іменовані after-таймери (скасовуються при закритті)
        self._btns = {}
        self._btn_seq = 0
        self._meta = None                # «1920×1080 · 2:31 · 60 fps» (рахується у фоні)
        self._screen = ""

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-transparentcolor", C_KEY)
        except tk.TclError:
            pass
        self.configure(bg=C_KEY)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self._x, self._y = (sw - self.W) // 2, int(sh * 0.26)
        self.geometry(f"{self.W}x{self.H}+{self._x}+{self._y + 18}")

        self.canvas = tk.Canvas(self, width=self.W, height=self.H, bg=C_KEY, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._widgets = []
        self._draw_card()
        self.canvas.tag_bind("drag", "<Button-1>", self._drag_start)
        self.canvas.tag_bind("drag", "<B1-Motion>", self._drag)
        self._hover_tag = None
        self.canvas.bind("<Motion>", self._btn_motion)
        self.canvas.bind("<Enter>", self._btn_motion)
        self.canvas.bind("<Leave>", self._btn_leave)
        self.canvas.bind("<ButtonPress-1>", self._btn_press)
        self.canvas.bind("<ButtonRelease-1>", self._btn_release)
        self.bind("<Escape>", lambda e: self._esc())

        # веб-дизайн: те саме вікно, але показує його Edge (живий місяць, справжнє скло)
        self._mirror = None
        try:
            if ui.is_mono(self.P) and watcher is not None and cfg.get("web_ui", True) is not False:
                import webov
                import webui
                if webov.window(wait=0.05):
                    self._attach_web(watcher)
                else:
                    # веб-вікна нема (його закрив Edge / сон ПК): запускаємо і чекаємо до 4 с,
                    # а не показуємо одразу запасне Tk-вікно (воно виглядало «криво»)
                    webov.prelaunch(watcher)
                    self._web_wait = time.monotonic()
                    self.attributes("-alpha", 0.0)
                    self.geometry(f"{self.W}x{self.H}+-32000+-32000")
                    dc_core.dlog("webov: window missing on paste -> launching, waiting")
        except Exception as e:
            dc_core.dlog("webov attach fail " + repr(e))
            self._mirror = None

        self._show_offer()
        self._load_meta()
        if getattr(self, "_web_wait", None):
            self.after(100, self._await_web)
        elif self._mirror is None:
            self._intro()

        # оверлей живе «поверх Discord»: ховаємо його, коли Discord згорнули або
        # прикрили іншим вікном, і показуємо знову, коли Discord знову активний
        self._alive = True
        self._visible = True
        self._suspend_vis = False
        self._vis_after = self.after(400, self._visibility_tick)

    # ------------------------------------------------------------ сервіс --- #
    def _later(self, name, ms, fn):
        """after() з іменем: новий таймер з тим самим іменем скасовує попередній."""
        old = self._timers.pop(name, None)
        if old:
            try:
                self.after_cancel(old)
            except Exception:
                pass
        if self._closed:
            return None

        def run():
            self._timers.pop(name, None)
            if not self._closed:
                fn()
        tid = self.after(ms, run)
        self._timers[name] = tid
        return tid

    def _ui(self, fn):
        """Безпечний виклик у головному потоці Tk з робочого потоку."""
        if self._closed:
            return
        try:
            self.after(0, lambda: None if self._closed else fn())
        except Exception:
            pass

    def _attach_web(self, watcher):
        import webov
        import webui
        self.attributes("-alpha", 0.0)
        self.geometry(f"{self.W}x{self.H}+-32000+-32000")
        bridge, _port = webui.start(watcher)
        self._mirror = webov.Mirror(self, bridge)

    def _await_web(self):
        """Чекаємо, поки щойно запущене веб-вікно з'явиться; не вийшло за 6 с — Tk-вікно."""
        if self._closed or not getattr(self, "_web_wait", None):
            return
        try:
            import webov
            if webov.window(wait=0.02):
                t0 = self._web_wait
                self._web_wait = None
                self._attach_web(self.watcher)
                dc_core.dlog("webov: window ready after %.1fs" % (time.monotonic() - t0))
                return
        except Exception as e:
            dc_core.dlog("webov await fail " + repr(e))
        if time.monotonic() - self._web_wait > 6.0:
            self._web_wait = None
            dc_core.dlog("webov: no web window in 6 s -> Tk overlay")
            try:
                self.geometry(f"{self.W}x{self.H}+{self._x}+{self._y + 18}")
            except tk.TclError:
                return
            self._intro()
            return
        self.after(100, self._await_web)

    def _intro(self):
        """Поява: легкий виїзд знизу + проявлення."""
        try:
            self.attributes("-alpha", 0.0)
        except tk.TclError:
            return
        steps = 10

        def tick(i=1):
            if self._closed:
                return
            t = ui.ease_out(i / steps)
            try:
                self.attributes("-alpha", t)
                self.geometry(f"+{self._x}+{int(self._y + 18 * (1 - t))}")
            except tk.TclError:
                return
            if i < steps:
                self.after(16, lambda: tick(i + 1))
        self.after(10, tick)

    def _fg_is_own_process(self, fg):
        """Чи належить активне вікно НАШОМУ процесу (оверлей, редактор тощо)."""
        if not fg:
            return False
        if self._mirror is not None:
            import webov
            if webov.is_own(fg):           # клік по веб-вікну оверлея — це теж «наше»
                return True
        try:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
            return pid.value == os.getpid()
        except Exception:
            return False

    def _visibility_tick(self):
        self._vis_after = None
        if not self._alive:
            return
        if self._suspend_vis:  # відкрито редактор обрізки — не втручаємось
            self._vis_after = self.after(300, self._visibility_tick)
            return
        try:
            fg, title = foreground_title()
            if self._fg_is_own_process(fg):
                show = True            # клікнули по НАШОМУ вікну — не ховаємось (виняток)
            elif "discord" in title.lower() and not (
                    self.discord_hwnd and user32.IsIconic(self.discord_hwnd)):
                show = True            # активний Discord і він не згорнутий
            else:
                show = False           # згорнули Discord або перейшли в іншу програму
            if show and not self._visible:
                if self._mirror is None:
                    self.deiconify()
                    self.attributes("-topmost", True)
                self._visible = True
            elif not show and self._visible:
                if self._mirror is None:
                    self.withdraw()
                self._visible = False
        except Exception:
            pass
        if self._alive:
            self._vis_after = self.after(300, self._visibility_tick)

    # ------------------------------------------------------ малювання ---- #
    def _set_height(self, h):
        h = int(h)
        if h == self.H:
            return
        self.H = h
        try:
            self.canvas.config(height=h)
            self.geometry(f"{self.W}x{h}")
        except tk.TclError:
            pass
        self._draw_card()

    def _draw_card(self):
        """Підложка: заокруглена картка з тінню, градієнтна смужка зверху,
        логотип + назва (за них можна тягнути вікно) і хрестик закриття."""
        c, P, W, H = self.canvas, self.P, self.W, self.H
        c.delete("card")
        # «тінь» — кілька зсунутих темних обрисів (у Tk немає альфи)
        mono = ui.is_mono(P)
        if not mono:
            for i, t in ((5, 0.55), (3, 0.35)):
                ui.round_rect(c, 2 + i - 2, 2 + i, W - 2 - i + 2, H - 2 + i - 4, 26,
                              fill=ui.darken(C_BG, t), outline="", tags="card")
        ui.round_rect(c, 2, 2, W - 4, H - 6, 26, fill=C_BG,
                      outline=ui.mix(C_BG, C_TEXT, 0.10), tags=("card", "drag", "cardbg"))
        sky = mono
        if mono:     # Moon: живий місяць з променями (частота монітора); поза карткою — «прозоре»
            if getattr(self, "_moonfx", None) is None:
                self._moonfx = ui.MoonFX(c, W - 40, 34, 110, reach=6.5)
                self.bind("<Destroy>", lambda e: self._moonfx.stop() if e.widget is self else None, add="+")
            k = 80
            c.create_polygon(ui.rr_pts(2 - k / 2, 2 - k / 2, W - 4 + k / 2, H - 6 + k / 2, 26 + k / 2), smooth=True,
                             fill="", outline=C_KEY, width=k, tags=("card", "cardmask"))
            ui.round_rect(c, 2, 2, W - 4, H - 6, 26, fill="", outline="#1a1a1a", tags=("card", "cardmask"))
        # м'яке сяйво акценту у верхній частині
        for i in range(10 if not sky else 0, 0, -1):
            t = i / 10.0
            rx, ry = 176 * t + 20, 64 * t + 14
            c.create_oval(W / 2 - rx, 34 - ry, W / 2 + rx, 34 + ry,
                          fill=ui.mix(C_BG, ui.mix(C_BLURPLE, ui.accent2(P), 0.5), 0.09 * (1 - t) + 0.01),
                          outline="", tags=("card", "glow", "drag"))
        # верхній край картки малюємо ще раз, щоб сяйво не вилазило за заокруглення
        c.create_rectangle(0, 0, W, 2, fill=C_KEY, outline="", tags="card")
        if not sky:
            ui.grad_round_rect(c, 26, 3, W - 28, 6, 2, C_BLURPLE, ui.accent2(P), tags=("card",))
        # логотип і назва
        ui.logo(c, 22, 16, 20, P, tags=("card", "drag"))
        c.create_text(50, 26, text="AUTO-COMPRESS" if sky else "Auto-Compress", anchor="w", fill=C_MUTED,
                      font=ui.tag_font(8) if sky else (FONT, 9, "bold"), tags=("card", "drag"))
        # хрестик
        cx, cy = W - 32, 26
        c.create_oval(cx - 13, cy - 13, cx + 13, cy + 13, fill=C_BG, outline="",
                      tags=("card", "xbtn", "xbg"))
        c.create_text(cx, cy, text="✕", fill=C_MUTED, font=(FONT, 10, "bold"),
                      tags=("card", "xbtn", "xfg"))
        c.tag_bind("xbtn", "<Enter>", lambda e: (c.itemconfig("xbg", fill=ui.mix(C_BG, C_RED, 0.85)),
                                                  c.itemconfig("xfg", fill="#ffffff"),
                                                  c.config(cursor="hand2")))
        c.tag_bind("xbtn", "<Leave>", lambda e: (c.itemconfig("xbg", fill=C_BG),
                                                  c.itemconfig("xfg", fill=C_MUTED),
                                                  c.config(cursor="")))
        c.tag_bind("xbtn", "<Button-1>", lambda e: self._esc())
        c.tag_lower("card")
        if mono:     # порядок: картка -> промені/місяць -> маска кутів -> решта
            c.tag_lower("moonfx")
            c.tag_lower("cardbg")
            c.tag_raise("cardmask", "moonfx")

    def _clear(self):
        for name in ("ring", "joke", "autoclose", "pop"):
            old = self._timers.pop(name, None)
            if old:
                try:
                    self.after_cancel(old)
                except Exception:
                    pass
        for w in self._widgets:
            try:
                w.destroy()
            except tk.TclError:
                pass
        self._widgets.clear()
        self._btns.clear()
        self._w_chips, self._w_badge, self._w_done, self._w_ac = [], None, None, None
        self._hover_tag = None
        self.canvas.delete("dyn")
        try:
            self.canvas.config(cursor="")
        except tk.TclError:
            pass

    def _place(self, w, x, y, anchor="center"):
        self.canvas.create_window(x, y, window=w, anchor=anchor, tags="dyn")
        self._widgets.append(w)

    def _text(self, text, y, size, color, bold=True, x=None, tags=(), width=None):
        if ui.is_mono(self.P) and bold and size >= 15:      # Moon: заголовок Instrument Serif курсивом
            f = ui.title_font(text, size - 1)
        else:
            f = (FONT, size, "bold" if bold else "normal")
        return self.canvas.create_text(
            self.W // 2 if x is None else x, y, text=text, fill=color,
            font=f, justify="center",
            tags=("dyn",) + tuple(tags), width=width or (self.W - 2 * self.MARGIN))

    def _glow(self, cx, cy, R, color, strength=0.28):
        if ui.is_mono(self.P):       # Moon: без заливки навколо значка — щоб промені було видно
            return
        for i in range(8, 0, -1):
            t = i / 8.0
            r = R * (1 + 0.9 * t)
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="",
                                    fill=ui.mix(C_BG, color, strength * (1 - t) ** 1.6 + 0.02),
                                    tags="dyn")

    def _badge(self, icon, cy, c1=None, c2=None, R=34):
        """Значок у кружку з градієнтним кільцем і м'яким сяйвом."""
        c1 = c1 or C_BLURPLE
        c2 = c2 or ui.accent2(self.P)
        cx = self.W // 2
        self._glow(cx, cy, R, ui.mix(c1, c2, 0.5))
        self._w_badge = {"icon": icon, "cx": cx, "cy": cy, "R": R}
        ui.grad_ring(self.canvas, cx, cy, R + 4, 4, 1.0, c1, c2, C_BG2, tags=("dyn", "badge"), segs=48)
        self.canvas.create_oval(cx - R + 2, cy - R + 2, cx + R - 2, cy + R - 2,
                                fill=C_BG2, outline="", tags=("dyn", "badge"))
        self.canvas.create_text(cx, cy + 1, text=icon, font=(FONT, 24), fill=C_TEXT, tags=("dyn", "badge"))

    def _chip(self, cx, cy, text, fg, fill, size=10, tag=None, pad=12, anchor="center"):
        """Заокруглений «чип» з текстом; повертає (x1, x2)."""
        w = ui.measure(self, text, size) + 2 * pad
        h = size * 2 + 10
        x1 = cx - w / 2 if anchor == "center" else (cx if anchor == "w" else cx - w)
        tags = ("dyn", "chip") + ((tag,) if tag else ())
        if not hasattr(self, "_w_chips"):
            self._w_chips = []
        self._w_chips.append({"t": text, "x1": x1, "x2": x1 + w, "cy": cy, "h": h, "tag": tag or "",
                              "size": size, "hot": tag == "custmb"})
        ui.round_rect(self.canvas, x1, cy - h / 2, x1 + w, cy + h / 2, h / 2, fill=fill,
                      outline="", tags=tags + (("chipbg_" + tag,) if tag else ()))
        self.canvas.create_text(x1 + w / 2, cy, text=text, fill=fg, font=(FONT, size, "bold"),
                                tags=tags)
        return x1, x1 + w

    # ---- кнопки на канвасі (градієнтні пігулки з hover/press) ----
    def _cbutton(self, text, cmd, cx, cy, w, kind="primary"):
        tag = f"b{self._btn_seq}"
        self._btn_seq += 1
        self._btns[tag] = {"text": text, "cmd": cmd, "cx": cx, "cy": cy, "w": w, "kind": kind,
                           "hover": False, "down": False}
        self._draw_btn(tag)
        return tag

    # Наведення/натискання рахуємо за КООРДИНАТАМИ миші на всьому канвасі, а не
    # через <Enter>/<Leave> самих елементів кнопки: кнопка при наведенні
    # перемальовується (delete + create), а видалення елемента під курсором Tk
    # сприймає як <Leave>, нового — як <Enter> -> нескінченна злива подій, і вікно
    # зависало зі 100% CPU, щойно курсор опинявся над кнопкою.
    def _btn_at(self, x, y):
        for tag, b in self._btns.items():
            if abs(x - b["cx"]) <= b["w"] / 2 and abs(y - b["cy"]) <= self.BTN_H / 2:
                return tag
        return None

    def _btn_motion(self, e):
        tag = self._btn_at(e.x, e.y)
        if tag == self._hover_tag:
            return
        old, self._hover_tag = self._hover_tag, tag
        for t, hov in ((old, False), (tag, True)):
            b = self._btns.get(t)
            if b:
                b["hover"] = hov
                if not hov:
                    b["down"] = False
                self._draw_btn(t)
        try:
            self.canvas.config(cursor="hand2" if tag else "")
        except tk.TclError:
            pass

    def _btn_leave(self, _e):
        self._btn_motion(type("Ev", (), {"x": -9999, "y": -9999})())

    def _btn_press(self, e):
        tag = self._btn_at(e.x, e.y)
        b = self._btns.get(tag)
        if b:
            b["down"] = True
            self._draw_btn(tag)

    def _btn_release(self, e):
        tag = self._btn_at(e.x, e.y)
        pressed = [t for t, b in self._btns.items() if b["down"]]
        for t in pressed:
            self._btns[t]["down"] = False
            self._draw_btn(t)
        if tag and tag in pressed:
            self._btns[tag]["cmd"]()

    def _draw_btn(self, tag):
        b = self._btns[tag]
        c = self.canvas
        c.delete(tag)
        h = self.BTN_H
        off = 1 if b["down"] else 0
        x1, y1 = b["cx"] - b["w"] / 2, b["cy"] - h / 2 + off
        x2, y2 = b["cx"] + b["w"] / 2, b["cy"] + h / 2 + off
        tags = ("dyn", tag)
        if ui.is_mono(self.P):
            # кнопки «скляні»: без заливки, тож промені місяця видно під ними
            if b["kind"] == "primary":    # головна: рамка чисто біла + обідок і світіння (кільцями)
                rings = ((7, "#141414"), (5, "#262626"), (3, "#3a3a3a")) if b["hover"] else                         ((6, "#0c0c0c"), (4, "#181818"), (2, "#2a2a2a"))
                for d, col in rings:
                    ui.round_rect(c, x1 + 4 - d, y1 + 4 - d, x2 - 4 + d, y2 - 4 + d, h / 2 - 4 + d,
                                  fill="", outline=col, tags=tags)
                ui.round_rect(c, x1 + 4, y1 + 4, x2 - 4, y2 - 4, h / 2 - 4, fill="",
                              outline="#ffffff", width=1.5 if b["hover"] else 1, tags=tags)
            else:                         # звичайна: радіус 12, рамка білий 24%
                up = 1 if b["hover"] and not b["down"] else 0
                ui.round_rect(c, x1, y1 - up, x2, y2 - up, 12, fill="",
                              outline="#7a7a7a" if b["hover"] else "#3d3d3d", tags=tags)
                off -= up
            # прозоре «тіло» кнопки, щоб клік/наведення ловились і між буквами
            c.create_rectangle(x1 + 6, y1 + 6, x2 - 6, y2 - 6, fill="", outline="", tags=tags)
            fs = ui.fit_size(self, b["text"], b["w"] - 26, 11)
            c.create_text(b["cx"], b["cy"] + off, text=b["text"], fill="#f5f5f2",
                          font=(FONT, fs, "bold"), tags=tags)
            return
        if b["kind"] == "primary":
            a1, a2 = C_BLURPLE, ui.accent2(self.P)
            if b["hover"]:
                a1, a2 = ui.lighten(a1, 0.12), ui.lighten(a2, 0.12)
            ui.grad_round_rect(c, x1, y1, x2, y2, h / 2, a1, a2, tags=tags)
            fg = ui.ink(ui.mix(a1, a2, 0.5))
        else:
            fill = ui.mix(C_BG2, C_BLURPLE, 0.22) if b["hover"] else C_BG2
            ui.round_rect(c, x1, y1, x2, y2, h / 2, fill=fill,
                          outline=ui.mix(C_BG2, C_TEXT, 0.10), tags=tags)
            fg = C_TEXT
        fs = ui.fit_size(self, b["text"], b["w"] - 26, 11)
        c.create_text(b["cx"], b["cy"] + off, text=b["text"], fill=fg,
                      font=(FONT, fs, "bold"), tags=tags)

    def _full_w(self):
        return self.W - 2 * self.MARGIN

    def _btn_full(self, text, cmd, y, primary=True):
        self._cbutton(text, cmd, self.W // 2, y, self._full_w(), "primary" if primary else "ghost")

    def _btn_pair(self, lt, lc, rt, rc, y, left_primary=False, right_primary=True):
        """Дві РІВНІ половинки з однаковим проміжком -> симетрично на будь-якій мові."""
        gutter = 12
        w = (self._full_w() - gutter) / 2
        self._cbutton(lt, lc, self.W // 2 - gutter / 2 - w / 2, y, w,
                      "primary" if left_primary else "ghost")
        self._cbutton(rt, rc, self.W // 2 + gutter / 2 + w / 2, y, w,
                      "primary" if right_primary else "ghost")

    def _esc(self):
        if self._screen == "progress":
            self.cancel["flag"] = True
            self._text(L("ov_cancelling"), self.H - 22, 9, C_MUTED, bold=False)
        else:
            self._close()

    # ------------------------------------------------------- метадані --- #
    def _load_meta(self):
        """Роздільність / тривалість / fps у фоні — щоб вікно з'явилось миттєво."""
        path, kind = self.file_path, self.kind

        def work():
            meta = ""
            try:
                if kind in ("video", "shrink"):
                    inf = dc_core.ffprobe_info(path)
                    parts = []
                    if inf["width"] and inf["height"]:
                        parts.append(f"{inf['width']}×{inf['height']}")
                    if inf["duration"]:
                        parts.append(_fmt_dur(inf["duration"]))
                    parts.append(f"{inf['fps']:.0f} fps")
                    if not inf["has_audio"]:
                        parts.append("🔇")
                    meta = "  ·  ".join(parts)
                elif kind == "image":
                    w, h = media.image_dims(path)
                    meta = f"{w}×{h}" if w else ""
                elif kind == "audio":
                    d = media.audio_info(path)["duration"]
                    meta = _fmt_dur(d) if d else ""
            except Exception:
                meta = ""
            self._ui(lambda: self._set_meta(meta))
        threading.Thread(target=work, daemon=True).start()

    def _set_meta(self, meta):
        self._meta = meta
        if self._screen == "offer" and meta:
            self.canvas.delete("meta")
            self._text(meta, self._meta_y, 9, C_MUTED, bold=False, tags=("meta",))

    # ------------------------------------------------------- екрани ----- #
    def _show_offer(self):
        self._clear()
        self._screen = "offer"
        name = ui.ellipsize(self, os.path.basename(self.file_path), self._full_w(), 10)
        icon = {"video": "🎬", "image": "🖼", "audio": "🎵", "shrink": "🗜"}.get(self.kind, "🎬")
        big = {"video": "ov_video_big", "image": "ov_image_big",
               "audio": "ov_audio_big", "shrink": "ov_shrink_q"}.get(self.kind, "ov_video_big")
        self._badge(icon, 100)
        self._text(L(big), 164, 15, C_TEXT)
        self._text(name, 188, 10, C_MUTED, bold=False)
        u = L("unit_mb")
        cx = self.W // 2
        if self.kind == "shrink":
            self._chip(cx, 222, f"{self.size_mb:.1f} {u}", C_TEXT, C_BG2)
        else:
            # «було -> стане»: лівий чип — поточний розмір, правий (клікабельний ✏) — ціль
            left = f"{self.size_mb:.1f} {u}"
            right = f"≈ {float(self.cfg['target_mb']):g} {u}  ✏"
            lw = ui.measure(self, left, 10) + 24
            rw = ui.measure(self, right, 10) + 24
            gap = 46
            x0 = cx - (lw + gap + rw) / 2
            self._chip(x0, 222, left, C_TEXT, ui.mix(C_BG2, C_RED, 0.25), anchor="w")
            ax1, ax2 = x0 + lw + 10, x0 + lw + gap - 10
            ui.grad_round_rect(self.canvas, ax1, 220, ax2, 224, 2, C_BLURPLE, ui.accent2(self.P),
                               tags=("dyn",), step=1)
            self.canvas.create_polygon(ax2 - 1, 216, ax2 + 7, 222, ax2 - 1, 228,
                                       fill=ui.accent2(self.P), outline="", tags="dyn")
            self._chip(x0 + lw + gap, 222, right, ui.ink(C_BLURPLE), C_BLURPLE, tag="custmb",
                       anchor="w")
            c = self.canvas
            c.tag_bind("custmb", "<Button-1>", lambda e: self._custom_input())
            c.tag_bind("custmb", "<Enter>", lambda e: (c.itemconfig("chipbg_custmb", fill=C_BLURPLE_H),
                                                       c.config(cursor="hand2")))
            c.tag_bind("custmb", "<Leave>", lambda e: (c.itemconfig("chipbg_custmb", fill=C_BLURPLE),
                                                       c.config(cursor="")))
        self._meta_y = 252
        if self._meta:
            self._set_meta(self._meta)
        y = 300
        if self.kind == "shrink":
            self._btn_full(L("ov_shrink_smaller"), self._shrink_input, y)
            self._btn_pair(L("ov_trim"), self._open_trim, L("close"), self._close, y + 50,
                           left_primary=False, right_primary=False)
            return self._set_height(y + 50 + 50)
        if self.kind == "video":
            self._btn_full(L("ov_compress"), self._start, y)
            self._btn_pair(L("ov_split"), lambda: self._start_split(balanced=False),
                           L("ov_split_bal"), lambda: self._start_split(balanced=True), y + 50,
                           left_primary=False, right_primary=False)
            self._btn_pair(L("ov_trim"), self._open_trim, L("close"), self._close, y + 100,
                           left_primary=False, right_primary=False)
            return self._set_height(y + 100 + 50)
        start = self._start_image if self.kind == "image" else self._start_audio
        self._btn_full(L("ov_compress"), start, y)
        self._btn_full(L("close"), self._close, y + 50, primary=False)
        self._set_height(y + 50 + 50)

    def _show_progress(self, title=None):
        self._clear()
        self._screen = "progress"
        self._set_height(430)
        self._ring = {"cx": self.W // 2, "cy": 146, "R": 60, "w": 11}
        self._pct_target = 0.0
        self._pct_disp = 0.0
        self._t0 = time.monotonic()
        self._eta_txt = ""
        r = self._ring
        self._glow(r["cx"], r["cy"], r["R"], ui.mix(C_BLURPLE, ui.accent2(self.P), 0.5), 0.22)
        self._text(title or L("ov_working"), 240, 15, C_TEXT)
        self.sub_id = self._text("", 264, 10, C_MUTED, bold=False)
        # цікавий факт про програму — щоб скоротати час завантаження
        self.joke_id = self._text("", 312, 9, C_MUTED, bold=False, width=self.W - 96)
        self._jokes_eff = jokes.facts_for(LANG)                          # факти поточною мовою
        self._joke_i = kernel32.GetTickCount() % max(1, len(self._jokes_eff))  # старт «випадковий», без random
        self._rotate_joke()
        self._btn_full(L("ov_cancel"), lambda: self._esc(), 380, primary=False)
        self._draw_ring()
        self._ring_tick()

    def _draw_ring(self):
        r, c = self._ring, self.canvas
        c.delete("ring")
        ui.grad_ring(c, r["cx"], r["cy"], r["R"], r["w"], self._pct_disp / 100.0,
                     C_BLURPLE, ui.accent2(self.P), C_BG2, tags=("dyn", "ring"))
        c.create_text(r["cx"], r["cy"] - 6, text=f"{int(self._pct_disp)}%", fill=C_TEXT,
                      font=(FONT, 22, "bold"), tags=("dyn", "ring"))
        c.create_text(r["cx"], r["cy"] + 20, text=self._eta_txt, fill=C_MUTED,
                      font=(FONT, 9), tags=("dyn", "ring"))

    def _ring_tick(self):
        """~30 кадрів/с: відсоток на кільці плавно «доїжджає» до справжнього."""
        if self._screen != "progress":
            return
        d = self._pct_target - self._pct_disp
        if abs(d) > 0.05:
            self._pct_disp += d * 0.18 if d > 0 else d
            self._draw_ring()
        self._later("ring", 33, self._ring_tick)

    def _rotate_joke(self):
        """Крутить цікаві факти кожні ~4.5с, поки видно екран стиснення."""
        if self._screen != "progress":
            return
        eff = getattr(self, "_jokes_eff", None) or ["💡"]
        try:
            self.canvas.itemconfig(self.joke_id, text="💡  " + eff[self._joke_i % len(eff)])
        except tk.TclError:
            return
        self._joke_i += 1
        self._later("joke", 4500, self._rotate_joke)

    def _set(self, pct):
        """Справжній прогрес від ffmpeg (0..100) + оцінка часу, що лишився."""
        if getattr(self, "_screen", "") != "progress":
            return
        pct = max(0.0, min(100.0, float(pct)))
        self._pct_target = max(self._pct_target, pct)
        el = time.monotonic() - self._t0
        p = self._pct_target
        if 3 <= p < 99.5 and el > 2:
            self._eta_txt = L("ov_eta", t=_fmt_dur(el * (100 - p) / p))
        elif p >= 99.5:
            self._eta_txt = ""

    def _show_done(self, final_mb, fits, pasted, milestone=0):
        self._clear()
        self._screen = "done"
        play_done_sound(self.cfg)
        col = C_GREEN if fits else C_WARN
        cx = self.W // 2
        self._glow(cx, 100, 34, col, 0.3)
        self._done_ring(cx, 100, col)
        self._text(L("ov_done"), 164, 16, C_TEXT)
        u = L("unit_mb")
        try:
            pct = int(round((1 - final_mb / self.size_mb) * 100)) if self.size_mb else 0
        except Exception:
            pct = 0
        if pct > 0:
            self._text(f"−{pct}%", 200, 24, col)
        self._text(f"{self.size_mb:.1f} {u}  →  {final_mb:.2f} {u}", 236, 10, C_MUTED, bold=False)
        self._notify_done(f"{self.size_mb:.1f} → {final_mb:.2f} {u}", pasted)
        msg = L("ov_pasted") if pasted else L("ov_in_clip")
        self._chip(cx, 268, msg, ui.ink(ui.mix(C_BG2, col, 0.35)), ui.mix(C_BG2, col, 0.35), size=9)
        y = self._total_saved_line(298, milestone)

        policy = self.cfg.get("keep_local", "ask")
        if policy == "ask" and self.out_path:
            # питаємо, чи лишати стиснуту копію на ПК (видалення відкладене — Discord ще читає файл)
            self._text(L("ov_keep_q"), y + 22, 11, C_TEXT)
            self._btn_pair(L("ov_keep"), self._keep_yes, L("ov_delete"), self._keep_no, y + 66,
                           left_primary=False, right_primary=True)
            self._msg_y = y + 108
            self._set_height(y + 128)
        else:
            if policy == "never":
                self._schedule_delete([self.out_path] if self.out_path else [])
            self._btn_full(L("ov_done"), self._close, y + 40)
            self._set_height(y + 96)
            self._autoclose(6000, y + 72)

    def _notify_done(self, sizes, pasted):
        """Сповіщення Windows «Готово ✓», якщо вікно зараз сховане (юзер пішов з Discord)."""
        if not self.cfg.get("notify_done", True) or self._visible or not self.watcher:
            return
        name = os.path.basename(self.file_path)
        if len(name) > 48:
            name = name[:45] + "…"
        self.watcher.notify(L("ntf_done_title"),
                            L("ntf_done_body", name=name, sizes=sizes,
                              state=L("ntf_pasted") if pasted else L("ntf_clip")))

    def _done_ring(self, cx, cy, col, step=0):
        """Галочка «Готово»: кільце швидко замикається, а значок легенько «пружинить»."""
        self.canvas.delete("donering")
        k = min(1.0, (step + 1) / 10.0)
        self._w_done = {"cx": cx, "cy": cy, "ok": col == C_GREEN}
        ui.grad_ring(self.canvas, cx, cy, 38, 5, ui.ease_out(k), col, ui.lighten(col, 0.35), C_BG2,
                     tags=("dyn", "donering"), segs=48)
        R = 30 * (0.75 + 0.25 * ui.ease_out(k) + 0.06 * (1 - k) * (k > 0.6))
        self.canvas.create_oval(cx - R, cy - R, cx + R, cy + R, fill=ui.mix(C_BG2, col, 0.18),
                                outline="", tags=("dyn", "donering"))
        self.canvas.create_text(cx, cy + 1, text="✓", fill=col, font=(FONT, int(14 + 12 * k), "bold"),
                                tags=("dyn", "donering"))
        if k < 1.0:
            self._later("pop", 22, lambda: self._done_ring(cx, cy, col, step + 1))

    def _autoclose(self, ms, y):
        """Тонка смужка-таймер: вікно закриється само (наведення миші — пауза)."""
        x1, x2 = self.MARGIN + 30, self.W - self.MARGIN - 30
        state = {"left": ms}

        def tick():
            if self._screen not in ("done", "done_split", "batch"):
                return
            try:
                w = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
                hover = w is not None and w.winfo_toplevel() is self
            except (tk.TclError, KeyError):
                hover = False
            if not hover:
                state["left"] -= 50
            if state["left"] <= 0:
                return self._close()
            self.canvas.delete("acbar")
            self._w_ac = {"y": y, "f": round(state["left"] / ms, 3)}
            ui.round_rect(self.canvas, x1, y, x2, y + 3, 1.5, fill=C_BG2, outline="",
                          tags=("dyn", "acbar"))
            xe = x1 + (x2 - x1) * state["left"] / ms
            if xe > x1 + 2:
                ui.grad_round_rect(self.canvas, x1, y, xe, y + 3, 1.5, C_BLURPLE,
                                   ui.accent2(self.P), tags=("dyn", "acbar"), step=1)
            self._later("autoclose", 50, tick)
        tick()

    def _total_saved_line(self, y, milestone=0):
        """Рядок «разом зекономлено N 💙» (або 🎉-ювілей). Повертає наступний вільний y."""
        try:
            u, g = L("unit_mb"), L("unit_gb")
            if milestone:
                self._text(L("ov_milestone", tot=stats.fmt_mb(milestone, u, g)), y, 10, C_GREEN)
                return y + 10
            tot = stats.load().get("saved_mb", 0.0)
            if tot >= 1:
                self._text(L("ov_total_saved", tot=stats.fmt_mb(tot, u, g)), y, 9, C_MUTED, bold=False)
                return y + 10
        except Exception:
            pass
        return y - 10

    def _keep_yes(self):
        self._text(L("ov_kept"), self._msg_y, 10, C_GREEN, bold=False)
        self._later("close", 1400, self._close)

    def _keep_no(self):
        self._schedule_delete([self.out_path] if self.out_path else [])
        self._text(L("ov_deleted"), self._msg_y, 10, C_MUTED, bold=False)
        self._later("close", 1400, self._close)

    def _schedule_delete(self, paths):
        """Видаляє файли з затримкою у ФОНОВОМУ потоці (Discord встигає прочитати).
        ВАЖЛИВО: не через self.after — вікно оверлея закривається раніше за таймер,
        і тоді таймер скасовувався й файли лишались (це й був баг)."""
        paths = [p for p in paths if p]
        if not paths:
            return

        def _rm():
            time.sleep(10)   # даємо Discord дочитати файли, потім прибираємо
            for p in paths:
                for _ in range(5):
                    try:
                        if os.path.exists(p):
                            os.remove(p)
                        break
                    except OSError:
                        time.sleep(2)   # файл ще зайнятий (Discord вантажить) — чекаємо і пробуємо ще
        threading.Thread(target=_rm, daemon=True).start()

    def _paste_files(self, paths):
        try:
            set_clipboard_files(paths)
            if self.watcher:
                self.watcher.mark_self_clipboard()
        except Exception:
            pass
        if self.cfg.get("auto_paste", True) and self.discord_hwnd and len(paths) <= 10:
            try:
                ok = user32.SetForegroundWindow(self.discord_hwnd)
                if not ok:
                    return False          # Windows не дав фокус Discord — лишаємо в буфері
                self.after(180, send_ctrl_v)
                return True
            except Exception:
                return False
        return False

    # ---- фото / звук ----
    def _start_image(self):
        out_path = media.image_out_name(self.file_path, float(self.cfg["target_mb"]))
        self._run_media(media.compress_image, out_path)

    def _start_audio(self):
        out_path = media.audio_out_name(self.file_path, float(self.cfg["target_mb"]))
        self._run_media(media.compress_audio, out_path)

    def _run_media(self, fn, out_path, target_override=None):
        target = float(target_override) if target_override else float(self.cfg["target_mb"])
        self.cancel["flag"] = False
        self._show_progress(title=L("ov_working"))

        def worker():
            try:
                ok, msg, mb = fn(self.file_path, out_path, target,
                                 progress_cb=lambda p: self._ui(lambda: self._set(p)),
                                 should_cancel=lambda: self.cancel["flag"])
            except Exception as e:
                import traceback
                dc_core.dlog("media worker EXCEPTION: " + repr(e) + "\n" + traceback.format_exc())
                err = f'{L("ov_err_prefix")} {str(e)[:90]}'   # рядок ДО лямбди (e зникає після except)
                return self._ui(lambda: self._show_error(err, allow_split=False, allow_trim=False))
            self._ui(lambda: self._after(ok, out_path, mb, target, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _show_error(self, msg, allow_split=True, allow_trim=True):
        self._clear()
        self._screen = "error"
        self._badge("⚠", 100, C_WARN, ui.lighten(C_WARN, 0.3))
        self._text(L("ov_fail"), 164, 15, C_TEXT)
        tid = self._text(msg, 190, 10, C_MUTED, bold=False)
        self.canvas.itemconfig(tid, anchor="n")
        try:
            y = self.canvas.bbox(tid)[3] + 36
        except Exception:
            y = 250
        # для довгих відео: поділ на частини (якісний) або «стиснути і поділити» (менше файлів)
        if allow_split:
            self._btn_full(L("ov_split"), lambda: self._start_split(balanced=False), y)
            self._btn_full(L("ov_split_bal"), lambda: self._start_split(balanced=True), y + 50,
                           primary=False)
            y += 100
        if allow_trim:
            self._btn_pair(L("ov_trim"), self._open_trim, L("close"), self._close, y,
                           left_primary=False, right_primary=False)
        else:
            self._btn_full(L("close"), self._close, y, primary=False)
        self._set_height(y + 50)

    def _open_trim(self):
        try:
            info = dc_core.ffprobe_info(self.file_path)
        except Exception:
            return self._show_error(L("ov_read_fail"), allow_split=False, allow_trim=False)
        self._suspend_vis = True   # редактор має «Discord» у заголовку — не смикаємо оверлей
        self.withdraw()
        self._visible = False
        try:
            from editor import VideoEditor
            VideoEditor(self.master, self.file_path, info, self.cfg, self.discord_hwnd,
                        self.watcher, on_close=self._close)
        except Exception as e:
            import traceback
            dc_core.dlog("editor EXCEPTION: " + repr(e) + "\n" + traceback.format_exc())
            self._suspend_vis = False
            self.deiconify()
            self._visible = True
            self._show_error(L("ov_editor_fail") + "\n" + str(e)[:80], allow_trim=False)

    def _start_shrink(self, target_mb):
        self._start(target_override=target_mb)

    def _size_input(self, icon, prompt, initial, on_ok, on_back):
        """Екран вводу розміру в МБ: велике поле в «капсулі» + підказка помилки."""
        self._clear()
        self._screen = "input"
        self._badge(icon, 100)
        self._text(prompt, 164, 12, C_TEXT)
        cx, cy = self.W // 2, 214
        ui.round_rect(self.canvas, cx - 86, cy - 26, cx + 86, cy + 26, 16, fill=C_DARK,
                      outline=C_BLURPLE, width=2, tags="dyn")
        self.mb_entry = tk.Entry(self.canvas, width=6, font=(FONT, 20, "bold"), justify="center",
                                 bg=C_DARK, fg=C_TEXT, insertbackground=C_TEXT, relief="flat",
                                 highlightthickness=0, bd=0)
        self.mb_entry.insert(0, initial)
        self._place(self.mb_entry, cx - 20, cy)
        self._text(L("unit_mb"), cy, 13, C_MUTED, bold=False, x=cx + 50)
        self.shrink_err = self._text("", 256, 9, C_RED, bold=False)
        self.mb_entry.bind("<Return>", lambda e: on_ok())
        self._entry_ok = on_ok          # для веб-вікна (Enter у полі на сторінці)
        self.mb_entry.bind("<Escape>", lambda e: on_back())
        self._btn_full(L("ov_compress"), on_ok, 300)
        self._btn_full(L("ov_back") if on_back != self._close else L("close"), on_back, 350,
                       primary=False)
        self._set_height(400)
        if self._mirror is not None:      # у веб-вікні поле вводу своє — не забираємо фокус
            return
        try:
            self.focus_force()
            self.mb_entry.focus_set()
            self.mb_entry.select_range(0, "end")
        except tk.TclError:
            pass

    def _input_err(self, text):
        try:
            self.canvas.itemconfig(self.shrink_err, text=text)
        except tk.TclError:
            pass

    def _shrink_input(self):
        """Екран, де юзер ВВОДИТЬ бажаний розмір у МБ (не більше за саме відео)."""
        self._size_input("🗜", L("ov_shrink_type", max=f"{self.size_mb:.1f}"),
                         str(max(1, int(self.size_mb * 0.6))), self._do_shrink_typed, self._close)

    def _read_mb(self):
        txt = self.mb_entry.get().strip().replace(",", ".")
        try:
            return float(txt)
        except ValueError:
            return None

    def _do_shrink_typed(self):
        val = self._read_mb()
        if val is None or val < 0.5:
            return self._input_err(L("ov_shrink_bad"))
        if val >= self.size_mb:
            return self._input_err(L("ov_shrink_toobig", max=f"{self.size_mb:.1f}"))
        self._start(target_override=val)

    # ---- свій розмір у МБ з екрана пропозиції (✏ на рядку розміру) ----
    def _custom_input(self):
        """Екран вводу СВОГО розміру: від 0.5 МБ до розміру самого файла (можна й менше ліміту)."""
        lim = float(self.cfg["target_mb"])
        init = lim if lim < self.size_mb else max(1, int(self.size_mb * 0.6))
        self._size_input("✏", L("ov_custom_type", min="0.5", max=f"{self.size_mb:.1f}"),
                         f"{init:g}", self._do_custom_typed, self._show_offer)

    def _do_custom_typed(self):
        val = self._read_mb()
        if val is None or val < 0.5:
            return self._input_err(L("ov_shrink_bad"))
        if val >= self.size_mb:
            return self._input_err(L("ov_shrink_toobig", max=f"{self.size_mb:.1f}"))
        if self.kind == "image":
            out = media.image_out_name(self.file_path, val)
            return self._run_media(media.compress_image, out, target_override=val)
        if self.kind == "audio":
            out = media.audio_out_name(self.file_path, val)
            return self._run_media(media.compress_audio, out, target_override=val)
        self._start(target_override=val)

    def _start(self, target_override=None):
        try:
            info = dc_core.ffprobe_info(self.file_path)
        except Exception:
            return self._show_error(L("ov_read_fail"), allow_split=False, allow_trim=False)
        target = float(target_override) if target_override else float(self.cfg["target_mb"])
        # перевірка здійсненності: навіть якщо ВЕСЬ бюджет віддати відео — чи вистачить?
        _a, best = dc_core.fit_bitrates(info["duration"], target, self.cfg["audio_kbps"], info["has_audio"])
        if not best:
            mins = info["duration"] / 60
            return self._show_error(L("ov_too_big", mb=f"{target:g}", mins=f"{mins:.0f}"))
        scale = (dc_core.pick_auto_scale(info, target, self.cfg["audio_kbps"])
                 if self.cfg.get("auto_scale", True) else 0)
        out_path = dc_core.output_name(self.file_path, target)
        self.cancel["flag"] = False
        self._show_progress()

        def worker():
            try:
                ok, msg, mb = dc_core.compress(self.file_path, out_path, target, scale,
                                               self.cfg["audio_kbps"], info,
                                               progress_cb=lambda p: self._ui(lambda: self._set(p)),
                                               should_cancel=lambda: self.cancel["flag"])
            except Exception as e:
                import traceback
                dc_core.dlog("compress worker EXCEPTION: " + repr(e) + "\n" + traceback.format_exc())
                err = f'{L("ov_err_prefix")} {str(e)[:90]}'   # рядок ДО лямбди (e зникає після except)
                return self._ui(lambda: self._show_error(err))
            self._ui(lambda: self._after(ok, out_path, mb, target, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _after(self, ok, out_path, final_mb, target, msg=""):
        if not ok or self.cancel["flag"]:
            if os.path.exists(out_path):
                try:
                    os.remove(out_path)
                except OSError:
                    pass
            if self.cancel["flag"]:
                return self._close()
            allow = self.kind in ("video", "shrink")
            return self._show_error(msg or L("ov_fail"), allow_split=allow, allow_trim=allow)
        self._set(100)
        self.out_path = out_path
        try:
            milestone = stats.record(self.kind, self.size_mb, final_mb, [out_path])
        except Exception:
            milestone = 0
        pasted = self._paste_files([out_path])
        self._show_done(final_mb, final_mb <= target, pasted, milestone=milestone)

    # ---- розділення довгого відео на кілька частин ----
    def _set_part(self, i, n):
        try:
            self.canvas.itemconfig(self.sub_id, text=L("ov_parts_prog", i=i, n=n))
        except (tk.TclError, AttributeError):
            pass

    def _start_split(self, balanced=False):
        try:
            info = dc_core.ffprobe_info(self.file_path)
        except Exception:
            return self._show_error(L("ov_read_fail"), allow_split=False, allow_trim=False)
        target = float(self.cfg["target_mb"])
        # balanced=True -> «стиснути і поділити»: менше частин, зате кожна стискається сильніше
        n_parts = (dc_core.plan_parts_balanced(info["duration"], target, self.cfg["audio_kbps"],
                                               info["has_audio"]) if balanced else None)
        self.cancel["flag"] = False
        self._show_progress(title=L("ov_comp_split") if balanced else L("ov_splitting"))
        dc_core.dlog(f"_start_split: balanced={balanced} n_parts={n_parts} target={target}")

        def worker():
            try:
                ok, msg, outs = dc_core.split_compress(
                    self.file_path, target, self.cfg.get("auto_scale", True),
                    self.cfg["audio_kbps"], info,
                    progress_cb=lambda p: self._ui(lambda: self._set(p)),
                    should_cancel=lambda: self.cancel["flag"],
                    part_cb=lambda i, n: self._ui(lambda: self._set_part(i, n)),
                    n_parts=n_parts)
            except Exception as e:
                import traceback
                dc_core.dlog("split worker EXCEPTION: " + repr(e) + "\n" + traceback.format_exc())
                err = f'{L("ov_err_prefix")} {str(e)[:90]}'   # рядок ДО лямбди (e зникає після except)
                return self._ui(lambda: self._show_error(err, allow_trim=False))
            self._ui(lambda: self._after_split(ok, outs, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _after_split(self, ok, outs, msg=""):
        if self.cancel["flag"]:
            for p in outs:
                try:
                    os.remove(p)
                except OSError:
                    pass
            return self._close()
        if not ok or not outs:
            return self._show_error(msg or L("ov_split_fail"), allow_trim=False)
        self._set(100)
        self.out_paths = outs
        self._split_milestone = 0
        try:
            final_mb = sum(os.path.getsize(p) for p in outs if os.path.isfile(p)) / (1024 * 1024)
            self._split_milestone = stats.record("video", self.size_mb, final_mb, outs,
                                                 parts=len(outs))
        except Exception:
            pass
        # Discord бере МАКС 10 вкладень за раз -> >10 файлів шлемо пачками по 10
        if len(outs) > 10:
            self._batches = [outs[i:i + 10] for i in range(0, len(outs), 10)]
            self._batch_i = 0
            pasted = self._paste_files(self._batches[0])
            self._show_batches(pasted)
        else:
            pasted = self._paste_files(outs)
            self._show_done_split(len(outs), pasted)

    def _show_batches(self, pasted):
        """Екран пакетної відправки: показує поточну пачку 1–10, потім кнопку «наступні»."""
        self._clear()
        self._screen = "batch"
        total = len(self.out_paths)
        b = self._batch_i
        lo, hi = b * 10 + 1, min(total, (b + 1) * 10)
        cx = self.W // 2
        self._glow(cx, 100, 34, C_GREEN, 0.3)
        self._done_ring(cx, 100, C_GREEN)
        key = "ov_batch_in" if pasted else "ov_batch_clip"
        self._text(L(key, a=lo, b=hi, total=total), 164, 12, C_TEXT)
        if b + 1 < len(self._batches):
            self._text(L("ov_batch_hint"), 192, 10, C_MUTED, bold=False)
            nlo, nhi = (b + 1) * 10 + 1, min(total, (b + 2) * 10)
            self._btn_full(L("ov_batch_next", a=nlo, b=nhi), self._next_batch, 244)
            self._btn_full(L("close"), self._close, 294, primary=False)
            self._set_height(344)
        else:
            # усі пачки надіслано -> питаємо про копію на ПК / завершуємо
            play_done_sound(self.cfg)
            self._text(L("ov_done"), 196, 13, C_GREEN)
            self._ask_keep_parts(222)

    def _next_batch(self):
        self._batch_i += 1
        pasted = self._paste_files(self._batches[self._batch_i])
        self._show_batches(pasted)

    def _show_done_split(self, n, pasted):
        self._clear()
        self._screen = "done_split"
        play_done_sound(self.cfg)
        self._notify_done(L("ov_done_parts", n=n), pasted)
        cx = self.W // 2
        self._glow(cx, 100, 34, C_GREEN, 0.3)
        self._done_ring(cx, 100, C_GREEN)
        self._text(L("ov_done_parts", n=n), 164, 16, C_TEXT)
        if pasted:
            msg = L("ov_pasted")
        elif n > 10:
            msg = L("ov_all_clip")
        else:
            msg = L("ov_in_clip")
        self._chip(cx, 198, msg, ui.ink(ui.mix(C_BG2, C_GREEN, 0.35)),
                   ui.mix(C_BG2, C_GREEN, 0.35), size=9)
        self._text(L("ov_parts_near"), 228, 9, C_MUTED, bold=False)
        y = self._total_saved_line(252, getattr(self, "_split_milestone", 0))
        self._ask_keep_parts(y)

    def _ask_keep_parts(self, y):
        outs = getattr(self, "out_paths", [])
        policy = self.cfg.get("keep_local", "ask")
        if policy == "ask" and outs:
            self._text(L("ov_keep_q"), y + 22, 11, C_TEXT)
            self._btn_pair(L("ov_keep"), lambda: self._keep_parts(True),
                           L("ov_delete"), lambda: self._keep_parts(False), y + 66,
                           left_primary=False, right_primary=True)
            self._msg_y = y + 108
            self._set_height(y + 128)
        else:
            if policy == "never":
                self._schedule_delete(outs)
            self._btn_full(L("ov_done"), self._close, y + 40)
            self._set_height(y + 96)
            self._autoclose(9000, y + 72)

    def _keep_parts(self, keep):
        if not keep:
            self._schedule_delete(getattr(self, "out_paths", []))
            self._text(L("ov_deleted"), self._msg_y, 10, C_MUTED, bold=False)
        else:
            self._text(L("ov_kept"), self._msg_y, 10, C_GREEN, bold=False)
        self._later("close", 1500, self._close)

    def _close(self):
        if self._closed:          # друга спроба (таймер + клік) — нічого не робимо
            return
        self._alive = False
        self._closed = True
        self.cancel["flag"] = True if self._screen == "progress" else self.cancel["flag"]
        for tid in list(self._timers.values()) + [getattr(self, "_vis_after", None)]:
            if tid:
                try:
                    self.after_cancel(tid)
                except Exception:
                    pass
        self._timers.clear()
        if getattr(self, "_mirror", None) is not None:
            try:
                self._mirror.close()
            except Exception:
                pass
        try:
            self.destroy()
        except Exception:
            pass
        finally:
            if self.on_close:
                self.on_close()

    def _drag_start(self, e):
        self._d = (e.x, e.y)

    def _drag(self, e):
        d = getattr(self, "_d", None)
        if not d:
            return
        self._x = self.winfo_x() + e.x - d[0]
        self._y = self.winfo_y() + e.y - d[1]
        self.geometry(f"+{self._x}+{self._y}")


# --------------------------------------------------------------------------- #
#  Значок-пропозиція «стиснути дрібніше» (для відео, що вже влазить у ліміт)
# --------------------------------------------------------------------------- #
class ShrinkPill(tk.Toplevel):
    W, H = 260, 54
    LIFE_MS = 3500        # скільки живе пілюля, якщо її не чіпати

    def __init__(self, master, discord_hwnd, path, size, cfg, watcher):
        super().__init__(master)
        self.discord_hwnd, self.path, self.size = discord_hwnd, path, size
        self.cfg, self.watcher = cfg, watcher
        self.P = _palette()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-transparentcolor", C_KEY)
        except tk.TclError:
            pass
        self.configure(bg=C_KEY)
        self._place_near_discord()
        self.c = tk.Canvas(self, width=self.W, height=self.H, bg=C_KEY, highlightthickness=0,
                           cursor="hand2")
        self.c.pack()
        self._hover = False                            # наведення миші ставить таймер на паузу
        self._hover_x = False
        self._left = self.LIFE_MS
        self._draw()
        self.c.bind("<Motion>", self._motion)
        self.c.bind("<Enter>", lambda e: self._set_hover(True))
        self.c.bind("<Leave>", lambda e: self._set_hover(False))
        self.c.bind("<Button-1>", self._click)

        # робимо помітним: піднімаємо поверх усього
        self.lift()
        self.update_idletasks()
        self._force_top()                              # win32: реально виносимо поверх Discord
        self._alive = True
        ui.fade_in(self, 140)
        self._countdown()                              # запуск таймера-смужки
        self.after(600, self._tick)                    # закриваємось, якщо юзер пішов з Discord

    def _draw(self):
        c, W, H = self.c, self.W, self.H
        c.delete("all")
        a1, a2 = C_BLURPLE, ui.accent2(self.P)
        if self._hover:
            a1, a2 = ui.lighten(a1, 0.12), ui.lighten(a2, 0.12)
        ui.round_rect(c, 3, 5, W - 1, H - 1, (H - 6) / 2, fill=ui.darken(a1, 0.55), outline="")
        ui.grad_round_rect(c, 1, 1, W - 3, H - 5, (H - 6) / 2, a1, a2)
        fg = ui.ink(ui.mix(a1, a2, 0.5))
        c.create_text(26, (H - 4) / 2, text="🗜", font=(FONT, 14), fill=fg, anchor="w")
        c.create_text(54, (H - 4) / 2, text=L("pill_shrink"), font=(FONT, 11, "bold"),
                      fill=fg, anchor="w")
        xc = W - 26
        if self._hover_x:
            c.create_oval(xc - 12, (H - 4) / 2 - 12, xc + 12, (H - 4) / 2 + 12,
                          fill=ui.darken(a2, 0.25), outline="")
        c.create_text(xc, (H - 4) / 2, text="✕", font=(FONT, 10, "bold"), fill=fg)
        # таймер — тонка смужка, що тане
        bw = (W - 64) * max(0.0, self._left) / self.LIFE_MS
        if bw > 2:
            ui.round_rect(c, 30, H - 12, 30 + bw, H - 9, 1.5, fill=ui.mix(fg, a2, 0.35), outline="")

    def _motion(self, e):
        on_x = e.x > self.W - 46
        if on_x != self._hover_x:
            self._hover_x = on_x
            self._draw()

    def _set_hover(self, on):
        self._hover = on
        if not on:
            self._hover_x = False
        self._draw()

    def _click(self, e):
        if e.x > self.W - 46:
            return self._close()
        self._open()

    def _countdown(self):
        """Плавно спускає смужку-таймер; на паузі поки миша над пілюлею (щоб встиг клікнути)."""
        if not self._alive:
            return
        if not self._hover:
            self._left -= 50
        if self._left <= 0:
            return self._close()
        try:
            self._draw()
        except tk.TclError:
            return
        self.after(50, self._countdown)

    def _force_top(self):
        """Виносимо вікно у топ-бенд Windows БЕЗ крадіжки фокуса в Discord.
        `overrideredirect`+Tk `-topmost` виставлений ДО мапінгу вікна часто «не
        приклеюється» (вікно ховається за Discord після його перемалювання), тому
        дублюємо через SetWindowPos(HWND_TOPMOST) — його треба переставляти щотіка."""
        try:
            hwnd = user32.GetAncestor(self.winfo_id(), 2)  # GA_ROOT
            # HWND_TOPMOST=-1; SWP_NOSIZE|SWP_NOMOVE|SWP_NOACTIVATE|SWP_SHOWWINDOW
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)
        except Exception:
            pass

    def _tick(self):
        if not self._alive:
            return
        try:
            fg, title = foreground_title()
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
            own = pid.value == os.getpid()             # клік по самій пілюлі — не ховаємось
            if not own and "discord" not in title.lower():
                return self._close()                    # передумали / пішли -> прибираємо значок
            # Discord перемальовує себе й «топить» пілюлю — щоразу піднімаємо назад
            self.attributes("-topmost", True)
            self._force_top()
        except Exception:
            pass
        self.after(600, self._tick)

    def _place_near_discord(self):
        # ПО СЕРЕДИНІ ЕКРАНА (як просив юзер)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = (sw - self.W) // 2, (sh - self.H) // 2
        self.geometry(f"{self.W}x{self.H}+{x}+{y}")

    def _open(self):
        self._alive = False        # зупиняє таймер-смужку і _tick (інакше стріляють по знищеному вікну)
        try:
            self.destroy()
        except Exception:
            pass
        if not self.watcher.overlay_open:
            self.watcher.overlay_open = True
            Overlay(self.watcher.root, self.path, self.size / 1024 / 1024, self.cfg,
                    self.discord_hwnd, on_close=self.watcher._closed, watcher=self.watcher, kind="shrink")

    def _close(self):
        self._alive = False
        try:
            self.destroy()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
#  Фон: перехоплення Ctrl+V у Discord
# --------------------------------------------------------------------------- #
_AUTO_MOVED_TO_WATCHER = True   # авто-оновлення без вікон; ручне — кнопкою в меню


class Watcher:
    def __init__(self, open_settings=False):
        global LANG
        first_run = not os.path.exists(CONFIG_PATH)
        self.cfg = load_config()
        LANG = self.cfg.get("lang", "en")
        dc_core.LANG = LANG
        dc_core.configure(self.cfg)
        if not self.cfg.get("design_mono"):     # 3.1: новий дизайн — один раз вмикаємо всім
            self.cfg["design_mono"] = True
            self.cfg["theme"] = "mono"
            save_config(self.cfg)
        apply_theme(self.cfg.get("theme", "mono"))
        # «Що нового»: показуємо ОДИН раз після оновлення (не на першому запуску).
        # Позначку ставимо одразу — до відкриття меню, яке має свою копію конфіга.
        import changelog
        show_news = (not first_run) and self.cfg.get("seen_version") != changelog.VERSION
        self._news_from = self.cfg.get("seen_version")   # з якої версії оновились -> покажемо все після неї
        if self.cfg.get("seen_version") != changelog.VERSION:
            self.cfg["seen_version"] = changelog.VERSION
            save_config(self.cfg)
        # енкодер відеокарти визначаємо у фоні, щоб перше стиснення не чекало
        threading.Thread(target=dc_core.hw_encoder, daemon=True).start()
        # швидкий програвач редактора (libmpv): докачуємо одразу при запуску програми,
        # щоб до відкриття редактора він уже був; не вийде — пробує далі сам, без кінця
        try:
            import mpvplayer
            mpvplayer.ensure_downloaded()
        except Exception as e:
            dc_core.dlog(f"mpv preload: {e!r}")
        # самолікування: якщо при запуску частина файлів прийшла іншої версії —
        # докачуємо їх з ОДНОГО коміту (діє лише у встановленій копії з маркером .autoupdate)
        threading.Thread(target=self._self_heal, daemon=True).start()
        try:
            import appicon
            appicon.register_process_app_id()   # «Discord Auto-Compress» на панелі завдань і в сповіщеннях
        except Exception as e:
            dc_core.dlog("app id: " + repr(e))
        self.root = tk.Tk()
        self.root.withdraw()
        # будь-яка помилка в обробнику подій -> у журнал (у exe консолі немає, і вона губилась)
        self.root.report_callback_exception = self._tk_error
        self.q = queue.Queue()
        self.overlay_open = False
        self.settings_win = None
        self.last_seq_self = 0
        self._cooldown_until = 0
        threading.Thread(target=self._hook_thread, daemon=True).start()
        self.root.after(120, self._poll_queue)
        self._start_tray()
        if open_settings:
            self.root.after(200, self.open_settings)
        # веб-вікно стиснення запускаємо заздалегідь (сховане) — після Ctrl+V воно з'явиться одразу
        self.root.after(300, self._close_stale_web)
        self.root.after(2500, self._prelaunch_overlay)
        self.root.after(15000, self._web_watchdog)
        if show_news:
            self.root.after(1400, self.show_whats_new)
        self.root.after(3000, self._heal_watch)

    def _self_heal(self):
        """Фонове оновлення на старті. Нові файли приходять, коли старий код уже
        завантажений, — тож якщо змінилась ВЕРСІЯ, програма сама перезапускається
        (коли нічого не стискає й редактор закритий). Інакше нова версія з'являлась
        лише після ще одного ручного перезапуску."""
        try:
            import update
            n = update.auto() or 0
        except Exception as e:
            dc_core.dlog("self-heal update failed: " + repr(e))
            return
        if not n:
            return
        try:
            import changelog
            import re
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "changelog.py"),
                      encoding="utf-8") as f:
                m = re.search(r'\{"v":\s*"([^"]+)"', f.read())
            if m and m.group(1) != changelog.VERSION:
                dc_core.dlog(f"self-heal: {n} files, {changelog.VERSION} -> {m.group(1)}; restart when idle")
                self._heal_restart = time.monotonic()
        except Exception as e:
            dc_core.dlog("self-heal version check failed: " + repr(e))

    def _heal_watch(self, tries=0):
        """Головний потік: чекаємо прапорець від _self_heal і перезапускаємось, коли вільно."""
        if getattr(self, "_heal_restart", None) is None:
            if tries < 120:                         # ~4 хв після старту
                self.root.after(2000, lambda: self._heal_watch(tries + 1))
            return
        busy = bool(self.overlay_open)
        try:
            ed = sys.modules.get("editor")
            if ed is not None:
                busy = busy or any(isinstance(w, ed.VideoEditor) and w.winfo_exists()
                                   for w in self.root.winfo_children())
        except Exception:
            pass
        if busy:
            self.root.after(5000, lambda: self._heal_watch(tries))
            return
        dc_core.dlog("self-heal: restarting into the new version")
        self.restart_app()

    @staticmethod
    def _tk_error(exc, val, tb):
        import traceback
        dc_core.dlog("TK CALLBACK ERROR: " + "".join(traceback.format_exception(exc, val, tb)))

    def show_whats_new(self):
        if self._web("news"):
            return
        try:
            import whatsnew
            whatsnew.WhatsNew(self.root, LANG, THEME,
                              on_open_tab=lambda tab: self.open_settings(tab=tab),
                              since=getattr(self, "_news_from", None))
        except Exception as e:
            import traceback
            dc_core.dlog("whatsnew FAILED: " + repr(e) + "\n" + traceback.format_exc())

    def notify(self, title, text):
        """Сповіщення Windows із трею (коли вікно програми сховане)."""
        try:
            if self.tray:
                self.tray.notify(title, text)
        except Exception:
            pass

    # ---- системний трей ----
    def _tray_texts(self):
        return (i18n.tr(LANG, "tray_open"), i18n.tr(LANG, "tray_quit"), i18n.tr(LANG, "tray_tip"))

    def open_gallery(self, hwnd=None):
        """«Мої монтажі» (Ctrl+Alt+E / трей). Якщо гарячу клавішу натиснули в Discord —
        клік по відео одразу вставить його туди."""
        try:
            title = ""
            if hwnd:
                n = user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                title = buf.value
            dh = hwnd if "Discord" in title else None
            if self._web("gallery", gallery_hwnd=dh):
                return
            import library
            library.open_gallery(self, dh)
        except Exception as e:
            dc_core.dlog("gallery EXCEPTION " + repr(e))

    def _start_tray(self):
        try:
            import tray
            self.tray = tray.Tray(
                on_open=lambda: self.root.after(0, self.open_settings),
                on_balloon=lambda: self.root.after(0, lambda: self.open_settings(tab="stats")),
                on_quit=lambda: self.root.after(0, self.quit_app),
                texts=self._tray_texts(),
                extra=[(lambda: i18n.tr(LANG, "tray_gallery"),
                        lambda: self.root.after(0, self.open_gallery))])
            self.tray.start()
        except Exception:
            self.tray = None

    # Авто-вікон про оновлення БІЛЬШЕ НЕМАЄ (на прохання юзера): жодних питань
    # чи повідомлень само собою. Оновлення — ЛИШЕ кнопкою «Перевірити оновлення»
    # у меню (вкладка Оновлення), там же кнопка перезапуску.

    def quit_app(self):
        try:                              # веб-вікна (Edge) — окремі процеси: закриваємо їх самі
            import webui
            webui.close_all()
        except Exception:
            pass
        try:
            if self.tray:
                self.tray.stop()          # posts WM_CLOSE -> NIM_DELETE на потоці трею
        except Exception:
            pass
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
        # ГАРАНТОВАНИЙ вихід. Раніше лишався ЗОМБІ-процес: значок трею вже видалено
        # (NIM_DELETE), але не-daemon-потік (клав. хук/автооновлення) тримав процес живим
        # -> на рестарті нова копія бачила старе вікно трею (single-instance) й не піднімалась,
        # тож значок «зникав». Даємо трею мить обробити WM_CLOSE, тоді жорстко виходимо.
        try:
            import time as _t
            _t.sleep(0.25)
        except Exception:
            pass
        try:
            os._exit(0)
        except Exception:
            pass

    def restart_app(self):
        """Закриває поточну копію й запускає свіжу (із затримкою, щоб трей встиг звільнитись)."""
        try:
            if getattr(sys, "frozen", False):
                inner = 'start "" "%s"' % sys.executable
            else:
                parts = " ".join('"%s"' % a for a in [sys.executable] + sys.argv)
                inner = 'start "" %s' % parts
            full = 'ping 127.0.0.1 -n 3 >nul & ' + inner
            import subprocess
            # КРИТИЧНО для onefile-.exe: чистимо ВСІ змінні PyInstaller/Tcl (за префіксом),
            # інакше нова копія або шукає Tcl у видаленій _MEIxxxx («Can't find a usable
            # init.tcl»), або бачить залишковий маркер child-процесу (_PYI_PARENT_PROCESS_LEVEL)
            # без _PYI_APPLICATION_HOME_DIR -> «_PYI_APPLICATION_HOME_DIR is not defined!».
            # Прибираємо все _PYI*/_MEI* -> свіжий exe стартує як чистий parent і розпакується заново.
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith("_PYI") and not k.startswith("_MEI")
                   and k not in ("TCL_LIBRARY", "TK_LIBRARY", "TKPATH")}
            # shell=True з РЯДКОМ (не списком!) — інакше вкладені лапки ламаються
            # й Windows бачить '\' як команду («Windows cannot find '\'»).
            subprocess.Popen(full, shell=True, creationflags=0x08000000, env=env)
            dc_core.dlog("restart launching: " + full)
        except Exception as e:
            dc_core.dlog("restart launch failed: " + repr(e))
        # ВАЖЛИВО: не руйнуємо root просто зараз (ми всередині обробки кліку кнопки —
        # це давало помилку «application has been destroyed»). Виходимо трохи згодом.
        try:
            self.root.after(250, self.quit_app)
        except Exception:
            self.quit_app()

    # ---- меню налаштувань ----
    def _close_stale_web(self):
        """Залишки веб-вікон від попереднього запуску (після збою) — закриваємо, щоб нова копія
        не «вчепилась» у старе вікно, яке говорить з уже мертвим сервером."""
        try:
            import webui
            webui.close_all()
        except Exception as e:
            dc_core.dlog("close stale web fail " + repr(e))

    def _web_watchdog(self):
        """Кожні 10 с: сховане веб-вікно стиснення живе? Ні (Edge закрив, сон ПК) — тихо
        запускаємо знову, щоб Ctrl+V завжди відкривав нормальне вікно одразу."""
        try:
            if (themes.palette(THEME).get("mono") and self.cfg.get("web_ui", True) is not False
                    and not self.overlay_open):
                import webov
                st = webov._st
                recent = time.monotonic() - float(st.get("launched") or 0.0) < 15.0
                if not recent and not webov._find():
                    dc_core.dlog("watchdog: overlay web window gone -> relaunch")
                    webov.prelaunch(self)
                    threading.Thread(target=lambda: webov.window(wait=20), daemon=True).start()
        except Exception as e:
            dc_core.dlog("watchdog fail " + repr(e))
        self.root.after(10000, self._web_watchdog)

    def _prelaunch_overlay(self):
        try:
            if themes.palette(THEME).get("mono") and self.cfg.get("web_ui", True) is not False:
                import webov
                import webui
                webui.prelaunch(self)          # сховане вікно меню/галереї/новин — показ миттєвий
                webov.prelaunch(self)
                threading.Thread(target=lambda: webov.window(wait=20), daemon=True).start()
        except Exception as e:
            dc_core.dlog("webov prelaunch fail " + repr(e))

    def _web(self, page, **kw):
        """Веб-вікно (дизайн Moon у Edge). False — Edge немає або вимкнено -> Tk."""
        if self.cfg.get("web_ui", True) is False:
            dc_core.dlog(f"web {page}: disabled in config")
            return False
        if not themes.palette(self.cfg.get("theme", "mono")).get("mono"):
            return False                 # веб = лише дизайн Moon; інші теми — у звичайних вікнах
        try:
            import webui
            ok = webui.open_page(self, page, **kw)
            dc_core.dlog(f"web {page}: {'opened' if ok else 'NOT opened -> Tk'}")
            return ok
        except Exception as e:
            dc_core.dlog("webui EXCEPTION " + repr(e))
            return False

    def open_settings(self, tab=None):
        if self.settings_win is None and self._web("menu", tab=tab):
            return
        if self.settings_win is not None:
            try:
                if tab:
                    self.settings_win._show_tab(tab)
                self.settings_win.win.deiconify()
                self.settings_win.win.lift()
                self.settings_win.win.attributes("-topmost", True)
                self.settings_win.win.after(300,
                    lambda: self.settings_win.win.attributes("-topmost", False))
                return
            except Exception:
                self.settings_win = None
        import settings_app

        def _closed():
            try:
                self.settings_win.win.destroy()
            except Exception:
                pass
            self.settings_win = None

        def _editor():
            import library
            library.open_empty_editor(self)

        kw = dict(on_save=self._on_settings_save, on_apply=self._on_settings_apply,
                  on_close=_closed, on_restart=self.restart_app,
                  on_editor=_editor, on_gallery=lambda: self.open_gallery())
        try:
            self.settings_win = settings_app.SettingsApp(self.root, self.cfg, tab=tab, **kw)
        except TypeError:
            # меню старішої версії (не докачалось) — відкриваємо без нових параметрів
            dc_core.dlog("SettingsApp: older settings_app.py")
            for k in ("on_editor", "on_gallery"):
                kw.pop(k, None)
            try:
                self.settings_win = settings_app.SettingsApp(self.root, self.cfg, tab=tab, **kw)
            except TypeError:
                self.settings_win = settings_app.SettingsApp(self.root, self.cfg, **kw)

    def _on_settings_save(self, cfg):
        self.cfg = cfg
        save_config(cfg)
        self._on_settings_apply(cfg)

    def _on_settings_apply(self, cfg):
        global LANG
        self.cfg = cfg
        LANG = cfg.get("lang", "en")
        dc_core.LANG = LANG
        dc_core.configure(cfg)
        was_mono = themes.palette(THEME).get("mono")
        apply_theme(cfg.get("theme", "mono"))
        try:
            if self.tray:
                self.tray.update_texts(self._tray_texts())
        except Exception:
            pass
        is_mono = themes.palette(THEME).get("mono")
        # у звичайному меню вибрали Moon -> закриваємо його й відкриваємо веб-меню
        if not was_mono and is_mono and self.settings_win is not None:
            self.root.after(150, self._switch_to_web_menu)
        if not was_mono and is_mono:
            self.root.after(400, self._prelaunch_overlay)     # веб-оверлей знову готовий заздалегідь
        if was_mono and not is_mono:
            # інша тема: сховані вікна Edge (меню й оверлей) більше не потрібні — не тримаємо їх
            def _close_web():
                try:
                    import webui
                    webui.close_all()
                except Exception as e:
                    dc_core.dlog("close web on theme change fail " + repr(e))
            self.root.after(800, _close_web)

    def _switch_to_web_menu(self):
        sw = self.settings_win
        self.settings_win = None
        try:
            sw.win.destroy()
        except Exception:
            pass
        if not self._web("menu", tab="appearance"):
            self.open_settings(tab="appearance")

    def mark_self_clipboard(self):
        # ми самі поклали файл — стартуємо коротку «паузу», щоб не зреагувати на свою ж вставку
        self._cooldown_until = kernel32.GetTickCount() + 1500

    # ---- перевірка: чи треба перехопити цю вставку ----
    def _should_intercept(self):
        hwnd, title = foreground_title()
        if "discord" not in title.lower():
            return None
        limit = self.cfg["target_mb"] * 1024 * 1024
        enabled = {"video": self.cfg.get("compress_video", True),
                   "image": self.cfg.get("compress_images", True),
                   "audio": self.cfg.get("compress_audio", True)}
        files = clipboard_files()
        vids = [p for p in files if os.path.isfile(p) and media.kind_of(p) == "video"]
        if vids:
            dc_core.dlog("paste@discord vids=" + str([(os.path.basename(v),
                         round(os.path.getsize(v) / 1048576, 2)) for v in vids])
                         + f" limit={self.cfg['target_mb']}MB offer_shrink={self.cfg.get('offer_shrink', True)}")
        small_hit = None
        for path in files:
            if not os.path.isfile(path):
                continue
            # раніше пропускали наші «_discord_» файли; тепер їх ТЕЖ беремо
            # (щоб можна було стиснути дрібніше вже стиснуте). Від само-циклу боронить
            # cooldown + ігнор ін'єктованого Ctrl+V (наша авто-вставка не тригерить хук).
            kind = media.kind_of(path)
            if not kind or not enabled.get(kind):
                continue
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if size > limit:
                return (hwnd, path, size, kind, "big")          # завелике -> перехопити й стиснути
            # влазить, але відео й ≥1.3 МБ -> пропонуємо стиснути дрібніше (значок, БЕЗ блокування)
            if (small_hit is None and kind == "video" and size >= 1.3 * 1024 * 1024
                    and self.cfg.get("offer_shrink", True)):
                small_hit = (hwnd, path, size, kind, "small")
                dc_core.dlog(f"intercept SMALL (shrink offer): {os.path.basename(path)} "
                             f"{size/1048576:.2f}MB limit={limit/1048576:.0f}MB")
        return small_hit

    # ---- LL keyboard hook ----
    def _ll_proc(self, nCode, wParam, lParam):
        try:
            if nCode == 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if (kb.vkCode == VK_E and not (kb.flags & LLKHF_INJECTED)
                        and (user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                        and (user32.GetAsyncKeyState(VK_MENU) & 0x8000)):
                    self.q.put((user32.GetForegroundWindow(), "", 0, "gallery", "gallery"))
                    return 1          # Ctrl+Alt+E -> «Мої монтажі», далі клавішу не пускаємо
                if (kb.vkCode == VK_V and not (kb.flags & LLKHF_INJECTED)
                        and (user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)):
                    now = kernel32.GetTickCount()
                    if now >= self._cooldown_until and not self.overlay_open:
                        hit = self._should_intercept()
                        if hit:
                            self._cooldown_until = now + 1500
                            self.q.put(hit)
                            # блокуємо вставку ЛИШЕ для завеликих; для «стиснути дрібніше»
                            # пускаємо вставку як є — покажемо лише значок-пропозицію
                            if hit[4] == "big" and self.cfg.get("block_paste", True):
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
        while True:
            try:
                hwnd, path, size, kind, mode = self.q.get_nowait()
            except queue.Empty:
                break
            if mode == "gallery":
                self.open_gallery(hwnd)
            elif mode == "small":
                self._show_pill(hwnd, path, size)           # ненав'язливий значок-пропозиція
            elif not self.overlay_open:
                self.overlay_open = True
                Overlay(self.root, path, size / 1024 / 1024, self.cfg, hwnd,
                        on_close=self._closed, watcher=self, kind=kind)
        self.root.after(120, self._poll_queue)

    def _closed(self):
        self.overlay_open = False
        self.root.after(1500, self._prelaunch_overlay)     # якщо веб-вікно закрили — підготувати знову

    def _show_pill(self, hwnd, path, size):
        try:
            if getattr(self, "pill", None):
                self.pill._close()
        except Exception:
            pass
        try:
            self.pill = ShrinkPill(self.root, hwnd, path, size, self.cfg, self)
            dc_core.dlog("pill SHOWN at " + self.pill.winfo_geometry())
        except Exception as e:
            import traceback
            dc_core.dlog("pill FAILED: " + repr(e) + "\n" + traceback.format_exc())
            self.pill = None

    def run(self):
        self.root.mainloop()


# --------------------------------------------------------------------------- #
#  Налаштування
# --------------------------------------------------------------------------- #
def run_app(open_settings=True):
    """Єдина точка входу. Якщо копія вже працює — просимо її відкрити меню й виходимо
    (не плодимо другий трей/хук). Інакше запускаємо фон + (за потреби) меню."""
    try:
        import tray
        if tray.find_existing():
            if open_settings:
                tray.signal_open()
            return
    except Exception:
        pass
    Watcher(open_settings=open_settings).run()


def settings_window():
    """Запускає програму з одразу відкритим меню налаштувань (для «--settings»)."""
    run_app(open_settings=True)


if __name__ == "__main__":
    # --background -> тихий автозапуск (без меню); решта -> фон + відкрите меню
    run_app(open_settings="--background" not in sys.argv)
