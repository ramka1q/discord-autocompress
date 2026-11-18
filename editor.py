#!/usr/bin/env python3
"""
Video Editor для Discord Auto-Compress
======================================
Міні-редактор у стилі CapCut:
  • КІЛЬКА джерел на одній доріжці: відео + картинки (➕ або перетягни файли у вікно);
  • звуки поверх монтажу (окрема смужка під хвилею, тягнуться мишкою);
  • масштаб/позиція відео прямо на прев'ю: клік по відео -> рамка з ручками;
  • ПКМ по кліпу -> меню (розрізати/дублювати/швидкість/звук/масштаб/прибрати);
  • відтворення ЗІ ЗВУКОМ через вбудований ffplay; авто-перехід на наступний кліп;
  • експорт: монтаж нормалізується (канвас першого відео), звуки підмішуються,
    результат тиснеться під ліміт Discord. Простий випадок (одне джерело без
    трансформ) іде старим ШВИДКИМ шляхом compress_segments.
Імпортується ліниво з discord_overlay.
"""
import ctypes
import math
import os
import shutil
import subprocess
import tempfile
import threading
import time

import tkinter as tk
from tkinter import filedialog

import themes

import appicon
import dc_core
import discord_overlay as host
import i18n
import jokes
import edit_fx as fx
import edit_inspector
import media
import ui

# ---- WinAPI для вбудовування вікна ffplay у наш відео-екран (SetParent) ----
_u32 = ctypes.windll.user32
_u32.FindWindowW.restype = ctypes.c_void_p
_u32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
_u32.SetParent.restype = ctypes.c_void_p
_u32.SetParent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_u32.MoveWindow.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                            ctypes.c_int, ctypes.c_int, ctypes.c_bool]
try:                                    # 64-біт: SetWindowLongPtrW
    _SetWinLong = _u32.SetWindowLongPtrW
    _SetWinLong.restype = ctypes.c_void_p
    _SetWinLong.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
except AttributeError:                  # 32-біт
    _SetWinLong = _u32.SetWindowLongW
    _SetWinLong.restype = ctypes.c_long
    _SetWinLong.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
_GWL_STYLE = -16
_WS_CHILD = 0x40000000
_WS_VISIBLE = 0x10000000

# ---- WinAPI для ПЕРЕТЯГУВАННЯ файлів у вікно (WM_DROPFILES, без сторонніх пакетів) ----
_GWL_WNDPROC = -4
_WM_DROPFILES = 0x0233
_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint,
                              ctypes.c_size_t, ctypes.c_ssize_t)
# CallWindowProcW юзаємо лише ми -> argtypes безпечні (НЕ чіпаємо спільні GetCursorPos тощо)
_u32.CallWindowProcW.restype = ctypes.c_ssize_t
_u32.CallWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
                                 ctypes.c_size_t, ctypes.c_ssize_t]
_shell32 = ctypes.windll.shell32
_shell32.DragAcceptFiles.argtypes = [ctypes.c_void_p, ctypes.c_bool]
_shell32.DragQueryFileW.restype = ctypes.c_uint
_shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                    ctypes.c_wchar_p, ctypes.c_uint]
_shell32.DragFinish.argtypes = [ctypes.c_void_p]

C_BG, C_BG2, C_DARK = host.C_BG, host.C_BG2, host.C_DARK
C_BLURPLE, C_BLURPLE_H = host.C_BLURPLE, host.C_BLURPLE_H
C_TEXT, C_MUTED, C_GREEN, C_RED = host.C_TEXT, host.C_MUTED, host.C_GREEN, host.C_RED
FONT = host.FONT

# ---- палітра таймлайна в стилі CapCut ----
C_TRACK = "#121317"          # тло таймлайна
C_LANE = "#1a1b20"           # смуга доріжки
C_RULER = "#0e0f12"          # лінійка часу + ліва колонка
C_CLIP = "#2c2f37"           # кліп у монтажі
C_CLIP_SEL = host.C_BLURPLE  # вибраний кліп
C_HANDLE = "#ffffff"         # білі ручки-хендли обрізки (як у CapCut)
C_PLAY = "#ffffff"           # плейхед
C_SND = "#33c27f"            # блоки доданих звуків
C_OVL = "#a77cf0"            # блоки накладок (медіа поверх відео)
C_WAVE_IN = "#dfe6ff"        # хвиля всередині ВИБРАНОГО кліпа
C_SNAP = "#ffd23f"           # лінія «магніту»
C_DROP = "#4cc9ff"           # куди ляже перетягнутий кліп
C_TXT = "#f0a742"            # блоки тексту
TLH = 66                     # висота основної доріжки (кліпи)
THUMB_H = TLH - 6            # висота кадру кіно-стрічки
THUMB_W = 40                 # ширина кадру, поки пропорції невідомі
SCRUB_H = 360                # висота кадрів кешу «живого» перемотування
# ---- геометрія таймлайна (ОДИН канвас: лінійка + 3 доріжки + скролбар) ----
LX = 44                      # ліва колонка з іконками доріжок
PAD_L = 10                   # відступ від колонки до 00:00
RUL_H = 26                   # лінійка часу
TXT_Y = RUL_H + 6            # доріжка тексту (титри)
TXT_H = 26
OVL_Y = TXT_Y + TXT_H + 4
OVL_H = 30
TL_Y = OVL_Y + OVL_H + 6
SND_Y = TL_Y + TLH + 6
SND_H = 30
SB_Y = SND_Y + SND_H + 10
SB_H = 8
TL_TOTAL_H = SB_Y + SB_H + 6
ZMIN, ZMAX = 0.02, 80.0      # межі зуму доріжки
IMG_DUR = 4.0                # скільки секунд показувати додану картинку (тягнеться ручками)
IMG_MAX = 3600.0             # стеля розтягування картинки


def E(key, **kw):
    """Переклад рядка редактора поточною мовою програми (раніше редактор був лише українською)."""
    return i18n.tr(host.LANG, key, **kw)


def _sync_theme():
    """Кольори модуля = ПОТОЧНА тема оверлея. Раніше бралися один раз при імпорті,
    тож після зміни теми в меню редактор лишався у старих кольорах."""
    global C_BG, C_BG2, C_DARK, C_BLURPLE, C_BLURPLE_H, C_TEXT, C_MUTED, C_GREEN, C_RED
    global C_CLIP_SEL, C_ACC2
    C_BG, C_BG2, C_DARK = host.C_BG, host.C_BG2, host.C_DARK
    C_BLURPLE, C_BLURPLE_H = host.C_BLURPLE, host.C_BLURPLE_H
    C_TEXT, C_MUTED, C_GREEN, C_RED = host.C_TEXT, host.C_MUTED, host.C_GREEN, host.C_RED
    C_CLIP_SEL = host.C_BLURPLE
    C_ACC2 = ui.accent2(themes.palette(host.THEME))


C_ACC2 = C_BLURPLE


def fmt(t):
    t = max(0, t)
    return f"{int(t // 60)}:{int(t % 60):02d}.{int((t * 10) % 10)}"


class PillBtn(tk.Canvas):
    """Кнопка-пігулка в стилі оверлея (заокруглений полігон на канвасі).
    Підтримує .config(text=..., state=...) — як tk.Button, тож стара логіка
    (play_btn/export_btn) працює без змін."""

    def __init__(self, parent, text, cmd, primary=True, minw=0, small=False):
        self._txt = text
        self._cmd = cmd
        self._fill = C_BLURPLE if primary else C_BG2
        self._hov = C_BLURPLE_H if primary else C_DARK
        self._fg = "#ffffff" if primary else C_TEXT
        self._h = 30 if small else 38
        self._fs = 9 if small else 10
        self._minw = minw
        self._state = "normal"
        self._hover = False
        try:
            pbg = parent.cget("bg")
        except tk.TclError:
            pbg = C_BG
        super().__init__(parent, height=self._h, bg=pbg, highlightthickness=0,
                         cursor="hand2")
        self._draw()
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", self._click)

    def _click(self, _ev):
        if self._state == "normal" and self._cmd:
            self._cmd()

    def _set_hover(self, on):
        self._hover = on
        self._draw()

    def _measure(self):
        try:
            tw = int(self.tk.call("font", "measure", (FONT, self._fs, "bold"), self._txt))
        except tk.TclError:
            tw = 8 * len(self._txt)
        return max(self._minw, tw + (22 if self._h < 34 else 30))

    def _draw(self):
        w = self._measure()
        tk.Canvas.configure(self, width=w)
        self.delete("all")
        if self._state != "normal":
            fill, fg = C_DARK, C_MUTED
        elif self._hover:
            fill, fg = self._hov, self._fg
        else:
            fill, fg = self._fill, self._fg
        r = self._h // 2 - 1
        if self._state == "normal" and self._fill == C_BLURPLE:
            a1, a2 = (ui.lighten(C_BLURPLE, 0.12), ui.lighten(C_ACC2, 0.12)) if self._hover \
                else (C_BLURPLE, C_ACC2)
            ui.grad_round_rect(self, 1, 1, w - 1, self._h - 1, r, a1, a2)
        else:
            self.create_polygon(host._rr_pts(1, 1, w - 1, self._h - 1, r), smooth=True,
                                fill=fill, outline=("" if self._fill == C_BLURPLE
                                                    else ui.mix(fill, C_TEXT, 0.10)))
        self.create_text(w / 2, self._h / 2, text=self._txt, fill=fg,
                         font=(FONT, self._fs, "bold"))

    def config(self, cnf=None, **kw):
        redraw = False
        if "text" in kw and kw["text"] != self._txt:
            self._txt = kw.pop("text"); redraw = True
        else:
            kw.pop("text", None)
        if "state" in kw:
            st = str(kw.pop("state"))
            if st != self._state:
                self._state = st; redraw = True
        for k in ("bg", "activebackground", "fg", "activeforeground"):
            kw.pop(k, None)
        if kw or cnf:
            tk.Canvas.configure(self, cnf, **kw)
        if redraw:
            self._draw()

    configure = config


class Tip:
    """Підказка при наведенні (як у CapCut): назва дії + гаряча клавіша."""

    def __init__(self, widget, text):
        self.w, self.text = widget, text
        self._after = None
        self._win = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<ButtonPress>", self._leave, add="+")

    def _enter(self, _e=None):
        self._cancel()
        try:
            self._after = self.w.after(450, self._show)
        except tk.TclError:
            self._after = None

    def _cancel(self):
        if self._after:
            try:
                self.w.after_cancel(self._after)
            except Exception:
                pass
            self._after = None

    def _leave(self, _e=None):
        self._cancel()
        if self._win is not None:
            try:
                self._win.destroy()
            except tk.TclError:
                pass
            self._win = None

    def _show(self):
        self._after = None
        txt = self.text() if callable(self.text) else self.text
        if not txt:
            return
        try:
            win = tk.Toplevel(self.w)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            tk.Label(win, text=txt, bg="#0b0c0f", fg="#ffffff", font=(FONT, 9),
                     padx=9, pady=4, highlightthickness=1,
                     highlightbackground="#3a3d46").pack()
            win.update_idletasks()
            x = self.w.winfo_rootx() + self.w.winfo_width() // 2 - win.winfo_reqwidth() // 2
            y = self.w.winfo_rooty() - win.winfo_reqheight() - 6
            if y < 0:
                y = self.w.winfo_rooty() + self.w.winfo_height() + 6
            win.geometry(f"+{max(0, x)}+{y}")
            self._win = win
        except tk.TclError:
            self._win = None


class IconBtn(tk.Canvas):
    """Кнопка-іконка панелі інструментів (як у CapCut): підсвітка при наведенні,
    «натискання», вимкнений стан і підказка з гарячою клавішею."""

    def __init__(self, parent, icon, cmd, tip="", size=32, fs=12, accent=False, round_=False):
        self._icon, self._cmd, self._size, self._fs = icon, cmd, size, fs
        self._accent, self._round = accent, round_
        self._state, self._hover, self._down, self._on = "normal", False, False, False
        try:
            self._pbg = parent.cget("bg")
        except tk.TclError:
            self._pbg = C_BG
        super().__init__(parent, width=size, height=size, bg=self._pbg,
                         highlightthickness=0, cursor="hand2")
        self.bind("<Enter>", lambda e: self._set(h=True))
        self.bind("<Leave>", lambda e: self._set(h=False, d=False))
        self.bind("<ButtonPress-1>", lambda e: self._set(d=True))
        self.bind("<ButtonRelease-1>", self._release)
        self.tip = Tip(self, tip) if tip else None
        self._draw()

    def _set(self, h=None, d=None):
        if h is not None:
            self._hover = h
        if d is not None:
            self._down = d
        self._draw()

    def _release(self, ev):
        was = self._down
        self._down = False
        self._draw()
        if (was and self._state == "normal" and self._cmd
                and 0 <= ev.x <= self._size and 0 <= ev.y <= self._size):
            self._cmd()

    def set_icon(self, icon):
        if icon != self._icon:
            self._icon = icon
            self._draw()

    def set_on(self, on):
        if bool(on) != self._on:
            self._on = bool(on)
            self._draw()

    def set_state(self, st):
        st = str(st)
        if st != self._state:
            self._state = st
            self.configure(cursor=("hand2" if st == "normal" else ""))
            self._draw()

    def _draw(self):
        try:
            self.delete("all")
        except tk.TclError:
            return
        s = self._size
        dis = self._state != "normal"
        if self._accent:
            fill = C_DARK if dis else C_BLURPLE
            if not dis and self._down:
                fill = ui.darken(C_BLURPLE, 0.12)
            elif not dis and self._hover:
                fill = ui.lighten(C_BLURPLE, 0.14)
            fg = "#ffffff"
        else:
            fill = self._pbg
            if not dis and self._down:
                fill = ui.mix(self._pbg, C_TEXT, 0.22)
            elif not dis and self._hover:
                fill = ui.mix(self._pbg, C_TEXT, 0.12)
            if self._on and not dis and not self._hover and not self._down:
                fill = ui.mix(self._pbg, C_BLURPLE, 0.55)
            fg = ui.mix(self._pbg, C_MUTED, 0.45) if dis else C_TEXT
        if self._round:
            self.create_oval(1, 1, s - 1, s - 1, fill=fill, outline="")
        elif fill != self._pbg:
            self.create_polygon(host._rr_pts(1, 1, s - 1, s - 1, 8), smooth=True,
                                fill=fill, outline="")
        off = 1 if (self._down and not dis) else 0
        self.create_text(s / 2, s / 2 + off, text=self._icon, fill=fg, font=(FONT, self._fs))


class ZoomSlider(tk.Canvas):
    """Повзунок масштабу доріжки (логарифмічний, як у CapCut) — тягнеться мишкою."""

    def __init__(self, parent, lo, hi, get, set_, width=120):
        try:
            bg = parent.cget("bg")
        except tk.TclError:
            bg = C_BG
        super().__init__(parent, width=width, height=26, bg=bg, highlightthickness=0,
                         cursor="hand2")
        self._lo, self._hi, self._get, self._setf, self._sw = lo, hi, get, set_, width
        self._hover = False
        self.bind("<Button-1>", self._drag)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<Enter>", lambda e: self._hov(True))
        self.bind("<Leave>", lambda e: self._hov(False))
        self.tip = Tip(self, E("ed_tt_zoom"))
        self.redraw()

    def _hov(self, on):
        self._hover = on
        self.redraw()

    def _frac(self):
        try:
            z = max(self._lo, min(self._hi, float(self._get())))
            return (math.log(z) - math.log(self._lo)) / (math.log(self._hi) - math.log(self._lo))
        except (ValueError, ZeroDivisionError):
            return 0.5

    def _drag(self, ev):
        f = max(0.0, min(1.0, (ev.x - 8) / float(self._sw - 16)))
        z = math.exp(math.log(self._lo) + f * (math.log(self._hi) - math.log(self._lo)))
        self._setf(z)
        self.redraw()

    def redraw(self):
        try:
            self.delete("all")
        except tk.TclError:
            return
        x1, x2, y = 8, self._sw - 8, 13
        kx = x1 + self._frac() * (x2 - x1)
        self.create_line(x1, y, x2, y, fill=ui.mix(C_BG2, C_TEXT, 0.18), width=3, capstyle="round")
        self.create_line(x1, y, kx, y, fill=C_BLURPLE, width=3, capstyle="round")
        r = 7 if self._hover else 6
        self.create_oval(kx - r, y - r, kx + r, y + r, fill="#ffffff", outline="")


