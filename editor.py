#!/usr/bin/env python3
"""
Video Editor для Discord Auto-Compress
======================================
Міні-редактор:
  • відтворення ЗІ ЗВУКОМ у окремому вікні через ffplay (кнопка «Грати») — стабільно, без ffpyplayer;
  • прев'ю/перемотка кадру (ffmpeg→PNG) — миттєво при кліку на таймлайн;
  • ножиці: розрізати відео на кілька шматків (клік «✂ Розрізати тут»);
  • перевпорядкування / видалення / перегляд кожного шматка;
  • експорт: склейка вибраних шматків у порядку та стиснення під ліміт Discord.

Кадрове прев'ю — через перевірений extract_frame (ffmpeg→PNG); звук — через ffplay-процес.
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

import dc_core
import discord_overlay as host

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
TLH = 66                     # висота ЄДИНОЇ доріжки монтажу
THUMB_W = 40                 # ширина кадру кіно-стрічки


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
        self.dur = max(0.1, info["duration"])

        self.pieces = [(0.0, self.dur)]
        self.order = [0]
        self.sel = 0

        self.playing = False
        self.cur = 0.0
        self.play_until = None
        self._ffplay = None
        self._embedded = None
        self._play_start = 0.0
        self._play_end = 0.0
        self._play_t0 = 0.0
        self._embed_title = ""
        self._img = None
        self._tick_id = None
        self._prev_after = None
        self._frame_idx = 0
        self.busy = False
        self._drag = None            # 'L'/'R' — тягнемо ручку обрізки; None — ні
        self._active = None          # 'L'/'R' — остання чіпана ручка (для стрілок-нуджу)
        self._fps = float(info.get("fps", 30) or 30)
        self._tip_t = None           # час над ручкою під час обрізки (як у CapCut, тимчасово)
        self._tip_after = None
        self._nudge_active = False   # щоб серія стрілок була ОДНИМ кроком undo
        self._playhead_x = 0
        self._ffplay_pos = None      # РЕАЛЬНА позиція ffplay (парситься з його -stats у stderr)
        self._stat_offset = None     # абс/віднос конвенція часу ffplay
        self._stat_log_t = 0.0       # тротлінг логу позицій
        self._strip_imgs = None      # кадри кіно-стрічки (готуються у фоні)
        self._strip_times = []       # час кожного кадру стрічки у джерелі (сек)
        self._sel_xs = self._sel_xe = 0
        self._clip_rects = []        # (slot, cx1, cx2, ix) для кліків по кліпах
        self._undo = []; self._redo = []   # історія для скасувати/повторити
        self._zoom = 1.0             # масштаб доріжки (Ctrl+колесо)
        self._scroll = 0.0           # горизонтальний зсув (px) коли зумнуто
        self._tmp = tempfile.mkdtemp(prefix="dedit_")
        self._frames = [os.path.join(self._tmp, "a.png"), os.path.join(self._tmp, "b.png")]

        self.title("✂ Редактор відео — Discord Auto-Compress")
        self.configure(bg=C_BG)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._build()
        self._redraw()
        self._show_poster(0.0)
        self._gen_filmstrip()        # кіно-стрічка кадрів на доріжку (як у CapCut)

    # ----------------------------------------------------------------- UI -- #
    def _build(self):
        tk.Label(self, text="Одна доріжка: клік — вибрати кліп · тягни білі ручки — обрізати · ✂ — розрізати",
                 bg=C_BG, fg=C_MUTED, font=(FONT, 9)).pack(pady=(10, 6))
        self.video = tk.Canvas(self, width=self.VW, height=self.VH, bg="black", highlightthickness=0)
        self.video.pack()

        pc = tk.Frame(self, bg=C_BG); pc.pack(pady=6)
        self.play_btn = self._btn(pc, "▶ Грати", self._toggle_play)
        self.play_btn.pack(side="left", padx=3)
        self._btn(pc, "⏮", self._to_start, primary=False).pack(side="left", padx=3)
        self._btn(pc, "✂ Розрізати", self._cut_here).pack(side="left", padx=3)
        self.undo_btn = self._btn(pc, "↶", self._undo_action, primary=False)
        self.undo_btn.pack(side="left", padx=(12, 3))
        self.redo_btn = self._btn(pc, "↷", self._redo_action, primary=False)
        self.redo_btn.pack(side="left", padx=3)

        # ---- ЄДИНА доріжка монтажу: кіно-стрічка + ручки обрізки + плейхед ----
        self.tl = tk.Canvas(self, width=self.TW, height=TLH, bg=C_TRACK, highlightthickness=0)
        self.tl.pack(padx=14, pady=(4, 8))
        self.tl.bind("<Button-1>", self._tl_press)
        self.tl.bind("<B1-Motion>", self._tl_motion)
        self.tl.bind("<ButtonRelease-1>", self._tl_release)
        self.tl.bind("<Control-MouseWheel>", self._on_zoom)   # Ctrl+колесо = зум
        self.tl.bind("<MouseWheel>", self._on_scroll)          # колесо = горизонтальний скрол (коли зумнуто)
        # кнопки зуму (Ctrl+колесо неочевидне) + точне підлаштування стрілками
        zc = tk.Frame(self, bg=C_BG); zc.pack(pady=(0, 2))
        self._btn(zc, "🔍−", lambda: self._zoom_step(0.8), primary=False).pack(side="left", padx=3)
        self._btn(zc, "🔍+", lambda: self._zoom_step(1.25)).pack(side="left", padx=3)
        tk.Label(zc, text="◀ ▶ стрілки — точно по кадру (Shift = 1с)", bg=C_BG, fg=C_MUTED,
                 font=(FONT, 8)).pack(side="left", padx=8)
        # стрілки клавіатури -> зсув активної ручки обрізки по кадру (точність як у CapCut)
        self.bind("<Left>", lambda e: self._nudge(-1, big=False))
        self.bind("<Right>", lambda e: self._nudge(1, big=False))
        self.bind("<Shift-Left>", lambda e: self._nudge(-1, big=True))
        self.bind("<Shift-Right>", lambda e: self._nudge(1, big=True))
        try:
            self.focus_set()
        except tk.TclError:
            pass

        sc = tk.Frame(self, bg=C_BG); sc.pack(pady=2)
        self._btn(sc, "◀ Пересунути", lambda: self._move(-1), primary=False).pack(side="left", padx=3)
        self._btn(sc, "Пересунути ▶", lambda: self._move(1), primary=False).pack(side="left", padx=3)
        self._btn(sc, "► Переглянути", self._play_segment, primary=False).pack(side="left", padx=3)
        self._btn(sc, "🗑 Прибрати", self._remove, primary=False).pack(side="left", padx=3)

        # гарячі клавіші скасувати/повторити
        self.bind("<Control-z>", lambda e: self._undo_action())
        self.bind("<Control-y>", lambda e: self._redo_action())
        self.bind("<Control-Z>", lambda e: self._redo_action())   # Ctrl+Shift+Z

        self.info_lbl = tk.Label(self, text="", bg=C_BG, fg=C_TEXT, font=(FONT, 11, "bold"))
        self.info_lbl.pack(pady=(8, 2))
        ec = tk.Frame(self, bg=C_BG); ec.pack(pady=(2, 12))
        self.export_btn = self._btn(ec, "Зберегти і вставити  ▶", self._export)
        self.export_btn.pack(side="left", padx=4)
        self._btn(ec, "Скасувати", self._close, primary=False).pack(side="left", padx=4)

    def _btn(self, parent, text, cmd, primary=True):
        bg, hov = (C_BLURPLE, C_BLURPLE_H) if primary else (C_BG2, C_DARK)
        b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=C_TEXT,
                      activebackground=hov, activeforeground=C_TEXT, relief="flat",
                      font=(FONT, 10, "bold"), bd=0, padx=12, pady=7, cursor="hand2")
        b.bind("<Enter>", lambda e: b.config(bg=hov))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

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
        self._frame_idx ^= 1
        png = self._frames[self._frame_idx]

        def work():
            if dc_core.extract_frame(self.file_path, t, png, width=self.VW):
                self.after(0, lambda: self._draw_png(png))
        threading.Thread(target=work, daemon=True).start()

    def _draw_png(self, png):
        if self.playing:
            return
        try:
            self._img = tk.PhotoImage(file=png)
            self.video.delete("frame")
            self.video.create_image(self.VW // 2, self.VH // 2, image=self._img, tags="frame")
        except tk.TclError:
            pass

    # -------------- ВБУДОВАНЕ ВІДТВОРЕННЯ ЗІ ЗВУКОМ (ffplay через SetParent) ---- #
    # ffplay-процес запускаємо БЕЗ рамки і його вікно «вклеюємо» в наш відео-екран
    # через WinAPI SetParent -> відео зі звуком просто в редакторі (як у капкуті),
    # без крихкого рендерингу в самому Python (той давав segfault).
    def _toggle_play(self):
        if self.playing:
            self._pause()
        else:
            s, e = self.pieces[self.order[self.sel]]      # від плейхеда до кінця вибраного кліпа
            start = min(max(s, self.cur), e - 0.05)
            self._launch(start, e - start)

    def _play_segment(self):
        s, e = self.pieces[self.order[self.sel]]
        self.cur = s
        self._launch(s, e - s)

    def _launch(self, start, dur):
        self._pause()
        start = max(0.0, min(self.dur, start))
        self._play_start = start
        self._play_end = min(self.dur, start + dur) if dur else self.dur
        w = self.video.winfo_width() or self.VW
        h = self.video.winfo_height() or self.VH
        self._embed_title = f"dac_play_{os.getpid()}_{int(start * 1000)}"
        cmd = ["ffplay", "-hide_banner", "-loglevel", "error", "-stats", "-noborder", "-autoexit",
               "-left", "32000", "-top", "32000",   # спавн за межами екрана — без спалаху
               "-x", str(w), "-y", str(h), "-ss", f"{start:.3f}"]
        if dur is not None:
            cmd += ["-t", f"{max(0.1, dur):.3f}"]
        cmd += ["-window_title", self._embed_title, "-i", self.file_path]
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
        dc_core.dlog(f"PLAY launch build={dc_core.BUILD} start={start:.3f} dur={dur} "
                     f"t0={self._play_t0:.3f}")
        threading.Thread(target=self._read_ffplay_stats, args=(self._ffplay,), daemon=True).start()
        try:
            self.play_btn.config(text="⏸ Стоп")
        except tk.TclError:
            pass
        self._embed_try(0)
        self._play_progress()

    def _read_ffplay_stats(self, proc):
        """Читаємо stderr ffplay і парсимо ЙОГО реальну позицію відтворення (перше число
        у рядку -stats, напр. '  36.05 A-V: ...'). Рядки оновлюються через \\r."""
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
        if v != v or v < 0 or v > self.dur + 5:   # nan/сміття (ffplay спершу друкує nan) -> пропуск
            return
        if self._stat_offset is None:
            # визначаємо: ffplay звітує АБСОЛЮТНИЙ час чи від нуля сегмента
            self._stat_offset = 0.0 if abs(v - self._play_start) < abs(v) else self._play_start
            dc_core.dlog(f"  ffplay stat first={v:.3f} play_start={self._play_start:.3f} "
                         f"-> offset={self._stat_offset:.3f}")
        self._ffplay_pos = self._stat_offset + v
        now = time.monotonic()
        if now - self._stat_log_t > 0.4:      # тротлінг, щоб не залити лог
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
                dc_core.dlog(f"EMBED ok n={n} elapsed={n * 0.05:.2f}s ffplay_pos={self._ffplay_pos}")
                return
        except Exception:
            pass
        if n < 80:  # ffplay може створювати вікно кілька сотень мс
            self.after(50, lambda: self._embed_try(n + 1))

    def _play_progress(self):
        """Рухаємо playhead. Пріоритет — РЕАЛЬНА позиція ffplay (-stats); wall-clock лише запас."""
        if not self.playing:
            return
        p = getattr(self, "_ffplay", None)
        if p is None or p.poll() is not None:
            return self._pause()
        if self._ffplay_pos is not None:
            pos = self._ffplay_pos                    # де ffplay РЕАЛЬНО грає
        else:
            pos = self._play_start + (time.monotonic() - self._play_t0)  # запасний годинник
        if pos >= self._play_end:
            return self._pause()
        self.cur = min(self.dur, pos)
        self._draw_track()
        self._tick_id = self.after(80, self._play_progress)

    def _pause(self):
        if self.playing:
            dc_core.dlog(f"PAUSE cur={self.cur:.3f} ffplay_pos={self._ffplay_pos}")
        self.playing = False
        self.play_until = None
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
            self._pause()             # почали перемотувати — зупиняємо відтворення
        t = max(0, min(self.dur, t))
        self.cur = t
        self._show_poster(t)
        self._redraw()

    def _to_start(self):
        self._seek(self.pieces[self.order[self.sel]][0])   # на початок вибраного кліпа

    # --------------------------------------------------------- ножиці ------ #
    def _cut_here(self):
        wall = self._play_start + (time.monotonic() - self._play_t0)
        dc_core.dlog(f"CUT_HERE build={dc_core.BUILD} playing={self.playing} cur={self.cur:.3f} "
                     f"ffplay_pos={self._ffplay_pos} wallclock={wall:.3f} "
                     f"play_start={self._play_start:.3f} play_end={self._play_end:.3f}")
        if self.playing:
            self._pause()          # спершу пауза -> ріжемо рівно по кадру, який ВИДНО (не по годиннику)
        dc_core.dlog(f"CUT_HERE after_pause cur={self.cur:.3f}")
        self._cut_at(self.cur)

    def _cut_at(self, t):
        done = False
        for pi, (s, e) in enumerate(self.pieces):
            if s < t < e:
                self._push_undo()
                self.pieces[pi] = (s, t)
                self.pieces.insert(pi + 1, (t, e))
                self.order = [ix + 1 if ix >= pi + 1 else ix for ix in self.order]
                slot = self.order.index(pi)
                self.order.insert(slot + 1, pi + 1)
                self.sel = slot
                done = True
                break
        dc_core.dlog(f"CUT_AT t={t:.3f} done={done} "
                     f"pieces={[(round(a, 3), round(b, 3)) for a, b in self.pieces]}")
        self._redraw()

    def _move(self, d):
        j = self.sel + d
        if 0 <= j < len(self.order):
            self._push_undo()
            self.order[self.sel], self.order[j] = self.order[j], self.order[self.sel]
            self.sel = j
            self._redraw()

    def _remove(self):
        if len(self.order) > 1:
            self._push_undo()
            del self.order[self.sel]
            self.sel = min(self.sel, len(self.order) - 1)
            self._redraw()

    # ------------------------------------------------ скасувати / повторити --- #
    def _snapshot(self):
        return (list(self.pieces), list(self.order), self.sel)

    def _push_undo(self):
        self._undo.append(self._snapshot())
        if len(self._undo) > 80:
            self._undo.pop(0)
        self._redo.clear()

    def _apply_state(self, st):
        pieces, order, sel = st
        self.pieces = list(pieces)
        self.order = list(order)
        self.sel = min(sel, len(self.order) - 1) if self.order else 0
        s, e = self.pieces[self.order[self.sel]]
        self.cur = min(max(self.cur, s), e)

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

    def _update_time(self):
        pass   # без цифр — позиція видно по плейхеду

    # ---- кіно-стрічка (кадри) — по одному набору на все відео, ділиться між кліпами ----
    def _gen_filmstrip(self):
        n = 24
        # кожен кадр стрічки прив'язаний до КОНКРЕТНОГО часу — і саме на цей час його й
        # витягуємо (окремий -ss на кадр). Раніше один fps-фільтр давав кадри в трохи
        # інших моментах, ніж мітки _strip_times -> для довгих відео мініатюра «їхала»
        # на пару секунд від свого часу, і обрізка по картинці була неточною.
        self._strip_times = [(i + 0.5) / n * self.dur for i in range(n)]

        def work():
            # ffmpeg — у фоні; PhotoImage створюємо вже в головному потоці Tk (інакше краш)
            for i, t in enumerate(self._strip_times):
                p = os.path.join(self._tmp, "strip_%02d.png" % (i + 1))
                try:
                    subprocess.run(
                        ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", self.file_path,
                         "-frames:v", "1", "-vf", f"scale={THUMB_W}:{TLH - 6}", p],
                        capture_output=True, creationflags=dc_core.NO_WINDOW)
                except Exception:
                    pass
            self.after(0, lambda: self._load_filmstrip(n))
        threading.Thread(target=work, daemon=True).start()

    def _load_filmstrip(self, n):
        imgs = []
        for i in range(1, n + 1):
            p = os.path.join(self._tmp, f"strip_{i:02d}.png")
            try:
                imgs.append(tk.PhotoImage(file=p) if os.path.exists(p) else None)
            except tk.TclError:
                imgs.append(None)
        if any(imgs):
            m = len(imgs)
            self._strip_imgs = imgs
            self._strip_times = [(i + 0.5) / m * self.dur for i in range(m)]
            self._draw_track()

    def _nearest_thumb(self, src):
        t = self._strip_times
        if not t:
            return None
        i = min(range(len(t)), key=lambda k: abs(t[k] - src))
        return self._strip_imgs[i]

    def _draw_clip_strip(self, c, cx1, cx2, s, e):
        """Тайлимо кадри кіно-стрічки всередині кліпа за його джерельним діапазоном."""
        if not self._strip_imgs:
            return
        width = cx2 - cx1
        k = max(1, int(width // THUMB_W))
        for j in range(k):
            xx = cx1 + j * THUMB_W
            if xx + THUMB_W > cx2 + 4:
                break
            im = self._nearest_thumb(s + (j + 0.5) / k * (e - s))
            if im:
                c.create_image(int(xx), 3, image=im, anchor="nw")

    def _draw_handle(self, c, x, left, active=False):
        """Біла ручка-хендл обрізки з вертикальною рискою (як у CapCut).
        Активну (яку рухають стрілки) підсвічуємо кольором плейхеда."""
        w = 10 if active else 8
        x1, x2 = (x, x + w) if left else (x - w, x)
        col = C_PLAY if active else C_HANDLE
        c.create_polygon(host._rr_pts(x1, 2, x2, TLH - 2, 4), smooth=True, fill=col, outline="")
        cx = (x1 + x2) / 2
        c.create_line(cx, TLH * 0.30, cx, TLH * 0.70, fill=C_DARK, width=2)

    # ---- ЄДИНА доріжка: кліпи в порядку монтажу, фіксований масштаб (px/сек) ----
    # ---- масштаб/скрол доріжки (Ctrl+колесо приближає біля плейхеда) ----
    def _pps(self):
        return (self.TW / self.dur) * self._zoom

    def _clip_durs(self):
        return [self.pieces[ix][1] - self.pieces[ix][0] for ix in self.order]

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
            s, e = self.pieces[self.order[slot]]
            if slot == self.sel:
                return acc + min(max(self.cur, s), e) - s
            acc += (e - s)
        return acc

    def _clamp_scroll(self, pps):
        self._scroll = max(0.0, min(self._scroll, max(0.0, self._content_width(pps) - self.TW)))

    def _apply_zoom(self, factor):
        old = self._pps()
        ft = self._playhead_montage_t()
        screen_x = self._content_x_of(ft, old) - self._scroll     # тримаємо плейхед на місці
        self._zoom = min(60.0, max(1.0, self._zoom * factor))     # до 60x -> точний різ на довгих відео
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
        step = 1.0 if big else 1.0 / self._fps
        eps = 1.0 / self._fps
        pi = self.order[self.sel]
        s, e = self.pieces[pi]
        lo = self.pieces[pi - 1][1] if pi > 0 else 0.0
        hi = self.pieces[pi + 1][0] if pi < len(self.pieces) - 1 else self.dur
        if not self._nudge_active:      # уся серія стрілок = один крок undo
            self._push_undo(); self._nudge_active = True
        if self._active == "L":
            ns = min(max(lo, s + direction * step), e - eps)
            self.pieces[pi] = (ns, e); self.cur = self._tip_t = ns
        elif self._active == "R":
            ne = max(min(hi, e + direction * step), s + eps)
            self.pieces[pi] = (s, ne); self.cur = self._tip_t = ne
        else:                           # нема активної ручки -> рухаємо плейхед
            self.cur = self._tip_t = min(max(s, self.cur + direction * step), e)
        self._show_poster(self.cur)
        self._redraw()
        self._update_info()
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
            s, e = self.pieces[ix]
            w = max(6.0, (e - s) * pps)
            cx1, cx2 = x, x + w
            sel = slot == self.sel
            c.create_rectangle(cx1, 3, cx2, TLH - 3, fill=C_CLIP, outline="")
            self._draw_clip_strip(c, cx1, cx2, s, e)
            if not sel:                    # неактивні кліпи трохи притемнені (фокус на вибраному)
                c.create_rectangle(cx1, 3, cx2, TLH - 3, fill="#000000", stipple="gray25", outline="")
            c.create_rectangle(cx1, 3, cx2, TLH - 3,
                               outline=C_HANDLE if sel else C_DARK, width=2 if sel else 1)
            if sel:
                self._sel_xs, self._sel_xe = cx1, cx2
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
        # час-підказка над активною ручкою/плейхедом (з'являється лише під час обрізки)
        if self._tip_t is not None:
            tx = (self._sel_xe if self._active == "R"
                  else self._sel_xs if self._active == "L" else self._playhead_x)
            tx = min(max(30, tx), W - 30)
            c.create_rectangle(tx - 30, 0, tx + 30, 16, fill=C_DARK, outline=C_PLAY)
            c.create_text(tx, 8, text=self._fmt_tt(self._tip_t), fill="#ffffff", font=(FONT, 8, "bold"))

    # ---- взаємодія на одній доріжці: ручки / вибір кліпа / плейхед ----
    def _tl_press(self, ev):
        # 1) ручки обрізки вибраного кліпа
        if abs(ev.x - self._sel_xs) <= 11 or abs(ev.x - self._sel_xe) <= 11:
            pi = self.order[self.sel]
            s, e = self.pieces[pi]
            self._push_undo()
            self._drag = "L" if abs(ev.x - self._sel_xs) <= 11 else "R"
            self._active = self._drag        # ця ручка тепер «активна» для стрілок
            self._nudge_active = True         # drag уже штовхнув undo -> стрілки не дублюють
            self._tip_t = s if self._drag == "L" else e
            self._d0 = {"x0": ev.x, "s0": s, "e0": e,
                        "pps": (self._sel_xe - self._sel_xs) / max(0.001, e - s)}
            self._redraw()
            return
        # 2) клік по кліпу: вибрати; всередині вибраного — перемістити плейхед
        self._drag = None
        self._active = None        # клік по тілу кліпа -> стрілки рухають ПЛЕЙХЕД (для ножиць)
        self._tip_t = None
        for slot, ix, cx1, cx2 in self._clip_rects:
            if cx1 - 2 <= ev.x <= cx2 + 2:
                s, e = self.pieces[ix]
                if self.playing:
                    self._pause()
                if slot == self.sel:
                    self.cur = min(max(s, s + (ev.x - cx1) / max(1.0, cx2 - cx1) * (e - s)), e)
                else:
                    self.sel = slot
                    self.cur = s
                self._show_poster(self.cur)
                self._redraw()
                return

    def _tl_motion(self, ev):
        if not self._drag:
            return
        if self.playing:
            self._pause()
        pi = self.order[self.sel]
        d0 = self._d0
        dsrc = (ev.x - d0["x0"]) / d0["pps"]
        lo = self.pieces[pi - 1][1] if pi > 0 else 0.0
        hi = self.pieces[pi + 1][0] if pi < len(self.pieces) - 1 else self.dur
        if self._drag == "L":
            ns = max(lo, min(d0["s0"] + dsrc, d0["e0"] - 0.1))
            self.pieces[pi] = (ns, d0["e0"]); self.cur = self._tip_t = ns
        else:
            ne = min(hi, max(d0["e0"] + dsrc, d0["s0"] + 0.1))
            self.pieces[pi] = (d0["s0"], ne); self.cur = self._tip_t = ne
        self._show_poster(self.cur)
        self._redraw()

    def _tl_release(self, _ev):
        self._drag = None
        if self._tip_t is not None:      # лишаємо час-підказку на мить, тоді ховаємо
            self._schedule_tip_clear()

    def _update_info(self):
        total = sum(self.pieces[ix][1] - self.pieces[ix][0] for ix in self.order)
        target = float(self.cfg["target_mb"])
        v = dc_core.calc_video_kbps(total, target, self.cfg["audio_kbps"], self.info["has_audio"]) or 0
        if v >= 600: col, tag = C_GREEN, "✓ Гарна якість"
        elif v >= 150: col, tag = "#faa61a", "⚠ Нормальна якість"
        elif v >= 50: col, tag = "#faa61a", "⚠ Слабка якість"
        else: col, tag = C_RED, "✗ Задовгий фрагмент"
        self.info_lbl.config(text=tag, fg=col)   # без цифр — лише оцінка якості
        if not self.busy:
            self.export_btn.config(state=("normal" if v >= 50 else "disabled"))

    # ----------------------------------------------------------- експорт --- #
    def _export(self):
        segs = [self.pieces[ix] for ix in self.order]
        if not segs:
            return
        # ДІАГНОСТИКА обрізки -> %TEMP%\dac_debug.log (щоб зрозуміти зсув на реальному відео юзера)
        try:
            dc_core.dlog(f"EDITOR EXPORT build={dc_core.BUILD} dur={self.dur:.3f} "
                         f"segs={[(round(s,3), round(e,3)) for s, e in segs]}")
            dc_core.dlog(dc_core.probe_diag(self.file_path))
        except Exception:
            pass
        self._pause()
        self.busy = True
        self.export_btn.config(state="disabled")
        target = float(self.cfg["target_mb"])
        scale = (dc_core.pick_auto_scale(self.info, target, self.cfg["audio_kbps"])
                 if self.cfg.get("auto_scale", True) else 0)
        out_path = dc_core.output_name(self.file_path, target)

        def worker():
            ok, msg, mb = dc_core.compress_segments(
                self.file_path, out_path, target, scale, self.cfg["audio_kbps"], self.info, segs,
                progress_cb=lambda p: self.after(0, lambda: self.info_lbl.config(
                    text=f"Зберігаю… {int(p)}%", fg=C_BLURPLE)),
                should_cancel=lambda: False)
            self.after(0, lambda: self._done(ok, out_path, mb, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, ok, out_path, mb, msg):
        if not ok:
            if os.path.exists(out_path):
                try: os.remove(out_path)
                except OSError: pass
            self.busy = False
            self.export_btn.config(state="normal")
            self.info_lbl.config(text=msg or "Не вдалося зберегти", fg=C_RED)
            return
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
        # keep_local: як і в оверлеї — питаємо / завжди лишаємо / завжди видаляємо
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
        """Видаляє файли з затримкою у ФОНОВОМУ потоці (переживає закриття вікна редактора)."""
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
        shutil.rmtree(self._tmp, ignore_errors=True)
        try:
            self.destroy()
        finally:
            if self.on_close:
                self.on_close()
