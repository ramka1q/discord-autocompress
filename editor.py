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
import os
import shutil
import subprocess
import tempfile
import threading
import time

import tkinter as tk
from tkinter import filedialog

import dc_core
import discord_overlay as host
import jokes
import media

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
C_TRACK = "#17181c"          # тло доріжки
C_CLIP = "#3a3d46"           # кліп у монтажі
C_CLIP_SEL = host.C_BLURPLE  # вибраний кліп
C_HANDLE = "#ffffff"         # білі ручки-хендли обрізки (як у CapCut)
C_PLAY = "#ffffff"           # плейхед
C_SND = "#3ba55d"            # блоки доданих звуків
C_OVL = "#a06be0"            # блоки накладок (медіа поверх відео)
C_WAVE_IN = "#dfe6ff"        # хвиля всередині ВИБРАНОГО кліпа
TLH = 66                     # висота доріжки монтажу
THUMB_W = 40                 # ширина кадру кіно-стрічки
IMG_DUR = 4.0                # скільки секунд показувати додану картинку (тягнеться ручками)
IMG_MAX = 3600.0             # стеля розтягування картинки


def fmt(t):
    t = max(0, t)
    return f"{int(t // 60)}:{int(t % 60):02d}.{int((t * 10) % 10)}"


class VideoEditor(tk.Toplevel):
    VW, VH = 480, 270
    TW = 600

    def __init__(self, master, file_path, info, cfg, discord_hwnd, watcher, on_close):
        super().__init__(master)
        self.file_path, self.info, self.cfg = file_path, info, cfg
        self.discord_hwnd, self.watcher, self.on_close = discord_hwnd, watcher, on_close

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
        # накладки ПОВЕРХ відео (картинка-в-картинці): {"src","s","e","at","zoom","nx","ny","mute"}
        self.ovls = []
        self.sel_ovl = None          # вибрана накладка -> рамка на прев'ю керує НЕЮ
        self._ovl_rects = []
        self._ovl_drag = None

        # ---- канвас експорту = розміри першого відео (кап 1920) ----
        w0 = int(info.get("width") or 1280) or 1280
        h0 = int(info.get("height") or 720) or 720
        k = min(1.0, 1920.0 / max(w0, h0))
        self._ccw = max(2, int(w0 * k / 2) * 2)
        self._cch = max(2, int(h0 * k / 2) * 2)
        self._cfps = min(60.0, float(info.get("fps", 30) or 30))
        pk = min(self.VW / self._ccw, self.VH / self._cch)
        self._pcw = max(2, int(self._ccw * pk / 2) * 2)   # прев'ю-канвас (вписаний у 480x270)
        self._pch = max(2, int(self._cch * pk / 2) * 2)

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
        self._ffplay_pos = None      # РЕАЛЬНА позиція ffplay (парситься з його -stats)
        self._stat_offset = None
        self._stat_log_t = 0.0
        self._sel_xs = self._sel_xe = 0
        self._clip_rects = []        # (slot, ix, cx1, cx2) для кліків по кліпах
        self._snd_rects = []         # (i, x1, x2) блоки звуків на нижній смужці
        self._snd_drag = None
        self._undo = []; self._redo = []
        self._zoom = 1.0
        self._scroll = 0.0
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

        self.title("✂ Редактор відео — Discord Auto-Compress")
        self.configure(bg=C_BG)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._build()
        self._redraw()
        self._show_poster(0.0)
        self._gen_visuals(si)        # кіно-стрічка + хвиля для першого джерела
        self.after(400, self._enable_dnd)   # перетягування файлів (після мапінгу вікна)

    # ------------------------------------------------------------ джерела -- #
    def _new_piece(self, si, s, e):
        return {"src": si, "s": float(s), "e": float(e),
                "zoom": 1.0, "nx": 0.0, "ny": 0.0, "speed": 1.0, "mute": False}

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
        tk.Label(self, text="Клік по кліпу — вибрати · ручки — обрізати · клік по ВІДЕО — масштаб/позиція · ПКМ — меню (накладки теж) · тягни файли сюди",
                 bg=C_BG, fg=C_MUTED, font=(FONT, 9)).pack(pady=(10, 6))
        self.video = tk.Canvas(self, width=self.VW, height=self.VH, bg="black", highlightthickness=0)
        self.video.pack()
        self.video.bind("<Button-1>", self._video_press)
        self.video.bind("<B1-Motion>", self._video_motion)
        self.video.bind("<ButtonRelease-1>", self._video_release)
        self.video.bind("<Double-Button-1>", lambda e: self._tf_reset())

        pc = tk.Frame(self, bg=C_BG); pc.pack(pady=6)
        self.play_btn = self._btn(pc, "▶ Грати", self._toggle_play)
        self.play_btn.pack(side="left", padx=3)
        self._btn(pc, "⏮", self._to_start, primary=False).pack(side="left", padx=3)
        self._btn(pc, "✂ Розрізати", self._cut_here).pack(side="left", padx=3)
        self._btn(pc, "➕ Додати", self._add_dialog, primary=False).pack(side="left", padx=(12, 3))
        self.undo_btn = self._btn(pc, "↶", self._undo_action, primary=False)
        self.undo_btn.pack(side="left", padx=(12, 3))
        self.redo_btn = self._btn(pc, "↷", self._redo_action, primary=False)
        self.redo_btn.pack(side="left", padx=3)

        # ---- доріжка НАКЛАДОК (медіа поверх відео, як у CapCut) ----
        self.OVL_H = 26
        self.ovl = tk.Canvas(self, width=self.TW, height=self.OVL_H, bg=C_TRACK, highlightthickness=0)
        self.ovl.pack(padx=14, pady=(4, 0))
        self.ovl.bind("<Button-1>", self._ovl_press)
        self.ovl.bind("<B1-Motion>", self._ovl_motion)
        self.ovl.bind("<ButtonRelease-1>", self._ovl_release)
        self.ovl.bind("<Button-3>", self._ovl_menu)
        # ---- доріжка монтажу: кіно-стрічка + ручки обрізки + плейхед ----
        self.tl = tk.Canvas(self, width=self.TW, height=TLH, bg=C_TRACK, highlightthickness=0)
        self.tl.pack(padx=14, pady=(2, 2))
        # аудіо-хвиля кліпів + смужка ДОДАНИХ звуків (тягнуться мишкою, ПКМ — меню)
        self.WAVE_H = 58
        self.wave = tk.Canvas(self, width=self.TW, height=self.WAVE_H, bg=C_TRACK, highlightthickness=0)
        self.wave.pack(padx=14, pady=(0, 8))
        self.tl.bind("<Button-1>", self._tl_press)
        self.tl.bind("<B1-Motion>", self._tl_motion)
        self.tl.bind("<ButtonRelease-1>", self._tl_release)
        self.tl.bind("<Button-3>", self._tl_menu)
        self.tl.bind("<Control-MouseWheel>", self._on_zoom)
        self.tl.bind("<MouseWheel>", self._on_scroll)
        self.wave.bind("<Button-1>", self._wave_press)
        self.wave.bind("<B1-Motion>", self._wave_motion)
        self.wave.bind("<ButtonRelease-1>", self._wave_release)
        self.wave.bind("<Button-3>", self._wave_menu)
        zc = tk.Frame(self, bg=C_BG); zc.pack(pady=(0, 2))
        self._btn(zc, "🔍−", lambda: self._zoom_step(0.8), primary=False).pack(side="left", padx=3)
        self._btn(zc, "🔍+", lambda: self._zoom_step(1.25)).pack(side="left", padx=3)
        tk.Label(zc, text="◀ ▶ стрілки — точно по кадру (Shift = 1с)", bg=C_BG, fg=C_MUTED,
                 font=(FONT, 8)).pack(side="left", padx=8)
        self.bind("<Left>", lambda e: self._nudge(-1, big=False))
        self.bind("<Right>", lambda e: self._nudge(1, big=False))
        self.bind("<Shift-Left>", lambda e: self._nudge(-1, big=True))
        self.bind("<Shift-Right>", lambda e: self._nudge(1, big=True))
        self.bind("<Delete>", lambda e: self._remove())
        try:
            self.focus_set()
        except tk.TclError:
            pass

        sc = tk.Frame(self, bg=C_BG); sc.pack(pady=2)
        self._btn(sc, "◀ Пересунути", lambda: self._move(-1), primary=False).pack(side="left", padx=3)
        self._btn(sc, "Пересунути ▶", lambda: self._move(1), primary=False).pack(side="left", padx=3)
        self._btn(sc, "► Переглянути", self._play_segment, primary=False).pack(side="left", padx=3)
        self._btn(sc, "🗑 Прибрати", self._remove, primary=False).pack(side="left", padx=3)

        self.bind("<Control-z>", lambda e: self._undo_action())
        self.bind("<Control-y>", lambda e: self._redo_action())
        self.bind("<Control-Z>", lambda e: self._redo_action())   # Ctrl+Shift+Z

        self.info_lbl = tk.Label(self, text="", bg=C_BG, fg=C_TEXT, font=(FONT, 11, "bold"))
        self.info_lbl.pack(pady=(8, 0))
        self.joke_lbl = tk.Label(self, text="", bg=C_BG, fg=C_MUTED, font=(FONT, 9),
                                 wraplength=self.VW, justify="center")
        self.joke_lbl.pack(pady=(0, 2))
        ec = tk.Frame(self, bg=C_BG); ec.pack(pady=(2, 12))
        self.export_btn = self._btn(ec, "Зберегти і вставити  ▶", self._export)
        self.export_btn.pack(side="left", padx=4)
        self.gif_btn = self._btn(ec, "🎞 GIF", self._export_gif, primary=False)
        self.gif_btn.pack(side="left", padx=4)
        self._btn(ec, "Скасувати", self._close, primary=False).pack(side="left", padx=4)

    def _btn(self, parent, text, cmd, primary=True):
        bg, hov = (C_BLURPLE, C_BLURPLE_H) if primary else (C_BG2, C_DARK)
        b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=C_TEXT,
                      activebackground=hov, activeforeground=C_TEXT, relief="flat",
                      font=(FONT, 10, "bold"), bd=0, padx=12, pady=7, cursor="hand2")
        b.bind("<Enter>", lambda e: b.config(bg=hov))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

    # ----------------------------------------- додавання медіа (➕ і перетяг) -- #
    def _add_dialog(self):
        pats = " ".join("*" + e for e in
                        sorted(dc_core.VIDEO_EXT | media.IMAGE_EXT | media.AUDIO_EXT))
        try:
            paths = filedialog.askopenfilenames(
                parent=self, title="Додати відео / картинки / звуки",
                filetypes=[("Медіа", pats), ("Всі файли", "*.*")])
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
                    sn = {"path": p, "at": self._playhead_montage_t(), "dur": d,
                          "vol": 1.0, "name": os.path.basename(p), "env": None}
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
                self.info_lbl.config(text="Цей формат не підтримується", fg=C_RED)
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
    def _show_poster(self, t):
        self._pending = t
        if self._prev_after:
            try: self.after_cancel(self._prev_after)
            except Exception: pass
        self._prev_after = self.after(110, self._run_poster)

    def _run_poster(self):
        if self.playing:
            return
        t = self._pending
        piece = dict(self._sel_piece())          # заморожений стан (фоновий потік)
        src = self._src(piece)
        self._frame_idx ^= 1
        png = self._frames[self._frame_idx]
        vf = self._transform_vf(piece, self._pcw, self._pch)
        # накладки, активні на поточному монтажному часі — постер показує КОМПОЗИЦІЮ
        mt = self._playhead_montage_t()
        active = [dict(o) for o in self.ovls
                  if o["at"] - 0.001 <= mt <= o["at"] + (o["e"] - o["s"]) + 0.001]

        cmd = ["ffmpeg", "-y"]
        if src["kind"] == "image":
            cmd += ["-i", src["path"]]
        else:
            cmd += ["-ss", f"{t:.3f}", "-i", src["path"]]
        if not active:
            cmd += ["-frames:v", "1", "-vf", vf, png]
        else:
            fc = [f"[0:v]{vf}[b0]"]
            vin = "[b0]"
            for j, o in enumerate(active):
                osrc = self.sources[o["src"]]
                if osrc["kind"] == "image":
                    cmd += ["-i", osrc["path"]]
                else:
                    tt = max(0.0, o["s"] + (mt - o["at"]))
                    cmd += ["-ss", f"{tt:.3f}", "-i", osrc["path"]]
                sw, sh, x, y = self._ovl_geom(o, self._pcw, self._pch)
                fc.append(f"[{j + 1}:v]scale={sw}:{sh}[o{j}]")
                fc.append(f"{vin}[o{j}]overlay={x}:{y}[b{j + 1}]")
                vin = f"[b{j + 1}]"
            cmd += ["-filter_complex", ";".join(fc), "-map", vin, "-frames:v", "1", png]

        def work():
            try:
                rc = subprocess.run(cmd, capture_output=True, creationflags=dc_core.NO_WINDOW).returncode
            except Exception:
                rc = 1
            if rc == 0 and os.path.exists(png):
                self.after(0, lambda: self._draw_png(png))
        threading.Thread(target=work, daemon=True).start()

    def _draw_png(self, png):
        if self.playing:
            return
        try:
            self._img = tk.PhotoImage(file=png)
            self.video.delete("frame")
            self.video.create_image(self.VW // 2, self.VH // 2, image=self._img, tags="frame")
            self.video.tag_lower("frame")       # рамка масштабу лишається поверх кадру
            self._draw_tfbox()
        except tk.TclError:
            pass

    # -------- масштаб/позиція відео на прев'ю: рамка з ручками (як у CapCut) -------- #
    def _tf_target(self):
        """Що редагує рамка на прев'ю: вибрана НАКЛАДКА, інакше вибраний кліп."""
        if self.sel_ovl is not None and self.sel_ovl < len(self.ovls):
            return self.ovls[self.sel_ovl]
        return self._sel_piece()

    def _tf_rect(self):
        """Прямокутник цілі рамки на канвасі прев'ю (з урахуванням zoom/nx/ny)."""
        p = self._tf_target()
        src = self._src(p)
        iw = src["w"] or self._pcw
        ih = src["h"] or self._pch
        f0 = min(self._pcw / iw, self._pch / ih)
        sw, sh = iw * f0 * p["zoom"], ih * f0 * p["zoom"]
        ox = (self.VW - self._pcw) / 2.0
        oy = (self.VH - self._pch) / 2.0
        cx = ox + self._pcw / 2.0 + p["nx"] * self._pcw
        cy = oy + self._pch / 2.0 + p["ny"] * self._pch
        return cx - sw / 2, cy - sh / 2, cx + sw / 2, cy + sh / 2

    def _draw_tfbox(self):
        c = self.video
        c.delete("tf")
        if not self._tf_on or self.playing:
            return
        x1, y1, x2, y2 = self._tf_rect()
        col = C_OVL if self.sel_ovl is not None else C_HANDLE
        c.create_rectangle(x1, y1, x2, y2, outline=col, width=2, tags="tf")
        r = 7
        for hx, hy in ((x1, y1), (x2, y1), (x1, y2), (x2, y2)):    # кутові ручки
            c.create_rectangle(hx - r, hy - r, hx + r, hy + r,
                               fill=col, outline=C_DARK, width=1, tags="tf")
        what = " (накладка)" if self.sel_ovl is not None else ""
        c.create_text((x1 + x2) / 2, min(self.VH - 10, max(12, y2 + 14)),
                      text=f"тягни кут — масштаб · середину — позиція{what} · подвійний клік — скинути",
                      fill=C_HANDLE, font=(FONT, 8), tags="tf")

    def _video_press(self, ev):
        if self.busy:
            return
        if self.playing:
            self._pause()                 # пауза -> на постері можна редагувати рамку
        p = self._tf_target()
        if not self._tf_on:
            self._tf_on = True
            self._tf_drag = None
            self._draw_tfbox()
            return
        x1, y1, x2, y2 = self._tf_rect()
        cxm, cym = (x1 + x2) / 2, (y1 + y2) / 2
        corner = None
        for hx, hy in ((x1, y1), (x2, y1), (x1, y2), (x2, y2)):
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
            p["nx"] = min(1.4, max(-1.4, b["nx"] + (ev.x - b["x"]) / self._pcw))
            p["ny"] = min(1.4, max(-1.4, b["ny"] + (ev.y - b["y"]) / self._pch))
        self._draw_tfbox()
        self._show_poster(self.cur)        # кадр підтягнеться (дебаунс 110мс)

    def _video_release(self, ev):
        if not self._tf_drag:
            return
        mode, b = self._tf_drag
        self._tf_drag = None
        if not b["moved"]:
            self._tf_on = False            # клік без руху -> сховати рамку
            self.video.delete("tf")
            return
        self._show_poster(self.cur)
        self._draw_tfbox()
        self._redraw()                     # оновити значок 🔍 на кліпі

    def _tf_reset(self):
        p = self._tf_target()
        if p["zoom"] != 1.0 or p["nx"] or p["ny"]:
            self._push_undo()
            p["zoom"], p["nx"], p["ny"] = 1.0, 0.0, 0.0
            self._show_poster(self.cur)
            self._draw_tfbox()
            self._redraw()

    def _is_transformed(self, p):
        return p["zoom"] != 1.0 or p["nx"] != 0.0 or p["ny"] != 0.0

    # -------------- ВБУДОВАНЕ ВІДТВОРЕННЯ ЗІ ЗВУКОМ (ffplay через SetParent) ---- #
    def _toggle_play(self):
        if self.playing:
            self._pause()
        else:
            p = self._sel_piece()
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
            try:
                self.play_btn.config(text="⏸ Стоп")
            except tk.TclError:
                pass
            self._play_progress()
            return
        w = self.video.winfo_width() or self.VW
        h = self.video.winfo_height() or self.VH
        self._embed_title = f"dac_play_{os.getpid()}_{int(start * 1000)}"
        cmd = ["ffplay", "-hide_banner", "-loglevel", "error", "-stats", "-noborder", "-autoexit",
               "-left", "32000", "-top", "32000",   # спавн за межами екрана — без спалаху
               "-x", str(w), "-y", str(h), "-ss", f"{start:.3f}"]
        if dur is not None:
            cmd += ["-t", f"{max(0.1, dur):.3f}"]
        if piece["mute"]:
            cmd += ["-an"]
        cmd += ["-window_title", self._embed_title, "-i", src["path"]]
        self._ffplay_pos = None
        self._stat_offset = None
        try:
            self._ffplay = subprocess.Popen(cmd, creationflags=dc_core.NO_WINDOW,
                                            stderr=subprocess.PIPE)
        except FileNotFoundError:
            self.info_lbl.config(text="ffplay не знайдено — онови ffmpeg", fg=C_RED)
            return
        self.playing = True
        self._embedded = None
        self._play_t0 = time.monotonic()
        dc_core.dlog(f"PLAY launch build={dc_core.BUILD} src={piece['src']} start={start:.3f} "
                     f"dur={dur} t0={self._play_t0:.3f}")
        threading.Thread(target=self._read_ffplay_stats, args=(self._ffplay,), daemon=True).start()
        try:
            self.play_btn.config(text="⏸ Стоп")
        except tk.TclError:
            pass
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
        if v != v or v < 0 or v > self._play_src_dur + 5:   # nan/сміття -> пропуск
            return
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
                w = self.video.winfo_width() or self.VW
                h = self.video.winfo_height() or self.VH
                _u32.MoveWindow(hwnd, 0, 0, w, h, True)
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
            if p is None or p.poll() is not None:
                return self._advance_or_stop()          # ffplay дограв кліп сам (-autoexit)
            if self._ffplay_pos is not None:
                pos = self._ffplay_pos
            else:
                pos = self._play_start + (time.monotonic() - self._play_t0)
        if pos >= self._play_end - 0.02:
            return self._advance_or_stop()
        self.cur = min(self._play_src_dur, pos)
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
        try:
            self.play_btn.config(text="▶ Грати")
        except tk.TclError:
            return
        self._show_poster(self.cur)   # повертаємо статичний кадр на екран

    def _seek(self, t):
        if self.playing:
            self._pause()
        t = max(0, min(self._src(self._sel_piece())["dur"], t))
        self.cur = t
        self._show_poster(t)
        self._redraw()

    def _to_start(self):
        self._seek(self._sel_piece()["s"])

    # --------------------------------------------------------- ножиці ------ #
    def _cut_here(self):
        if self.playing:
            self._pause()          # ріжемо рівно по кадру, який ВИДНО
        self._cut_at(self.cur)

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
        self.pieces.append(p)
        self.order.insert(self.sel + 1, len(self.pieces) - 1)
        self._redraw()

    def _set_speed(self, sp):
        p = self._sel_piece()
        if p["speed"] != sp:
            self._push_undo()
            p["speed"] = sp
            self._redraw()

    def _toggle_mute(self):
        p = self._sel_piece()
        self._push_undo()
        p["mute"] = not p["mute"]
        self._redraw()

    # ------------------------------------------------ скасувати / повторити --- #
    def _snapshot(self):
        return ([dict(p) for p in self.pieces], list(self.order), self.sel,
                [dict(s) for s in self.snds], [dict(o) for o in self.ovls])

    def _push_undo(self):
        self._undo.append(self._snapshot())
        if len(self._undo) > 80:
            self._undo.pop(0)
        self._redo.clear()

    def _apply_state(self, st):
        pieces, order, sel, snds, ovls = st
        self.pieces = [dict(p) for p in pieces]
        self.order = list(order)
        self.snds = [dict(s) for s in snds]
        self.ovls = [dict(o) for o in ovls]
        self.sel_ovl = None
        self._sel_snd = None
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
        self._draw_track(); self._update_info()

    # ---- кіно-стрічка + хвиля: генеруються ОКРЕМО для кожного джерела ----
    def _gen_visuals(self, si):
        src = self.sources[si]
        if src["kind"] == "image":
            p = os.path.join(self._tmp, f"s{si}_img.png")

            def work_img():
                subprocess.run(
                    ["ffmpeg", "-y", "-i", src["path"], "-frames:v", "1", "-vf",
                     f"scale={THUMB_W}:{TLH - 6}:force_original_aspect_ratio=increase,"
                     f"crop={THUMB_W}:{TLH - 6}", p],
                    capture_output=True, creationflags=dc_core.NO_WINDOW)
                self.after(0, lambda: self._load_strip(si, [p], [0.0]))
            threading.Thread(target=work_img, daemon=True).start()
            return

        n = 24
        times = [(i + 0.5) / n * src["dur"] for i in range(n)]
        paths = [os.path.join(self._tmp, f"s{si}_strip_{i:02d}.png") for i in range(n)]

        def work():
            for t, p in zip(times, paths):
                try:
                    subprocess.run(
                        ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", src["path"],
                         "-frames:v", "1", "-vf", f"scale={THUMB_W}:{TLH - 6}", p],
                        capture_output=True, creationflags=dc_core.NO_WINDOW)
                except Exception:
                    pass
            self.after(0, lambda: self._load_strip(si, paths, times))
        threading.Thread(target=work, daemon=True).start()

        if src["has_audio"]:
            def work_env():
                env = dc_core.audio_envelope(src["path"], hz=100)
                if env:
                    def apply():
                        src["env"] = env
                        self._draw_wave()
                    self.after(0, apply)
            threading.Thread(target=work_env, daemon=True).start()

    def _load_strip(self, si, paths, times):
        imgs = []
        for p in paths:
            try:
                imgs.append(tk.PhotoImage(file=p) if os.path.exists(p) else None)
            except tk.TclError:
                imgs.append(None)
        if any(imgs):
            self.sources[si]["strip"] = imgs
            self.sources[si]["times"] = list(times)
            self._draw_track()

    def _nearest_thumb(self, src, t):
        ts, imgs = src.get("times"), src.get("strip")
        if not ts or not imgs:
            return None
        i = min(range(len(ts)), key=lambda k: abs(ts[k] - t))
        return imgs[i % len(imgs)]

    def _draw_clip_strip(self, c, cx1, cx2, piece):
        src = self._src(piece)
        if not src.get("strip"):
            return
        width = cx2 - cx1
        k = max(1, int(width // THUMB_W))
        s, e = piece["s"], piece["e"]
        for j in range(k):
            xx = cx1 + j * THUMB_W
            if xx + THUMB_W > cx2 + 4:
                break
            im = self._nearest_thumb(src, s + (j + 0.5) / k * (e - s))
            if im:
                c.create_image(int(xx), 3, image=im, anchor="nw")

    def _draw_handle(self, c, x, left, active=False):
        w = 10 if active else 8
        x1, x2 = (x, x + w) if left else (x - w, x)
        col = C_PLAY if active else C_HANDLE
        c.create_polygon(host._rr_pts(x1, 2, x2, TLH - 2, 4), smooth=True, fill=col, outline="")
        cx = (x1 + x2) / 2
        c.create_line(cx, TLH * 0.30, cx, TLH * 0.70, fill=C_DARK, width=2)

    # ---- масштаб/скрол доріжки ----
    def _clip_durs(self):
        return [(self.pieces[ix]["e"] - self.pieces[ix]["s"]) / self.pieces[ix]["speed"]
                for ix in self.order]

    def _total(self):
        return max(0.1, sum(self._clip_durs()))

    def _pps(self):
        return (self.TW / self._total()) * self._zoom

    def _content_width(self, pps):
        ds = self._clip_durs()
        return 4.0 + sum(d * pps for d in ds) + 3 * max(0, len(ds) - 1)

    def _content_x_of(self, montage_t, pps):
        x, acc, gap = 2.0, 0.0, 3
        for d in self._clip_durs():
            if montage_t <= acc + d:
                return x + (montage_t - acc) * pps
            x += d * pps + gap
            acc += d
        return x

    def _playhead_montage_t(self):
        acc = 0.0
        for slot in range(len(self.order)):
            p = self.pieces[self.order[slot]]
            d = (p["e"] - p["s"]) / p["speed"]
            if slot == self.sel:
                return acc + (min(max(self.cur, p["s"]), p["e"]) - p["s"]) / p["speed"]
            acc += d
        return acc

    def _clamp_scroll(self, pps):
        self._scroll = max(0.0, min(self._scroll, max(0.0, self._content_width(pps) - self.TW)))

    def _apply_zoom(self, factor):
        old = self._pps()
        ft = self._playhead_montage_t()
        screen_x = self._content_x_of(ft, old) - self._scroll
        self._zoom = min(60.0, max(1.0, self._zoom * factor))
        new = self._pps()
        self._scroll = self._content_x_of(ft, new) - screen_x
        self._clamp_scroll(new)
        self._draw_track()

    def _on_zoom(self, ev):
        self._apply_zoom(1.25 if ev.delta > 0 else 0.8)
        return "break"

    def _zoom_step(self, factor):
        self._apply_zoom(factor)

    # ---- точне підлаштування обрізки стрілками (по кадру) + час-підказка ----
    def _fmt_tt(self, t):
        t = max(0.0, t); m = int(t // 60)
        return f"{m}:{t - m * 60:04.1f}"

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
        if not self._nudge_active:      # уся серія стрілок = один крок undo
            self._push_undo(); self._nudge_active = True
        if self._active == "L":
            ns = min(max(lo, p["s"] + direction * step), p["e"] - eps)
            p["s"] = ns; self.cur = self._tip_t = ns
        elif self._active == "R":
            ne = max(min(hi, p["e"] + direction * step), p["s"] + eps)
            p["e"] = ne; self.cur = self._tip_t = ne
        else:                           # нема активної ручки -> рухаємо плейхед
            self.cur = self._tip_t = min(max(p["s"], self.cur + direction * step), p["e"])
        self._show_poster(self.cur)
        self._redraw()
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

    def _on_scroll(self, ev):
        if self._zoom <= 1.0:
            return
        self._scroll -= (ev.delta / 120.0) * 60
        self._clamp_scroll(self._pps())
        self._draw_track()
        return "break"

    def _draw_track(self):
        c = self.tl; c.delete("all"); W = self.TW
        c.create_rectangle(0, 0, W, TLH, fill=C_TRACK, outline="")
        pps = self._pps()
        x = 2.0 - self._scroll; gap = 3
        self._clip_rects = []
        self._sel_xs = self._sel_xe = 0
        for slot, ix in enumerate(self.order):
            p = self.pieces[ix]
            s, e = p["s"], p["e"]
            w = max(6.0, (e - s) / p["speed"] * pps)
            cx1, cx2 = x, x + w
            sel = slot == self.sel
            c.create_rectangle(cx1, 3, cx2, TLH - 3, fill=C_CLIP, outline="")
            self._draw_clip_strip(c, cx1, cx2, p)
            if not sel:
                c.create_rectangle(cx1, 3, cx2, TLH - 3, fill="#000000", stipple="gray25", outline="")
            c.create_rectangle(cx1, 3, cx2, TLH - 3,
                               outline=C_HANDLE if sel else C_DARK, width=2 if sel else 1)
            # значки стану кліпа: швидкість / без звуку / масштаб / картинка
            badges = []
            if p["speed"] != 1.0: badges.append(f"{p['speed']:g}×")
            if p["mute"]: badges.append("🔇")
            if self._is_transformed(p): badges.append("🔍")
            if self._src(p)["kind"] == "image": badges.append("🖼")
            if badges:
                c.create_text(cx1 + 5, 11, anchor="w", text=" ".join(badges),
                              fill="#ffffff", font=(FONT, 8, "bold"))
            if sel:
                self._sel_xs, self._sel_xe = cx1, cx2
                # хвиля звуку прямо НА вибраному кліпі (внизу, як у CapCut)
                env = self._src(p).get("env")
                if env and not p["mute"]:
                    by = TLH - 5
                    span = max(0.001, e - s)
                    xx = max(0.0, cx1)
                    while xx < min(float(W), cx2):
                        a = self._env_at(env, s + (xx - cx1) / max(1.0, cx2 - cx1) * span)
                        c.create_line(xx, by - max(0.6, a * 17), xx, by, fill=C_WAVE_IN, width=1)
                        xx += 2
                self._draw_handle(c, cx1, left=True, active=self._active == "L")
                self._draw_handle(c, cx2, left=False, active=self._active == "R")
                if e > s:
                    xh = cx1 + (self.cur - s) / (e - s) * (cx2 - cx1)
                    xh = min(max(cx1, xh), cx2)
                    self._playhead_x = xh
                    c.create_line(xh, 3, xh, TLH, fill=C_PLAY, width=2)
                    c.create_polygon(xh - 5, 0, xh + 5, 0, xh, 7, fill=C_PLAY, outline="")
            self._clip_rects.append((slot, ix, cx1, cx2))
            x = cx2 + gap
        if self._tip_t is not None:
            tx = (self._sel_xe if self._active == "R"
                  else self._sel_xs if self._active == "L" else self._playhead_x)
            tx = min(max(30, tx), W - 30)
            c.create_rectangle(tx - 30, 0, tx + 30, 16, fill=C_DARK, outline=C_PLAY)
            c.create_text(tx, 8, text=self._fmt_tt(self._tip_t), fill="#ffffff", font=(FONT, 8, "bold"))
        self._draw_ovl()
        self._draw_wave()

    # ---- хвиля кліпів (верх) + смужка доданих звуків (низ) ----
    def _env_at(self, env, t):
        if not env:
            return 0.0
        i = int(t * 100)
        if i < 0:
            i = 0
        elif i >= len(env):
            i = len(env) - 1
        return env[i]

    def _draw_wave(self):
        c = getattr(self, "wave", None)
        if c is None:
            return
        try:
            c.delete("all")
            W, H = self.TW, self.WAVE_H
            LANE = 36                        # верх: хвиля кліпів; низ: додані звуки
            mid = LANE / 2.0
            c.create_rectangle(0, 0, W, H, fill=C_TRACK, outline="")
            c.create_line(0, LANE + 1, W, LANE + 1, fill=C_DARK)
            for slot, ix, cx1, cx2 in self._clip_rects:
                p = self.pieces[ix]
                src = self._src(p)
                env = src.get("env")
                wpx = cx2 - cx1
                if wpx <= 0:
                    continue
                if not env or p["mute"]:
                    continue
                s, e = p["s"], p["e"]
                span = max(0.001, e - s)
                col = C_BLURPLE if slot == self.sel else "#4a4d57"
                xx = max(0.0, cx1)
                xend = min(float(W), cx2)
                while xx < xend:
                    a = self._env_at(env, s + (xx - cx1) / wpx * span)
                    h = max(0.6, a * (mid - 1))
                    c.create_line(xx, mid - h, xx, mid + h, fill=col, width=1)
                    xx += 2
            # ---- додані звуки (зелені блоки, тягнуться мишкою, ПКМ — меню) ----
            self._snd_rects = []
            pps = self._pps()
            for i, sn in enumerate(self.snds):
                x1 = self._content_x_of(sn["at"], pps) - self._scroll
                x2 = x1 + max(10.0, sn["dur"] * pps)
                self._snd_rects.append((i, x1, x2))
                if x2 < 0 or x1 > W:
                    continue
                sel = i == self._sel_snd
                c.create_polygon(host._rr_pts(x1, LANE + 3, x2, H - 2, 5),
                                 smooth=True, fill=C_SND, outline="")
                if sel:
                    c.create_rectangle(x1, LANE + 3, x2, H - 2, outline=C_HANDLE, width=2)
                # хвиля вибраного звуку прямо в його блоці
                env = sn.get("env")
                if sel and env:
                    smid = (LANE + H) / 2.0
                    xx = max(0.0, x1)
                    while xx < min(float(W), x2):
                        a = self._env_at(env, (xx - x1) / max(1.0, x2 - x1) * sn["dur"])
                        h = max(0.5, a * (H - LANE - 6) / 2.0)
                        c.create_line(xx, smid - h, xx, smid + h, fill="#0d3d20", width=1)
                        xx += 2
                nm = sn["name"]
                if len(nm) > 16:
                    nm = nm[:14] + "…"
                v = "" if sn["vol"] == 1.0 else f" · {int(sn['vol'] * 100)}%"
                c.create_text(max(x1 + 6, 6), (LANE + H) / 2 + 1, anchor="w",
                              text=f"🎵 {nm}{v}", fill="#10121a", font=(FONT, 8, "bold"))
            if not self.snds and all(not self._src(self.pieces[ix]).get("env")
                                     for _, ix, _, _ in self._clip_rects):
                c.create_text(W // 2, mid, text="без звуку", fill=C_MUTED, font=(FONT, 8))
            xh = getattr(self, "_playhead_x", 0)
            if xh:
                c.create_line(xh, 0, xh, H, fill=C_PLAY, width=2)
        except tk.TclError:
            pass

    def _snd_hit(self, x):
        for i, x1, x2 in self._snd_rects:
            if x1 - 3 <= x <= x2 + 3:
                return i
        return None

    def _wave_press(self, ev):
        i = self._snd_hit(ev.x)
        if i != self._sel_snd:
            self._sel_snd = i          # вибраний звук -> його хвиля видно у блоці
            self._draw_wave()
        if i is None:
            self._snd_drag = None
            return
        self._snd_drag = [i, ev.x, self.snds[i]["at"], False]   # undo лише при реальному русі

    def _wave_motion(self, ev):
        if not self._snd_drag:
            return
        i, x0, at0, pushed = self._snd_drag
        if not pushed:
            self._push_undo()
            self._snd_drag[3] = True
        pps = self._pps()
        at = at0 + (ev.x - x0) / max(0.001, pps)
        self.snds[i]["at"] = max(0.0, min(self._total() - 0.1, at))
        self._draw_wave()

    def _wave_release(self, _ev):
        self._snd_drag = None

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

    def _to_overlay(self):
        """Вибраний кліп доріжки -> накладка поверх відео (на тому ж місці монтажу)."""
        if len(self.order) <= 1 or self.busy:
            return
        self._push_undo()
        slot = self.sel
        p = self.pieces[self.order[slot]]
        durs = self._clip_durs()
        at = sum(durs[:slot])
        self.ovls.append({"src": p["src"], "s": p["s"], "e": p["e"], "at": at,
                          "zoom": 0.5, "nx": 0.28, "ny": -0.22, "mute": p["mute"]})
        del self.order[slot]
        self.sel = min(slot, len(self.order) - 1)
        self.sel_ovl = len(self.ovls) - 1
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
        self.pieces.append(p)
        self.order.append(len(self.pieces) - 1)
        del self.ovls[i]
        self.sel_ovl = None
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
        self._show_poster(self.cur)
        self._redraw()

    def _ovl_mute(self):
        i = self.sel_ovl
        if i is None:
            return
        self._push_undo()
        self.ovls[i]["mute"] = not self.ovls[i]["mute"]
        self._draw_ovl()

    def _draw_ovl(self):
        c = getattr(self, "ovl", None)
        if c is None:
            return
        try:
            c.delete("all")
            W, H = self.TW, self.OVL_H
            c.create_rectangle(0, 0, W, H, fill=C_TRACK, outline="")
            self._ovl_rects = []
            pps = self._pps()
            if not self.ovls:
                c.create_text(W // 2, H / 2, text="накладки поверх відео: ПКМ по кліпу → «🎭 Зробити накладкою»",
                              fill=C_MUTED, font=(FONT, 8))
            for i, o in enumerate(self.ovls):
                x1 = self._content_x_of(o["at"], pps) - self._scroll
                x2 = x1 + max(10.0, (o["e"] - o["s"]) * pps)
                self._ovl_rects.append((i, x1, x2))
                if x2 < 0 or x1 > W:
                    continue
                sel = i == self.sel_ovl
                c.create_polygon(host._rr_pts(x1, 2, x2, H - 2, 5),
                                 smooth=True, fill=C_OVL, outline="")
                if sel:
                    c.create_rectangle(x1, 2, x2, H - 2, outline=C_HANDLE, width=2)
                src = self.sources[o["src"]]
                # хвиля вибраної накладки прямо в блоці ("на тій доріжці, яку вибрали")
                env = src.get("env")
                if sel and env and not o["mute"]:
                    mid = H / 2.0
                    span = max(0.001, o["e"] - o["s"])
                    xx = max(0.0, x1)
                    while xx < min(float(W), x2):
                        a = self._env_at(env, o["s"] + (xx - x1) / (x2 - x1) * span)
                        h = max(0.5, a * (mid - 3))
                        c.create_line(xx, mid - h, xx, mid + h, fill="#2a0d45", width=1)
                        xx += 2
                nm = src["name"]
                if len(nm) > 18:
                    nm = nm[:16] + "…"
                mut = " 🔇" if o["mute"] else ""
                c.create_text(max(x1 + 6, 6), H / 2, anchor="w",
                              text=f"🎭 {nm}{mut}", fill="#10121a", font=(FONT, 8, "bold"))
            xh = getattr(self, "_playhead_x", 0)
            if xh:
                c.create_line(xh, 0, xh, H, fill=C_PLAY, width=1)
        except tk.TclError:
            pass

    def _ovl_hit(self, x):
        for i, x1, x2 in self._ovl_rects:
            if x1 - 3 <= x <= x2 + 3:
                return i, x1, x2
        return None

    def _ovl_press(self, ev):
        hit = self._ovl_hit(ev.x)
        if hit is None:
            if self.sel_ovl is not None:
                self.sel_ovl = None
                self._show_poster(self.cur)
                self._redraw()
            self._ovl_drag = None
            return
        i, x1, x2 = hit
        if self.playing:
            self._pause()
        self.sel_ovl = i
        o = self.ovls[i]
        edge = "L" if abs(ev.x - x1) <= 8 else ("R" if abs(ev.x - x2) <= 8 else None)
        self._ovl_drag = [i, ev.x, dict(o), edge, False]
        self._show_poster(self.cur)
        self._redraw()

    def _ovl_motion(self, ev):
        if not self._ovl_drag:
            return
        i, x0, o0, edge, pushed = self._ovl_drag
        if not pushed:
            self._push_undo()
            self._ovl_drag[4] = True
        d = (ev.x - x0) / max(0.001, self._pps())
        o = self.ovls[i]
        src = self.sources[o["src"]]
        hi = src["dur"] if src["kind"] == "video" else IMG_MAX
        if edge == "L":      # лівий край: рухаємо і початок джерела, і позицію в монтажі
            ns = min(max(0.0, o0["s"] + d), o0["e"] - 0.1)
            o["s"] = ns
            o["at"] = max(0.0, o0["at"] + (ns - o0["s"]))
        elif edge == "R":
            o["e"] = min(hi, max(o0["e"] + d, o0["s"] + 0.1))
        else:
            o["at"] = max(0.0, min(self._total() - 0.1, o0["at"] + d))
        self._draw_ovl()

    def _ovl_release(self, _ev):
        if self._ovl_drag and self._ovl_drag[4]:
            self._show_poster(self.cur)
        self._ovl_drag = None

    def _ovl_menu(self, ev):
        if self.busy:
            return
        hit = self._ovl_hit(ev.x)
        if hit is None:
            return
        i = hit[0]
        self.sel_ovl = i
        self._show_poster(self.cur)
        self._redraw()
        o = self.ovls[i]
        src = self.sources[o["src"]]
        m = self._menu_new()
        m.add_command(label=f"🎭  {src['name']}", state="disabled")
        if src["kind"] == "video" and src["has_audio"]:
            m.add_command(label=("🔊  Увімкнути звук" if o["mute"] else "🔇  Вимкнути звук"),
                          command=self._ovl_mute)
        m.add_command(label="🔍  На весь екран (скинути масштаб)", command=self._tf_reset)
        m.add_command(label="⬇  Повернути на доріжку", command=self._ovl_to_track)
        m.add_separator()
        m.add_command(label="🗑  Видалити накладку", command=self._ovl_del)
        try:
            m.tk_popup(ev.x_root, ev.y_root)
        finally:
            m.grab_release()

    # ------------------------------------------- контекстні меню (ПКМ) ----- #
    def _menu_new(self):
        return tk.Menu(self, tearoff=0, bg=C_BG2, fg=C_TEXT, bd=0,
                       activebackground=C_BLURPLE, activeforeground="#ffffff",
                       font=(FONT, 10))

    def _tl_menu(self, ev):
        if self.busy:
            return
        # вибираємо кліп під курсором (як лівий клік)
        hit = None
        for slot, ix, cx1, cx2 in self._clip_rects:
            if cx1 - 2 <= ev.x <= cx2 + 2:
                hit = (slot, ix, cx1, cx2)
                break
        if hit is None:
            return
        slot, ix, cx1, cx2 = hit
        if self.playing:
            self._pause()
        p = self.pieces[ix]
        if slot != self.sel:
            self.sel = slot
            self.cur = p["s"]
        # плейхед — у точку кліку (для «розрізати тут»)
        self.cur = min(max(p["s"], p["s"] + (ev.x - cx1) / max(1.0, cx2 - cx1) * (p["e"] - p["s"])), p["e"])
        self._show_poster(self.cur)
        self._redraw()
        src = self._src(p)
        m = self._menu_new()
        m.add_command(label="✂  Розрізати тут", command=lambda: self._cut_at(self.cur))
        m.add_command(label="📄  Дублювати кліп", command=self._duplicate)
        if len(self.order) > 1:
            m.add_command(label="🎭  Зробити накладкою (поверх відео)", command=self._to_overlay)
        if src["kind"] == "video":
            sp = self._menu_new()
            for v in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0):
                sp.add_command(label=(f"{v:g}×" + ("   ✓" if p["speed"] == v else "")),
                               command=lambda v=v: self._set_speed(v))
            m.add_cascade(label=f"⚡  Швидкість ({p['speed']:g}×)", menu=sp)
            if src["has_audio"]:
                m.add_command(label=("🔊  Увімкнути звук" if p["mute"] else "🔇  Вимкнути звук"),
                              command=self._toggle_mute)
        if self._is_transformed(p):
            m.add_command(label="🔍  Скинути масштаб/позицію", command=self._tf_reset)
        m.add_separator()
        m.add_command(label="◀  Пересунути лівіше", command=lambda: self._move(-1))
        m.add_command(label="▶  Пересунути правіше", command=lambda: self._move(1))
        if len(self.order) > 1:
            m.add_separator()
            m.add_command(label="🗑  Прибрати кліп", command=self._remove)
        try:
            m.tk_popup(ev.x_root, ev.y_root)
        finally:
            m.grab_release()

    def _wave_menu(self, ev):
        if self.busy:
            return
        i = self._snd_hit(ev.x)
        if i is None:
            return
        sn = self.snds[i]
        m = self._menu_new()
        m.add_command(label=f"🎵  {sn['name']}", state="disabled")
        m.add_command(label="▶  Прослухати", command=lambda: self._preview_sound(sn))
        vol = self._menu_new()
        for v in (0.5, 0.75, 1.0, 1.5, 2.0):
            vol.add_command(label=(f"{int(v * 100)}%" + ("   ✓" if sn["vol"] == v else "")),
                            command=lambda v=v: self._set_snd_vol(i, v))
        m.add_cascade(label=f"🔉  Гучність ({int(sn['vol'] * 100)}%)", menu=vol)
        m.add_separator()
        m.add_command(label="🗑  Видалити звук", command=lambda: self._del_snd(i))
        try:
            m.tk_popup(ev.x_root, ev.y_root)
        finally:
            m.grab_release()

    def _preview_sound(self, sn):
        try:
            subprocess.Popen(["ffplay", "-hide_banner", "-loglevel", "error", "-nodisp",
                              "-autoexit", "-t", "10", "-i", sn["path"]],
                             creationflags=dc_core.NO_WINDOW)
        except Exception:
            pass

    def _set_snd_vol(self, i, v):
        self._push_undo()
        self.snds[i]["vol"] = v
        self._draw_wave()

    def _del_snd(self, i):
        self._push_undo()
        del self.snds[i]
        self._draw_wave()

    # ---- взаємодія на доріжці: ручки / вибір кліпа / плейхед ----
    def _tl_press(self, ev):
        # 1) ручки обрізки вибраного кліпа
        if abs(ev.x - self._sel_xs) <= 11 or abs(ev.x - self._sel_xe) <= 11:
            p = self._sel_piece()
            self._push_undo()
            self._drag = "L" if abs(ev.x - self._sel_xs) <= 11 else "R"
            self._active = self._drag
            self._nudge_active = True         # drag уже штовхнув undo -> стрілки не дублюють
            self._tip_t = p["s"] if self._drag == "L" else p["e"]
            self._d0 = {"x0": ev.x, "s0": p["s"], "e0": p["e"],
                        "pps": (self._sel_xe - self._sel_xs) / max(0.001, p["e"] - p["s"])}
            self._redraw()
            return
        # 2) клік по кліпу: вибрати; всередині вибраного — перемістити плейхед
        self._drag = None
        self._active = None
        self._tip_t = None
        for slot, ix, cx1, cx2 in self._clip_rects:
            if cx1 - 2 <= ev.x <= cx2 + 2:
                p = self.pieces[ix]
                if self.playing:
                    self._pause()
                if slot == self.sel:
                    self.cur = min(max(p["s"], p["s"] + (ev.x - cx1) / max(1.0, cx2 - cx1)
                                       * (p["e"] - p["s"])), p["e"])
                else:
                    self.sel = slot
                    self.cur = p["s"]
                    self._tf_on = False
                self.sel_ovl = None          # фокус на кліпі -> рамка керує кліпом
                self._show_poster(self.cur)
                self._redraw()
                return

    def _tl_motion(self, ev):
        if not self._drag:
            return
        if self.playing:
            self._pause()
        p = self._sel_piece()
        src = self._src(p)
        d0 = self._d0
        dsrc = (ev.x - d0["x0"]) / d0["pps"]
        lo, hi = 0.0, src["dur"]
        if self._drag == "L":
            ns = max(lo, min(d0["s0"] + dsrc, d0["e0"] - 0.1))
            p["s"] = ns; self.cur = self._tip_t = ns
        else:
            ne = min(hi, max(d0["e0"] + dsrc, d0["s0"] + 0.1))
            p["e"] = ne; self.cur = self._tip_t = ne
        self._show_poster(self.cur)
        self._redraw()

    def _tl_release(self, _ev):
        self._drag = None
        if self._tip_t is not None:
            self._schedule_tip_clear()

    def _update_info(self):
        total = self._total()
        target = float(self.cfg["target_mb"])
        has_a = bool(self.snds) or any(
            self._src(self.pieces[ix])["has_audio"] and not self.pieces[ix]["mute"]
            for ix in self.order) or any(
            self.sources[o["src"]]["has_audio"] and not o["mute"] for o in self.ovls)
        v = dc_core.calc_video_kbps(total, target, self.cfg["audio_kbps"], has_a) or 0
        if v >= 600: col, tag = C_GREEN, "✓ Гарна якість"
        elif v >= 150: col, tag = "#faa61a", "⚠ Нормальна якість"
        elif v >= 50: col, tag = "#faa61a", "⚠ Слабка якість"
        else: col, tag = C_RED, "✗ Задовгий фрагмент"
        self.info_lbl.config(text=tag, fg=col)   # без цифр — лише оцінка якості
        if not self.busy:
            self.export_btn.config(state=("normal" if v >= 50 else "disabled"))

    # ----------------------------------------------------------- експорт --- #
    def _is_simple(self):
        """Одне (початкове) джерело, без картинок/звуків/швидкості/муту/масштабу ->
        можна старим ШВИДКИМ шляхом compress_segments."""
        if len(self.sources) != 1 or self.snds or self.ovls:
            return False
        for ix in self.order:
            p = self.pieces[ix]
            if p["src"] != 0 or p["speed"] != 1.0 or p["mute"] or self._is_transformed(p):
                return False
        return True

    def _transform_vf(self, p, cw, ch):
        """Фільтр композиції кліпа на канвас cw×ch: вписати + zoom/nx/ny (щільний pad)."""
        src = self.sources[p["src"]]
        iw = src["w"] or cw
        ih = src["h"] or ch
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
        return (f"scale={sw}:{sh},pad={pw}:{ph}:{px}:{py}:black,"
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
        """Рендерить монтаж у ОДИН нормалізований mp4 (канвас, CFR, transform, speed,
        тиша замість відсутнього звуку; картинки -> loop). Повертає (шлях|None, total)."""
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
            base = acc / total * 88.0
            span = dd / total * 88.0
            if src["kind"] == "image":
                cmd = ["ffmpeg", "-y", "-loop", "1", "-framerate", f"{fps:g}",
                       "-t", f"{dd:.3f}", "-i", src["path"],
                       "-f", "lavfi", "-t", f"{dd:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
                       "-map", "0:v", "-map", "1:a", "-t", f"{dd:.3f}",
                       "-vf", vf + ",setsar=1", "-r", f"{fps:g}",
                       "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                       "-video_track_timescale", "90000", f]
            else:
                sp = p["speed"]
                if sp != 1.0:
                    vf += f",setpts=PTS/{sp:g}"
                use_a = src["has_audio"] and not p["mute"]
                cmd = ["ffmpeg", "-y", "-ss", f"{p['s']:.3f}", "-i", src["path"]]
                if not use_a:
                    cmd += ["-f", "lavfi", "-t", f"{dd:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
                            "-map", "0:v", "-map", "1:a"]
                cmd += ["-t", f"{dd:.3f}", "-vsync", "cfr", "-r", f"{fps:g}",
                        "-vf", vf + ",setsar=1",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                        "-pix_fmt", "yuv420p"]
                if use_a:
                    af = (self._atempo(sp) + "," if sp != 1.0 else "") + "aresample=44100"
                    cmd += ["-af", af, "-ac", "2", "-c:a", "aac", "-b:a", "192k"]
                else:
                    cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
                cmd += ["-video_track_timescale", "90000", f]
            rc = dc_core._run_pass(cmd, dd, base, span, prog, cancel)
            if rc != 0 or not os.path.exists(f):
                dc_core.dlog(f"MONTAGE clip {i} FAIL rc={rc} cmd={' '.join(cmd[:20])}")
                return None, total
            files.append(f)
            acc += dd

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

        # композиція: НАКЛАДКИ поверх відео + додані звуки — одним проходом
        joined = self._compose(tmpd, joined, total, prog, cancel)
        if prog and joined:
            prog(96.0)
        return joined, total

    def _compose(self, tmpd, joined, total, prog, cancel):
        """Накладає self.ovls на відео (overlay з вікном enable) і підмішує self.snds
        (adelay+amix). Повертає новий шлях (або joined, якщо нема чого накладати; None=збій)."""
        ovls = [o for o in self.ovls if o["at"] < total - 0.05]
        snds = [s for s in self.snds if s["at"] < total - 0.05 and os.path.isfile(s["path"])]
        if not ovls and not snds:
            return joined
        cw, ch = self._ccw, self._cch
        cmd = ["ffmpeg", "-y", "-i", joined]
        fc, alabs = [], []
        vin = "[0:v]"
        idx = 1
        for j, o in enumerate(ovls):
            src = self.sources[o["src"]]
            d = min(o["e"] - o["s"], total - o["at"])
            if src["kind"] == "image":
                cmd += ["-loop", "1", "-t", f"{d:.3f}", "-i", src["path"]]
            else:
                cmd += ["-ss", f"{o['s']:.3f}", "-t", f"{d:.3f}", "-i", src["path"]]
            sw, sh, x, y = self._ovl_geom(o, cw, ch)
            at = o["at"]
            fc.append(f"[{idx}:v]scale={sw}:{sh},setpts=PTS-STARTPTS+{at:.3f}/TB[ow{j}]")
            fc.append(f"{vin}[ow{j}]overlay={x}:{y}:"
                      f"enable='between(t,{at:.3f},{at + d:.3f})'[vb{j}]")
            vin = f"[vb{j}]"
            if src["kind"] == "video" and src["has_audio"] and not o["mute"]:
                ms = int(at * 1000)
                fc.append(f"[{idx}:a]atrim=0:{d:.3f},aresample=44100,adelay={ms}|{ms}[oa{j}]")
                alabs.append(f"[oa{j}]")
            idx += 1
        for k, sn in enumerate(snds):
            cmd += ["-i", sn["path"]]
            ms = int(sn["at"] * 1000)
            fc.append(f"[{idx}:a]aresample=44100,volume={sn['vol']:g},adelay={ms}|{ms}[sa{k}]")
            alabs.append(f"[sa{k}]")
            idx += 1
        if alabs:
            fc.append(f"[0:a]{''.join(alabs)}amix=inputs={len(alabs) + 1}:"
                      f"duration=first:normalize=0[ao]")
        out = os.path.join(tmpd, "composed.mp4")
        cmd += ["-filter_complex", ";".join(fc)]
        cmd += ["-map", vin] if ovls else ["-map", "0:v"]
        cmd += ["-map", "[ao]"] if alabs else ["-map", "0:a"]
        if ovls:   # відео змінилось -> перекодовуємо; без накладок можна copy
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                    "-pix_fmt", "yuv420p"]
        else:
            cmd += ["-c:v", "copy"]
        cmd += ["-c:a", "aac", "-b:a", "192k", out]
        rc = dc_core._run_pass(cmd, total, 92.0, 4.0, prog, cancel)
        if rc != 0 or not os.path.exists(out):
            dc_core.dlog("MONTAGE compose FAIL")
            return None
        return out

    def _render_and_compress(self, out_path, target, prog, cancel):
        tmpd = tempfile.mkdtemp(prefix="dmix_")
        try:
            joined, total = self._render_montage(tmpd, lambda p: prog(p * 0.55), cancel)
            if not joined:
                return False, "Не вдалося зібрати монтаж.", 0.0
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
        try:
            dc_core.dlog(f"EDITOR EXPORT build={dc_core.BUILD} simple={self._is_simple()} "
                         f"clips={len(self.order)} sources={len(self.sources)} snds={len(self.snds)}")
        except Exception:
            pass
        self._pause()
        self.busy = True
        self.export_btn.config(state="disabled")
        target = float(self.cfg["target_mb"])
        out_path = dc_core.output_name(self.file_path, target)
        self._start_export_jokes()
        prog = lambda p: self.after(0, lambda: self.info_lbl.config(
            text=f"Зберігаю… {int(p)}%", fg=C_BLURPLE))

        if self._is_simple():
            segs = [(self.pieces[ix]["s"], self.pieces[ix]["e"]) for ix in self.order]
            scale = (dc_core.pick_auto_scale(self.info, target, self.cfg["audio_kbps"])
                     if self.cfg.get("auto_scale", True) else 0)

            def worker():
                ok, msg, mb = dc_core.compress_segments(
                    self.file_path, out_path, target, scale, self.cfg["audio_kbps"],
                    self.info, segs, progress_cb=prog, should_cancel=lambda: False)
                self.after(0, lambda: self._done(ok, out_path, mb, msg))
        else:
            def worker():
                try:
                    ok, msg, mb = self._render_and_compress(out_path, target, prog,
                                                            lambda: False)
                except Exception as e:
                    import traceback
                    dc_core.dlog("EXPORT EXCEPTION: " + repr(e) + "\n" + traceback.format_exc())
                    ok, msg, mb = False, f"Помилка: {str(e)[:60]}", 0.0
                self.after(0, lambda: self._done(ok, out_path, mb, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _export_gif(self):
        if not self.order:
            return
        total = self._total()
        if total > 30:
            self.info_lbl.config(text="Для GIF задовгий фрагмент (макс ~30с)", fg=C_RED)
            return
        self._pause()
        self.busy = True
        self.export_btn.config(state="disabled")
        self.gif_btn.config(state="disabled")
        out_path = dc_core.gif_out_name(self.file_path)
        self._start_export_jokes()
        prog = lambda p: self.after(0, lambda: self.info_lbl.config(
            text=f"Роблю GIF… {int(p)}%", fg=C_BLURPLE))

        if self._is_simple():
            segs = [(self.pieces[ix]["s"], self.pieces[ix]["e"]) for ix in self.order]

            def worker():
                ok, msg, mb = dc_core.export_gif(self.file_path, out_path, segs,
                                                 progress_cb=prog)
                self.after(0, lambda: self._done(ok, out_path, mb, msg))
        else:
            def worker():
                tmpd = tempfile.mkdtemp(prefix="dgifm_")
                try:
                    joined, tot = self._render_montage(tmpd, lambda p: prog(p * 0.6),
                                                       lambda: False)
                    if not joined:
                        ok, msg, mb = False, "Не вдалося зібрати монтаж.", 0.0
                    else:
                        ok, msg, mb = dc_core.export_gif(
                            joined, out_path, [(0.0, tot)],
                            progress_cb=lambda p: prog(60.0 + p * 0.4))
                except Exception as e:
                    dc_core.dlog("GIF EXCEPTION: " + repr(e))
                    ok, msg, mb = False, f"Помилка: {str(e)[:60]}", 0.0
                finally:
                    shutil.rmtree(tmpd, ignore_errors=True)
                self.after(0, lambda: self._done(ok, out_path, mb, msg))

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

    def _done(self, ok, out_path, mb, msg):
        self.busy = False                       # зупиняє ротацію фактів
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
            self.info_lbl.config(text=msg or "Не вдалося зберегти", fg=C_RED)
            return
        host.play_done_sound(self.cfg)          # звук «готово»
        try:                                    # статистика: обрізка/монтаж/gif = теж стиснення
            import stats
            orig_mb = os.path.getsize(self.file_path) / (1024 * 1024)
            stats.record("video", orig_mb, mb, [out_path])
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
                pasted = " · вставлено в Discord"
            except Exception:
                pasted = ""
        self.info_lbl.config(text=f"Готово ✓ {mb:.2f} МБ{pasted}", fg=C_GREEN)
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
        self.info_lbl.config(text="Лишити стиснуту копію на ПК?", fg=C_TEXT)
        self._btn(ec, "Лишити", self._close, primary=False).pack(side="left", padx=4)
        self._btn(ec, "Видалити",
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
        self._pause()                  # зупиняємо ffplay і його опитування
        self._disable_dnd()            # повертаємо оригінальний WndProc (інакше краш після destroy)
        shutil.rmtree(self._tmp, ignore_errors=True)
        try:
            self.destroy()
        finally:
            if self.on_close:
                self.on_close()