class VideoEditor(tk.Toplevel):
    VW, VH = 640, 360
    VPAD = 40        # поля навколо екрана плеєра — рамка масштабу видно й ЗА плеєром
    TW = 900

    def __init__(self, master, file_path, info, cfg, discord_hwnd, watcher, on_close):
        _sync_theme()
        super().__init__(master)
        self.file_path, self.info, self.cfg = file_path, info, cfg
        self.discord_hwnd, self.watcher, self.on_close = discord_hwnd, watcher, on_close
        self._cancel_flag = False    # закриття під час експорту зупиняє ffmpeg
        self._closed = False

        # ---- джерела медіа (source 0 = початкове відео) ----
        self.sources = []
        self._tmp = tempfile.mkdtemp(prefix="dedit_")
        si = self._add_source(file_path, "video", info)

        # ---- кліпи доріжки: словники (src, s, e, zoom, nx, ny, speed, mute) ----
        self.pieces = [self._new_piece(si, 0.0, max(0.1, info["duration"]))]
        self.order = [0]
        self.sel = 0
        self.snds = []               # додані звуки: {"path","at","dur","vol","name","env"}
        self._sel_snd = None         # вибраний звук (його хвиля малюється в блоці)
        self.sel_txt = None
        # накладки ПОВЕРХ відео (картинка-в-картинці): {"src","s","e","at","zoom","nx","ny","mute"}
        self.ovls = []
        self.sel_ovl = None          # вибрана накладка -> рамка на прев'ю керує НЕЮ
        self.sel_txt = None
        self.texts = []              # титри: див. edit_fx.new_text
        self.sel_txt = None
        self._txt_rects = []
        self._txt_drag = None
        self._font = fx.find_font()  # шрифт для drawtext (Segoe UI Bold — є кирилиця)
        self._insp = None            # права панель властивостей
        self._play_sp = 1.0
        self._play_fx = False
        self._fx_broken = False      # ffplay не прийняв фільтри -> граємо без них
        self._play_launch_t = 0.0
        self._ovl_rects = []
        self._ovl_drag = None

        # ---- канвас експорту = розміри першого відео (кап 1920) ----
        w0 = int(info.get("width") or 1280) or 1280
        h0 = int(info.get("height") or 720) or 720
        k = min(1.0, 1920.0 / max(w0, h0))
        self._ccw = max(2, int(w0 * k / 2) * 2)
        self._cch = max(2, int(h0 * k / 2) * 2)
        self._cfps = min(60.0, float(info.get("fps", 30) or 30))
        # базовий масштаб доріжки: перше відео рівно вміщується у TW (далі НЕ перераховується
        # при обрізці — фіксований px/сек, як у CapCut)
        self._base_pps = (self.TW - LX - PAD_L - 40) / max(0.1, info["duration"])
        pk = min(self.VW / self._ccw, self.VH / self._cch)
        self._pcw = max(2, int(self._ccw * pk / 2) * 2)   # прев'ю-канвас (вписаний у 480x270)
        self._pch = max(2, int(self._cch * pk / 2) * 2)
        self._w0, self._h0 = self._ccw, self._cch   # «Оригінал» для формату кадру
        self._ratio = "orig"         # формат кадру: orig / 16:9 / 9:16 / 1:1 / 4:5 / 4:3
        self._bgmode = "black"       # чим заповнити поля: black / blur (розмите відео)
        self._uidn = 0               # унікальні мітки для графів фільтрів
        self._junc = []              # іконки переходів на стиках кліпів

        self.playing = False
        self.cur = 0.0
        self._ffplay = None
        self._embedded = None
        self._play_start = 0.0
        self._play_end = 0.0
        self._play_t0 = 0.0
        self._play_kind = "video"
        self._play_src_dur = max(0.1, info["duration"])
        self._embed_title = ""
        self._img = None
        self._tick_id = None
        self._prev_after = None
        self._frame_idx = 0
        self.busy = False
        self._drag = None            # 'L'/'R' — тягнемо ручку обрізки; None — ні
        self._active = None          # 'L'/'R' — остання чіпана ручка (для стрілок-нуджу)
        self._tip_t = None           # час над ручкою під час обрізки
        self._tip_after = None
        self._nudge_active = False   # щоб серія стрілок була ОДНИМ кроком undo
        self._playhead_x = 0
        self._hwdec_try = []         # які апаратні декодери пробувати (ставить _single_pass)
        self._rec = None             # запис голосу: {"proc","path","at","t0"} або None
        self._rec_n = 0
        self._ffplay_pos = None      # РЕАЛЬНА позиція ffplay (парситься з його -stats)
        self._stat_offset = None
        self._stat_log_t = 0.0
        self._sel_xs = self._sel_xe = None
        self._clip_rects = []        # (slot, ix, cx1, cx2) для кліків по кліпах
        self._snd_rects = []         # (i, x1, x2) блоки звуків на нижній смужці
        self._snd_drag = None
        self._undo = []; self._redo = []
        self._zoom = 1.0
        self._scroll = 0.0
        # ---- таймлайн: режим перетягування, магніт, підсвітка ----
        self._mode = None            # 'ph' | 'trim' | 'clip' | 'ovl' | 'snd' | 'sb' | None
        self._clip_drag = None
        self._sb_drag = None
        self._sb_thumb = None
        self._snap_lt = None
        self._nosnap = False
        self._hover = None
        self._cursor = ""
        self._last_ev = None
        self._edge_after = None
        self._draw_after = None
        self._fit_done = False
        self._poster_busy = False
        self._poster_dirty = False
        self._qcache = {}            # кеш масштабованих кадрів для живого скрабу
        # ---- рамка масштабу/позиції на прев'ю (як у CapCut) ----
        self._tf_on = False
        self._tf_drag = None         # ("move"|"corner", дані початку)
        self._tf_pushed = False
        # ---- drag&drop файлів ----
        self._dnd_hwnd = None
        self._old_wp = None
        self._wndproc_ref = None
        self._dropped = []           # черга перетягнутих файлів (WndProc -> Tk-поллер)
        self._frames = [os.path.join(self._tmp, "a.png"), os.path.join(self._tmp, "b.png")]
        # ---- адаптивний розмір (вікно можна розтягнути/розгорнути на весь екран) ----
        self.VW, self.VH, self.TW = VideoEditor.VW, VideoEditor.VH, VideoEditor.TW
        self._clip_rects, self._ovl_rects, self._snd_rects = [], [], []
        self._rs_after = None
        self._chrome_h = None

        self.title(E("ed_title"))
        try:
            appicon.set_window_icon(self)   # наша іконка в рамці вікна
        except Exception:
            pass
        self.configure(bg=C_BG)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._build()
        self._redraw()
        self._show_poster(0.0)
        self._gen_visuals(si)        # кіно-стрічка + хвиля для першого джерела
        self.after(400, self._enable_dnd)   # перетягування файлів (після мапінгу вікна)
        self._arm_resize()                  # велике вікно одразу + адаптивний розмір

    # ------------------------------------------------------------ джерела -- #
    def _new_piece(self, si, s, e):
        # gap = порожнє місце ПЕРЕД кліпом (сек монтажу): з'являється при обрізці
        # лівою ручкою, лишається на доріжці і зникає лише при збереженні
        p = {"src": si, "s": float(s), "e": float(e), "gap": 0.0,
             "zoom": 1.0, "nx": 0.0, "ny": 0.0, "speed": 1.0, "mute": False}
        p.update(fx.PIECE_DEFAULTS)          # гучність, фейди, фільтр, колір, поворот
        return p

    @staticmethod
    def _gapof(p):
        return max(0.0, p.get("gap", 0.0))

    def _add_source(self, path, kind, info):
        """Реєструє джерело (відео/картинку); повертає його індекс. Дублікати переюзуємо."""
        for i, s in enumerate(self.sources):
            if s["path"] == path and s["kind"] == kind:
                return i
        self.sources.append({
            "path": path, "kind": kind, "name": os.path.basename(path),
            "dur": max(0.1, float(info.get("duration") or 0) or (IMG_MAX if kind == "image" else 0.1)),
            "fps": float(info.get("fps", 30) or 30),
            "has_audio": bool(info.get("has_audio", False)),
            "w": int(info.get("width") or 0), "h": int(info.get("height") or 0),
            "env": None, "strip": None, "times": [],
        })
        return len(self.sources) - 1

    def _src(self, piece):
        return self.sources[piece["src"]]

    def _sel_piece(self):
        return self.pieces[self.order[self.sel]]

    # ----------------------------------------------------------------- UI -- #
    def _build(self):
        """Лейаут як у CapCut: верхня панель (файл + експорт) · великий плеєр ·
        транспорт · панель інструментів · ОДИН таймлайн з лінійкою часу і плейхедом."""
        top = tk.Frame(self, bg=C_DARK)
        top.pack(side="top", fill="x")
        tk.Label(top, text="✂", bg=C_DARK, fg=C_BLURPLE,
                 font=(FONT, 15, "bold")).pack(side="left", padx=(14, 6), pady=8)
        nm = os.path.basename(self.file_path)
        if len(nm) > 44:
            nm = nm[:42] + "…"
        tk.Label(top, text=nm, bg=C_DARK, fg=C_TEXT, font=(FONT, 10, "bold")).pack(side="left")
        self.dims_lbl = tk.Label(top, text="", bg=C_DARK, fg=C_MUTED, font=(FONT, 9))
        self.dims_lbl.pack(side="left")
        self.ratio_btn = self._btn(top, "▭", self._ratio_menu, primary=False, small=True)
        self.ratio_btn.pack(side="left", padx=(14, 0))
        Tip(self.ratio_btn, E("ratio_tt"))
        self._update_dims()
        ec = tk.Frame(top, bg=C_DARK)
        ec.pack(side="right", padx=(6, 12), pady=7)
        self._btn(ec, E("ov_cancel"), self._close, primary=False).pack(side="left", padx=3)
        fm = self.cfg.get("editor_export")
        self._xfmt = fm if fm in ("video", "audio", "gif") else "video"
        self.fmt_btn = self._btn(ec, "🎬 MP4 ▾", self._fmt_menu, primary=False)
        self.fmt_btn.pack(side="left", padx=3)
        Tip(self.fmt_btn, E("ed_fmt_tt"))
        self.gif_btn = self.fmt_btn          # під час збереження вимикається разом з експортом
        self.export_btn = self._btn(ec, E("ed_export"), self._export_any)
        self.export_btn.pack(side="left", padx=3)
        self._update_fmt()
        self.info_lbl = tk.Label(top, text="", bg=C_DARK, fg=C_TEXT, font=(FONT, 10, "bold"))
        self.info_lbl.pack(side="right", padx=10)
        # тонка смужка прогресу збереження під верхньою панеллю
        self.prog = tk.Canvas(self, height=3, bg=C_DARK, highlightthickness=0)
        self.prog.pack(side="top", fill="x")

        # ---- низ вікна пакуємо ЗНИЗУ: якщо місця мало, стискається плеєр, а не таймлайн ----
        self.joke_lbl = tk.Label(self, text=E("ed_status_hint"), bg=C_BG, fg=C_MUTED,
                                 font=(FONT, 9), anchor="w")
        self.joke_lbl.pack(side="bottom", fill="x", padx=14, pady=(3, 5))

        self.tl = tk.Canvas(self, width=self.TW, height=TL_TOTAL_H, bg=C_TRACK,
                            highlightthickness=0)
        self.tl.pack(side="bottom", fill="x")
        self.tl.bind("<Configure>", self._on_tl_config)
        self.tl.bind("<Button-1>", self._tl_press)
        self.tl.bind("<B1-Motion>", self._tl_motion)
        self.tl.bind("<ButtonRelease-1>", self._tl_release)
        self.tl.bind("<Button-3>", self._tl_rclick)
        self.tl.bind("<Motion>", self._tl_hover)
        self.tl.bind("<Leave>", self._tl_leave)
        self.tl.bind("<MouseWheel>", self._on_wheel)
        self.tl.bind("<Double-Button-1>", self._tl_double)

        # ---- панель інструментів над таймлайном ----
        bar = tk.Frame(self, bg=C_BG2)
        bar.pack(side="bottom", fill="x")
        lb = tk.Frame(bar, bg=C_BG2)
        lb.pack(side="left", padx=8, pady=4)

        def sep(parent):
            tk.Frame(parent, bg=ui.mix(C_BG2, C_TEXT, 0.16), width=1,
                     height=20).pack(side="left", padx=7)

        def ib(parent, icon, cmd, tip, **kw):
            b = IconBtn(parent, icon, cmd, tip=tip, **kw)
            b.pack(side="left", padx=1)
            return b
        self.b_undo = ib(lb, "↶", self._undo_action, E("ed_tt_undo"), fs=14)
        self.b_redo = ib(lb, "↷", self._redo_action, E("ed_tt_redo"), fs=14)
        sep(lb)
        self.b_split = ib(lb, "✂", self._cut_here, E("ed_tt_split"))
        self.b_del = ib(lb, "🗑", self._delete_selected, E("ed_tt_delete"))
        self.b_dup = ib(lb, "📄", self._duplicate, E("ed_tt_dup"))
        self.b_speed = ib(lb, "⚡", self._speed_popup, E("ed_tt_speed"))
        self.b_mute = ib(lb, "🔊", self._toggle_mute, E("ed_tt_mute"))
        self.b_ovl = ib(lb, "🎭", lambda: self._to_overlay(), E("ed_tt_ovl"))
        sep(lb)
        self.b_txt = ib(lb, "T", self._add_text, E("ed_tt_text"), fs=14)
        self.b_mic = ib(lb, "🎙", self._toggle_rec, E("ed_tt_mic"), fs=13)
        self.b_mic.bind("<Button-3>", lambda e: self._mic_menu())
        self.b_add = ib(lb, "➕", self._add_dialog, E("ed_tt_add"))
        sep(lb)
        self.b_insp = ib(lb, "⚙", self._toggle_insp, E("ed_tt_insp"), fs=13)

        rb = tk.Frame(bar, bg=C_BG2)
        rb.pack(side="right", padx=8, pady=4)
        IconBtn(rb, "❓", self._show_help, tip=E("ed_help_title")).pack(side="right", padx=1)
        tk.Frame(rb, bg=ui.mix(C_BG2, C_TEXT, 0.16), width=1, height=20).pack(side="right", padx=7)
        IconBtn(rb, "⤢", self._zoom_fit, tip=E("ed_tt_fit"), fs=13).pack(side="right", padx=1)
        IconBtn(rb, "+", lambda: self._zoom_at(1.25), tip=E("ed_tt_zin"), fs=14).pack(side="right", padx=1)
        self.zoom_sl = ZoomSlider(rb, ZMIN, ZMAX, lambda: self._zoom, self._set_zoom, width=130)
        self.zoom_sl.pack(side="right", padx=2)
        IconBtn(rb, "−", lambda: self._zoom_at(0.8), tip=E("ed_tt_zout"), fs=14).pack(side="right", padx=1)

        # ---- транспорт під плеєром: час · ⏮ ‹ ▶ › ⏭ · на весь екран ----
        tb = tk.Frame(self, bg=C_BG, height=50)
        tb.pack(side="bottom", fill="x")
        tb.pack_propagate(False)
        self.time_lbl = tk.Label(tb, text="", bg=C_BG, fg=C_TEXT, font=("Consolas", 11, "bold"))
        self.time_lbl.pack(side="left", padx=16)
        IconBtn(tb, "⛶", self._toggle_max, tip=E("ed_tt_max"), fs=13).pack(side="right", padx=14)
        mid = tk.Frame(tb, bg=C_BG)
        mid.place(relx=0.5, rely=0.5, anchor="center")
        IconBtn(mid, "⏮", self._to_start, tip=E("ed_tt_start")).pack(side="left", padx=3)
        IconBtn(mid, "‹", lambda: self._nudge(-1), tip=E("ed_tt_prev"), fs=17).pack(side="left", padx=3)
        self.play_btn = IconBtn(mid, "▶", self._toggle_play, tip=E("ed_tt_play"),
                                size=42, fs=15, accent=True, round_=True)
        self.play_btn.pack(side="left", padx=8)
        IconBtn(mid, "›", lambda: self._nudge(1), tip=E("ed_tt_next"), fs=17).pack(side="left", padx=3)
        IconBtn(mid, "⏭", self._to_end, tip=E("ed_tt_end")).pack(side="left", padx=3)

        # ---- плеєр: канвас ШИРШИЙ за екран (поля VPAD) -> рамку масштабу видно й за кадром ----
        self.mid = tk.Frame(self, bg=C_BG)
        self.mid.pack(side="top", fill="both", expand=True)
        P = {"bg2": C_BG2, "dark": C_DARK, "text": C_TEXT, "muted": C_MUTED,
             "accent": C_BLURPLE, "font": FONT}
        self._insp = edit_inspector.Inspector(self.mid, self, P, E)
        self._insp_on = False        # права панель відкривається кнопкою ⚙ на панелі інструментів
        self.video = tk.Canvas(self.mid, width=self.VW + 2 * self.VPAD,
                               height=self.VH + 2 * self.VPAD, bg=C_BG, highlightthickness=0)
        self.video.pack(side="left", expand=True)
        self._draw_player_frame()
        self.video.bind("<Button-1>", self._video_press)
        self.video.bind("<B1-Motion>", self._video_motion)
        self.video.bind("<ButtonRelease-1>", self._video_release)
        self.video.bind("<Double-Button-1>", lambda e: self._tf_reset())

        # гарячі клавіші — по КОДУ клавіші (працюють і на укр/рус розкладці)
        self.bind("<KeyPress>", self._on_key)
        try:
            self.focus_set()
        except tk.TclError:
            pass

    def _btn(self, parent, text, cmd, primary=True, minw=0, small=False):
        return PillBtn(parent, text, cmd, primary=primary, minw=minw, small=small)

    def _set_play_icon(self, on):
        try:
            self.play_btn.set_icon("⏸" if on else "▶")
        except (tk.TclError, AttributeError):
            pass

    def _set_progress(self, p, text=None, col=None):
        """Тонка смужка прогресу під верхньою панеллю (+ текст у верхній панелі)."""
        try:
            if text is not None:
                self.info_lbl.config(text=text, fg=col or C_BLURPLE)
            c = self.prog
            c.delete("all")
            if p is None:
                return
            w = max(1, c.winfo_width())
            x = w * max(0.0, min(100.0, p)) / 100.0
            c.create_rectangle(0, 0, max(2, x), 3, fill=C_BLURPLE, outline="")
        except (tk.TclError, Exception):
            pass

    def _toggle_max(self):
        try:
            self.state("normal" if self.state() == "zoomed" else "zoomed")
        except tk.TclError:
            pass

    def _draw_player_frame(self):
        """Картка-підложка і чорний екран плеєра (перемальовується при зміні розміру)."""
        c = self.video
        c.delete("card"); c.delete("screen")
        m = 10
        c.create_polygon(
            host._rr_pts(self.VPAD - m, self.VPAD - m,
                         self.VPAD + self.VW + m, self.VPAD + self.VH + m, 14),
            smooth=True, fill=C_BG2, outline="", tags="card")
        c.create_rectangle(self.VPAD, self.VPAD, self.VPAD + self.VW,
                           self.VPAD + self.VH, fill="#000000", outline=C_DARK,
                           tags="screen")
        c.tag_lower("screen")
        c.tag_lower("card")

    # ---- адаптивний розмір: велике вікно одразу, плеєр росте разом з вікном ----
    def _arm_resize(self):
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            W = max(760, min(sw - 60, 1440))
            H = max(560, min(sh - 90, 940))
            self.minsize(min(W, 980), min(H, 660))
            self.geometry(f"{W}x{H}+{max(0, (sw - W) // 2)}+{max(0, (sh - H) // 2 - 30)}")
            self.mid.bind("<Configure>", self._on_resize)
        except tk.TclError:
            pass

    def _on_resize(self, ev):
        if self.busy:
            return
        if self._rs_after:
            try: self.after_cancel(self._rs_after)
            except Exception: pass
        self._rs_after = self.after(90, self._apply_resize)

    def _apply_resize(self):
        """Плеєр займає все вільне місце між верхньою панеллю, правою панеллю і таймлайном."""
        self._rs_after = None
        try:
            mw, mh = self.mid.winfo_width(), self.mid.winfo_height()
        except tk.TclError:
            return
        if mw < 100 or mh < 100:
            return
        avail_w = mw - (edit_inspector.Inspector.W + 12 if self._insp_on else 0) - 2 * self.VPAD - 28
        avail_h = mh - 2 * self.VPAD - 4
        vw = max(240, min(avail_w, int(avail_h * 16 / 9)))
        vh = max(135, int(vw * 9 / 16))
        if vh > avail_h:
            vh = max(135, avail_h)
            vw = max(240, int(vh * 16 / 9))
        if abs(vw - self.VW) < 6 and abs(vh - self.VH) < 6:
            return
        self.VW, self.VH = vw, vh
        self.video.config(width=vw + 2 * self.VPAD, height=vh + 2 * self.VPAD)
        pk = min(self.VW / self._ccw, self.VH / self._cch)
        self._pcw = max(2, int(self._ccw * pk / 2) * 2)
        self._pch = max(2, int(self._cch * pk / 2) * 2)
        self._draw_player_frame()
        if self._embedded:              # вікно ffplay підганяємо під новий екран
            try:
                _u32.MoveWindow(self._embedded, self.VPAD, self.VPAD, self.VW, self.VH, True)
            except Exception:
                pass
        self.video.delete("frame")
        self._qcache.clear()
        self._show_poster(self.cur, fast=True)
        self._draw_tfbox()

    def _show_help(self):
        """Довідка окремим маленьким вікном (замість написів у самому редакторі)."""
        w = tk.Toplevel(self)
        w.title(E("ed_help_title"))
        try:
            appicon.set_window_icon(w)
        except Exception:
            pass
        w.configure(bg=C_BG)
        w.resizable(False, False)
        w.attributes("-topmost", True)
        w.geometry(f"+{self.winfo_rootx() + 60}+{self.winfo_rooty() + 60}")
        tips = E("ed_tips").split("\n")
        box = tk.Frame(w, bg=C_BG2)
        box.pack(padx=14, pady=(14, 8))
        for t in tips:
            tk.Label(box, text=t, bg=C_BG2, fg=C_TEXT, font=(FONT, 9),
                     justify="left", anchor="w").pack(fill="x", padx=14, pady=2)
        PillBtn(w, E("ed_got_it"), w.destroy, primary=True).pack(pady=(4, 12))

    # ----------------------------------------- додавання медіа (➕ і перетяг) -- #
    def _add_dialog(self):
        pats = " ".join("*" + e for e in
                        sorted(dc_core.VIDEO_EXT | media.IMAGE_EXT | media.AUDIO_EXT))
        try:
            paths = filedialog.askopenfilenames(
                parent=self, title=E("ed_add_title"),
                filetypes=[(E("ed_media"), pats), (E("ed_all_files"), "*.*")])
        except tk.TclError:
            return
        if paths:
            self._add_files(list(paths))

    def _add_files(self, paths):
        """Додає файли на таймлайн: відео/картинки -> кліпи в кінець, звуки -> на плейхед."""
        if self.busy:
            return
        snap = self._snapshot()
        added, skipped = 0, 0
        for p in paths:
            try:
                kind = media.kind_of(p)
                if kind == "video":
                    inf = dc_core.ffprobe_info(p)
                    if inf["duration"] <= 0:
                        skipped += 1
                        continue
                    si = self._add_source(p, "video", inf)
                    self.pieces.append(self._new_piece(si, 0.0, inf["duration"]))
                    self.order.append(len(self.pieces) - 1)
                    self.sel = len(self.order) - 1
                    self._gen_visuals(si)
                elif kind == "image":
                    w, h = media.image_dims(p)
                    si = self._add_source(p, "image",
                                          {"duration": 0, "has_audio": False,
                                           "width": w, "height": h, "fps": self._cfps})
                    self.pieces.append(self._new_piece(si, 0.0, IMG_DUR))
                    self.order.append(len(self.pieces) - 1)
                    self.sel = len(self.order) - 1
                    self._gen_visuals(si)
                elif kind == "audio":
                    d = media.audio_info(p)["duration"]
                    if d <= 0:
                        skipped += 1
                        continue
                    sn = {"path": p, "at": self._playhead_montage_t(), "dur": d, "s": 0.0, "fdur": d,
                          "vol": 1.0, "name": os.path.basename(p), "env": None,
                          "fin": 0.0, "fout": 0.0}
                    self.snds.append(sn)
                    self._gen_snd_env(sn)
                else:
                    skipped += 1
                    continue
                added += 1
            except Exception:
                skipped += 1
        if added:
            self._undo.append(snap)
            if len(self._undo) > 80:
                self._undo.pop(0)
            self._redo.clear()
            p = self._sel_piece()
            self.cur = min(max(self.cur, p["s"]), p["e"])
            self._show_poster(self.cur)
            self._redraw()
        if skipped and not added:
            try:
                self.info_lbl.config(text=E("ed_unsupported"), fg=C_RED)
            except tk.TclError:
                pass

    def _gen_snd_env(self, sn):
        """Хвиля доданого звуку — малюється всередині його блока, коли він вибраний."""
        def work():
            env = dc_core.audio_envelope(sn["path"], hz=100)
            if env:
                def apply():
                    sn["env"] = env
                    self._draw_wave()
                try:
                    self.after(0, apply)
                except Exception:
                    pass
        threading.Thread(target=work, daemon=True).start()

    # ---- WM_DROPFILES: приймаємо перетягнуті файли БЕЗ сторонніх пакетів ----
    def _enable_dnd(self):
        if self._dnd_hwnd:
            return
        try:
            hw = _u32.GetAncestor(int(self.winfo_id()), 2)   # GA_ROOT (без argtypes — спільний user32)
            if not hw:
                return
            _shell32.DragAcceptFiles(hw, True)
            self._wndproc_ref = _WNDPROC(self._wndproc)      # тримаємо посилання від GC!
            self._old_wp = _SetWinLong(hw, _GWL_WNDPROC,
                                       ctypes.cast(self._wndproc_ref, ctypes.c_void_p))
            self._dnd_hwnd = hw
            self._dnd_poll()
        except Exception:
            pass

    def _dnd_poll(self):
        """Забирає файли, які WndProc склав у чергу. ВАЖЛИВО: сам WndProc НЕ сміє
        чіпати Tcl (after/віджети) — реентрантний виклик зсередини диспетчера
        повідомлень валить процес; тому черга + цей поллер."""
        if not self._dnd_hwnd:
            return
        try:
            if self._dropped:
                paths = self._dropped[:]
                del self._dropped[:]
                self._add_files(paths)
            self.after(350, self._dnd_poll)
        except tk.TclError:
            pass

    def _disable_dnd(self):
        hw = self._dnd_hwnd
        if not hw:
            return
        self._dnd_hwnd = None
        try:
            if self._old_wp:
                _SetWinLong(hw, _GWL_WNDPROC, ctypes.c_void_p(self._old_wp))
            _shell32.DragAcceptFiles(hw, False)
        except Exception:
            pass

    def _wndproc(self, hwnd, msg, wp, lp):
        if msg == _WM_DROPFILES:
            try:
                n = _shell32.DragQueryFileW(wp, 0xFFFFFFFF, None, 0)
                paths = []
                for i in range(n):
                    ln = _shell32.DragQueryFileW(wp, i, None, 0) + 1
                    buf = ctypes.create_unicode_buffer(ln)
                    _shell32.DragQueryFileW(wp, i, buf, ln)
                    if buf.value:
                        paths.append(buf.value)
                _shell32.DragFinish(wp)
                # НЕ чіпаємо Tcl звідси (краш) — лише кладемо у чергу для _dnd_poll
                self._dropped.extend(paths)
            except Exception:
                pass
            return 0
        try:
            return _u32.CallWindowProcW(self._old_wp, hwnd, msg, wp, lp)
        except Exception:
            return 0

    # ----------------------------------------------- ПРЕВ'Ю (ffmpeg→PNG) --- #
    def _show_poster(self, t, fast=False):
        self._pending = t
        if fast:
            self._quick_frame(t)            # миттєво з кешу, точний кадр — слідом
        if self._prev_after:
            try: self.after_cancel(self._prev_after)
            except Exception: pass
        self._prev_after = self.after(25 if fast else 110, self._run_poster)

    def _ovl_vf(self, o, cw, ch, alpha=1.0):
        """Ланцюжок накладки: поворот/колір -> масштаб -> прозорість. Повертає (vf, x, y)."""
        sw, sh, x, y = self._ovl_geom(o, cw, ch)
        pre = fx.pre_vf(o)
        f = (pre + "," if pre else "") + f"scale={sw}:{sh}"
        op = float(o.get("op", 1.0)) * alpha
        if op < 0.999:
            f += f",format=rgba,colorchannelmixer=aa={fx.num(max(0.0, op))}"
        return f, x, y

    def _active_texts(self, mt):
        if not self._font:
            return []
        return [t for t in self.texts if t["at"] - 0.001 <= mt <= t["at"] + t["dur"] + 0.001
                and t["text"].strip()]

    def _run_poster(self):
        self._prev_after = None
        if self.playing or self._closed:
            return
        if self._poster_busy:              # кадр ще рендериться -> оновимо одразу після нього
            self._poster_dirty = True
            return
        t = self._pending
        piece = dict(self._sel_piece())          # заморожений стан (фоновий потік)
        src = self._src(piece)
        self._frame_idx ^= 1
        png = self._frames[self._frame_idx]
        cw, ch = self._pcw, self._pch
        vf = self._transform_vf(piece, cw, ch)
        # фейд кліпа в цей момент -> кадр темнішає, як у готовому відео
        cd = (piece["e"] - piece["s"]) / piece["speed"]
        fa = fx.alpha_factor((t - piece["s"]) / piece["speed"], cd,
                             fx.g(piece, "fin"), fx.g(piece, "fout"))
        if fa < 0.999:
            k = fx.num(fa)
            vf += f",colorchannelmixer=rr={k}:gg={k}:bb={k}"
        # накладки й тексти, активні на поточному монтажному часі — постер = КОМПОЗИЦІЯ
        mt = self._playhead_montage_t()
        active = [dict(o) for o in self.ovls
                  if o["at"] - 0.001 <= mt <= o["at"] + (o["e"] - o["s"]) + 0.001]
        texts = [dict(x) for x in self._active_texts(mt)]

        cmd = ["ffmpeg", "-y"]
        if src["kind"] == "image":
            cmd += ["-i", src["path"]]
        else:
            cmd += ["-ss", f"{t:.3f}", "-i", src["path"]]
        fc = [f"[0:v]{vf}[b0]"]
        vin = "[b0]"
        for j, o in enumerate(active):
            osrc = self.sources[o["src"]]
            if osrc["kind"] == "image":
                cmd += ["-i", osrc["path"]]
            else:
                tt = max(0.0, o["s"] + (mt - o["at"]))
                cmd += ["-ss", f"{tt:.3f}", "-i", osrc["path"]]
            a = fx.alpha_factor(mt - o["at"], o["e"] - o["s"], fx.g(o, "fin"), fx.g(o, "fout"))
            ovf, x, y = self._ovl_vf(o, cw, ch, alpha=a)
            fc.append(f"[{j + 1}:v]{ovf}[o{j}]")
            fc.append(f"{vin}[o{j}]overlay={x}:{y}[b{j + 1}]")
            vin = f"[b{j + 1}]"
        for k, tx in enumerate(texts):
            tf = fx.write_text_file(tx, self._tmp, f"p{self._frame_idx}_{k}")
            a = fx.alpha_factor(mt - tx["at"], tx["dur"], tx.get("fin", 0), tx.get("fout", 0))
            fc.append(f"{vin}{fx.drawtext(tx, cw, ch, self._font, tf, alpha_mul=a)}[t{k}]")
            vin = f"[t{k}]"
        cmd += ["-filter_complex", ";".join(fc), "-map", vin, "-frames:v", "1", png]

        self._poster_busy = True

        def work():
            try:
                rc = subprocess.run(cmd, capture_output=True, creationflags=dc_core.NO_WINDOW).returncode
            except Exception:
                rc = 1

            def fin():
                self._poster_busy = False
                if rc == 0 and os.path.exists(png):
                    self._draw_png(png)
                if self._poster_dirty:        # живий скраб: одразу наступний кадр
                    self._poster_dirty = False
                    self._run_poster()
            try:
                self.after(0, fin)
            except Exception:
                self._poster_busy = False
        threading.Thread(target=work, daemon=True).start()

    def _draw_png(self, png):
        if self.playing:
            return
        try:
            self._img = tk.PhotoImage(file=png)
            self.video.delete("frame")
            self.video.create_image(self.VPAD + self.VW // 2, self.VPAD + self.VH // 2,
                                    image=self._img, tags="frame")
            self.video.tag_lower("frame")       # рамка масштабу лишається поверх кадру
            self.video.tag_lower("screen")      # чорний екран — під кадром
            self.video.tag_lower("card")        # картка-підложка — на самому дні
            self._draw_tfbox()
        except tk.TclError:
            pass

    # -------- масштаб/позиція на прев'ю: рамка з ручками (як у CapCut) -------- #
    def _tf_target(self):
        """Що редагує рамка на прев'ю: вибраний ТЕКСТ, НАКЛАДКА, інакше вибраний кліп."""
        if self.sel_txt is not None and self.sel_txt < len(self.texts):
            return self.texts[self.sel_txt]
        if self.sel_ovl is not None and self.sel_ovl < len(self.ovls):
            return self.ovls[self.sel_ovl]
        return self._sel_piece()

    def _screen_origin(self):
        return (self.VPAD + (self.VW - self._pcw) / 2.0, self.VPAD + (self.VH - self._pch) / 2.0)

    def _txt_rect(self, t):
        fs = fx.text_px(t, self._pch)
        lines = (t["text"] or " ").split("\n")
        try:
            w = max(int(self.tk.call("font", "measure", (FONT, -fs, "bold"), ln or " "))
                    for ln in lines)
        except tk.TclError:
            w = int(fs * 0.55 * max(len(ln) for ln in lines))
        h = len(lines) * fs * 1.17
        pad = max(4, fs // 4) if t.get("style") == "box" else 3
        ox, oy = self._screen_origin()
        cx = ox + self._pcw / 2.0 + t["nx"] * self._pcw
        cy = oy + self._pch / 2.0 + t["ny"] * self._pch
        return cx - w / 2 - pad, cy - h / 2 - pad, cx + w / 2 + pad, cy + h / 2 + pad

    def _rect_of(self, p):
        """Прямокутник об'єкта на канвасі прев'ю (кліп/накладка з zoom/nx/ny або текст)."""
        if "text" in p:
            return self._txt_rect(p)
        src = self._src(p)
        iw, ih = fx.eff_dims(src["w"] or self._pcw, src["h"] or self._pch, p)
        f0 = min(self._pcw / float(iw), self._pch / float(ih))
        sw, sh = iw * f0 * p["zoom"], ih * f0 * p["zoom"]
        ox, oy = self._screen_origin()
        cx = ox + self._pcw / 2.0 + p["nx"] * self._pcw
        cy = oy + self._pch / 2.0 + p["ny"] * self._pch
        return cx - sw / 2, cy - sh / 2, cx + sw / 2, cy + sh / 2

    def _tf_rect(self):
        return self._rect_of(self._tf_target())

    def _draw_tfbox(self):
        c = self.video
        c.delete("tf")
        if not self._tf_on or self.playing:
            return
        x1, y1, x2, y2 = self._tf_rect()
        CW = self.VW + 2 * self.VPAD
        CH = self.VH + 2 * self.VPAD
        if self.sel_txt is not None:
            col, what = C_TXT, E("ed_tf_txt")
        elif self.sel_ovl is not None:
            col, what = C_OVL, E("ed_tf_ovl")
        else:
            col, what = C_HANDLE, ""
        c.create_rectangle(x1, y1, x2, y2, outline=col, width=2, tags="tf")
        r = 7
        # ручки КЛАМПЛЯТЬСЯ у межі канваса: навіть коли рамка більша за поля —
        # кут завжди видно і можна схопити (масштаб рахується від центру, не від ручки)
        self._tf_handles = []
        for hx, hy in ((x1, y1), (x2, y1), (x1, y2), (x2, y2)):
            hxc = min(max(hx, r + 2), CW - r - 2)
            hyc = min(max(hy, r + 2), CH - r - 2)
            self._tf_handles.append((hxc, hyc))
            c.create_rectangle(hxc - r, hyc - r, hxc + r, hyc + r,
                               fill=col, outline=C_DARK, width=1, tags="tf")
        ty = min(CH - 9, max(10, y2 + 14))
        c.create_text(CW / 2, ty, text=E("ed_tf_hint", what=what),
                      fill=C_HANDLE, font=(FONT, 8), tags="tf")

    def _preview_pick(self, x, y):
        """Що під курсором на прев'ю: ('txt', i) / ('ovl', i) / None (сам кліп)."""
        mt = self._playhead_montage_t()
        for i in reversed(range(len(self.texts))):
            t = self.texts[i]
            if t["at"] - 0.001 <= mt <= t["at"] + t["dur"] + 0.001:
                x1, y1, x2, y2 = self._txt_rect(t)
                if x1 - 4 <= x <= x2 + 4 and y1 - 4 <= y <= y2 + 4:
                    return ("txt", i)
        for i in reversed(range(len(self.ovls))):
            o = self.ovls[i]
            if o["at"] - 0.001 <= mt <= o["at"] + (o["e"] - o["s"]) + 0.001:
                x1, y1, x2, y2 = self._rect_of(o)
                if x1 <= x <= x2 and y1 <= y <= y2:
                    return ("ovl", i)
        return None

    def _video_press(self, ev):
        if self.busy:
            return
        try:
            self.focus_set()
        except tk.TclError:
            pass
        if self.playing:
            self._pause()                 # пауза -> на постері можна редагувати рамку
        on_corner = False
        if self._tf_on:
            for hx, hy in getattr(self, "_tf_handles", None) or ():
                if abs(ev.x - hx) <= 12 and abs(ev.y - hy) <= 12:
                    on_corner = True
                    break
        if not on_corner:                 # клік по тексту/накладці на відео -> вибрати її
            hit = self._preview_pick(ev.x, ev.y)
            if hit is not None and hit != self._sel_kind():
                self._select(hit)
                self._tf_on = True
                self._draw_tfbox()
                self._redraw()
            elif hit is None and self._sel_kind() is not None and self._sel_kind()[0] != "snd":
                x1, y1, x2, y2 = self._tf_rect()
                if not (x1 - 4 <= ev.x <= x2 + 4 and y1 - 4 <= ev.y <= y2 + 4):
                    self._select(None)    # клік по самому відео -> рамка кліпа
                    self._tf_on = True
                    self._draw_tfbox()
                    self._redraw()
        p = self._tf_target()
        if not self._tf_on:
            self._tf_on = True
            self._tf_drag = None
            self._draw_tfbox()
            return
        x1, y1, x2, y2 = self._tf_rect()
        cxm, cym = (x1 + x2) / 2, (y1 + y2) / 2
        corner = None
        for hx, hy in getattr(self, "_tf_handles", None) or ((x1, y1), (x2, y1), (x1, y2), (x2, y2)):
            if abs(ev.x - hx) <= 12 and abs(ev.y - hy) <= 12:
                corner = (hx, hy)
                break
        base = {"x": ev.x, "y": ev.y, "zoom": p["zoom"], "nx": p["nx"], "ny": p["ny"],
                "cx": cxm, "cy": cym, "moved": False}
        self._tf_pushed = False
        if corner:
            base["d0"] = max(8.0, ((ev.x - cxm) ** 2 + (ev.y - cym) ** 2) ** 0.5)
            self._tf_drag = ("corner", base)
        elif x1 - 4 <= ev.x <= x2 + 4 and y1 - 4 <= ev.y <= y2 + 4:
            self._tf_drag = ("move", base)
        else:
            self._tf_drag = ("off", base)   # клік поза відео -> сховати рамку на release

    def _video_motion(self, ev):
        if not self._tf_drag:
            return
        mode, b = self._tf_drag
        if mode == "off":
            return
        if abs(ev.x - b["x"]) + abs(ev.y - b["y"]) < 3 and not b["moved"]:
            return
        if not self._tf_pushed:            # один undo-крок на весь drag
            self._push_undo()
            self._tf_pushed = True
        b["moved"] = True
        p = self._tf_target()
        if mode == "corner":
            d = max(8.0, ((ev.x - b["cx"]) ** 2 + (ev.y - b["cy"]) ** 2) ** 0.5)
            p["zoom"] = min(5.0, max(0.2, b["zoom"] * d / b["d0"]))
        else:
            nx = b["nx"] + (ev.x - b["x"]) / self._pcw
            ny = b["ny"] + (ev.y - b["y"]) / self._pch
            # магніт до центру кадру (як у CapCut); Alt — без нього
            if not (ev.state & 0x20000):
                if abs(nx) < 0.012:
                    nx = 0.0
                if abs(ny) < 0.012 and "text" not in p:
                    ny = 0.0
            p["nx"] = min(1.4, max(-1.4, nx))
            p["ny"] = min(1.4, max(-1.4, ny))
        self._draw_tfbox()
        if p["nx"] == 0.0 and mode == "move":     # підказка: вирівняно по центру
            cx = self._screen_origin()[0] + self._pcw / 2.0
            self.video.create_line(cx, self.VPAD, cx, self.VPAD + self.VH, fill=C_SNAP,
                                   dash=(4, 3), tags="tf")
        self._show_poster(self.cur)        # кадр підтягнеться (дебаунс 110мс)

    def _video_release(self, ev):
        if not self._tf_drag:
            return
        mode, b = self._tf_drag
        self._tf_drag = None
        if not b["moved"]:
            if mode == "off":
                self._tf_on = False        # клік поза об'єктом -> сховати рамку
                self.video.delete("tf")
            return
        self._show_poster(self.cur)
        self._draw_tfbox()
        self._redraw()                     # оновити значок 🔍 на кліпі

    def _tf_reset(self):
        p = self._tf_target()
        if p["zoom"] != 1.0 or p["nx"] or p["ny"]:
            self._push_undo()
            p["zoom"], p["nx"] = 1.0, 0.0
            p["ny"] = 0.30 if "text" in p else 0.0
            self._show_poster(self.cur)
            self._draw_tfbox()
            self._redraw()

    def _is_transformed(self, p):
        return p["zoom"] != 1.0 or p["nx"] != 0.0 or p["ny"] != 0.0

    # ---- вибір об'єкта (кліп / накладка / текст / звук) ----
    def _sel_kind(self):
        if self.sel_txt is not None:
            return ("txt", self.sel_txt)
        if self.sel_ovl is not None:
            return ("ovl", self.sel_ovl)
        if self._sel_snd is not None:
            return ("snd", self._sel_snd)
        return None

    def _select(self, what):
        self.sel_ovl = None
        self.sel_txt = None
        self._sel_snd = None
        self.sel_txt = None
        self.sel_txt = None
        if what:
            kind, i = what
            if kind == "txt":
                self.sel_txt = i
            elif kind == "ovl":
                self.sel_ovl = i
                self.sel_txt = None
            elif kind == "snd":
                self._sel_snd = i
                self.sel_txt = None

    def _sel_key(self):
        k = self._sel_kind()
        try:
            if k:
                obj = {"txt": self.texts, "ovl": self.ovls, "snd": self.snds}[k[0]][k[1]]
                return (k[0], k[1], id(obj))
            if not self.order:
                return None
            return ("clip", self.sel, id(self._sel_piece()))
        except (IndexError, KeyError):
            return None

    def _prop_changed(self):
        """Змінили властивість у правій панелі -> прев'ю + доріжка (+ відтворення наживо)."""
        self._show_poster(self.cur)
        self._req_draw()
        self._replay_soon()

    def _replay_soon(self):
        """Якщо зараз грає — перезапускаємо ffplay з ТОГО Ж місця з новими налаштуваннями
        (з затримкою: поки тягнеш повзунок, не перезапускаємо на кожен піксель)."""
        if not self.playing:
            return
        if getattr(self, "_replay_after", None):
            try:
                self.after_cancel(self._replay_after)
            except Exception:
                pass
        self._replay_after = self.after(300, self._replay_now)

    def _replay_now(self):
        self._replay_after = None
        if not self.playing or self._closed or not self.order:
            return
        p = self._sel_piece()
        t = min(max(self.cur, p["s"]), p["e"] - 0.05)
        self._launch(t, p["e"] - t)

    def _look_target(self):
        if self.sel_ovl is not None and self.sel_ovl < len(self.ovls):
            return self.ovls[self.sel_ovl]
        return self._sel_piece()

    def _rotate(self):
        p = self._look_target()
        self._push_undo()
        p["rot"] = (int(fx.g(p, "rot")) + 90) % 360
        self._prop_changed()
        self._draw_tfbox()

    def _flip(self):
        p = self._look_target()
        self._push_undo()
        p["flip"] = not fx.g(p, "flip")
        self._prop_changed()

    def _reset_look(self):
        p = self._look_target()
        self._push_undo()
        for k in ("flt", "br", "ct", "sat", "rot", "flip"):
            p[k] = fx.PIECE_DEFAULTS[k]
        if self.sel_ovl is None:
            p["zoom"], p["nx"], p["ny"] = 1.0, 0.0, 0.0
        self._prop_changed()
        self._draw_tfbox()
        if self._insp:
            self._insp.sync(force=True)

    # ---- тексти (титри) ----
    def _add_text(self):
        if self.busy:
            return
        if self.playing:
            self._pause()
        self._push_undo()
        t = fx.new_text(self._playhead_montage_t(), E("ed_text_default"))
        self.texts.append(t)
        self._select(("txt", len(self.texts) - 1))
        self._tf_on = True
        self._show_poster(self.cur)
        self._redraw()
        self._toggle_insp(True)
        self.after(80, self._focus_text_box)

    def _toggle_insp(self, show=None):
        """Показати/сховати праву панель властивостей (кнопка ⚙). Плеєр займає звільнене місце."""
        show = (not self._insp_on) if show is None else bool(show)
        if show == self._insp_on:
            return
        self._insp_on = show
        try:
            if show:
                self._insp.pack(side="right", fill="y", padx=(0, 12), pady=8, before=self.video)
                self._insp.sync(force=True)
            else:
                self._insp.pack_forget()
                self.focus_set()
            self.b_insp.set_on(show)
            self.update_idletasks()
        except tk.TclError:
            return
        self._apply_resize()

    def _focus_text_box(self):
        if not self._insp_on:
            self._toggle_insp(True)
        b = getattr(self._insp, "text_box", None) if self._insp else None
        try:
            if b is not None and b.winfo_exists():
                b.focus_set()
                b.tag_add("sel", "1.0", "end-1c")
                b.mark_set("insert", "end-1c")
        except tk.TclError:
            pass

    def _txt_dup(self):
        i = self.sel_txt
        if i is None or i >= len(self.texts):
            return
        self._push_undo()
        t = dict(self.texts[i])
        t["at"] = t["at"] + t["dur"]
        self.texts.append(t)
        self._select(("txt", len(self.texts) - 1))
        self._redraw()

    def _txt_del(self):
        i = self.sel_txt
        if i is None or i >= len(self.texts):
            return
        self._push_undo()
        del self.texts[i]
        self._select(None)
        self._tf_on = False
        self.video.delete("tf")
        self._show_poster(self.cur)
        self._redraw()

    # -------------- ВБУДОВАНЕ ВІДТВОРЕННЯ ЗІ ЗВУКОМ (ffplay через SetParent) ---- #
    def _toggle_play(self):
        if self.playing:
            self._pause()
        else:
            p = self._sel_piece()
            if self.sel == len(self.order) - 1 and self.cur >= p["e"] - 0.06:
                self.sel = 0                  # стоїмо в самому кінці -> граємо з початку
                p = self._sel_piece()
                self.cur = p["s"]
                self._scroll = 0.0
            start = min(max(p["s"], self.cur), p["e"] - 0.05)
            self._launch(start, p["e"] - start)

    def _play_segment(self):
        p = self._sel_piece()
        self.cur = p["s"]
        self._launch(p["s"], p["e"] - p["s"])

    def _launch(self, start, dur):
        self._pause()
        piece = self._sel_piece()
        src = self._src(piece)
        self._tf_on = False
        self.video.delete("tf")
        self._play_kind = src["kind"]
        self._play_src_dur = src["dur"]
        start = max(0.0, min(self._play_src_dur, start))
        self._play_start = start
        self._play_end = min(piece["e"], start + dur) if dur else piece["e"]
        if src["kind"] == "image":
            # картинка: «граємо» по годиннику, без ffplay
            self.playing = True
            self._play_t0 = time.monotonic()
            self._ffplay = None
            self._set_play_icon(True)
            self._play_progress()
            return
        w, h = self.VW, self.VH          # ffplay = рівно екран плеєра (канвас ширший на поля)
        self._embed_title = f"dac_play_{os.getpid()}_{int(start * 1000)}"
        cmd = ["ffplay", "-hide_banner", "-loglevel", "error", "-stats", "-noborder", "-autoexit",
               "-left", "32000", "-top", "32000",   # спавн за межами екрана — без спалаху
               "-x", str(w), "-y", str(h), "-ss", f"{start:.3f}"]
        if dur is not None:
            cmd += ["-t", f"{max(0.1, dur):.3f}"]
        vf = af = None
        if not self._fx_broken:
            try:
                vf, af, _a_ok = self._play_graph(piece, start)
            except Exception as e:
                dc_core.dlog("PLAY graph EXCEPTION " + repr(e))
                vf = af = None
        self._play_fx = bool(vf)
        self._play_sp = piece["speed"] if vf else 1.0
        if vf:
            cmd += ["-vf", vf]
            if af and not self._rec:
                cmd += ["-af", af]
        if self._rec or (not vf and piece["mute"]):
            cmd += ["-an"]
        cmd += ["-window_title", self._embed_title, "-i", src["path"]]
        self._ffplay_pos = None
        self._stat_offset = None
        try:
            self._ffplay = subprocess.Popen(cmd, creationflags=dc_core.NO_WINDOW,
                                            stderr=subprocess.PIPE)
        except FileNotFoundError:
            self.info_lbl.config(text=E("ed_no_ffplay"), fg=C_RED)
            return
        self.playing = True
        self._embedded = None
        self._play_t0 = self._play_launch_t = time.monotonic()
        dc_core.dlog(f"PLAY launch build={dc_core.BUILD} src={piece['src']} start={start:.3f} "
                     f"dur={dur} t0={self._play_t0:.3f}")
        threading.Thread(target=self._read_ffplay_stats, args=(self._ffplay,), daemon=True).start()
        self._set_play_icon(True)
        self._embed_try(0)
        self._play_progress()

    def _read_ffplay_stats(self, proc):
        """Читаємо stderr ffplay і парсимо ЙОГО реальну позицію відтворення (перше число
        у рядку -stats). Рядки оновлюються через \\r."""
        buf = b""
        try:
            while True:
                ch = proc.stderr.read(1)
                if not ch:
                    break
                if ch in (b"\r", b"\n"):
                    line = buf.decode("utf-8", "ignore").strip(); buf = b""
                    if line:
                        self._parse_stat(line)
                else:
                    buf += ch
        except Exception:
            pass

    def _parse_stat(self, line):
        try:
            v = float(line.split()[0])
        except (ValueError, IndexError):
            return
        if v != v or v < 0 or v > self._play_src_dur * 4 + 5:   # nan/сміття -> пропуск
            return
        if self._play_fx:                 # граф нормалізує час (PTS-STARTPTS)/speed
            self._ffplay_pos = self._play_start + v * self._play_sp
        else:
            if self._stat_offset is None:
                self._stat_offset = 0.0 if abs(v - self._play_start) < abs(v) else self._play_start
            self._ffplay_pos = self._stat_offset + v
        now = time.monotonic()
        if now - self._stat_log_t > 0.4:
            self._stat_log_t = now
            dc_core.dlog(f"  ffplay_pos={self._ffplay_pos:.3f} (raw={v:.3f})")

    def _embed_try(self, n):
        """Знаходимо вікно ffplay за заголовком і вклеюємо його в наш відео-екран."""
        if not self.playing or self._embedded:
            return
        try:
            hwnd = _u32.FindWindowW(None, self._embed_title)
            if hwnd:
                parent = self.video.winfo_id()
                _SetWinLong(hwnd, _GWL_STYLE, _WS_CHILD | _WS_VISIBLE)
                _u32.SetParent(hwnd, parent)
                _u32.MoveWindow(hwnd, self.VPAD, self.VPAD, self.VW, self.VH, True)
                self._embedded = hwnd
                # РЕСИНХ запасного годинника на момент появи вікна ffplay.
                self._play_t0 = time.monotonic()
                dc_core.dlog(f"EMBED ok n={n} ffplay_pos={self._ffplay_pos}")
                return
        except Exception:
            pass
        if n < 80:  # ffplay може створювати вікно кілька сотень мс
            self.after(50, lambda: self._embed_try(n + 1))

    def _play_progress(self):
        """Рухаємо playhead. Пріоритет — РЕАЛЬНА позиція ffplay (-stats); wall-clock запас."""
        if not self.playing:
            return
        if self._play_kind == "image":
            pos = self._play_start + (time.monotonic() - self._play_t0)
        else:
            p = getattr(self, "_ffplay", None)
            if p is not None and p.poll() is not None and self._play_fx \
                    and self._ffplay_pos is None and time.monotonic() - self._play_launch_t < 2.0:
                dc_core.dlog("PLAY: ffplay rejected the filter graph -> plain playback")
                self._fx_broken = True             # запасний план: граємо без ефектів
                return self._launch(self._play_start, self._play_end - self._play_start)
            if p is None or p.poll() is not None:
                return self._advance_or_stop()          # ffplay дограв кліп сам (-autoexit)
            if self._ffplay_pos is not None:
                pos = self._ffplay_pos
            else:
                pos = self._play_start + (time.monotonic() - self._play_t0) * self._play_sp
        if pos >= self._play_end - 0.02:
            return self._advance_or_stop()
        self.cur = min(self._play_src_dur, pos)
        self._follow_playhead()
        self._draw_track()
        self._tick_id = self.after(80, self._play_progress)

    def _advance_or_stop(self):
        """Кінець кліпа: авто-перехід на наступний (щоб переглянути ВЕСЬ монтаж) або стоп."""
        if self.sel + 1 < len(self.order):
            self.sel += 1
            p = self._sel_piece()
            self.cur = p["s"]
            self._redraw()
            self._launch(p["s"], p["e"] - p["s"])
        else:
            self._pause()

    def _pause(self):
        if self.playing:
            dc_core.dlog(f"PAUSE cur={self.cur:.3f} ffplay_pos={self._ffplay_pos}")
        self.playing = False
        p = getattr(self, "_ffplay", None)
        if p is not None and p.poll() is None:
            try: p.terminate()
            except Exception: pass
        self._ffplay = None
        self._embedded = None
        if self._tick_id:
            try: self.after_cancel(self._tick_id)
            except Exception: pass
            self._tick_id = None
        if self._closed:
            return
        self._set_play_icon(False)
        self._show_poster(self.cur)   # повертаємо статичний кадр на екран

    def _seek(self, t):
        if self.playing:
            self._pause()
        t = max(0, min(self._src(self._sel_piece())["dur"], t))
        self.cur = t
        self._show_poster(t)
        self._redraw()

    def _to_start(self):
        if self.playing:
            self._pause()
        self._set_playhead_lt(0.0, fast=False)
        self._scroll = 0.0
        self._req_draw()

    # --------------------------------------------------------- ножиці ------ #
    def _cut_here(self):
        if self.playing:
            self._pause()          # ріжемо рівно по кадру, який ВИДНО
        if self._sel_snd is not None and self._sel_snd < len(self.snds):
            return self._cut_snd(self._sel_snd, self._playhead_montage_t())
        self._cut_at(self.cur)

    def _snd_cuttable(self, i, lt):
        sn = self.snds[i]
        return sn["at"] + 0.05 < lt < sn["at"] + sn["dur"] - 0.05

    def _cut_snd(self, i, lt):
        """Розрізає звук на два шматки по повзунку (зайвий потім — Delete)."""
        if not (0 <= i < len(self.snds)) or not self._snd_cuttable(i, lt):
            return
        self._push_undo()
        sn = self.snds[i]
        off = lt - sn["at"]
        right = dict(sn)
        right["s"] = float(sn.get("s", 0.0)) + off
        right["at"] = lt
        right["dur"] = sn["dur"] - off
        right.setdefault("fdur", float(sn.get("s", 0.0)) + sn["dur"])
        sn["dur"] = off
        sn.setdefault("fdur", right["fdur"])
        self.snds.insert(i + 1, right)
        self._select(("snd", i + 1))
        self._redraw()

    def _cut_at(self, t):
        slot = self.sel
        p = self.pieces[self.order[slot]]
        eps = 0.04
        if not (p["s"] + eps < t < p["e"] - eps):
            dc_core.dlog(f"CUT_AT t={t:.3f} skipped (поза кліпом)")
            return
        self._push_undo()
        right = dict(p)
        right["s"] = t
        right["gap"] = 0.0            # права половина йде впритул до лівої
        p["e"] = t
        self.pieces.append(right)
        self.order.insert(slot + 1, len(self.pieces) - 1)
        self.sel = slot
        dc_core.dlog(f"CUT_AT t={t:.3f} pieces={len(self.pieces)}")
        self._redraw()

    def _move(self, d):
        j = self.sel + d
        if 0 <= j < len(self.order):
            self._push_undo()
            self.order[self.sel], self.order[j] = self.order[j], self.order[self.sel]
            self.sel = j
            self._redraw()

    def _remove(self):
        if len(self.order) > 1 and not self.busy:
            self._push_undo()
            del self.order[self.sel]
            self.sel = min(self.sel, len(self.order) - 1)
            p = self._sel_piece()
            self.cur = min(max(self.cur, p["s"]), p["e"])
            self._show_poster(self.cur)
            self._redraw()

    def _duplicate(self):
        self._push_undo()
        p = dict(self._sel_piece())
        p["gap"] = 0.0
        self.pieces.append(p)
        self.order.insert(self.sel + 1, len(self.pieces) - 1)
        self._redraw()

    def _set_speed(self, sp, undo=True):
        p = self._sel_piece()
        if p["speed"] != sp:
            if undo:
                self._push_undo()
            p["speed"] = sp
            self._redraw()
            self._replay_soon()

    def _toggle_mute(self):
        p = self._sel_piece()
        src = self._src(p)
        if src["kind"] != "video" or not src["has_audio"]:
            return
        self._push_undo()
        p["mute"] = not p["mute"]
        self._redraw()
        self._replay_soon()

    def _toggle_novideo(self):
        """Прибрати картинку кліпа (лишається лише звук — у відео чорний кадр) або повернути."""
        p = self._sel_piece()
        if self._src(p)["kind"] != "video":
            return
        self._push_undo()
        p["novideo"] = not fx.g(p, "novideo")
        self._prop_changed()
        self._redraw()
        if self._insp:
            self._insp.sync(force=True)

    def _gap_remove(self):
        self._push_undo()
        self._sel_piece()["gap"] = 0.0
        self._redraw()

    def _gaps_remove_all(self):
        self._push_undo()
        for ix in self.order:
            self.pieces[ix]["gap"] = 0.0
        self._redraw()

    # ------------------------------------------------ скасувати / повторити --- #
    def _snapshot(self):
        return ([dict(p) for p in self.pieces], list(self.order), self.sel,
                [dict(s) for s in self.snds], [dict(o) for o in self.ovls],
                [dict(t) for t in self.texts], (self._ratio, self._bgmode))

    def _push_undo(self):
        self._undo.append(self._snapshot())
        if len(self._undo) > 80:
            self._undo.pop(0)
        self._redo.clear()

    def _apply_state(self, st):
        pieces, order, sel, snds, ovls = st[:5]
        self.texts = [dict(t) for t in (st[5] if len(st) > 5 else [])]
        if len(st) > 6 and tuple(st[6]) != (self._ratio, self._bgmode):
            self._ratio, self._bgmode = st[6]
            self._apply_canvas()
        self.pieces = [dict(p) for p in pieces]
        self.order = list(order)
        self.snds = [dict(s) for s in snds]
        self.ovls = [dict(o) for o in ovls]
        self.sel_ovl = None
        self.sel_txt = None
        self._sel_snd = None
        self.sel_txt = None
        self.sel = min(sel, len(self.order) - 1) if self.order else 0
        p = self._sel_piece()
        self.cur = min(max(self.cur, p["s"]), p["e"])

    def _undo_action(self):
        if not self._undo:
            return
        self._pause()
        self._redo.append(self._snapshot())
        self._apply_state(self._undo.pop())
        self._show_poster(self.cur); self._redraw()

    def _redo_action(self):
        if not self._redo:
            return
        self._pause()
        self._undo.append(self._snapshot())
        self._apply_state(self._redo.pop())
        self._show_poster(self.cur); self._redraw()

    # --------------------------------------------------------- малювання --- #
    def _redraw(self):
        self._draw_track()
        self._update_info()

    def _req_draw(self):
        """Перемальовка доріжки максимум раз за «кадр» — для плавних перетягувань."""
        if self._draw_after:
            return

        def run():
            self._draw_after = None
            if not self._closed:
                try:
                    self._draw_track()
                except tk.TclError:
                    pass
        try:
            self._draw_after = self.after_idle(run)
        except tk.TclError:
            self._draw_after = None

    # старі імена: звуки й накладки тепер на тому ж канвасі, що й кліпи
    def _draw_wave(self):
        self._req_draw()

    def _draw_ovl(self):
        self._req_draw()

    # ---- кіно-стрічка + хвиля: генеруються ОКРЕМО для кожного джерела ----
    def _gen_visuals(self, si):
        src = self.sources[si]
        if src["kind"] == "image":
            tw = THUMB_W
            if src["w"] and src["h"]:
                tw = max(24, min(140, int(round(THUMB_H * src["w"] / float(src["h"]) / 2)) * 2))
            p = os.path.join(self._tmp, f"s{si}_img.png")

            def work_img():
                try:
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", src["path"], "-frames:v", "1", "-vf",
                         f"scale={tw}:{THUMB_H}:force_original_aspect_ratio=increase,"
                         f"crop={tw}:{THUMB_H}", p],
                        capture_output=True, creationflags=dc_core.BG)
                except Exception:
                    pass
                self._ui(lambda: self._load_strip(si, [p], [0.0]))
            threading.Thread(target=work_img, daemon=True).start()
            return

        def work():
            # два проходи: спершу 8 кадрів (стрічка з'являється майже одразу), потім 24 детальніше
            done = []

            def batch(ts, tag):
                for k, t in enumerate(ts):
                    if self._closed:
                        return
                    pth = os.path.join(self._tmp, f"s{si}_{tag}_{k:02d}.png")
                    try:
                        subprocess.run(
                            ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", src["path"],
                             "-frames:v", "1", "-vf", f"scale=-2:{THUMB_H}", pth],
                            capture_output=True, creationflags=dc_core.BG)
                    except Exception:
                        continue
                    if os.path.exists(pth):
                        done.append((t, pth))
                items = sorted(done)
                self._ui(lambda: self._load_strip(si, [q for _, q in items],
                                                  [t for t, _ in items]))
            d = src["dur"]
            batch([(i + 0.5) / 8 * d for i in range(8)], "a")
            if not self._closed:          # один прохід: кадри скрабу + детальна стрічка
                self._gen_scrub(si)
        threading.Thread(target=work, daemon=True).start()

        if src["has_audio"]:
            def work_env():
                env = dc_core.audio_envelope(src["path"], hz=100)
                if env:
                    def apply():
                        src["env"] = env
                        self._req_draw()
                    self._ui(apply)
            threading.Thread(target=work_env, daemon=True).start()

    def _gen_scrub(self, si):
        """Кадри для ЖИВОГО перемотування: один прохід ffmpeg (fps-фільтр) у фоні.
        Поки тягнеш повзунок — показуємо найближчий з них миттєво, точний кадр
        підставляється, щойно ffmpeg його відрендерить."""
        src = self.sources[si]
        d = max(0.1, src["dur"])
        rate = max(0.25, min(4.0, 160.0 / d))
        pat = os.path.join(self._tmp, f"s{si}_sc_%04d.png")
        try:
            # лише КЛЮЧОВІ кадри (-skip_frame nokey): для перемотування вистачає, а декодувати
            # треба в десятки разів менше; фоновий пріоритет — не гальмує решту програми
            subprocess.run(["ffmpeg", "-y", "-threads", "2", "-skip_frame", "nokey", "-i", src["path"],
                            "-an", "-sn", "-vf", f"fps={rate:g},scale=-2:{SCRUB_H}",
                            "-start_number", "0", pat],
                           capture_output=True, creationflags=dc_core.BG)
        except Exception:
            return
        paths = []
        k = 0
        while True:
            q = pat % k
            if not os.path.exists(q):
                break
            paths.append(q)
            k += 1
        if paths:
            self._ui(lambda: self._apply_scrub(si, rate, paths))

    def _apply_scrub(self, si, rate, paths):
        """Кеш скрабу готовий -> з нього ж детальна кіно-стрічка (кадри /4 = висота стрічки)."""
        src = self.sources[si]
        src["scrub"] = (rate, paths)
        n = min(len(paths), 48)
        idx = sorted({int(round(i * (len(paths) - 1) / max(1, n - 1))) for i in range(n)})
        imgs, ts = [], []
        k = max(1, SCRUB_H // THUMB_H)
        for i in idx:
            try:
                im = tk.PhotoImage(file=paths[i])
                imgs.append(im.subsample(k) if k > 1 else im)
                ts.append(i / rate)
            except tk.TclError:
                continue
        if imgs:
            src["strip"], src["times"] = imgs, ts
            src["tw"] = max(16, min(220, imgs[0].width()))
            self._req_draw()

    def _quick_frame(self, t):
        """Миттєвий кадр із кешу скрабу (без ffmpeg). False — кешу ще нема."""
        p = self._sel_piece()
        src = self._src(p)
        sc = src.get("scrub")
        if (not sc or src["kind"] != "video" or self.playing or self._is_transformed(p)
                or not fx.look_default(p) or self._bgmode == "blur" or fx.g(p, "novideo")):
            return False
        mt = self._playhead_montage_t()
        if self._active_texts(mt) or any(o["at"] <= mt <= o["at"] + o["e"] - o["s"] for o in self.ovls):
            return False
        rate, paths = sc
        k = min(len(paths) - 1, max(0, int(round(t * rate))))
        key = (p["src"], k, self._pcw, self._pch)
        im = self._qcache.pop(key, None)
        if im is None:
            try:
                base = tk.PhotoImage(file=paths[k])
            except tk.TclError:
                return False
            r = min(self._pcw / float(max(1, base.width())), self._pch / float(max(1, base.height())))
            best, err = (1, 1), 9.0
            for b in (1, 2):
                a = max(1, int(r * b + 1e-6))
                e = r - a / float(b)
                if -1e-6 <= e < err:
                    best, err = (a, b), e
            a, b = best
            im = base
            if a > 1:
                im = im.zoom(a)
            if b > 1:
                im = im.subsample(b)
        self._qcache[key] = im                 # LRU: свіжий — у кінець
        while len(self._qcache) > 48:
            self._qcache.pop(next(iter(self._qcache)))
        try:
            self._img = im
            self.video.delete("frame")
            self.video.create_image(self.VPAD + self.VW // 2, self.VPAD + self.VH // 2,
                                    image=im, tags="frame")
            self.video.tag_lower("frame")
            self.video.tag_lower("screen")
            self.video.tag_lower("card")
        except tk.TclError:
            return False
        return True

    def _load_strip(self, si, paths, times):
        imgs, ts = [], []
        for p, t in zip(paths, times):
            try:
                im = tk.PhotoImage(file=p)
            except tk.TclError:
                continue
            imgs.append(im)
            ts.append(t)
        if imgs:
            src = self.sources[si]
            src["strip"], src["times"] = imgs, ts
            src["tw"] = max(16, min(220, imgs[0].width()))
            self._req_draw()

    def _nearest_thumb(self, src, t):
        ts, imgs = src.get("times"), src.get("strip")
        if not ts or not imgs:
            return None
        i = min(range(len(ts)), key=lambda k: abs(ts[k] - t))
        return imgs[i % len(imgs)]

    def _draw_clip_strip(self, c, cx1, cx2, piece, y0, fit=False):
        """Кадри кіно-стрічки в кліпі (лише видима частина). Кадр, що вилазить
        за правий край, накривається маскою з _draw_clips."""
        src = self._src(piece)
        if not src.get("strip"):
            return
        tw = src.get("tw") or THUMB_W
        width = cx2 - cx1
        if width <= 2:
            return
        s, e = piece["s"], piece["e"]
        j = max(0, int((LX - cx1) // tw))
        n = 0
        while n < 400:
            xx = cx1 + j * tw
            if xx >= cx2 or xx > self.TW:
                break
            if fit and xx + tw > cx2:
                break
            t = s + min(1.0, (j * tw + tw / 2.0) / width) * (e - s)
            im = self._nearest_thumb(src, t)
            if im:
                c.create_image(int(xx), y0 + 3, image=im, anchor="nw")
            j += 1
            n += 1

    def _draw_handle(self, c, x, left, active, y1, y2):
        w = 11 if active else 9
        x1, x2 = (x, x + w) if left else (x - w, x)
        c.create_polygon(host._rr_pts(x1, y1, x2, y2, 4), smooth=True, fill=C_HANDLE, outline="")
        cx = (x1 + x2) / 2
        c.create_line(cx, y1 + (y2 - y1) * 0.32, cx, y1 + (y2 - y1) * 0.68, fill="#1e1f22", width=2)

    # ---- час доріжки <-> пікселі ----
    def _clip_durs(self):
        return [(self.pieces[ix]["e"] - self.pieces[ix]["s"]) / self.pieces[ix]["speed"]
                for ix in self.order]

    def _total(self):
        # тривалість ЕКСПОРТУ: без пропусків, мінус перекриття переходів
        return max(0.1, sum(self._clip_durs()) - sum(self._tr_d(k) for k in range(len(self.order))))

    def _tr_d(self, slot):
        """Реальна тривалість переходу В кліп slot (не більше половини сусідніх кліпів)."""
        if slot <= 0 or slot >= len(self.order):
            return 0.0
        p = self.pieces[self.order[slot]]
        tr = p.get("tr")
        if not tr:
            return 0.0
        q = self.pieces[self.order[slot - 1]]
        dp = (q["e"] - q["s"]) / q["speed"]
        dc = (p["e"] - p["s"]) / p["speed"]
        return max(0.0, min(float(tr.get("d", 0.5)), dp * 0.5, dc * 0.5))

    def _layout_total(self):
        """Тривалість доріжки ЯК ВИДНО (з порожніми місцями)."""
        return max(0.1, sum(self._gapof(self.pieces[ix]) for ix in self.order)
                   + sum(self._clip_durs()))

    def _layout_end_all(self):
        """Кінець УСЬОГО на таймлайні (кліпи, накладки, звуки) — до нього можна прокрутити."""
        t = self._layout_total()
        for o in self.ovls:
            t = max(t, o["at"] + (o["e"] - o["s"]))
        for s in self.snds:
            t = max(t, s["at"] + s["dur"])
        for x in self.texts:
            t = max(t, x["at"] + x["dur"])
        return t

    def _gapless(self, t):
        """Час доріжки (з пропусками) -> час ЕКСПОРТУ (пропуски стиснуто).
        Так звуки/накладки лягають у готовому відео саме туди, де їх видно."""
        acc = out = 0.0
        for k, ix in enumerate(self.order):
            p = self.pieces[ix]
            g = self._gapof(p)
            d = (p["e"] - p["s"]) / p["speed"]
            out -= self._tr_d(k)               # перехід: кліп починається раніше
            if t <= acc + g:
                return max(0.0, out)           # у порожньому місці -> початок кліпа
            acc += g
            if t <= acc + d:
                return max(0.0, out + (t - acc))
            acc += d
            out += d
        return max(0.0, out)

    def _pps(self):
        # px/сек: база (перше відео рівно по ширині) × зум. Обрізаєш кліп -> він
        # КОРОТШАЄ, а не тягнеться на всю доріжку (як у CapCut).
        return self._base_pps * self._zoom

    def _content_width(self, pps):
        return PAD_L + self._layout_end_all() * pps + 160

    def _x_of(self, lt):
        """Час доріжки -> x на канвасі."""
        return LX + PAD_L + lt * self._pps() - self._scroll

    def _lt_of(self, x):
        """x на канвасі -> час доріжки."""
        return (x - LX - PAD_L + self._scroll) / max(1e-6, self._pps())

    def _content_x_of(self, layout_t, pps):
        return PAD_L + layout_t * pps

    def _playhead_montage_t(self):
        acc = 0.0
        for slot in range(len(self.order)):
            p = self.pieces[self.order[slot]]
            acc += self._gapof(p)
            if slot == self.sel:
                return acc + (min(max(self.cur, p["s"]), p["e"]) - p["s"]) / p["speed"]
            acc += (p["e"] - p["s"]) / p["speed"]
        return acc

    def _locate(self, lt):
        """Час доріжки -> (кліп, час у його джерелі). На стику — наступний кліп."""
        n = len(self.order)
        acc = 0.0
        for slot in range(n):
            p = self.pieces[self.order[slot]]
            g = self._gapof(p)
            d = (p["e"] - p["s"]) / p["speed"]
            if lt < acc + g:
                return slot, p["s"]
            acc += g
            if lt < acc + d or slot == n - 1:
                t = p["s"] + max(0.0, lt - acc) * p["speed"]
                return slot, min(max(p["s"], t), p["e"])
            acc += d
        return max(0, n - 1), self._sel_piece()["e"]

    def _clip_edges(self):
        pts, lt = [0.0], 0.0
        for ix in self.order:
            p = self.pieces[ix]
            lt += self._gapof(p)
            pts.append(lt)
            lt += (p["e"] - p["s"]) / p["speed"]
            pts.append(lt)
        return pts

    def _set_playhead_lt(self, lt, fast=True):
        """Ставить ГЛОБАЛЬНИЙ плейхед: вибирає кліп під ним і час у джерелі."""
        if not self.order:
            return
        slot, t = self._locate(max(0.0, lt))
        if slot != self.sel:
            self.sel = slot
            self._tf_on = False
            try:
                self.video.delete("tf")
            except tk.TclError:
                pass
        self.cur = t
        self._show_poster(t, fast=fast)
        self._req_draw()

    def _clamp_scroll(self, pps):
        vis = max(10, self.TW - LX)
        self._scroll = max(0.0, min(self._scroll, max(0.0, self._content_width(pps) - vis)))

    # ---- зум: Ctrl+колесо — ДО КУРСОРА миші; кнопки/клавіші — до плейхеда ----
    def _zoom_at(self, factor, sx=None):
        if sx is None:
            px = self._x_of(self._playhead_montage_t())
            sx = px if LX <= px <= self.TW else (LX + self.TW) / 2.0
        lt = self._lt_of(sx)                       # час під точкою зуму лишається НА МІСЦІ
        self._zoom = min(ZMAX, max(ZMIN, self._zoom * factor))
        new = self._pps()
        self._scroll = PAD_L + lt * new - (sx - LX)
        self._clamp_scroll(new)
        self._draw_track()
        try:
            self.zoom_sl.redraw()
        except (tk.TclError, AttributeError):
            pass

    def _set_zoom(self, z):
        self._zoom_at(z / max(1e-6, self._zoom))

    def _zoom_fit(self):
        vis = max(50, self.TW - LX - PAD_L - 40)
        self._zoom = min(ZMAX, max(ZMIN, vis / max(0.1, self._layout_end_all()) / self._base_pps))
        self._scroll = 0.0
        self._draw_track()
        try:
            self.zoom_sl.redraw()
        except (tk.TclError, AttributeError):
            pass

    def _zoom_step(self, factor):
        self._zoom_at(factor)

    def _on_tl_config(self, ev):
        w = int(ev.width)
        if w < 80:
            return
        first = not self._fit_done
        self.TW = w
        if first:
            self._fit_done = True
            self._zoom_fit()
            return
        self._clamp_scroll(self._pps())
        self._req_draw()

    def _on_wheel(self, ev):
        if ev.state & 0x4:                          # Ctrl -> зум до курсора
            self._zoom_at(1.2 ** (ev.delta / 120.0), max(LX, ev.x))
            return "break"
        self._scroll -= (ev.delta / 120.0) * 90     # колесо / Shift+колесо -> прокрутка
        self._clamp_scroll(self._pps())
        self._draw_track()
        return "break"

    # ---- точне підлаштування обрізки стрілками (по кадру) + час-підказка ----
    def _fmt_tt(self, t):
        t = max(0.0, t); m = int(t // 60)
        return f"{m}:{t - m * 60:04.1f}"

    @staticmethod
    def _fmt_tc(t):
        t = max(0.0, t); m = int(t // 60)
        return f"{m:02d}:{t - m * 60:05.2f}"

    def _nudge(self, direction, big=False):
        if self.busy:
            return "break"
        if self.playing:
            self._pause()
        p = self._sel_piece()
        src = self._src(p)
        fps = src["fps"] if src["kind"] == "video" else 30.0
        step = 1.0 if big else 1.0 / fps
        eps = 1.0 / fps
        lo, hi = 0.0, src["dur"]
        if self._active in ("L", "R") and self.sel_ovl is None and self._sel_snd is None:
            if not self._nudge_active:      # уся серія стрілок = один крок undo
                self._push_undo(); self._nudge_active = True
            if self._active == "L":
                ns = min(max(lo, p["s"] + direction * step), p["e"] - eps)
                p["gap"] = max(0.0, self._gapof(p) + (ns - p["s"]) / p["speed"])
                p["s"] = ns; self.cur = self._tip_t = ns
            else:
                ne = max(min(hi, p["e"] + direction * step), p["s"] + eps)
                p["e"] = ne; self.cur = self._tip_t = ne
            self._show_poster(self.cur)
            self._redraw()
        else:                               # нема активної ручки -> плейхед (через кліпи)
            lt = self._playhead_montage_t() + direction * step / p["speed"]
            self._set_playhead_lt(min(self._layout_total(), max(0.0, lt)), fast=False)
            self._tip_t = None
        self._schedule_tip_clear()
        return "break"

    def _schedule_tip_clear(self):
        if self._tip_after:
            try: self.after_cancel(self._tip_after)
            except Exception: pass
        self._tip_after = self.after(1500, self._clear_tip)

    def _clear_tip(self):
        self._tip_t = None; self._nudge_active = False; self._tip_after = None
        try: self._redraw()
        except Exception: pass

    def _to_end(self):
        self._set_playhead_lt(self._layout_total(), fast=False)

    def _follow_playhead(self):
        """Під час відтворення доріжка сама їде за плейхедом (як у CapCut)."""
        x = self._x_of(self._playhead_montage_t())
        if x > self.TW - 30 or x < LX:
            self._scroll += x - (LX + (self.TW - LX) * 0.15)
            self._clamp_scroll(self._pps())

    # ------------------------------------------------- малювання таймлайна --- #
    def _draw_track(self):
        c = self.tl
        try:
            c.delete("all")
        except tk.TclError:
            return
        W = self.TW
        pps = self._pps()
        self._clamp_scroll(pps)
        c.create_rectangle(0, 0, W, TL_TOTAL_H, fill=C_TRACK, outline="")
        for y, h in ((TXT_Y, TXT_H), (OVL_Y, OVL_H), (TL_Y, TLH), (SND_Y, SND_H)):
            c.create_rectangle(LX, y, W, y + h, fill=C_LANE, outline="")
        self._draw_ruler(c, W, pps)
        self._draw_clips(c, W, pps)
        self._draw_ovl_lane(c, W, pps)
        self._draw_txt_lane(c, W, pps)
        self._draw_snd_lane(c, W, pps)
        self._draw_drag_ghost(c, W)
        if self._snap_lt is not None:              # жовта лінія «магніту»
            sx = self._x_of(self._snap_lt)
            if LX <= sx <= W:
                c.create_line(sx, RUL_H, sx, SB_Y - 4, fill=C_SNAP, width=1, dash=(4, 3))
        if self._tip_t is not None and self._sel_xs is not None:
            tx = (self._sel_xe if self._active == "R"
                  else self._sel_xs if self._active == "L" else self._playhead_x)
            tx = min(max(LX + 32, tx), W - 32)
            c.create_rectangle(tx - 30, TL_Y - 19, tx + 30, TL_Y - 3, fill=C_DARK, outline=C_PLAY)
            c.create_text(tx, TL_Y - 11, text=self._fmt_tt(self._tip_t), fill="#ffffff",
                          font=(FONT, 8, "bold"))
        self._draw_gutter(c)
        self._draw_playhead(c, W)
        self._draw_scrollbar(c, W, pps)
        try:
            self.time_lbl.config(text=f"{self._fmt_tc(self._playhead_montage_t())}"
                                      f"  /  {self._fmt_tc(self._layout_total())}")
        except (tk.TclError, AttributeError):
            pass
        self._update_tools()
        if self._insp:
            self._insp.sync()

    def _draw_ruler(self, c, W, pps):
        c.create_rectangle(LX, 0, W, RUL_H, fill=C_RULER, outline="")
        major = 600.0
        for st in (0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600):
            if st * pps >= 70:
                major = float(st)
                break
        minor = major / 5.0 if major * pps / 5.0 >= 9 else major / 2.0
        t0 = max(0.0, self._lt_of(LX))
        t1 = self._lt_of(W)
        i = int(t0 // minor)
        n = 0
        while n < 600:
            t = i * minor
            if t > t1:
                break
            x = self._x_of(t)
            if x >= LX:
                q = t / major
                if abs(q - round(q)) < 1e-6:
                    c.create_line(x, RUL_H - 10, x, RUL_H, fill=C_MUTED)
                    m = int(round(t) // 60) if major >= 1 else int(t // 60)
                    if major >= 1:
                        lab = f"{m:02d}:{int(round(t)) - m * 60:02d}"
                    else:
                        lab = f"{m:02d}:{t - m * 60:04.1f}"
                    c.create_text(x + 4, 9, text=lab, anchor="w", fill=C_MUTED, font=(FONT, 8))
                else:
                    c.create_line(x, RUL_H - 4, x, RUL_H, fill="#4a4d57")
            i += 1
            n += 1
        c.create_line(LX, RUL_H - 0.5, W, RUL_H - 0.5, fill="#2a2c33")

    def _draw_clips(self, c, W, pps):
        self._clip_rects = []
        self._sel_xs = self._sel_xe = None
        y1, y2 = TL_Y, TL_Y + TLH
        drag = self._clip_drag if (self._clip_drag and self._clip_drag["active"]) else None
        focus_clip = self.sel_ovl is None and self._sel_snd is None and self.sel_txt is None
        lt = 0.0
        for slot, ix in enumerate(self.order):
            p = self.pieces[ix]
            s, e = p["s"], p["e"]
            g = self._gapof(p)
            d = (e - s) / p["speed"]
            # порожнє місце перед кліпом: лишається на доріжці (зникне при збереженні)
            if g * pps > 0.5:
                gx1, gx2 = self._x_of(lt), self._x_of(lt + g)
                if gx2 > LX and gx1 < W:
                    c.create_rectangle(gx1, y1 + 3, gx2, y2 - 3, fill="#101116", outline="")
                    c.create_rectangle(gx1, y1 + 3, gx2, y2 - 3, fill=C_CLIP,
                                       stipple="gray12", outline="")
                    if gx2 - gx1 > 76:
                        c.create_text((max(gx1, LX) + gx2) / 2, (y1 + y2) / 2, text=E("ed_empty"),
                                      fill=C_MUTED, font=(FONT, 8))
            lt += g
            cx1, cx2 = self._x_of(lt), self._x_of(lt + d)
            if cx2 - cx1 < 6:
                cx2 = cx1 + 6
            lt += d
            self._clip_rects.append((slot, ix, cx1, cx2))
            sel = slot == self.sel and focus_clip
            if sel:
                self._sel_xs, self._sel_xe = cx1, cx2
            if cx2 < LX - 12 or cx1 > W + 12:
                continue
            if drag and drag["slot"] == slot:      # місце, звідки тягнемо кліп
                c.create_rectangle(cx1 + 1, y1 + 2, cx2 - 1, y2 - 2, outline=C_MUTED,
                                   dash=(4, 3), width=1)
                continue
            hv = self._hover == ("clip", slot)
            c.create_rectangle(cx1 + 1, y1, cx2 - 1, y2, fill=C_CLIP, outline="")
            if fx.g(p, "novideo"):          # «тільки звук»: замість кадрів — темна смуга
                c.create_rectangle(cx1 + 1, y1, cx2 - 1, y2, fill="#16171b", outline="")
                if cx2 - cx1 > 60:
                    self._block_label(c, cx1, cx2, W, (y1 + y2) / 2 - 8, "🎵 " + E("ed_audio_only"), C_MUTED)
            else:
                self._draw_clip_strip(c, cx1 + 1, cx2 - 1, p, y1)
            # маска: кадр, що вилазить за кліп, накриваємо (наступний кліп ляже зверху)
            c.create_rectangle(cx2 - 1, y1, cx2 + 230, y2, fill=C_LANE, outline="")
            # хвиля звуку прямо НА вибраному кліпі (внизу, як у CapCut)
            env = self._src(p).get("env")
            if sel and env and not p["mute"]:
                by = y2 - 4
                span = max(0.001, e - s)
                xx = max(float(LX), cx1 + 1)
                end = min(float(W), cx2 - 1)
                c.create_rectangle(max(LX, cx1 + 1), y2 - 22, min(W, cx2 - 1), y2, fill="#000000",
                                   stipple="gray50", outline="")
                while xx < end:
                    a = self._env_at(env, s + (xx - cx1) / max(1.0, cx2 - cx1) * span)
                    c.create_line(xx, by - max(0.6, a * 17), xx, by, fill=C_WAVE_IN, width=1)
                    xx += 2
            if sel:
                c.create_rectangle(cx1 + 1, y1 + 1, cx2 - 1, y2 - 1, outline=C_HANDLE, width=2)
            elif hv:
                c.create_rectangle(cx1 + 1, y1, cx2 - 1, y2, outline="#8a8f9c", width=1)
            else:
                c.create_rectangle(cx1 + 1, y1, cx2 - 1, y2, outline="#0d0e11", width=1)
            # ярлик: тривалість + значки (швидкість / без звуку / масштаб / картинка)
            if cx2 - cx1 > 34 and cx2 > LX + 20:
                lab = f"{d:.1f}s"
                if p["speed"] != 1.0:
                    lab += f"  {p['speed']:g}×"
                if p["mute"]:
                    lab += "  🔇"
                if self._is_transformed(p):
                    lab += "  🔍"
                if not fx.look_default(p):
                    lab += "  🎨"
                if fx.g(p, "fin") > 0.01 or fx.g(p, "fout") > 0.01:
                    lab += "  ◐"
                if not fx.afx_default(p):
                    lab += "  🎛"
                if self._src(p)["kind"] == "image":
                    lab = "🖼 " + lab
                tx = max(cx1 + (14 if sel else 6), LX + 6)
                tid = c.create_text(tx + 3, y1 + 11, anchor="w", text=lab, fill="#ffffff",
                                    font=(FONT, 8, "bold"))
                bb = c.bbox(tid)
                if bb and bb[2] < cx2 - 4:
                    r = c.create_rectangle(bb[0] - 4, bb[1] - 1, bb[2] + 4, bb[3] + 1,
                                           fill="#000000", stipple="gray50", outline="")
                    c.tag_lower(r, tid)
                elif bb:
                    c.delete(tid)
            if sel:
                self._draw_handle(c, cx1 + 1, True, self._active == "L", y1, y2)
                self._draw_handle(c, cx2 - 1, False, self._active == "R", y1, y2)
        # стики кліпів: іконка переходу (клік -> вибрати перехід)
        self._junc = []
        cy = (y1 + y2) / 2.0
        for k in range(1, len(self._clip_rects)):
            slot, ix, cx1, cx2 = self._clip_rects[k]
            pcx1, pcx2 = self._clip_rects[k - 1][2:]
            if cx1 < LX + 8 or cx1 > W - 8 or (drag and drag["slot"] in (slot, slot - 1)):
                continue
            if cx2 - cx1 < 26 or pcx2 - pcx1 < 26:
                continue
            p = self.pieces[ix]
            has = bool(p.get("tr"))
            hv = self._hover == ("junc", slot)
            r = 10 if hv else 9
            fill = C_DROP if has else ("#5a5e6b" if hv else "#23252c")
            c.create_polygon(host._rr_pts(cx1 - r, cy - r, cx1 + r, cy + r, 5), smooth=True,
                             fill=fill, outline="#0b0c0f", width=1)
            c.create_text(cx1, cy, text="⋈" if has else "+", fill=("#06222e" if has else "#ffffff"),
                          font=(FONT, 9, "bold"))
            self._junc.append((slot, cx1, cy))

    def _junc_hit(self, x, y):
        for slot, jx, jy in self._junc:
            if abs(x - jx) <= 11 and abs(y - jy) <= 11:
                return slot
        return None

    def _junc_menu(self, slot, ev):
        """Меню переходу між кліпами slot-1 і slot."""
        if self.playing:
            self._pause()
        self._select(None)
        self.sel = slot
        p = self.pieces[self.order[slot]]
        self.cur = p["s"]
        self._show_poster(self.cur)
        self._redraw()
        cur = (p.get("tr") or {}).get("type")
        m = self._menu_new()
        m.add_command(label=E("ins_trans"), state="disabled")
        m.add_command(label=E("tr_none") + ("   ✓" if not cur else ""),
                      command=lambda: self._set_tr(slot, None))
        m.add_separator()
        for t in fx.TRANSITIONS:
            m.add_command(label=E("tr_" + t) + ("   ✓" if cur == t else ""),
                          command=lambda t=t: self._set_tr(slot, t))
        if cur:
            dm = self._menu_new()
            d0 = float(p["tr"].get("d", 0.5))
            for d in (0.25, 0.5, 0.75, 1.0, 1.5):
                dm.add_command(label=f"{d:g} s" + ("   ✓" if abs(d - d0) < 1e-6 else ""),
                               command=lambda d=d: self._set_tr(slot, cur, d))
            m.add_separator()
            m.add_cascade(label=E("ins_trans_d"), menu=dm)
        self._popup(m, ev.x_root, ev.y_root)

    def _set_tr(self, slot, typ, d=None, undo=True):
        if not (0 < slot < len(self.order)):
            return
        p = self.pieces[self.order[slot]]
        old = p.get("tr")
        new = None if typ is None else {"type": typ, "d": float(d if d is not None else
                                                               (old or {}).get("d", 0.5))}
        if new == old:
            return
        if undo:
            self._push_undo()
        p["tr"] = new                        # завжди НОВИЙ словник (undo тримає старий)
        self._redraw()

    # ---- формат кадру (9:16, 1:1 …) і фон ----
    RATIOS = ["orig", "16:9", "9:16", "1:1", "4:5", "4:3"]

    def _measure_peak(self, d):
        """Пік звуку файла (dBFS, ffmpeg volumedetect) у фоні -> d["peak_db"].
        Потрібен, щоб чесно показати, до скількох % гучність ще без спотворень."""
        if d.get("_peak_busy") or "peak_db" in d:
            return
        d["_peak_busy"] = True
        path = d.get("path")

        def work():
            peak = None
            try:
                r = subprocess.run(["ffmpeg", "-hide_banner", "-vn", "-i", path, "-af", "volumedetect",
                                    "-f", "null", "-"], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", creationflags=dc_core.BG)
                for ln in r.stderr.splitlines():
                    if "max_volume:" in ln:
                        peak = float(ln.split("max_volume:")[1].split("dB")[0].strip())
            except Exception:
                peak = None

            def apply():
                d["peak_db"] = peak if peak is not None else -91.0
                d.pop("_peak_busy", None)
                if self._insp and self._insp_on:
                    self._insp.sync(force=True)
            self._ui(apply)
        threading.Thread(target=work, daemon=True).start()

    # --------------------------------------------- запис голосу (озвучка) ---- #
    @staticmethod
    def _mic_list():
        """Мікрофони Windows (DirectShow) — так, як їх бачить ffmpeg."""
        try:
            r = subprocess.run(["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow",
                                "-i", "dummy"], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", creationflags=dc_core.NO_WINDOW, timeout=10)
        except Exception:
            return []
        out = []
        for ln in r.stderr.splitlines():
            if ln.rstrip().endswith("(audio)") and '"' in ln:
                out.append(ln.split('"')[1])
        return out

    def _mic_menu(self):
        if self.busy or self._rec:
            return
        mics = self._mic_list()
        m = self._menu_new()
        if not mics:
            m.add_command(label=E("ed_mic_none"), state="disabled")
        cur = self.cfg.get("mic_device")
        for name in mics:
            m.add_command(label=("🎙  " + name + ("   ✓" if name == cur else "")),
                          command=lambda n=name: self._set_mic(n))
        b = self.b_mic
        self._popup(m, b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    def _set_mic(self, name):
        self.cfg["mic_device"] = name
        try:
            host.save_config(self.cfg)
        except Exception:
            pass

    def _toggle_rec(self):
        if self._rec:
            return self._stop_rec()
        if self.busy:
            return
        mics = self._mic_list()
        if not mics:
            self.info_lbl.config(text=E("ed_mic_none"), fg=C_RED)
            return
        dev = self.cfg.get("mic_device") if self.cfg.get("mic_device") in mics else mics[0]
        self._rec_n += 1
        path = os.path.join(self._tmp, f"voice_{self._rec_n}.wav")
        try:
            proc = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "dshow",
                                     "-audio_buffer_size", "50", "-i", "audio=" + dev,
                                     "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", path],
                                    stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                                    creationflags=dc_core.NO_WINDOW)
        except Exception as e:
            dc_core.dlog("MIC start fail " + repr(e))
            self.info_lbl.config(text=E("ed_mic_fail"), fg=C_RED)
            return
        self._rec = {"proc": proc, "path": path, "at": self._playhead_montage_t(),
                     "t0": time.monotonic(), "dev": dev}
        dc_core.dlog(f"MIC start dev={dev!r} at={self._rec['at']:.2f}")
        self.b_mic.set_on(True)
        self.b_mic.set_icon("⏺")
        if not self.playing:                 # озвучка під відео, як у CapCut
            self._toggle_play()
        self._rec_tick()

    def _rec_tick(self):
        r = self._rec
        if not r or self._closed:
            return
        if r["proc"].poll() is not None:      # ffmpeg мікрофона впав (зайнятий / від'єднали)
            err = (r["proc"].stderr.read() or b"").decode("utf-8", "ignore")[-200:]
            dc_core.dlog("MIC died: " + err)
            self._rec = None
            self.b_mic.set_on(False)
            self.b_mic.set_icon("🎙")
            self.info_lbl.config(text=E("ed_mic_fail"), fg=C_RED)
            return
        t = time.monotonic() - r["t0"]
        self.info_lbl.config(text=E("ed_rec", t=f"{int(t // 60)}:{int(t % 60):02d}"), fg=C_RED)
        self._rec_after = self.after(250, self._rec_tick)

    def _stop_rec(self):
        r, self._rec = self._rec, None
        if not r:
            return
        try:
            r["proc"].communicate(b"q", timeout=5)   # «q» — ffmpeg коректно дописує WAV
        except Exception:
            try:
                r["proc"].kill()
            except Exception:
                pass
        self.b_mic.set_on(False)
        self.b_mic.set_icon("🎙")
        if self.playing:
            self._pause()
        try:
            d = media.audio_info(r["path"])["duration"] if os.path.exists(r["path"]) else 0
        except Exception:
            d = 0
        dc_core.dlog(f"MIC stop dur={d:.2f}")
        if d < 0.2:
            self.info_lbl.config(text=E("ed_mic_fail"), fg=C_RED)
            return
        self._push_undo()
        sn = {"path": r["path"], "at": r["at"], "dur": d, "s": 0.0, "fdur": d, "vol": 1.0,
              "name": f"🎙 {E('ed_voice')} {self._rec_n}", "env": None, "fin": 0.0, "fout": 0.0}
        self.snds.append(sn)
        self._gen_snd_env(sn)
        self._select(("snd", len(self.snds) - 1))
        self._redraw()

    def _ratio_label(self, r):
        return {"orig": E("ratio_orig"), "16:9": "16:9  YouTube", "9:16": "9:16  TikTok · Shorts · Reels",
                "1:1": "1:1  " + E("ratio_square"), "4:5": "4:5  Instagram", "4:3": "4:3"}[r]

    def _update_dims(self):
        try:
            self.dims_lbl.config(text=f"   {self._ccw}×{self._cch} · {self._cfps:g} fps")
            short = E("ratio_orig") if self._ratio == "orig" else self._ratio
            self.ratio_btn.config(text="▭  " + short + ("  · ◌" if self._bgmode == "blur" else ""))
        except (tk.TclError, AttributeError):
            pass

    def _ratio_menu(self):
        if self.busy:
            return
        m = self._menu_new()
        for r in self.RATIOS:
            m.add_command(label=self._ratio_label(r) + ("   ✓" if r == self._ratio else ""),
                          command=lambda r=r: self._set_canvas(ratio=r))
        m.add_separator()
        for b in ("black", "blur"):
            m.add_command(label=E("bg_" + b) + ("   ✓" if b == self._bgmode else ""),
                          command=lambda b=b: self._set_canvas(bg=b))
        bt = self.ratio_btn
        self._popup(m, bt.winfo_rootx(), bt.winfo_rooty() + bt.winfo_height())

    def _set_canvas(self, ratio=None, bg=None):
        r = self._ratio if ratio is None else ratio
        b = self._bgmode if bg is None else bg
        if (r, b) == (self._ratio, self._bgmode):
            return
        if self.playing:
            self._pause()
        self._push_undo()
        self._ratio, self._bgmode = r, b
        self._apply_canvas()
        self._redraw()

    def _apply_canvas(self):
        """Розмір кадру експорту з формату: коротка сторона = коротка сторона оригіналу (≤1080)."""
        w0, h0 = self._w0, self._h0
        if self._ratio == "orig":
            cw, ch = w0, h0
        else:
            a, b = (int(v) for v in self._ratio.split(":"))
            S = min(1080, min(w0, h0))
            if a >= b:
                ch, cw = S, S * a / float(b)
            else:
                cw, ch = S, S * b / float(a)
            k = min(1.0, 1920.0 / max(cw, ch))
            cw, ch = cw * k, ch * k
        self._ccw = max(2, int(cw / 2) * 2)
        self._cch = max(2, int(ch / 2) * 2)
        pk = min(self.VW / self._ccw, self.VH / self._cch)
        self._pcw = max(2, int(self._ccw * pk / 2) * 2)
        self._pch = max(2, int(self._cch * pk / 2) * 2)
        self._qcache.clear()
        try:
            self.video.delete("frame")
        except tk.TclError:
            pass
        self._update_dims()
        self._show_poster(self.cur)
        self._draw_tfbox()

    def _draw_drag_ghost(self, c, W):
        d = self._clip_drag
        if not d or not d["active"]:
            return
        x1 = d["x"] - d["grab_dx"]
        x2 = x1 + d["w"]
        p = self.pieces[d["ix"]]
        if d["to_ovl"]:
            y1, y2 = OVL_Y + 2, OVL_Y + OVL_H - 2
            c.create_polygon(host._rr_pts(x1, y1, x2, y2, 6), smooth=True, fill=C_OVL, outline="")
            c.create_rectangle(x1, y1, x2, y2, outline=C_HANDLE, width=2)
            c.create_text(max(x1 + 8, LX + 8), (y1 + y2) / 2, anchor="w", text="🎭  " + E("ed_drop_ovl"),
                          fill="#10121a", font=(FONT, 8, "bold"))
            return
        others = [r for r in self._clip_rects if r[0] != d["slot"]]
        tgt = d["target"]
        if others:
            mx = others[-1][3] if tgt >= len(others) else others[tgt][2]
            c.create_line(mx, TL_Y - 3, mx, TL_Y + TLH + 3, fill=C_DROP, width=3)
            c.create_polygon(mx - 6, TL_Y - 8, mx + 6, TL_Y - 8, mx, TL_Y - 2, fill=C_DROP, outline="")
        y1, y2 = TL_Y - 6, TL_Y + TLH - 6
        c.create_rectangle(x1, y1, x2, y2, fill=C_CLIP, outline="")
        self._draw_clip_strip(c, x1, x2, p, y1, fit=True)
        c.create_rectangle(x1, y1, x2, y2, outline=C_HANDLE, width=2)

    def _draw_ovl_lane(self, c, W, pps):
        self._ovl_rects = []
        y1, y2 = OVL_Y + 2, OVL_Y + OVL_H - 2
        for i, o in enumerate(self.ovls):
            x1 = self._x_of(o["at"])
            x2 = x1 + max(10.0, (o["e"] - o["s"]) * pps)
            self._ovl_rects.append((i, x1, x2))
            if x2 < LX or x1 > W:
                continue
            sel = i == self.sel_ovl
            hv = self._hover == ("ovl", i)
            c.create_polygon(host._rr_pts(x1, y1, x2, y2, 6), smooth=True,
                             fill=(ui.lighten(C_OVL, 0.1) if hv else C_OVL), outline="")
            src = self.sources[o["src"]]
            env = src.get("env")
            if sel and env and not o["mute"]:          # хвиля вибраної накладки
                mid = (y1 + y2) / 2.0
                span = max(0.001, o["e"] - o["s"])
                xx = max(float(LX), x1)
                while xx < min(float(W), x2):
                    a = self._env_at(env, o["s"] + (xx - x1) / max(1.0, x2 - x1) * span)
                    h = max(0.5, a * (mid - y1 - 2))
                    c.create_line(xx, mid - h, xx, mid + h, fill="#2a0d45", width=1)
                    xx += 2
            mut = " 🔇" if o["mute"] else ""
            self._block_label(c, x1, x2, W, (y1 + y2) / 2, f"🎭 {src['name']}{mut}", "#10121a")
            if sel:
                c.create_polygon(host._rr_pts(x1, y1, x2, y2, 6), smooth=True, fill="",
                                 outline=C_HANDLE, width=2)
                c.create_rectangle(x1, y1 + 4, x1 + 5, y2 - 4, fill=C_HANDLE, outline="")
                c.create_rectangle(x2 - 5, y1 + 4, x2, y2 - 4, fill=C_HANDLE, outline="")
        if not self.ovls and not (self._clip_drag and self._clip_drag["active"]):
            c.create_text((LX + W) / 2, (y1 + y2) / 2, text=E("ed_ovl_hint"),
                          fill="#6d717c", font=(FONT, 8))

    def _fit_label(self, text, maxw, size=8):
        """Текст, що влазить у maxw пікселів (обрізаний з «…»), або "" якщо місця нема."""
        if maxw < 18:
            return ""
        font = (FONT, size, "bold")
        try:
            meas = lambda s: int(self.tk.call("font", "measure", font, s))
            if meas(text) <= maxw:
                return text
            lo, hi = 0, len(text)
            while lo < hi:                      # найдовший префікс, що влазить разом з «…»
                mid = (lo + hi + 1) // 2
                if meas(text[:mid] + "…") <= maxw:
                    lo = mid
                else:
                    hi = mid - 1
            return (text[:lo].rstrip() + "…") if lo > 0 else ""
        except tk.TclError:
            return text[:max(0, int(maxw // 7))]

    def _block_label(self, c, x1, x2, W, y, text, color):
        sx = max(x1 + 8, LX + 8)
        lab = self._fit_label(text, min(x2, W) - sx - 6)
        if lab:
            c.create_text(sx, y, anchor="w", text=lab, fill=color, font=(FONT, 8, "bold"))

    def _draw_snd_lane(self, c, W, pps):
        self._snd_rects = []
        y1, y2 = SND_Y + 2, SND_Y + SND_H - 2
        for i, sn in enumerate(self.snds):
            x1 = self._x_of(sn["at"])
            x2 = x1 + max(10.0, sn["dur"] * pps)
            self._snd_rects.append((i, x1, x2))
            if x2 < LX or x1 > W:
                continue
            sel = i == self._sel_snd
            hv = self._hover == ("snd", i)
            c.create_polygon(host._rr_pts(x1, y1, x2, y2, 6), smooth=True,
                             fill=(ui.lighten(C_SND, 0.1) if hv else C_SND), outline="")
            env = sn.get("env")
            if env:                                    # хвиля звуку видна завжди
                mid = (y1 + y2) / 2.0
                xx = max(float(LX), x1)
                while xx < min(float(W), x2):
                    a = self._env_at(env, float(sn.get("s", 0.0))
                                     + (xx - x1) / max(1.0, x2 - x1) * sn["dur"])
                    h = max(0.5, a * (mid - y1 - 2))
                    c.create_line(xx, mid - h, xx, mid + h, fill="#0d3d20", width=1)
                    xx += 2
            v = "" if sn["vol"] == 1.0 else f" · {fx.vol_label(sn['vol'])}"
            self._block_label(c, x1, x2, W, (y1 + y2) / 2, f"🎵 {sn['name']}{v}", "#071a0e")
            if sel:
                c.create_polygon(host._rr_pts(x1, y1, x2, y2, 6), smooth=True, fill="",
                                 outline=C_HANDLE, width=2)
                if x2 - x1 > 22:            # ручки обрізки країв звуку
                    c.create_rectangle(x1, y1 + 4, x1 + 5, y2 - 4, fill=C_HANDLE, outline="")
                    c.create_rectangle(x2 - 5, y1 + 4, x2, y2 - 4, fill=C_HANDLE, outline="")
        if not self.snds:
            c.create_text((LX + W) / 2, (y1 + y2) / 2, text=E("ed_snd_hint"),
                          fill="#6d717c", font=(FONT, 8))

    def _draw_gutter(self, c):
        """Ліва колонка з іконками доріжок (накриває все, що заїхало за край)."""
        c.create_rectangle(0, 0, LX, TL_TOTAL_H, fill=C_RULER, outline="")
        c.create_line(LX - 0.5, 0, LX - 0.5, TL_TOTAL_H, fill="#2a2c33")
        c.create_text(LX / 2, TXT_Y + TXT_H / 2, text="T", fill=C_MUTED, font=(FONT, 11, "bold"))
        for y, h, ic in ((OVL_Y, OVL_H, "🎭"), (TL_Y, TLH, "🎬"), (SND_Y, SND_H, "🎵")):
            c.create_text(LX / 2, y + h / 2, text=ic, fill=C_MUTED, font=(FONT, 11))

    def _draw_playhead(self, c, W):
        x = self._x_of(self._playhead_montage_t())
        self._playhead_x = x
        if x < LX - 1 or x > W + 1:
            return
        c.create_line(x, RUL_H - 4, x, SB_Y - 4, fill=C_PLAY, width=2)
        c.create_polygon(x - 6, 3, x + 6, 3, x + 6, RUL_H - 11, x, RUL_H - 4, x - 6, RUL_H - 11,
                         fill=C_PLAY, outline="")
        if self._mode == "ph":                     # час біля голівки, поки тягнеш
            lab = self._fmt_tc(self._playhead_montage_t())
            bx = x + 10 if x + 84 < W else x - 84
            c.create_rectangle(bx, 3, bx + 74, RUL_H - 5, fill=C_DARK, outline=C_PLAY)
            c.create_text(bx + 37, (RUL_H - 2) / 2, text=lab, fill="#ffffff",
                          font=(FONT, 8, "bold"))

    def _draw_scrollbar(self, c, W, pps):
        x1, x2 = LX + 6, W - 6
        c.create_polygon(host._rr_pts(x1, SB_Y, x2, SB_Y + SB_H, 4), smooth=True,
                         fill="#1d1e24", outline="")
        vis = max(10, W - LX)
        cw = self._content_width(pps)
        if cw <= vis + 1:
            self._sb_thumb = None
            return
        track = x2 - x1
        tw = max(36.0, track * vis / cw)
        tx = x1 + (track - tw) * (self._scroll / max(1.0, cw - vis))
        self._sb_thumb = (tx, tx + tw, track, tw, cw, vis)
        hot = self._mode == "sb" or self._hover == ("sb",)
        c.create_polygon(host._rr_pts(tx, SB_Y, tx + tw, SB_Y + SB_H, 4), smooth=True,
                         fill=("#8a8f9c" if hot else "#4a4d57"), outline="")

    def _env_at(self, env, t):
        if not env:
            return 0.0
        i = int(t * 100)
        if i < 0:
            i = 0
        elif i >= len(env):
            i = len(env) - 1
        return env[i]

    def _update_tools(self):
        """Стан кнопок панелі (сірі, коли дія зараз неможлива)."""
        try:
            p = self._sel_piece()
            src = self._src(p)
            eps = 0.04
            self.b_undo.set_state("normal" if self._undo and not self.busy else "disabled")
            self.b_redo.set_state("normal" if self._redo and not self.busy else "disabled")
            if self._sel_snd is not None and self._sel_snd < len(self.snds):
                can_cut = self._snd_cuttable(self._sel_snd, self._playhead_montage_t())
            else:
                can_cut = p["s"] + eps < self.cur < p["e"] - eps
            self.b_split.set_state("normal" if can_cut and not self.busy else "disabled")
            can_del = (self.sel_ovl is not None or self._sel_snd is not None
                       or self.sel_txt is not None or len(self.order) > 1
                       or (src["kind"] == "video" and src["has_audio"] and not fx.g(p, "novideo")))
            self.b_del.set_state("normal" if can_del and not self.busy else "disabled")
            self.b_dup.set_state("disabled" if self.busy else "normal")
            vid = src["kind"] == "video"
            self.b_speed.set_state("normal" if vid and not self.busy else "disabled")
            self.b_mute.set_state("normal" if vid and src["has_audio"] and not self.busy
                                  else "disabled")
            self.b_mute.set_icon("🔇" if p["mute"] else "🔊")
            self.b_ovl.set_state("normal" if len(self.order) > 1 and not self.busy else "disabled")
            self.b_add.set_state("disabled" if self.busy else "normal")
            self.b_txt.set_state("disabled" if (self.busy or not self._font) else "normal")
        except (tk.TclError, AttributeError, IndexError):
            pass

    # --------------------------------------------------------- «магніт» ---- #
    def _snap_targets(self, exclude=None, playhead=True):
        pts = self._clip_edges()
        if playhead:
            pts.append(self._playhead_montage_t())
        for i, o in enumerate(self.ovls):
            if ("ovl", i) != exclude:
                pts += [o["at"], o["at"] + (o["e"] - o["s"])]
        for i, s in enumerate(self.snds):
            if ("snd", i) != exclude:
                pts += [s["at"], s["at"] + s["dur"]]
        for i, t in enumerate(self.texts):
            if ("txt", i) != exclude:
                pts += [t["at"], t["at"] + t["dur"]]
        return pts

    def _snap(self, lt, pts, thr_px=8):
        """Притягує час до найближчої точки (краї кліпів, плейхед…) в межах thr_px."""
        if self._nosnap:
            self._snap_lt = None
            return lt
        thr = thr_px / max(1e-6, self._pps())
        best = None
        for q in pts:
            if abs(q - lt) <= thr and (best is None or abs(q - lt) < abs(best - lt)):
                best = q
        self._snap_lt = best
        return lt if best is None else best

    def _snap_span(self, at, dur, pts, thr_px=8):
        """Те саме для блока: притягуємо або його початок, або кінець — що ближче."""
        if self._nosnap:
            self._snap_lt = None
            return at
        thr = thr_px / max(1e-6, self._pps())
        best, delta = None, None
        for q in pts:
            for edge in (at, at + dur):
                dd = q - edge
                if abs(dd) <= thr and (delta is None or abs(dd) < abs(delta)):
                    best, delta = q, dd
        self._snap_lt = best
        return at if delta is None else at + delta

    # --------------------- накладки: медіа ПОВЕРХ відео (як у CapCut) ------ #
    def _ovl_geom(self, o, cw, ch):
        """Розмір і позиція накладки на канвасі cw×ch (для overlay= і рамки)."""
        src = self.sources[o["src"]]
        iw = src["w"] or cw
        ih = src["h"] or ch
        f0 = min(cw / float(iw), ch / float(ih))
        sw = max(2, int(iw * f0 * o["zoom"] / 2) * 2)
        sh = max(2, int(ih * f0 * o["zoom"] / 2) * 2)
        x = int(round(cw / 2.0 + o["nx"] * cw - sw / 2.0))
        y = int(round(ch / 2.0 + o["ny"] * ch - sh / 2.0))
        return sw, sh, x, y

    def _to_overlay(self, at=None, slot=None):
        """Кліп доріжки -> накладка поверх відео (на тому ж місці монтажу або в `at`)."""
        if len(self.order) <= 1 or self.busy:
            return
        self._push_undo()
        slot = self.sel if slot is None else slot
        p = self.pieces[self.order[slot]]
        if at is None:                 # позиція кліпа на доріжці (з урахуванням пропусків)
            at = 0.0
            for sl in range(slot):
                q = self.pieces[self.order[sl]]
                at += self._gapof(q) + (q["e"] - q["s"]) / q["speed"]
            at += self._gapof(p)
        o = {k: fx.g(p, k) for k in fx.PIECE_DEFAULTS}
        o.update({"src": p["src"], "s": p["s"], "e": p["e"], "at": max(0.0, at),
                  "zoom": 0.5, "nx": 0.28, "ny": -0.22, "mute": p["mute"], "op": 1.0})
        self.ovls.append(o)
        del self.order[slot]
        if self.sel >= slot and self.sel > 0:
            self.sel -= 1
        self.sel = min(self.sel, len(self.order) - 1)
        self.sel_ovl = len(self.ovls) - 1
        self.sel_txt = None
        self._sel_snd = None
        self.sel_txt = None
        q = self._sel_piece()
        self.cur = min(max(self.cur, q["s"]), q["e"])
        self._tf_on = True                       # одразу показуємо рамку накладки
        self._show_poster(self.cur)
        self._redraw()

    def _ovl_to_track(self):
        i = self.sel_ovl
        if i is None:
            return
        self._push_undo()
        o = self.ovls[i]
        p = self._new_piece(o["src"], o["s"], o["e"])
        p["mute"] = o["mute"]
        for k in fx.PIECE_DEFAULTS:
            p[k] = fx.g(o, k)
        self.pieces.append(p)
        self.order.append(len(self.pieces) - 1)
        del self.ovls[i]
        self.sel_ovl = None
        self.sel_txt = None
        self.sel = len(self.order) - 1
        self.cur = p["s"]
        self._show_poster(self.cur)
        self._redraw()

    def _ovl_del(self):
        i = self.sel_ovl
        if i is None:
            return
        self._push_undo()
        del self.ovls[i]
        self.sel_ovl = None
        self.sel_txt = None
        self._tf_on = False
        self.video.delete("tf")
        self._show_poster(self.cur)
        self._redraw()

    def _ovl_mute(self):
        i = self.sel_ovl
        if i is None:
            return
        self._push_undo()
        self.ovls[i]["mute"] = not self.ovls[i]["mute"]
        self._req_draw()
        self._replay_soon()

    def _ovl_hit(self, x):
        for i, x1, x2 in reversed(self._ovl_rects):
            if x1 - 3 <= x <= x2 + 3:
                return i, x1, x2
        return None

    def _snd_hit(self, x):
        for i, x1, x2 in reversed(self._snd_rects):
            if x1 - 3 <= x <= x2 + 3:
                return i
        return None

    def _clip_hit(self, x):
        for r in self._clip_rects:
            if r[2] <= x <= r[3]:
                return r
        return None

    def _handle_hit(self, x, y):
        """'L'/'R' — курсор над білою ручкою обрізки вибраного кліпа."""
        if self._sel_xs is None or not (TL_Y <= y < TL_Y + TLH):
            return None
        dl, dr = abs(x - self._sel_xs), abs(x - self._sel_xe)
        if min(dl, dr) > 10:
            return None
        return "L" if dl <= dr else "R"

    def _lane_of(self, y):
        if y < RUL_H:
            return "ruler"
        if TXT_Y <= y < TXT_Y + TXT_H:
            return "txt"
        if OVL_Y <= y < OVL_Y + OVL_H:
            return "ovl"
        if TL_Y <= y < TL_Y + TLH:
            return "clip"
        if SND_Y <= y < SND_Y + SND_H:
            return "snd"
        if y >= SB_Y - 3:
            return "sb"
        return "gap"

    # ------------------------------------------- контекстні меню (ПКМ) ----- #
    def _menu_new(self):
        return tk.Menu(self, tearoff=0, bg=C_BG2, fg=C_TEXT, bd=0,
                       activebackground=C_BLURPLE, activeforeground="#ffffff",
                       font=(FONT, 10))

    def _popup(self, m, x, y):
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def _tl_rclick(self, ev):
        if self.busy or ev.x < LX:
            return
        lane = self._lane_of(ev.y)
        if lane == "clip":
            self._tl_menu(ev)
        elif lane == "ovl":
            self._ovl_menu(ev)
        elif lane == "snd":
            self._wave_menu(ev)
        elif lane == "txt":
            self._txt_menu(ev)

    def _tl_menu(self, ev):
        hit = self._clip_hit(ev.x)
        if hit is None:
            return
        slot, ix, cx1, cx2 = hit
        if self.playing:
            self._pause()
        p = self.pieces[ix]
        if slot != self.sel:
            self._tf_on = False
            self.video.delete("tf")
        self.sel = slot
        self.sel_ovl = None
        self.sel_txt = None
        self._sel_snd = None
        self.sel_txt = None
        # плейхед — у точку кліку (для «розрізати тут»)
        self.cur = min(max(p["s"], p["s"] + (ev.x - cx1) / max(1.0, cx2 - cx1) * (p["e"] - p["s"])), p["e"])
        self._show_poster(self.cur)
        self._redraw()
        src = self._src(p)
        m = self._menu_new()
        m.add_command(label=E("ed_cut_here") + "      S", command=lambda: self._cut_at(self.cur))
        m.add_command(label=E("ed_dup") + "      Ctrl+D", command=self._duplicate)
        if len(self.order) > 1:
            m.add_command(label=E("ed_make_ovl"), command=lambda: self._to_overlay())
        if src["kind"] == "video":
            sp = self._menu_new()
            for v in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0):
                sp.add_command(label=(f"{v:g}×" + ("   ✓" if p["speed"] == v else "")),
                               command=lambda v=v: self._set_speed(v))
            m.add_cascade(label=E("ed_speed", s=f"{p['speed']:g}"), menu=sp)
            if src["has_audio"]:
                m.add_command(label=(E("ed_unmute") if p["mute"] else E("ed_mute")) + "      M",
                              command=self._toggle_mute)
                m.add_command(label=(E("ed_revideo") if fx.g(p, "novideo") else E("ed_novideo")),
                              command=self._toggle_novideo)
        if self._is_transformed(p):
            m.add_command(label=E("ed_reset_tf"), command=self._tf_reset)
        if self._gapof(p) > 0.01:
            m.add_command(label=E("ed_gap_rm"), command=self._gap_remove)
        if any(self._gapof(self.pieces[k]) > 0.01 for k in self.order):
            m.add_command(label=E("ed_gaps_rm"), command=self._gaps_remove_all)
        m.add_separator()
        m.add_command(label=E("ed_move_left"), command=lambda: self._move(-1))
        m.add_command(label=E("ed_move_right"), command=lambda: self._move(1))
        if len(self.order) > 1:
            m.add_separator()
            m.add_command(label=E("ed_rm_clip") + "      Del", command=self._remove)
        self._popup(m, ev.x_root, ev.y_root)

    def _ovl_menu(self, ev):
        hit = self._ovl_hit(ev.x)
        if hit is None:
            return
        i = hit[0]
        self.sel_ovl = i
        self.sel_txt = None
        self._sel_snd = None
        self.sel_txt = None
        self._show_poster(self.cur)
        self._redraw()
        o = self.ovls[i]
        src = self.sources[o["src"]]
        m = self._menu_new()
        m.add_command(label=f"🎭  {src['name']}", state="disabled")
        if src["kind"] == "video" and src["has_audio"]:
            m.add_command(label=(E("ed_unmute") if o["mute"] else E("ed_mute")),
                          command=self._ovl_mute)
        m.add_command(label=E("ed_fullscreen"), command=self._tf_reset)
        m.add_command(label=E("ed_to_track"), command=self._ovl_to_track)
        m.add_separator()
        m.add_command(label=E("ed_del_ovl") + "      Del", command=self._ovl_del)
        self._popup(m, ev.x_root, ev.y_root)

    def _wave_menu(self, ev):
        i = self._snd_hit(ev.x)
        if i is None:
            return
        self._sel_snd = i
        self.sel_txt = None
        self.sel_ovl = None
        self.sel_txt = None
        self._req_draw()
        sn = self.snds[i]
        m = self._menu_new()
        m.add_command(label=f"🎵  {sn['name']}", state="disabled")
        m.add_command(label=E("ed_listen"), command=lambda: self._preview_sound(sn))
        if self._snd_cuttable(i, self._playhead_montage_t()):
            m.add_command(label=E("ed_cut_here") + "      S",
                          command=lambda: self._cut_snd(i, self._playhead_montage_t()))
        vol = self._menu_new()
        for v in (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 10.0, 100.0, 10 ** (888 / 20.0)):
            vol.add_command(label=(fx.vol_label(v) + ("  💀" if v > 100 else "")
                                   + ("   ✓" if abs(sn["vol"] - v) <= 1e-9 * v else "")),
                            command=lambda v=v: self._set_snd_vol(i, v))
        m.add_cascade(label=E("ed_volume", v=fx.vol_label(sn['vol'])), menu=vol)
        m.add_separator()
        m.add_command(label=E("ed_del_snd") + "      Del", command=lambda: self._del_snd(i))
        self._popup(m, ev.x_root, ev.y_root)

    def _speed_popup(self):
        p = self._sel_piece()
        if self._src(p)["kind"] != "video":
            return
        m = self._menu_new()
        for v in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0):
            m.add_command(label=(f"{v:g}×" + ("   ✓" if p["speed"] == v else "")),
                          command=lambda v=v: self._set_speed(v))
        b = self.b_speed
        self._popup(m, b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    def _preview_sound(self, sn):
        try:
            subprocess.Popen(["ffplay", "-hide_banner", "-loglevel", "error", "-nodisp",
                              "-autoexit", "-ss", f"{float(sn.get('s', 0.0)):.3f}",
                              "-t", f"{min(10.0, sn['dur']):.3f}", "-i", sn["path"]],
                             creationflags=dc_core.NO_WINDOW)
        except Exception:
            pass

    def _set_snd_vol(self, i, v):
        self._push_undo()
        self.snds[i]["vol"] = v
        self._req_draw()
        self._replay_soon()

    def _del_snd(self, i):
        if not (0 <= i < len(self.snds)):
            return
        self._push_undo()
        del self.snds[i]
        self._sel_snd = None
        self.sel_txt = None
        self._redraw()

    def _delete_selected(self):
        """Delete / кнопка 🗑: видаляє те, що вибрано — накладку, звук або кліп."""
        if self.busy:
            return
        if self.sel_txt is not None and self.sel_txt < len(self.texts):
            self._txt_del()
        elif self.sel_ovl is not None and self.sel_ovl < len(self.ovls):
            self._ovl_del()
        elif self._sel_snd is not None and self._sel_snd < len(self.snds):
            self._del_snd(self._sel_snd)
        elif len(self.order) > 1:
            self._remove()
        else:
            # єдиний кліп: видаляємо його КАРТИНКУ — звук лишається (Ctrl+Z поверне)
            p = self._sel_piece()
            src = self._src(p)
            if src["kind"] == "video" and src["has_audio"] and not fx.g(p, "novideo"):
                self._toggle_novideo()
                self.info_lbl.config(text=E("ed_del_last_video"), fg=host.C_WARN)
            else:
                self.info_lbl.config(text=E("ed_del_last"), fg=C_RED)

    # ---------------- мишка на таймлайні: плейхед / ручки / кліпи / блоки ---- #
    def _tl_press(self, ev):
        try:
            self.focus_set()
        except tk.TclError:
            pass
        if self.busy:
            return
        self._nosnap = bool(ev.state & 0x20000)       # Alt — без магніту
        self._last_ev = (ev.x, ev.y)
        x, y = ev.x, ev.y
        lane = self._lane_of(y)
        if lane == "sb":
            return self._sb_press(ev)
        if x < LX:
            return
        if lane == "ruler":
            return self._ph_start(ev)
        if lane == "clip":
            j = self._junc_hit(x, y)
            if j is not None:                            # іконка переходу на стику
                return self._junc_menu(j, ev)
        handle = self._handle_hit(x, y)
        if not handle and abs(x - self._playhead_x) <= 5:   # білий повзунок — хапаємо
            return self._ph_start(ev)
        if lane == "clip":
            return self._clip_press(ev, handle)
        if lane == "ovl":
            return self._ovl_press(ev)
        if lane == "txt":
            return self._txt_press(ev)
        if lane == "snd":
            return self._snd_press(ev)
        return self._ph_start(ev)

    def _tl_motion(self, ev):
        self._nosnap = bool(ev.state & 0x20000)
        self._last_ev = (ev.x, ev.y)
        self._motion_dispatch(ev.x, ev.y)
        if self._mode in ("ph", "clip", "ovl", "snd", "txt") and not self._edge_after:
            self._edge_tick()

    def _motion_dispatch(self, x, y):
        m = self._mode
        if m == "ph":
            self._ph_to(x)
        elif m == "trim":
            self._trim_motion(x)
        elif m == "clip":
            self._clip_motion(x, y)
        elif m == "ovl":
            self._ovl_motion(x)
        elif m == "txt":
            self._txt_motion(x)
        elif m == "snd":
            self._snd_motion(x)
        elif m == "sb":
            self._sb_motion(x)

    def _edge_tick(self):
        """Тягнеш щось до краю — доріжка сама прокручується (навіть якщо мишка стоїть)."""
        self._edge_after = None
        if self._mode not in ("ph", "clip", "ovl", "snd", "txt") or self._last_ev is None:
            return
        x = self._last_ev[0]
        d = 0.0
        if x > self.TW - 30:
            d = min(40.0, (x - (self.TW - 30)) * 0.8 + 4)
        elif x < LX + 30 and self._scroll > 0:
            d = -min(40.0, ((LX + 30) - x) * 0.8 + 4)
        if not d:
            return
        old = self._scroll
        self._scroll += d
        self._clamp_scroll(self._pps())
        if self._scroll == old:
            return
        self._motion_dispatch(*self._last_ev)
        try:
            self._edge_after = self.after(30, self._edge_tick)
        except tk.TclError:
            pass

    def _tl_release(self, ev):
        m = self._mode
        self._mode = None
        if self._edge_after:
            try: self.after_cancel(self._edge_after)
            except Exception: pass
            self._edge_after = None
        if m == "trim":
            self._drag = None
            if self._tip_t is not None:
                self._schedule_tip_clear()
        elif m == "clip":
            self._clip_release()
        elif m == "ovl":
            if self._ovl_drag and self._ovl_drag["pushed"]:
                self._show_poster(self.cur)
            self._ovl_drag = None
        elif m == "snd":
            self._snd_drag = None
        elif m == "txt":
            if self._txt_drag and self._txt_drag["pushed"]:
                self._show_poster(self.cur)
            self._txt_drag = None
        elif m == "ph":
            self._show_poster(self.cur)
        self._sb_drag = None
        self._snap_lt = None
        self._redraw()

    # ---- плейхед (білий повзунок): тягнеться по лінійці та по доріжках ----
    def _ph_start(self, ev):
        if self.playing:
            self._pause()
        self._mode = "ph"
        self._ph_to(ev.x)

    def _ph_to(self, x):
        lt = min(max(0.0, self._lt_of(x)), self._layout_total())
        lt = self._snap(lt, self._clip_edges(), thr_px=6)
        self._set_playhead_lt(lt)

    # ---- кліпи: обрізка ручками / вибір / перетягування (переставити або в накладку) ----
    def _clip_press(self, ev, handle):
        if self.playing:
            self._pause()
        if handle:
            p = self._sel_piece()
            self._mode = "trim"
            self._drag = self._active = handle
            self._nudge_active = True         # drag штовхне undo -> стрілки не дублюють
            self._tip_t = p["s"] if handle == "L" else p["e"]
            self._d0 = {"lt0": self._lt_of(ev.x), "s0": p["s"], "e0": p["e"],
                        "g0": self._gapof(p), "pushed": False}
            self._redraw()
            return
        self._active = None
        self._tip_t = None
        hit = self._clip_hit(ev.x)
        if hit is None:                       # порожнє місце доріжки -> плейхед туди
            self.sel_ovl = None
            self.sel_txt = None
            self._sel_snd = None
            self.sel_txt = None
            return self._ph_start(ev)
        slot, ix, cx1, cx2 = hit
        p = self.pieces[ix]
        if slot != self.sel or self.sel_ovl is not None:
            self._tf_on = False
            self.video.delete("tf")
        self.sel = slot
        self.sel_ovl = None
        self.sel_txt = None
        self._sel_snd = None
        self.sel_txt = None
        self.cur = min(max(p["s"], p["s"] + (ev.x - cx1) / max(1.0, cx2 - cx1)
                           * (p["e"] - p["s"])), p["e"])
        self._show_poster(self.cur, fast=True)
        self._clip_drag = {"slot": slot, "ix": ix, "grab_dx": ev.x - cx1, "w": cx2 - cx1,
                           "x0": ev.x, "y0": ev.y, "x": ev.x, "y": ev.y, "active": False,
                           "target": slot, "to_ovl": False}
        self._mode = "clip"
        self._redraw()

    def _trim_motion(self, x):
        p = self._sel_piece()
        src = self._src(p)
        d0 = self._d0
        dsrc = (self._lt_of(x) - d0["lt0"]) * p["speed"]
        if not d0["pushed"]:
            if abs(dsrc) < 1e-4:
                return
            self._push_undo()
            d0["pushed"] = True
        lo, hi = 0.0, src["dur"]
        if self._drag == "L":
            ns = max(lo, min(d0["s0"] + dsrc, d0["e0"] - 0.1))
            p["s"] = ns; self.cur = self._tip_t = ns
            # зрізане зліва лишає ПОРОЖНЄ МІСЦЕ на доріжці (зникне при збереженні)
            p["gap"] = max(0.0, d0["g0"] + (ns - d0["s0"]) / p["speed"])
        else:
            ne = min(hi, max(d0["e0"] + dsrc, d0["s0"] + 0.1))
            p["e"] = ne; self.cur = self._tip_t = ne
        self._show_poster(self.cur, fast=True)
        self._req_draw()

    def _clip_motion(self, x, y):
        d = self._clip_drag
        if not d:
            return
        if not d["active"]:
            if abs(x - d["x0"]) + abs(y - d["y0"]) < 6 or len(self.order) < 2:
                return
            d["active"] = True
            try:
                self.tl.config(cursor="fleur")
                self._cursor = "fleur"
            except tk.TclError:
                pass
        d["x"], d["y"] = x, y
        d["to_ovl"] = y < TL_Y - 6
        center = x - d["grab_dx"] + d["w"] / 2.0
        others = [r for r in self._clip_rects if r[0] != d["slot"]]
        d["target"] = sum(1 for r in others if (r[2] + r[3]) / 2.0 < center)
        self._req_draw()

    def _clip_release(self):
        d = self._clip_drag
        self._clip_drag = None
        if not d or not d["active"]:
            return
        if d["to_ovl"]:                       # кинули на доріжку накладок
            at = max(0.0, self._lt_of(d["x"] - d["grab_dx"]))
            self._to_overlay(at=at, slot=d["slot"])
            return
        old, tgt = d["slot"], d["target"]
        if tgt != old:
            self._push_undo()
            ix = self.order.pop(old)
            self.order.insert(tgt, ix)
            self.pieces[ix]["gap"] = 0.0      # переставлений кліп стає впритул
            self.sel = tgt
            self._show_poster(self.cur)

    # ---- накладки на своїй доріжці: рух / обрізка країв ----
    def _ovl_press(self, ev):
        hit = self._ovl_hit(ev.x)
        if hit is None:
            if self.sel_ovl is not None:
                self.sel_ovl = None
                self.sel_txt = None
                self._tf_on = False
                self.video.delete("tf")
                self._show_poster(self.cur)
            return self._ph_start(ev)
        i, x1, x2 = hit
        if self.playing:
            self._pause()
        self.sel_ovl = i
        self.sel_txt = None
        self._sel_snd = None
        self.sel_txt = None
        o = self.ovls[i]
        edge = None
        if x2 - x1 > 22:
            edge = "L" if abs(ev.x - x1) <= 7 else ("R" if abs(ev.x - x2) <= 7 else None)
        self._ovl_drag = {"i": i, "lt0": self._lt_of(ev.x), "o0": dict(o), "edge": edge,
                          "pushed": False, "x0": ev.x,
                          "pts": self._snap_targets(("ovl", i))}
        self._mode = "ovl"
        self._tf_on = True                    # рамка на прев'ю одразу керує накладкою
        self._show_poster(self.cur)
        self._redraw()

    def _ovl_motion(self, x):
        d = self._ovl_drag
        if not d:
            return
        if not d["pushed"]:
            if abs(x - d["x0"]) < 3:
                return
            self._push_undo()
            d["pushed"] = True
        dl = self._lt_of(x) - d["lt0"]
        o = self.ovls[d["i"]]
        o0 = d["o0"]
        src = self.sources[o["src"]]
        hi = src["dur"] if src["kind"] == "video" else IMG_MAX
        if d["edge"] == "L":   # лівий край: і початок джерела, і позиція в монтажі
            ns = min(max(0.0, o0["s"] + dl), o0["e"] - 0.1)
            ns = max(ns, o0["s"] - o0["at"])
            at = self._snap(o0["at"] + (ns - o0["s"]), d["pts"])
            ns = min(max(0.0, o0["s"] + (at - o0["at"])), o0["e"] - 0.1)
            o["s"] = ns
            o["at"] = max(0.0, o0["at"] + (ns - o0["s"]))
        elif d["edge"] == "R":
            ne = min(hi, max(o0["e"] + dl, o0["s"] + 0.1))
            end = self._snap(o0["at"] + (ne - o0["s"]), d["pts"])
            o["e"] = min(hi, max(o0["s"] + 0.1, o0["s"] + (end - o0["at"])))
        else:
            at = max(0.0, o0["at"] + dl)
            at = self._snap_span(at, o0["e"] - o0["s"], d["pts"])
            o["at"] = max(0.0, min(self._layout_end_all() + 5.0, at))
        self._req_draw()

    # ---- звуки на своїй доріжці: рух ----
    def _snd_press(self, ev):
        i = self._snd_hit(ev.x)
        if i is None:
            self._sel_snd = None
            self.sel_txt = None
            return self._ph_start(ev)
        self._sel_snd = i
        self.sel_txt = None
        self.sel_ovl = None
        self.sel_txt = None
        sn = self.snds[i]
        x1, x2 = next(((a, b) for k, a, b in self._snd_rects if k == i), (ev.x, ev.x))
        edge = None
        if x2 - x1 > 22:
            edge = "L" if abs(ev.x - x1) <= 7 else ("R" if abs(ev.x - x2) <= 7 else None)
        self._snd_drag = {"i": i, "lt0": self._lt_of(ev.x), "at0": sn["at"], "edge": edge,
                          "s0": float(sn.get("s", 0.0)), "dur0": sn["dur"],
                          "pushed": False, "x0": ev.x, "pts": self._snap_targets(("snd", i))}
        self._mode = "snd"
        self._redraw()

    def _snd_motion(self, x):
        d = self._snd_drag
        if not d:
            return
        if not d["pushed"]:
            if abs(x - d["x0"]) < 3:
                return
            self._push_undo()
            d["pushed"] = True
        sn = self.snds[d["i"]]
        dl = self._lt_of(x) - d["lt0"]
        fdur = float(sn.get("fdur") or (d["s0"] + d["dur0"]))
        if d.get("edge") == "L":            # лівий край: зрізаємо початок звуку
            at = self._snap(d["at0"] + dl, d["pts"])
            ns = d["s0"] + (at - d["at0"])
            ns = max(0.0, min(ns, d["s0"] + d["dur0"] - 0.1))
            at = d["at0"] + (ns - d["s0"])
            if at < 0:
                ns -= at
                at = 0.0
            sn["s"], sn["at"], sn["dur"] = ns, at, d["dur0"] - (ns - d["s0"])
        elif d.get("edge") == "R":          # правий край: зрізаємо кінець
            end = self._snap(d["at0"] + d["dur0"] + dl, d["pts"])
            sn["dur"] = max(0.1, min(fdur - d["s0"], end - d["at0"]))
        else:
            at = max(0.0, d["at0"] + dl)
            at = self._snap_span(at, sn["dur"], d["pts"])
            sn["at"] = max(0.0, min(self._layout_total() - 0.1, at))
        self._req_draw()

    # ---- горизонтальний скролбар під доріжками ----
    def _sb_press(self, ev):
        t = self._sb_thumb
        if not t:
            return
        tx1, tx2 = t[0], t[1]
        if tx1 <= ev.x <= tx2:
            self._sb_drag = (ev.x, self._scroll)
            self._mode = "sb"
        else:                                  # клік повз повзунок — сторінка
            self._scroll += (1 if ev.x > tx2 else -1) * (self.TW - LX) * 0.8
            self._clamp_scroll(self._pps())
            self._draw_track()

    def _sb_motion(self, x):
        t = self._sb_thumb
        if not self._sb_drag or not t:
            return
        x0, s0 = self._sb_drag
        _, _, track, tw, cw, vis = t
        self._scroll = s0 + (x - x0) * (cw - vis) / max(1.0, track - tw)
        self._clamp_scroll(self._pps())
        self._req_draw()

    # ---- курсор і підсвітка при наведенні ----
    def _tl_hover(self, ev):
        if self._mode:
            return
        x, y = ev.x, ev.y
        lane = self._lane_of(y)
        cur, hv = "", None
        if x < LX:
            pass
        elif lane == "sb":
            t = self._sb_thumb
            if t and t[0] <= x <= t[1]:
                cur, hv = "hand2", ("sb",)
        elif lane == "ruler":
            cur = "hand2"
        elif lane == "clip" and self._junc_hit(x, y) is not None:
            cur, hv = "hand2", ("junc", self._junc_hit(x, y))
        elif self._handle_hit(x, y):
            cur = "sb_h_double_arrow"
        elif abs(x - self._playhead_x) <= 5:
            cur = "sb_h_double_arrow"
        elif lane == "clip":
            r = self._clip_hit(x)
            if r:
                cur, hv = "hand2", ("clip", r[0])
        elif lane == "ovl":
            h = self._ovl_hit(x)
            if h:
                i, x1, x2 = h
                edge = x2 - x1 > 22 and (abs(x - x1) <= 7 or abs(x - x2) <= 7)
                cur, hv = ("sb_h_double_arrow" if edge else "fleur"), ("ovl", i)
        elif lane == "snd":
            i = self._snd_hit(x)
            if i is not None:
                x1, x2 = next(((a, b) for k, a, b in self._snd_rects if k == i), (x, x))
                edge = i == self._sel_snd and x2 - x1 > 22 and (abs(x - x1) <= 7 or abs(x - x2) <= 7)
                cur, hv = ("sb_h_double_arrow" if edge else "fleur"), ("snd", i)
        elif lane == "txt":
            h = self._txt_hit(x)
            if h:
                i, x1, x2 = h
                edge = x2 - x1 > 22 and (abs(x - x1) <= 7 or abs(x - x2) <= 7)
                cur, hv = ("sb_h_double_arrow" if edge else "fleur"), ("txt", i)
        if cur != self._cursor:
            self._cursor = cur
            try:
                self.tl.config(cursor=cur)
            except tk.TclError:
                pass
        if hv != self._hover:
            self._hover = hv
            self._req_draw()

    def _tl_leave(self, _ev):
        if self._hover is not None and not self._mode:
            self._hover = None
            self._req_draw()

    # ------------- відтворення = результат: граф фільтрів для ffplay -------- #
    def _clip_layout_start(self, slot):
        acc = 0.0
        for sl in range(slot):
            q = self.pieces[self.order[sl]]
            acc += self._gapof(q) + (q["e"] - q["s"]) / q["speed"]
        return acc + self._gapof(self.pieces[self.order[slot]])

    def _play_graph(self, piece, start):
        """(-vf, -af|None, a_ok) для ffplay: швидкість, колір, масштаб, фейди, накладки,
        тексти і додані звуки — на тому ж часі, що й у готовому файлі."""
        sp = piece["speed"]
        src = self._src(piece)
        cw, ch = self._pcw, self._pch
        off = (start - piece["s"]) / sp                 # скільки кліпа вже «пройдено»
        cdur = (piece["e"] - piece["s"]) / sp
        rem = cdur - off
        m0 = self._clip_layout_start(self.sel) + off     # монтажний час старту відтворення
        chain = [f"setpts=(PTS-STARTPTS)/{sp:g}", self._transform_vf(piece, cw, ch)]
        chain += fx.fade_win(-off, cdur - off, fx.g(piece, "fin"), fx.g(piece, "fout"), "v")
        parts = ["[in]" + ",".join(chain) + "[b0]"]
        vin = "[b0]"
        n = 0
        for o in self.ovls:
            od = o["e"] - o["s"]
            a, b = o["at"] - m0, o["at"] + od - m0      # коли видно (час відтворення)
            if b <= 0 or a >= rem:
                continue
            osrc = self.sources[o["src"]]
            seek = o["s"] + max(0.0, -a)
            ovf, x, y = self._ovl_vf(o, cw, ch)
            fades = fx.fade_win(a, b, fx.g(o, "fin"), fx.g(o, "fout"), "v", alpha=True)
            mv = f"movie={fx.esc(osrc['path'])}"
            if osrc["kind"] == "video" and seek > 0.01:
                mv += f":seek_point={seek:.3f}"
            mv += f",setpts=PTS-STARTPTS+{max(0.0, a):.3f}/TB,{ovf}"
            if fades:
                mv += ",format=rgba," + ",".join(fades)
            parts.append(f"{mv}[o{n}]")
            parts.append(f"{vin}[o{n}]overlay={x}:{y}:enable='between(t,{max(0.0, a):.3f},{b:.3f})'[b{n + 1}]")
            vin = f"[b{n + 1}]"
            n += 1
        k = 0
        for t in (self.texts if self._font else []):
            a, b = t["at"] - m0, t["at"] + t["dur"] - m0
            if b <= 0 or a >= rem or not t["text"].strip():
                continue
            tf = fx.write_text_file(t, self._tmp, f"pl{k}")
            parts.append(f"{vin}{fx.drawtext(t, cw, ch, self._font, tf, a, b)}[t{k}]")
            vin = f"[t{k}]"
            k += 1
        parts[-1] = parts[-1][:parts[-1].rfind("[")] + "[out]"
        vf = ";".join(parts)

        a_ok = src["kind"] == "video" and src["has_audio"]
        if not a_ok:
            return vf, None, False
        vol = 0.0 if piece["mute"] else fx.g(piece, "vol")
        ach = ["asetpts=PTS-STARTPTS"] + ([self._atempo(sp)] if sp != 1.0 else [])
        ach += fx.audio_chain(piece, vol, fx.fade_win(-off, cdur - off, fx.g(piece, "fin"),
                                               fx.g(piece, "fout"), "a"))
        aparts = ["[in]" + ",".join(ach) + "[a0]"]
        labs = []
        for j, sn in enumerate(self.snds):
            a, b = sn["at"] - m0, sn["at"] + sn["dur"] - m0
            if b <= 0 or a >= rem or sn["vol"] <= 0.005 or not os.path.isfile(sn["path"]):
                continue
            seek = max(0.0, -a)
            sk = seek + float(sn.get("s", 0.0))         # точка початку шматка у файлі
            mv = f"amovie={fx.esc(sn['path'])}"
            if sk > 0.01:
                mv += f":seek_point={sk:.3f}"
            ms = int(max(0.0, a) * 1000)
            ach2 = ["asetpts=PTS-STARTPTS", f"atrim=0:{max(0.05, sn['dur'] - seek):.3f}",
                    "asetpts=PTS-STARTPTS", "aresample=44100"] + fx.audio_chain(sn,
                sn["vol"], fx.fade_win(-seek, sn["dur"] - seek, sn.get("fin", 0.0),
                                       sn.get("fout", 0.0), "a"))
            if ms:
                ach2.append(f"adelay={ms}|{ms}")
            aparts.append(f"{mv},{','.join(ach2)}[s{j}]")
            labs.append(f"[s{j}]")
        if labs:
            aparts.append(f"[a0]{''.join(labs)}amix=inputs={len(labs) + 1}:duration=first:normalize=0[out]")
        else:
            aparts[0] = aparts[0][:-4] + "[out]"
        return vf, ";".join(aparts), True

    # ------------------------------------------- доріжка тексту (титри) ---- #
    def _draw_txt_lane(self, c, W, pps):
        self._txt_rects = []
        y1, y2 = TXT_Y + 2, TXT_Y + TXT_H - 2
        for i, t in enumerate(self.texts):
            x1 = self._x_of(t["at"])
            x2 = x1 + max(10.0, t["dur"] * pps)
            self._txt_rects.append((i, x1, x2))
            if x2 < LX or x1 > W:
                continue
            sel = i == self.sel_txt
            hv = self._hover == ("txt", i)
            c.create_polygon(host._rr_pts(x1, y1, x2, y2, 6), smooth=True,
                             fill=(ui.lighten(C_TXT, 0.12) if hv else C_TXT), outline="")
            first = (t["text"].split("\n")[0] or "…")
            self._block_label(c, x1, x2, W, (y1 + y2) / 2, f"T  {first}", "#2a1a00")
            if sel:
                c.create_polygon(host._rr_pts(x1, y1, x2, y2, 6), smooth=True, fill="",
                                 outline=C_HANDLE, width=2)
                c.create_rectangle(x1, y1 + 4, x1 + 5, y2 - 4, fill=C_HANDLE, outline="")
                c.create_rectangle(x2 - 5, y1 + 4, x2, y2 - 4, fill=C_HANDLE, outline="")
        if not self.texts:
            c.create_text((LX + W) / 2, (y1 + y2) / 2, text=E("ed_txt_hint"),
                          fill="#6d717c", font=(FONT, 8))

    def _txt_hit(self, x):
        for i, x1, x2 in reversed(self._txt_rects):
            if x1 - 3 <= x <= x2 + 3:
                return i, x1, x2
        return None

    def _txt_press(self, ev):
        hit = self._txt_hit(ev.x)
        if hit is None:
            if self.sel_txt is not None:
                self._select(None)
                self._tf_on = False
                self.video.delete("tf")
            return self._ph_start(ev)
        i, x1, x2 = hit
        if self.playing:
            self._pause()
        self._select(("txt", i))
        t = self.texts[i]
        edge = None
        if x2 - x1 > 22:
            edge = "L" if abs(ev.x - x1) <= 7 else ("R" if abs(ev.x - x2) <= 7 else None)
        self._txt_drag = {"i": i, "lt0": self._lt_of(ev.x), "t0": dict(t), "edge": edge,
                          "pushed": False, "x0": ev.x, "pts": self._snap_targets(("txt", i))}
        self._mode = "txt"
        self._tf_on = True
        self._show_poster(self.cur)
        self._redraw()

    def _txt_motion(self, x):
        d = self._txt_drag
        if not d:
            return
        if not d["pushed"]:
            if abs(x - d["x0"]) < 3:
                return
            self._push_undo()
            d["pushed"] = True
        dl = self._lt_of(x) - d["lt0"]
        t = self.texts[d["i"]]
        t0 = d["t0"]
        end0 = t0["at"] + t0["dur"]
        if d["edge"] == "L":
            na = self._snap(max(0.0, min(end0 - 0.2, t0["at"] + dl)), d["pts"])
            na = max(0.0, min(end0 - 0.2, na))
            t["at"], t["dur"] = na, end0 - na
        elif d["edge"] == "R":
            ne = self._snap(max(t0["at"] + 0.2, end0 + dl), d["pts"])
            t["dur"] = max(0.2, ne - t0["at"])
        else:
            at = self._snap_span(max(0.0, t0["at"] + dl), t0["dur"], d["pts"])
            t["at"] = max(0.0, at)
        self._req_draw()

    def _txt_menu(self, ev):
        hit = self._txt_hit(ev.x)
        if hit is None:
            return
        self._select(("txt", hit[0]))
        self._tf_on = True
        self._show_poster(self.cur)
        self._redraw()
        m = self._menu_new()
        m.add_command(label=E("ed_txt_edit"), command=self._focus_text_box)
        m.add_command(label=E("ed_txt_dup"), command=self._txt_dup)
        m.add_separator()
        m.add_command(label=E("ed_txt_del") + "      Del", command=self._txt_del)
        self._popup(m, ev.x_root, ev.y_root)

    def _tl_double(self, ev):
        """Подвійний клік по тексту на доріжці -> одразу редагувати напис."""
        if self._lane_of(ev.y) == "txt" and self._txt_hit(ev.x) is not None:
            self._focus_text_box()

    # ---- гарячі клавіші (по коду клавіші — не залежать від розкладки) ----
    def _on_key(self, ev):
        if self.busy:
            return None
        if isinstance(ev.widget, (tk.Text, tk.Entry)):     # пишемо текст — клавіші не чіпаємо
            if ev.keycode == 27:
                self.focus_set()
            return None
        kc = ev.keycode
        ctrl = bool(ev.state & 0x4)
        shift = bool(ev.state & 0x1)
        if kc == 32:
            self._toggle_play()
        elif kc == 37:
            self._nudge(-1, big=shift)
        elif kc == 39:
            self._nudge(1, big=shift)
        elif kc == 36:
            self._to_start()
        elif kc == 35:
            self._to_end()
        elif kc in (46, 8):
            self._delete_selected()
        elif kc == 27:
            self._active = None
            self.sel_ovl = None
            self.sel_txt = None
            self._sel_snd = None
            self.sel_txt = None
            self._tf_on = False
            self.video.delete("tf")
            self._redraw()
        elif ctrl and kc == 90:
            (self._redo_action if shift else self._undo_action)()
        elif ctrl and kc == 89:
            self._redo_action()
        elif ctrl and kc == 68:
            self._duplicate()
        elif (ctrl and kc == 66) or (not ctrl and kc == 83):
            self._cut_here()
        elif ctrl and kc in (187, 107):
            self._zoom_at(1.25)
        elif ctrl and kc in (189, 109):
            self._zoom_at(0.8)
        elif ctrl and kc in (48, 96):
            self._zoom_fit()
        elif (ctrl and kc == 79) or (not ctrl and kc == 73):
            self._add_dialog()
        elif not ctrl and kc == 77:
            self._toggle_mute()
        elif not ctrl and kc == 84:
            self._add_text()
        elif not ctrl and kc == 80:
            self._toggle_insp()
        elif not ctrl and kc == 82:
            self._toggle_rec()
        else:
            return None
        return "break"

    def _update_info(self):
        if self.busy:
            return
        total = self._total()
        target = float(self.cfg["target_mb"])
        if getattr(self, "_xfmt", "video") == "audio":
            kb = self._mp3_kbps(total, target)
            self.info_lbl.config(text=(f"🎵 MP3 · {kb} kbps" if kb else E("ed_q_long")),
                                 fg=(C_GREEN if kb >= 128 else host.C_WARN if kb else C_RED))
            self.export_btn.config(state=("normal" if kb else "disabled"))
            return
        if getattr(self, "_xfmt", "video") == "gif":
            okg = total <= 30
            self.info_lbl.config(text=("🎞 GIF" if okg else dc_core._t("core_gif_long")),
                                 fg=(C_GREEN if okg else C_RED))
            self.export_btn.config(state=("normal" if okg else "disabled"))
            return
        has_a = bool(self.snds) or any(
            self._src(self.pieces[ix])["has_audio"] and not self.pieces[ix]["mute"]
            for ix in self.order) or any(
            self.sources[o["src"]]["has_audio"] and not o["mute"] for o in self.ovls)
        v = dc_core.fit_bitrates(total, target, self.cfg["audio_kbps"], has_a)[1] or 0
        if v >= 600: col, tag = C_GREEN, E("ed_q_good")
        elif v >= 150: col, tag = host.C_WARN, E("ed_q_ok")
        elif v >= dc_core.MIN_VKBPS: col, tag = host.C_WARN, E("ed_q_weak")
        else: col, tag = C_RED, E("ed_q_long")
        self.info_lbl.config(text=tag, fg=col)   # без цифр — лише оцінка якості
        self.export_btn.config(state=("normal" if v >= dc_core.MIN_VKBPS else "disabled"))

    # ----------------------------------------------------------- експорт --- #
    def _is_simple(self):
        """Одне (початкове) джерело, без картинок/звуків/тексту/швидкості/муту/масштабу/
        фільтрів -> можна старим ШВИДКИМ шляхом compress_segments."""
        if (len(self.sources) != 1 or self.snds or self.ovls or self.texts
                or self._ratio != "orig" or self._bgmode != "black"):
            return False
        for ix in self.order:
            p = self.pieces[ix]
            if (p["src"] != 0 or p["speed"] != 1.0 or p["mute"] or self._is_transformed(p)
                    or not fx.is_default(p) or p.get("tr")):
                return False
        return True

    def _transform_vf(self, p, cw, ch):
        """Фільтр композиції кліпа на канвас cw×ch: поворот/колір + вписати + zoom/nx/ny."""
        if fx.g(p, "novideo"):            # «тільки звук»: чорний кадр потрібного розміру
            return f"scale={cw}:{ch},setsar=1,drawbox=c=black:t=fill"
        src = self.sources[p["src"]]
        iw, ih = fx.eff_dims(src["w"] or cw, src["h"] or ch, p)
        f0 = min(cw / float(iw), ch / float(ih))
        sw = max(2, int(iw * f0 * p["zoom"] / 2) * 2)
        sh = max(2, int(ih * f0 * p["zoom"] / 2) * 2)
        cx = cw / 2.0 + p["nx"] * cw
        cy = ch / 2.0 + p["ny"] * ch
        x0 = int(round(sw / 2.0 - cx))
        y0 = int(round(sh / 2.0 - cy))
        px, py = max(0, -x0), max(0, -y0)
        pw = max(sw + px, x0 + px + cw)
        ph = max(sh + py, y0 + py + ch)
        pre = fx.pre_vf(p)
        if self._bgmode == "blur" and (sw < cw or sh < ch or x0 > 0 or y0 > 0
                                       or x0 + cw > sw or y0 + ch > sh):
            # поля кадру заповнює це ж відео, розмите на весь екран (як у CapCut)
            self._uidn += 1
            u = self._uidn
            x, y = int(round(cx - sw / 2.0)), int(round(cy - sh / 2.0))
            return ((pre + "," if pre else "") +
                    f"split=2[bg{u}][fg{u}];[bg{u}]scale={cw}:{ch}:force_original_aspect_ratio=increase,"
                    f"crop={cw}:{ch},boxblur=20:2,eq=brightness=-0.06[bb{u}];"
                    f"[fg{u}]scale={sw}:{sh}[ff{u}];[bb{u}][ff{u}]overlay={x}:{y}")
        return ((pre + "," if pre else "") +
                f"scale={sw}:{sh},pad={pw}:{ph}:{px}:{py}:black,"
                f"crop={cw}:{ch}:{x0 + px}:{y0 + py}")

    @staticmethod
    def _atempo(sp):
        """Ланцюжок atempo для будь-якої швидкості (кожна ланка в межах 0.5..2)."""
        parts = []
        v = sp
        while v > 2.0:
            parts.append("atempo=2.0"); v /= 2.0
        while v < 0.5:
            parts.append("atempo=0.5"); v /= 0.5
        parts.append(f"atempo={v:g}")
        return ",".join(parts)

    def _render_montage(self, tmpd, prog, cancel):
        """Рендерить монтаж у ОДИН нормалізований mp4 (канвас, CFR, transform, колір,
        speed, гучність, фейди; тиша замість відсутнього звуку; картинки -> loop).
        Повертає (шлях|None, total)."""
        clips = [self.pieces[ix] for ix in self.order]
        cw, ch, fps = self._ccw, self._cch, self._cfps
        durs = [(p["e"] - p["s"]) / p["speed"] for p in clips]
        total = sum(durs)
        files = []
        acc = 0.0
        for i, p in enumerate(clips):
            if cancel and cancel():
                return None, total
            src = self._src(p)
            dd = durs[i]
            f = os.path.join(tmpd, f"n{i:03d}.mp4")
            vf = self._transform_vf(p, cw, ch)
            vfade = fx.fade_win(0.0, dd, fx.g(p, "fin"), fx.g(p, "fout"), "v")
            afade = fx.fade_win(0.0, dd, fx.g(p, "fin"), fx.g(p, "fout"), "a")
            base = acc / total * 88.0
            span = dd / total * 88.0
            if src["kind"] == "image":
                vfi = ",".join([vf, "setsar=1"] + vfade)
                cmd = ["ffmpeg", "-y", "-loop", "1", "-framerate", f"{fps:g}",
                       "-t", f"{dd:.3f}", "-i", src["path"],
                       "-f", "lavfi", "-t", f"{dd:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
                       "-map", "0:v", "-map", "1:a", "-t", f"{dd:.3f}",
                       "-vf", vfi, "-r", f"{fps:g}",
                       "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                       "-video_track_timescale", "90000", f]
            else:
                sp = p["speed"]
                if sp != 1.0:
                    vf += f",setpts=PTS/{sp:g}"
                vf = ",".join([vf, "setsar=1"] + vfade)
                vol = fx.g(p, "vol")
                use_a = src["has_audio"] and not p["mute"] and vol > 0.005
                cmd = ["ffmpeg", "-y", "-ss", f"{p['s']:.3f}", "-i", src["path"]]
                if not use_a:
                    cmd += ["-f", "lavfi", "-t", f"{dd:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
                            "-map", "0:v", "-map", "1:a"]
                cmd += ["-t", f"{dd:.3f}", *dc_core.cfr_args(), "-r", f"{fps:g}",
                        "-vf", vf,
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                        "-pix_fmt", "yuv420p"]
                if use_a:
                    af = ([self._atempo(sp)] if sp != 1.0 else []) + ["aresample=44100"]
                    af += fx.audio_chain(p, vol, afade)
                    cmd += ["-af", ",".join(af), "-ac", "2", "-c:a", "aac", "-b:a", "192k"]
                else:
                    cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
                cmd += ["-video_track_timescale", "90000", f]
            rc = dc_core._run_pass(cmd, dd, base, span, prog, cancel)
            if rc != 0 or not os.path.exists(f):
                dc_core.dlog(f"MONTAGE clip {i} FAIL rc={rc} cmd={' '.join(cmd[:24])}")
                return None, total
            files.append(f)
            acc += dd

        trs = [self._tr_d(k) for k in range(len(clips))]
        if any(x > 0.01 for x in trs):
            joined = os.path.join(tmpd, "joined.mp4")
            if not self._xfade_join(files, durs, trs, clips, joined, prog, cancel):
                dc_core.dlog("MONTAGE xfade FAIL")
                return None, total
            total = max(0.1, total - sum(trs))
            if prog:
                prog(92.0)
            joined = self._compose(tmpd, joined, total, prog, cancel)
            if prog and joined:
                prog(96.0)
            return joined, total

        # склейка (усі сегменти нормалізовані однаково -> copy)
        listf = os.path.join(tmpd, "list.txt")
        with open(listf, "w", encoding="utf-8") as fh:
            for pf in files:
                fh.write("file '%s'\n" % pf.replace("\\", "/").replace("'", "'\\''"))
        joined = os.path.join(tmpd, "joined.mp4")
        rc = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listf,
                             "-c", "copy", "-movflags", "+faststart", joined],
                            capture_output=True, creationflags=dc_core.NO_WINDOW).returncode
        if rc != 0 or not os.path.exists(joined):
            dc_core.dlog("MONTAGE concat FAIL")
            return None, total
        if prog:
            prog(92.0)

        # композиція: НАКЛАДКИ + ТЕКСТИ поверх відео + додані звуки — одним проходом
        joined = self._compose(tmpd, joined, total, prog, cancel)
        if prog and joined:
            prog(96.0)
        return joined, total

    def _xfade_join(self, files, durs, trs, clips, out, prog, cancel):
        """Склейка з переходами: на стику з переходом — xfade + acrossfade, без нього — concat."""
        norm = f"settb=AVTB,fps={self._cfps:g},format=yuv420p"
        cmd = ["ffmpeg", "-y"]
        for f in files:
            cmd += ["-i", f]
        fc = [f"[{i}:v]{norm}[n{i}]" for i in range(len(files))]
        vl, al = "[n0]", "[0:a]"
        cum = durs[0]
        for i in range(1, len(files)):
            d = trs[i]
            if d > 0.01:
                typ = (clips[i].get("tr") or {}).get("type", "fade")
                if typ not in fx.TRANSITIONS:
                    typ = "fade"
                off = max(0.0, cum - d)
                fc.append(f"{vl}[n{i}]xfade=transition={typ}:duration={d:.3f}:offset={off:.3f}[x{i}]")
                fc.append(f"{al}[{i}:a]acrossfade=d={d:.3f}[a{i}]")
                cum = off + durs[i]
            else:
                fc.append(f"{vl}{al}[n{i}][{i}:a]concat=n=2:v=1:a=1[c{i}][a{i}]")
                cum += durs[i]
            fc.append(f"[{'x' if d > 0.01 else 'c'}{i}]{norm}[v{i}]")
            vl, al = f"[v{i}]", f"[a{i}]"
        cmd += ["-filter_complex", ";".join(fc), "-map", vl, "-map", al,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]
        rc = dc_core._run_pass(cmd, cum, 88.0, 4.0, prog, cancel)
        if rc != 0 or not os.path.exists(out):
            dc_core.dlog("XFADE cmd: " + " ".join(cmd)[-700:])
            return False
        return True

    def _overlay_graph(self, cmd, fc, vin, ain, idx, total, tmpd, cw=None, ch=None, hwdec=False):
        """Додає в граф накладки (прозорість/фейди/колір), тексти (drawtext) і звуки
        (гучність/фейди). Входи дописує в cmd, фільтри — у fc.
        Повертає (vout, aout, idx, відео_змінилось, звук_змінився)."""
        # позиції на доріжці (з пропусками) -> час ЕКСПОРТУ (пропуски стиснуто)
        ovls = [(o, self._gapless(o["at"])) for o in self.ovls]
        ovls = [(o, at) for o, at in ovls if at < total - 0.05]
        snds = [(s, self._gapless(s["at"])) for s in self.snds
                if os.path.isfile(s["path"]) and s["vol"] > 0.005]
        snds = [(s, at) for s, at in snds if at < total - 0.05]
        texts = []
        if self._font:
            for t in self.texts:
                if not t["text"].strip():
                    continue
                a = self._gapless(t["at"])
                b = min(total, self._gapless(t["at"] + t["dur"]))
                if b - a > 0.05:
                    texts.append((t, a, b))
        cw, ch = (cw or self._ccw), (ch or self._cch)
        alabs = []
        for j, (o, at) in enumerate(ovls):
            src = self.sources[o["src"]]
            d = min(o["e"] - o["s"], total - at)
            if src["kind"] == "image":
                cmd += ["-loop", "1", "-t", f"{d:.3f}", "-i", src["path"]]
            else:
                cmd += [*(self._hwdec_args(src) if hwdec else []),
                        "-ss", f"{o['s']:.3f}", "-t", f"{d:.3f}", "-i", src["path"]]
            ovf, x, y = self._ovl_vf(o, cw, ch)
            fades = fx.fade_win(0.0, o["e"] - o["s"], fx.g(o, "fin"), fx.g(o, "fout"), "v", alpha=True)
            if fades:
                ovf += ",format=rgba," + ",".join(fades)
            fc.append(f"[{idx}:v]{ovf},setpts=PTS-STARTPTS+{at:.3f}/TB[ow{j}]")
            fc.append(f"{vin}[ow{j}]overlay={x}:{y}:"
                      f"enable='between(t,{at:.3f},{at + d:.3f})'[vb{j}]")
            vin = f"[vb{j}]"
            vol = fx.g(o, "vol")
            if src["kind"] == "video" and src["has_audio"] and not o["mute"] and vol > 0.005:
                ms = int(at * 1000)
                af = [f"atrim=0:{d:.3f}", "aresample=44100"] + fx.audio_chain(o,
                    vol, fx.fade_win(0.0, o["e"] - o["s"], fx.g(o, "fin"), fx.g(o, "fout"), "a"))
                fc.append(f"[{idx}:a]{','.join(af)},adelay={ms}|{ms}[oa{j}]")
                alabs.append(f"[oa{j}]")
            idx += 1
        for k, (t, a, b) in enumerate(texts):
            tf = fx.write_text_file(t, tmpd, f"e{k}")
            fc.append(f"{vin}{fx.drawtext(t, cw, ch, self._font, tf, a, b)}[vt{k}]")
            vin = f"[vt{k}]"
        for k, (sn, at) in enumerate(snds):
            cmd += ["-ss", f"{float(sn.get('s', 0.0)):.3f}", "-t", f"{sn['dur']:.3f}", "-i", sn["path"]]
            ms = int(at * 1000)
            af = ["aresample=44100"] + fx.audio_chain(sn,
                sn["vol"], fx.fade_win(0.0, sn["dur"], sn.get("fin", 0.0), sn.get("fout", 0.0), "a"))
            fc.append(f"[{idx}:a]{','.join(af)},adelay={ms}|{ms}[sa{k}]")
            alabs.append(f"[sa{k}]")
            idx += 1
        aout = ain
        if alabs:
            fc.append(f"{ain}{''.join(alabs)}amix=inputs={len(alabs) + 1}:"
                      f"duration=first:normalize=0[ao]")
            aout = "[ao]"
        return vin, aout, idx, bool(ovls or texts), bool(alabs)

    def _compose(self, tmpd, joined, total, prog, cancel):
        """Старий (процесорний) шлях: накладки/тексти/звуки поверх уже склеєного відео.
        Повертає новий шлях (або joined, якщо нічого; None=збій)."""
        cmd = ["ffmpeg", "-y", "-i", joined]
        fc = []
        vout, aout, _idx, vch, ach = self._overlay_graph(cmd, fc, "[0:v]", "[0:a]", 1, total, tmpd)
        if not vch and not ach:
            return joined
        out = os.path.join(tmpd, "composed.mp4")
        cmd += ["-filter_complex", ";".join(fc)]
        cmd += ["-map", vout if vch else "0:v", "-map", aout if ach else "0:a"]
        if vch:   # відео змінилось -> перекодовуємо; без накладок можна copy
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                    "-pix_fmt", "yuv420p"]
        else:
            cmd += ["-c:v", "copy"]
        cmd += ["-c:a", "aac", "-b:a", "192k", out]
        rc = dc_core._run_pass(cmd, total, 92.0, 4.0, prog, cancel)
        if rc != 0 or not os.path.exists(out):
            dc_core.dlog("MONTAGE compose FAIL " + " ".join(cmd)[-600:])
            return None
        return out

    # ---------------- ШВИДКИЙ експорт: один прохід на відеокарті ------------- #
    def _gpu_prescale(self, src, p, cw, ch):
        """scale_cuda до розміру, в якому кліп ляже в кадр (з урахуванням зуму) + копія в RAM."""
        iw, ih = int(src.get("w") or 0), int(src.get("h") or 0)
        if iw and ih:
            ew, eh = fx.eff_dims(iw, ih, p)
            f = min(1.0, min(cw / float(ew), ch / float(eh)) * float(p.get("zoom", 1.0)))
            sc = f"scale_cuda={max(2, int(iw * f / 2) * 2)}:{max(2, int(ih * f / 2) * 2)}:format=nv12"
        else:
            sc = "scale_cuda=format=nv12"
        return sc + ",hwdownload,format=nv12"

    def _hwdec_args(self, src):
        """Декодування відео ВІДЕОКАРТОЮ (NVDEC / D3D11VA) — якщо цей файл так декодується.
        Перевіряємо на 0.5 с самого файлу один раз; інакше [] (декодує процесор)."""
        if src.get("kind") != "video" or not self._hwdec_try:
            return []
        if "hwdec" not in src:
            src["hwdec"] = ""
            for dec in self._hwdec_try:
                try:
                    r = subprocess.run(["ffmpeg", "-v", "error", "-hwaccel", dec, "-t", "0.5",
                                        "-i", src["path"], "-an", "-f", "null", "-"],
                                       capture_output=True, creationflags=dc_core.NO_WINDOW,
                                       timeout=20)
                    if r.returncode == 0 and not r.stderr.strip():
                        src["hwdec"] = dec
                        break
                except Exception:
                    pass
            dc_core.dlog(f"HWDEC {src['name']}: {src['hwdec'] or 'cpu'}")
        return ["-hwaccel", src["hwdec"]] if src["hwdec"] else []

    def _single_pass(self, out_path, target, prog, cancel, hw):
        """ВЕСЬ монтаж (кліпи, швидкість, колір, масштаб, фейди, переходи, накладки, текст,
        звуки) одним графом ffmpeg -> одразу стиснене відео енкодером відеокарти (як CapCut).
        Повертає (ok, msg, mb) або None — тоді викликач іде старим шляхом."""
        clips = [self.pieces[ix] for ix in self.order]
        cw, ch, fps = self._ccw, self._cch, self._cfps
        durs = [(p["e"] - p["s"]) / p["speed"] for p in clips]
        trs = [self._tr_d(k) for k in range(len(clips))]
        total = max(0.1, sum(durs) - sum(trs))
        akbps, v_kbps = dc_core.fit_bitrates(total, target, int(self.cfg["audio_kbps"]), True)
        if not v_kbps:
            return False, dc_core._t("core_toolong"), 0.0
        # розмір під ліміт рахуємо НАПЕРЕД і будуємо весь граф одразу в ньому:
        # переходи/текст/розмиття на 480p замість 1080p — у рази менше роботи
        info = {"duration": total, "has_audio": True, "width": cw, "height": ch, "fps": fps}
        scale = (dc_core.pick_auto_scale(info, target, akbps)
                 if self.cfg.get("auto_scale", True) else 0)
        if scale and scale < min(cw, ch):
            k = scale / float(min(cw, ch))
            cw, ch = max(2, int(cw * k / 2) * 2), max(2, int(ch * k / 2) * 2)
        # копіювати повнорозмірні кадри з відеокарти повільніше, ніж декод процесором,
        # тому накладки декодує процесор, а кліпи — відеокарта з масштабом (див. нижче)
        self._hwdec_try = []
        tmpd = tempfile.mkdtemp(prefix="d1p_")
        try:
            cmd = ["ffmpeg", "-y"]
            fc = []
            idx = 0
            afmt = "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"
            for i, p in enumerate(clips):
                src = self._src(p)
                dd = durs[i]
                vf = self._transform_vf(p, cw, ch)
                vfade = fx.fade_win(0.0, dd, fx.g(p, "fin"), fx.g(p, "fout"), "v")
                afade = fx.fade_win(0.0, dd, fx.g(p, "fin"), fx.g(p, "fout"), "a")
                sp = p["speed"]
                if src["kind"] == "image":
                    cmd += ["-loop", "1", "-framerate", f"{fps:g}", "-t", f"{dd:.3f}", "-i", src["path"]]
                    chain = [vf]
                    use_a = False
                else:
                    gpu = hw == "h264_nvenc" and dc_core.gpu_decode_ok(src["path"])
                    cmd += [*(dc_core.GPU_IN if gpu else []), "-ss", f"{p['s']:.3f}",
                            "-t", f"{p['e'] - p['s']:.3f}", "-i", src["path"]]
                    chain = [f"setpts=(PTS-STARTPTS)/{sp:g}", vf]
                    if gpu:   # зменшуємо НА ВІДЕОКАРТІ до потрібного розміру і лише тоді копіюємо
                        chain.insert(0, self._gpu_prescale(src, p, cw, ch))
                    vol = fx.g(p, "vol")
                    use_a = src["has_audio"] and not p["mute"] and vol > 0.005
                chain += [f"fps={fps:g}", f"trim=duration={dd:.3f}", "setpts=PTS-STARTPTS",
                          "setsar=1", "format=yuv420p", "settb=AVTB"] + vfade
                fc.append(f"[{idx}:v]" + ",".join(chain) + f"[cv{i}]")
                if use_a:
                    af = ["asetpts=PTS-STARTPTS"] + ([self._atempo(sp)] if sp != 1.0 else [])
                    af += ["aresample=44100"] + fx.audio_chain(p, fx.g(p, "vol"), afade) + [afmt]
                    af += ["apad", f"atrim=0:{dd:.3f}", "asetpts=PTS-STARTPTS"]
                    fc.append(f"[{idx}:a]" + ",".join(af) + f"[ca{i}]")
                else:                     # кліп без звуку -> тиша рівно на його довжину
                    fc.append(f"anullsrc=r=44100:cl=stereo,atrim=0:{dd:.3f},{afmt}[ca{i}]")
                idx += 1
            # ---- склейка: concat, а на стиках з переходом — xfade + acrossfade ----
            n = len(clips)
            if n == 1:
                vl, al = "[cv0]", "[ca0]"
            elif not any(x > 0.01 for x in trs):
                fc.append("".join(f"[cv{i}][ca{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[jv][ja]")
                vl, al = "[jv]", "[ja]"
            else:
                norm = f"fps={fps:g},format=yuv420p,settb=AVTB"   # fps ставить tb 1/fps -> settb ОСТАННІМ
                vl, al = "[cv0]", "[ca0]"
                cum = durs[0]
                for i in range(1, n):
                    d = trs[i]
                    if d > 0.01:
                        typ = (clips[i].get("tr") or {}).get("type", "fade")
                        if typ not in fx.TRANSITIONS:
                            typ = "fade"
                        off = max(0.0, cum - d)
                        fc.append(f"{vl}[cv{i}]xfade=transition={typ}:duration={d:.3f}:offset={off:.3f}[xf{i}]")
                        fc.append(f"{al}[ca{i}]acrossfade=d={d:.3f}[ja{i}]")
                        cum = off + durs[i]
                        fc.append(f"[xf{i}]{norm}[jv{i}]")
                    else:
                        fc.append(f"{vl}{al}[cv{i}][ca{i}]concat=n=2:v=1:a=1[cc{i}][ja{i}]")
                        cum += durs[i]
                        fc.append(f"[cc{i}]{norm}[jv{i}]")
                    vl, al = f"[jv{i}]", f"[ja{i}]"
            # ---- накладки, текст, звуки — у тому ж графі ----
            vl, al, idx, _vch, _ach = self._overlay_graph(cmd, fc, vl, al, idx, total, tmpd, cw, ch,
                                                         hwdec=True)
            fc.append(f"{vl}format=yuv420p[vout]")
            graph = ";".join(fc)
            ceiling = dc_core.target_ceiling(target)
            kb, mb = max(20, int(v_kbps * 0.93)), 0.0
            for attempt in range(3):
                full = cmd + ["-filter_complex", graph, "-map", "[vout]", "-map", al,
                              *dc_core._hw_args(hw, kb), "-pix_fmt", "yuv420p",
                              *dc_core.audio_enc_args(akbps),
                              "-movflags", "+faststart", out_path]
                rc = dc_core._run_pass(full, total, 0.0, 100.0, prog, cancel)
                if cancel and cancel():
                    return False, dc_core.cancelled_msg(), 0.0
                if rc != 0 or not os.path.exists(out_path):
                    dc_core.dlog(f"SINGLE-PASS {hw} FAIL rc={rc}: " + " ".join(full)[-900:])
                    return None
                mb = os.path.getsize(out_path) / 1024 / 1024
                dc_core.dlog(f"SINGLE-PASS {hw} try={attempt} kbps={kb} -> {mb:.2f} MB (ceil {ceiling:.2f})")
                if mb <= ceiling:
                    return True, "OK", mb
                if kb <= 20 or mb > ceiling * 1.3:
                    break
                kb = max(20, int(kb * (ceiling / mb) * 0.95))
            dc_core.dlog(f"SINGLE-PASS over limit ({mb:.2f} MB) -> exact legacy export")
            return None
        finally:
            shutil.rmtree(tmpd, ignore_errors=True)

    def _render_and_compress(self, out_path, target, prog, cancel):
        tmpd = tempfile.mkdtemp(prefix="dmix_")
        try:
            joined, total = self._render_montage(tmpd, lambda p: prog(p * 0.55), cancel)
            if not joined:
                return False, E("ed_montage_fail"), 0.0
            info = {"duration": total, "has_audio": True,
                    "width": self._ccw, "height": self._cch, "fps": self._cfps}
            scale = (dc_core.pick_auto_scale(info, target, self.cfg["audio_kbps"])
                     if self.cfg.get("auto_scale", True) else 0)
            return dc_core.compress(joined, out_path, target, scale, self.cfg["audio_kbps"],
                                    info, progress_cb=lambda p: prog(55.0 + p * 0.45),
                                    should_cancel=cancel)
        finally:
            shutil.rmtree(tmpd, ignore_errors=True)

    def _export(self):
        if not self.order:
            return
        simple = self._is_simple()
        try:
            hw = dc_core.active_hw()
        except Exception:
            hw = ""
        # один кліп без ефектів -> compress зі start/dur (і так один прохід на відеокарті)
        fast = bool(hw) and not (simple and len(self.order) == 1)
        try:
            dc_core.dlog(f"EDITOR EXPORT build={dc_core.BUILD} simple={simple} hw={hw or 'cpu'} "
                         f"single_pass={fast} clips={len(self.order)} sources={len(self.sources)} "
                         f"snds={len(self.snds)}")
        except Exception:
            pass
        self._pause()
        self.busy = True
        self.export_btn.config(state="disabled")
        target = float(self.cfg["target_mb"])
        out_path = dc_core.output_name(self.file_path, target)
        self._start_export_jokes()
        prog = lambda p: self._ui(lambda: self._set_progress(p, E("ed_saving", p=int(p))))
        self._export_t0 = time.monotonic()

        def legacy():
            if simple:
                segs = [(self.pieces[ix]["s"], self.pieces[ix]["e"]) for ix in self.order]
                scale = (dc_core.pick_auto_scale(self.info, target, self.cfg["audio_kbps"])
                         if self.cfg.get("auto_scale", True) else 0)
                return dc_core.compress_segments(
                    self.file_path, out_path, target, scale, self.cfg["audio_kbps"],
                    self.info, segs, progress_cb=prog, should_cancel=self._cancelled)
            return self._render_and_compress(out_path, target, prog, self._cancelled)

        def worker():
            try:
                res = None
                if fast:
                    res = self._single_pass(out_path, target, prog, self._cancelled, hw)
                    if res is None and not self._cancelled():
                        dc_core.dlog("SINGLE-PASS failed -> legacy export")
                        prog(0.0)
                if res is None:
                    res = legacy()
                ok, msg, mb = res
            except Exception as e:
                import traceback
                dc_core.dlog("EXPORT EXCEPTION: " + repr(e) + "\n" + traceback.format_exc())
                ok, msg, mb = False, f'{E("ov_err_prefix")} {str(e)[:60]}', 0.0
            dc_core.dlog(f"EDITOR EXPORT done ok={ok} in {time.monotonic() - self._export_t0:.1f}s "
                         f"mb={mb:.2f}")
            self._ui(lambda: self._done(ok, out_path, mb, msg))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------ формат збереження: відео / звук / GIF ---- #
    def _update_fmt(self):
        try:
            self.fmt_btn.config(text={"video": "🎬 MP4 ▾", "audio": "🎵 MP3 ▾", "gif": "🎞 GIF ▾"}[self._xfmt])
            self.export_btn.config(text={"video": E("ed_export"), "audio": E("ed_export_audio"),
                                         "gif": E("ed_export_gif")}[self._xfmt])
        except (tk.TclError, AttributeError):
            pass

    def _fmt_menu(self):
        if self.busy:
            return
        m = self._menu_new()
        for k in ("video", "audio", "gif"):
            m.add_command(label=E("fmt_" + k) + ("   ✓" if k == self._xfmt else ""),
                          command=lambda k=k: self._set_fmt(k))
        b = self.fmt_btn
        self._popup(m, b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    def _set_fmt(self, k):
        self._xfmt = k
        self.cfg["editor_export"] = k          # запам'ятати вибір
        try:
            host.save_config(self.cfg)
        except Exception:
            pass
        self._update_fmt()
        self._update_info()

    def _export_any(self):
        if self._xfmt == "audio":
            self._export_audio()
        elif self._xfmt == "gif":
            self._export_gif()
        else:
            self._export()

    @staticmethod
    def _mp3_kbps(total, target):
        """Найкращий бітрейт MP3, з яким звук влазить у ліміт Discord (0 — задовго)."""
        budget = dc_core.target_ceiling(target) * 1024 * 1024 * 0.97 * 8 / 1000.0 / max(0.1, total)
        for kb in (192, 160, 128, 112, 96, 80, 64, 56, 48, 40, 32):
            if kb <= budget:
                return kb
        return 0

    def _export_audio(self):
        if not self.order:
            return
        total = self._total()
        target = float(self.cfg["target_mb"])
        kb = self._mp3_kbps(total, target)
        if not kb:
            self.info_lbl.config(text=E("ed_q_long"), fg=C_RED)
            return
        self._pause()
        self.busy = True
        self.export_btn.config(state="disabled")
        self.fmt_btn.config(state="disabled")
        out_path = os.path.splitext(dc_core.output_name(self.file_path, target))[0] + ".mp3"
        self._start_export_jokes()
        prog = lambda p: self._ui(lambda: self._set_progress(p, E("ed_saving", p=int(p))))
        t0 = time.monotonic()

        def worker():
            try:
                ok, msg, mb = self._render_audio(out_path, kb, total, prog, self._cancelled)
            except Exception as e:
                import traceback
                dc_core.dlog("AUDIO EXPORT EXCEPTION: " + repr(e) + "\n" + traceback.format_exc())
                ok, msg, mb = False, f'{E("ov_err_prefix")} {str(e)[:60]}', 0.0
            dc_core.dlog(f"AUDIO EXPORT ok={ok} kbps={kb} {mb:.2f} MB in {time.monotonic() - t0:.1f}s")
            self._ui(lambda: self._done(ok, out_path, mb, msg))
        threading.Thread(target=worker, daemon=True).start()

    def _render_audio(self, out_path, kb, total, prog, cancel):
        """Звук УСЬОГО монтажу (гучність, фейди, швидкість, переходи, накладки, додані звуки)
        -> MP3. Відео не декодується зовсім (-vn на входах) — дуже швидко."""
        clips = [self.pieces[ix] for ix in self.order]
        durs = [(p["e"] - p["s"]) / p["speed"] for p in clips]
        trs = [self._tr_d(k) for k in range(len(clips))]
        afmt = "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"
        cmd = ["ffmpeg", "-y"]
        fc = []
        idx = 0
        any_audio = False
        for i, p in enumerate(clips):
            src = self._src(p)
            dd = durs[i]
            sp = p["speed"]
            vol = fx.g(p, "vol")
            if src["kind"] == "video" and src["has_audio"] and not p["mute"] and vol > 0.005:
                any_audio = True
                cmd += ["-vn", "-ss", f"{p['s']:.3f}", "-t", f"{p['e'] - p['s']:.3f}", "-i", src["path"]]
                af = ["asetpts=PTS-STARTPTS"] + ([self._atempo(sp)] if sp != 1.0 else [])
                af += ["aresample=44100"] + fx.audio_chain(p,
                    vol, fx.fade_win(0.0, dd, fx.g(p, "fin"), fx.g(p, "fout"), "a")) + [afmt]
                af += ["apad", f"atrim=0:{dd:.3f}", "asetpts=PTS-STARTPTS"]
                fc.append(f"[{idx}:a]" + ",".join(af) + f"[ca{i}]")
                idx += 1
            else:
                fc.append(f"anullsrc=r=44100:cl=stereo,atrim=0:{dd:.3f},{afmt}[ca{i}]")
        n = len(clips)
        if n == 1:
            al = "[ca0]"
        elif not any(x > 0.01 for x in trs):
            fc.append("".join(f"[ca{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[ja]")
            al = "[ja]"
        else:
            al = "[ca0]"
            for i in range(1, n):
                if trs[i] > 0.01:
                    fc.append(f"{al}[ca{i}]acrossfade=d={trs[i]:.3f}[ja{i}]")
                else:
                    fc.append(f"{al}[ca{i}]concat=n=2:v=0:a=1[ja{i}]")
                al = f"[ja{i}]"
        labs = []
        for j, o in enumerate(self.ovls):
            src = self.sources[o["src"]]
            at = self._gapless(o["at"])
            vol = fx.g(o, "vol")
            if (at >= total - 0.05 or src["kind"] != "video" or not src["has_audio"]
                    or o["mute"] or vol <= 0.005):
                continue
            any_audio = True
            d = min(o["e"] - o["s"], total - at)
            cmd += ["-vn", "-ss", f"{o['s']:.3f}", "-t", f"{d:.3f}", "-i", src["path"]]
            ms = int(at * 1000)
            af = [f"atrim=0:{d:.3f}", "aresample=44100"] + fx.audio_chain(o,
                vol, fx.fade_win(0.0, o["e"] - o["s"], fx.g(o, "fin"), fx.g(o, "fout"), "a"))
            fc.append(f"[{idx}:a]{','.join(af)},adelay={ms}|{ms}[oa{j}]")
            labs.append(f"[oa{j}]")
            idx += 1
        for k, sn in enumerate(self.snds):
            at = self._gapless(sn["at"])
            if at >= total - 0.05 or sn["vol"] <= 0.005 or not os.path.isfile(sn["path"]):
                continue
            any_audio = True
            cmd += ["-ss", f"{float(sn.get('s', 0.0)):.3f}", "-t", f"{sn['dur']:.3f}", "-i", sn["path"]]
            ms = int(at * 1000)
            af = ["aresample=44100"] + fx.audio_chain(sn,
                sn["vol"], fx.fade_win(0.0, sn["dur"], sn.get("fin", 0.0), sn.get("fout", 0.0), "a"))
            fc.append(f"[{idx}:a]{','.join(af)},adelay={ms}|{ms}[sa{k}]")
            labs.append(f"[sa{k}]")
            idx += 1
        if not any_audio:
            return False, E("ed_no_audio"), 0.0
        if labs:
            fc.append(f"{al}{''.join(labs)}amix=inputs={len(labs) + 1}:duration=first:normalize=0[mx]")
            al = "[mx]"
        fc.append(f"{al}aresample=44100,{afmt}[aout]")
        full = cmd + ["-filter_complex", ";".join(fc), "-map", "[aout]", "-c:a", "libmp3lame", "-compression_level", "9",
                      "-b:a", f"{kb}k", "-ar", "44100", "-ac", "2", out_path]
        rc = dc_core._run_pass(full, total, 0.0, 100.0, prog, cancel)
        if cancel and cancel():
            return False, dc_core.cancelled_msg(), 0.0
        if rc != 0 or not os.path.exists(out_path):
            dc_core.dlog("AUDIO EXPORT FAIL: " + " ".join(full)[-800:])
            return False, E("ed_save_fail"), 0.0
        return True, "OK", os.path.getsize(out_path) / 1024 / 1024

    def _export_gif(self):
        if not self.order:
            return
        total = self._total()
        if total > 30:
            self.info_lbl.config(text=dc_core._t("core_gif_long"), fg=C_RED)
            return
        self._pause()
        self.busy = True
        self.export_btn.config(state="disabled")
        self.gif_btn.config(state="disabled")
        out_path = dc_core.gif_out_name(self.file_path)
        self._start_export_jokes()
        prog = lambda p: self._ui(lambda: self._set_progress(p, E("ed_gif_prog", p=int(p))))

        if self._is_simple():
            segs = [(self.pieces[ix]["s"], self.pieces[ix]["e"]) for ix in self.order]

            def worker():
                try:
                    ok, msg, mb = dc_core.export_gif(self.file_path, out_path, segs,
                                                     progress_cb=prog)
                except Exception as e:
                    dc_core.dlog("GIF EXCEPTION: " + repr(e))
                    ok, msg, mb = False, f'{E("ov_err_prefix")} {str(e)[:60]}', 0.0
                self._ui(lambda: self._done(ok, out_path, mb, msg))
        else:
            def worker():
                tmpd = tempfile.mkdtemp(prefix="dgifm_")
                try:
                    joined, tot = self._render_montage(tmpd, lambda p: prog(p * 0.6),
                                                       self._cancelled)
                    if not joined:
                        ok, msg, mb = False, E("ed_montage_fail"), 0.0
                    else:
                        ok, msg, mb = dc_core.export_gif(
                            joined, out_path, [(0.0, tot)],
                            progress_cb=lambda p: prog(60.0 + p * 0.4))
                except Exception as e:
                    dc_core.dlog("GIF EXCEPTION: " + repr(e))
                    ok, msg, mb = False, f'{E("ov_err_prefix")} {str(e)[:60]}', 0.0
                finally:
                    shutil.rmtree(tmpd, ignore_errors=True)
                self._ui(lambda: self._done(ok, out_path, mb, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _start_export_jokes(self):
        self._jokes_eff = jokes.facts_for(host.LANG)
        self._joke_i = host.kernel32.GetTickCount() % max(1, len(self._jokes_eff))
        self._rotate_export_joke()

    def _rotate_export_joke(self):
        try:
            if not self.busy or not self.joke_lbl.winfo_exists():
                self.joke_lbl.config(text="")
                return
            eff = getattr(self, "_jokes_eff", None) or ["💡"]
            self.joke_lbl.config(text="💡  " + eff[self._joke_i % len(eff)])
            self._joke_i += 1
        except (tk.TclError, AttributeError):
            return
        self._joke_after = self.after(4500, self._rotate_export_joke)

    def _cancelled(self):
        return self._cancel_flag

    def _ui(self, fn):
        """Виклик у головному потоці Tk з робочого потоку (тихо, якщо вікно вже закрите)."""
        if self._closed:
            return
        try:
            self.after(0, lambda: None if self._closed else fn())
        except Exception:
            pass

    def _done(self, ok, out_path, mb, msg):
        if self._closed:                        # редактор закрили під час експорту
            if not ok and os.path.exists(out_path):
                try: os.remove(out_path)
                except OSError: pass
            return
        self.busy = False                       # зупиняє ротацію фактів
        self._set_progress(None)
        try:
            self.joke_lbl.config(text="")
            self.gif_btn.config(state="normal")
        except tk.TclError:
            pass
        if not ok:
            if os.path.exists(out_path):
                try: os.remove(out_path)
                except OSError: pass
            self.export_btn.config(state="normal")
            self.info_lbl.config(text=msg or E("ed_save_fail"), fg=C_RED)
            return
        host.play_done_sound(self.cfg)          # звук «готово»
        try:                                    # копія в «Мої монтажі» (Ctrl+Alt+E)
            import library
            library.add(out_path)
        except Exception:
            pass
        try:                                    # статистика: обрізка/монтаж/gif = теж стиснення
            import stats
            orig_mb = os.path.getsize(self.file_path) / (1024 * 1024)
            stats.record("audio" if out_path.lower().endswith(".mp3") else "video",
                         orig_mb, mb, [out_path])
        except Exception:
            pass
        try:
            host.set_clipboard_files([out_path])
            if self.watcher:
                self.watcher.mark_self_clipboard()
        except Exception:
            pass
        pasted = ""
        if self.cfg.get("auto_paste", True) and self.discord_hwnd:
            try:
                host.user32.SetForegroundWindow(self.discord_hwnd)
                self.after(180, host.send_ctrl_v)
                pasted = E("ed_pasted")
            except Exception:
                pasted = ""
        self.info_lbl.config(text=E("ed_done", mb=f"{mb:.2f}", u=E("unit_mb"), pasted=pasted),
                             fg=C_GREEN)
        policy = self.cfg.get("keep_local", "ask")
        if policy == "ask":
            self._ask_keep(out_path)
        else:
            if policy == "never":
                self._schedule_delete([out_path])
            self.after(2600, self._close)

    def _ask_keep(self, out_path):
        ec = self.export_btn.master
        for w in ec.winfo_children():
            w.destroy()
        self.info_lbl.config(text=E("ov_keep_q"), fg=C_TEXT)
        self._btn(ec, E("ov_keep"), self._close, primary=False).pack(side="left", padx=4)
        self._btn(ec, E("ov_delete"),
                  lambda: (self._schedule_delete([out_path]), self._close())).pack(side="left", padx=4)

    def _schedule_delete(self, paths):
        """Видаляє файли з затримкою у ФОНОВОМУ потоці (переживає закриття вікна)."""
        paths = [p for p in paths if p]
        if not paths:
            return

        def _rm():
            time.sleep(10)
            for p in paths:
                for _ in range(5):
                    try:
                        if os.path.exists(p):
                            os.remove(p)
                        break
                    except OSError:
                        time.sleep(2)
        threading.Thread(target=_rm, daemon=True).start()

    def _close(self):
        if self._closed:
            return
        self._closed = True
        self._cancel_flag = True       # експорт, якщо йде, зупиняється (ffmpeg гаситься)
        if self._rec:                  # запис голосу — зупиняємо ffmpeg мікрофона
            try:
                self._rec["proc"].kill()
            except Exception:
                pass
        self._pause()                  # зупиняємо ffplay і його опитування
        self._disable_dnd()            # повертаємо оригінальний WndProc (інакше краш після destroy)
        shutil.rmtree(self._tmp, ignore_errors=True)
        try:
            self.destroy()
        finally:
            if self.on_close:
                self.on_close()
