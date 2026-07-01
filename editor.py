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
        self._tmp = tempfile.mkdtemp(prefix="dedit_")
        self._frames = [os.path.join(self._tmp, "a.png"), os.path.join(self._tmp, "b.png")]

        self.title("✂ Редактор відео — Discord Auto-Compress")
        self.configure(bg=C_BG)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._build()
        self._redraw()
        self._show_poster(0.0)

    # ----------------------------------------------------------------- UI -- #
    def _build(self):
        tk.Label(self, text="Дивись, ріж на шматки, переставляй — і збережи під Discord",
                 bg=C_BG, fg=C_MUTED, font=(FONT, 10)).pack(pady=(10, 6))
        self.video = tk.Canvas(self, width=self.VW, height=self.VH, bg="black", highlightthickness=0)
        self.video.pack()

        pc = tk.Frame(self, bg=C_BG); pc.pack(pady=6)
        self.play_btn = self._btn(pc, "▶ Грати", self._toggle_play)
        self.play_btn.pack(side="left", padx=3)
        self._btn(pc, "⏮", self._to_start, primary=False).pack(side="left", padx=3)
        self._btn(pc, "✂ Розрізати тут", self._cut_here).pack(side="left", padx=3)
        self.time_lbl = tk.Label(pc, text="0:00.0 / 0:00.0", bg=C_BG, fg=C_TEXT, font=(FONT, 10))
        self.time_lbl.pack(side="left", padx=10)

        tk.Label(self, text="Джерело (клік — перемотати, ✂ ставить розріз):",
                 bg=C_BG, fg=C_MUTED, font=(FONT, 9)).pack(anchor="w", padx=14)
        self.tl = tk.Canvas(self, width=self.TW, height=34, bg=C_DARK, highlightthickness=0)
        self.tl.pack(padx=14, pady=(0, 8))
        self.tl.bind("<Button-1>", self._tl_click)

        tk.Label(self, text="Твій монтаж (клік — вибрати шматок):",
                 bg=C_BG, fg=C_MUTED, font=(FONT, 9)).pack(anchor="w", padx=14)
        self.seg = tk.Canvas(self, width=self.TW, height=48, bg=C_DARK, highlightthickness=0)
        self.seg.pack(padx=14, pady=(0, 6))
        self.seg.bind("<Button-1>", self._seg_click)

        sc = tk.Frame(self, bg=C_BG); sc.pack(pady=2)
        self._btn(sc, "◀ Лівіше", lambda: self._move(-1), primary=False).pack(side="left", padx=3)
        self._btn(sc, "▶ Правіше", lambda: self._move(1), primary=False).pack(side="left", padx=3)
        self._btn(sc, "► Переглянути шматок", self._play_segment, primary=False).pack(side="left", padx=3)
        self._btn(sc, "🗑 Прибрати", self._remove, primary=False).pack(side="left", padx=3)

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
            self._launch(self.cur, None)

    def _play_segment(self):
        s, e = self.pieces[self.order[self.sel]]
        self._launch(s, e - s)

    def _launch(self, start, dur):
        self._pause()
        start = max(0.0, min(self.dur, start))
        self._play_start = start
        self._play_end = min(self.dur, start + dur) if dur else self.dur
        w = self.video.winfo_width() or self.VW
        h = self.video.winfo_height() or self.VH
        self._embed_title = f"dac_play_{os.getpid()}_{int(start * 1000)}"
        cmd = ["ffplay", "-hide_banner", "-loglevel", "error", "-noborder", "-autoexit",
               "-left", "32000", "-top", "32000",   # спавн за межами екрана — без спалаху
               "-x", str(w), "-y", str(h), "-ss", f"{start:.3f}"]
        if dur is not None:
            cmd += ["-t", f"{max(0.1, dur):.3f}"]
        cmd += ["-window_title", self._embed_title, "-i", self.file_path]
        try:
            self._ffplay = subprocess.Popen(cmd, creationflags=dc_core.NO_WINDOW)
        except FileNotFoundError:
            self.info_lbl.config(text="ffplay не знайдено — онови ffmpeg", fg=C_RED)
            return
        self.playing = True
        self._embedded = None
        self._play_t0 = time.monotonic()
        try:
            self.play_btn.config(text="⏸ Стоп")
        except tk.TclError:
            pass
        self._embed_try(0)
        self._play_progress()

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
                return
        except Exception:
            pass
        if n < 80:  # ffplay може створювати вікно кілька сотень мс
            self.after(50, lambda: self._embed_try(n + 1))

    def _play_progress(self):
        """Рухаємо playhead за годинником + стежимо, чи не завершилось відтворення."""
        if not self.playing:
            return
        p = getattr(self, "_ffplay", None)
        if p is None or p.poll() is not None:
            return self._pause()
        pos = self._play_start + (time.monotonic() - self._play_t0)
        if pos >= self._play_end:
            return self._pause()
        self.cur = min(self.dur, pos)
        self._update_time()
        self._draw_timeline()
        self._tick_id = self.after(80, self._play_progress)

    def _pause(self):
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
        self._seek(0.0)

    # --------------------------------------------------------- ножиці ------ #
    def _cut_here(self):
        self._cut_at(self.cur)

    def _cut_at(self, t):
        for pi, (s, e) in enumerate(self.pieces):
            if s < t < e:
                self.pieces[pi] = (s, t)
                self.pieces.insert(pi + 1, (t, e))
                self.order = [ix + 1 if ix >= pi + 1 else ix for ix in self.order]
                slot = self.order.index(pi)
                self.order.insert(slot + 1, pi + 1)
                self.sel = slot
                break
        self._redraw()

    def _move(self, d):
        j = self.sel + d
        if 0 <= j < len(self.order):
            self.order[self.sel], self.order[j] = self.order[j], self.order[self.sel]
            self.sel = j
            self._redraw()

    def _remove(self):
        if len(self.order) > 1:
            del self.order[self.sel]
            self.sel = min(self.sel, len(self.order) - 1)
            self._redraw()

    # --------------------------------------------------------- малювання --- #
    def _redraw(self):
        self._draw_timeline(); self._draw_segments(); self._update_time(); self._update_info()

    def _update_time(self):
        self.time_lbl.config(text=f"{fmt(self.cur)} / {fmt(self.dur)}")

    def _draw_timeline(self):
        c = self.tl; c.delete("all"); W = self.TW
        s, e = self.pieces[self.order[self.sel]]
        c.create_rectangle(s / self.dur * W, 0, e / self.dur * W, 34, fill="#3a3f57", outline="")
        for b in sorted({b for p in self.pieces for b in p}):
            x = b / self.dur * W
            c.create_line(x, 0, x, 34, fill=C_BLURPLE, width=2)
        xh = self.cur / self.dur * W
        c.create_line(xh, 0, xh, 34, fill="#ffffff", width=2)

    def _draw_segments(self):
        c = self.seg; c.delete("all"); W = self.TW
        total = sum(self.pieces[ix][1] - self.pieces[ix][0] for ix in self.order) or 1
        x = 0; self._seg_rects = []
        for slot, ix in enumerate(self.order):
            s, e = self.pieces[ix]
            w = (e - s) / total * W
            fill = C_BLURPLE if slot == self.sel else C_BG2
            c.create_rectangle(x + 1, 2, x + w - 1, 46, fill=fill, outline=C_DARK)
            c.create_text(x + w / 2, 16, text=f"#{slot + 1}", fill=C_TEXT, font=(FONT, 9, "bold"))
            c.create_text(x + w / 2, 32, text=f"{fmt(s)}–{fmt(e)}", fill=C_TEXT, font=(FONT, 7))
            self._seg_rects.append((x, x + w, slot))
            x += w

    def _tl_click(self, ev):
        self._seek(ev.x / self.TW * self.dur)

    def _seg_click(self, ev):
        for x1, x2, slot in getattr(self, "_seg_rects", []):
            if x1 <= ev.x <= x2:
                self.sel = slot
                self._seek(self.pieces[self.order[slot]][0])
                break

    def _update_info(self):
        total = sum(self.pieces[ix][1] - self.pieces[ix][0] for ix in self.order)
        target = float(self.cfg["target_mb"])
        v = dc_core.calc_video_kbps(total, target, self.cfg["audio_kbps"], self.info["has_audio"]) or 0
        if v >= 600: col, tag = C_GREEN, "✓ гарна якість"
        elif v >= 150: col, tag = "#faa61a", "⚠ норм"
        elif v >= 50: col, tag = "#faa61a", "⚠ слабка"
        else: col, tag = C_RED, "✗ задовго"
        self.info_lbl.config(
            text=f"Підсумок: {len(self.order)} шматк. · {total:.1f} с · ~{v} kbps · {tag}", fg=col)
        if not self.busy:
            self.export_btn.config(state=("normal" if v >= 50 else "disabled"))

    # ----------------------------------------------------------- експорт --- #
    def _export(self):
        segs = [self.pieces[ix] for ix in self.order]
        if not segs:
            return
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
        self.after(2600, self._close)

    def _close(self):
        self._pause()                  # зупиняємо ffplay і його опитування
        shutil.rmtree(self._tmp, ignore_errors=True)
        try:
            self.destroy()
        finally:
            if self.on_close:
                self.on_close()
