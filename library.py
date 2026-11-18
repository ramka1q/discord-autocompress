#!/usr/bin/env python3
"""
library.py — «Мої монтажі».
  • усе, що збережено з редактора (MP4 / MP3 / GIF), копіюється в папку
    «Відео\\Discord Auto-Compress» — нічого не губиться, навіть якщо оригінал видалено;
  • Ctrl+Alt+E (або меню трею) — галерея цих відео: клік -> вставити в Discord,
    ▶ — переглянути, ✂ — змонтувати знову, «Новий монтаж» — редактор для будь-якого відео.
Тільки стандартна бібліотека.
"""
import os
import shutil
import subprocess
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog

import dc_core
import i18n

MEDIA_EXT = (".mp4", ".mp3", ".gif", ".webm", ".m4a", ".mov")
HOTKEY_TEXT = "Ctrl+Alt+E"
_open = {"win": None}


def T(key, **kw):
    import discord_overlay as host
    return i18n.tr(host.LANG, key, **kw)


def lib_dir() -> str:
    """Папка «Мої монтажі» (створюється сама; якщо «Відео» недоступна — у TEMP)."""
    for base in (os.path.join(os.path.expanduser("~"), "Videos"),
                 os.path.join(tempfile.gettempdir(), "DiscordAutoCompress")):
        d = os.path.join(base, "Discord Auto-Compress")
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".w")
            open(probe, "w").close()
            os.remove(probe)
            return d
        except OSError:
            continue
    return tempfile.gettempdir()


def add(path) -> str:
    """Копія збереженого файла в «Мої монтажі». Повертає шлях копії ("" — не вдалося)."""
    try:
        d = lib_dir()
        if os.path.dirname(os.path.abspath(path)) == os.path.abspath(d):
            return path
        dst = os.path.join(d, time.strftime("%Y-%m-%d %H-%M-%S ") + os.path.basename(path))
        shutil.copy2(path, dst)
        dc_core.dlog(f"LIBRARY add {os.path.basename(dst)}")
        return dst
    except Exception as e:
        dc_core.dlog("LIBRARY add fail " + repr(e))
        return ""


def items(limit=60) -> list:
    d = lib_dir()
    out = []
    try:
        for n in os.listdir(d):
            p = os.path.join(d, n)
            if n.lower().endswith(MEDIA_EXT) and os.path.isfile(p):
                out.append(p)
    except OSError:
        return []
    out.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return out[:limit]


def _thumb(path, w=192, h=108) -> str:
    """Перший кадр (кеш у TEMP). Для MP3 — None."""
    if path.lower().endswith((".mp3", ".m4a")):
        return ""
    cache = os.path.join(tempfile.gettempdir(), "dac_lib_thumbs")
    os.makedirs(cache, exist_ok=True)
    key = f"{abs(hash(path))}_{int(os.path.getmtime(path))}.png"
    out = os.path.join(cache, key)
    if not os.path.exists(out):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "0.3", "-i", path, "-frames:v", "1", "-vf",
                        f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x111214",
                        out], capture_output=True, creationflags=dc_core.BG)
    return out if os.path.exists(out) else ""


def open_editor(watcher, path, discord_hwnd=None):
    """Редактор для будь-якого відео (без вставки в Discord)."""
    try:
        info = dc_core.ffprobe_info(path)
    except Exception:
        return
    if not info.get("duration"):
        return
    from editor import VideoEditor
    watcher.overlay_open = True
    try:
        VideoEditor(watcher.root, path, info, watcher.cfg, discord_hwnd, watcher,
                    on_close=watcher._closed)
    except Exception as e:
        dc_core.dlog("LIBRARY open_editor fail " + repr(e))
        watcher.overlay_open = False


def pick_and_edit(watcher, parent=None, discord_hwnd=None):
    pats = " ".join("*" + e for e in sorted(dc_core.VIDEO_EXT))
    try:
        p = filedialog.askopenfilename(parent=parent or watcher.root, title=T("lib_pick"),
                                       filetypes=[(T("ed_media"), pats), (T("ed_all_files"), "*.*")])
    except tk.TclError:
        return
    if p:
        open_editor(watcher, p, discord_hwnd)


def open_gallery(watcher, discord_hwnd=None):
    w = _open.get("win")
    try:
        if w is not None and w.winfo_exists():
            w.lift()
            w.focus_force()
            return
    except tk.TclError:
        pass
    _open["win"] = Gallery(watcher, discord_hwnd)


class Gallery(tk.Toplevel):
    COLS, CW, CH = 3, 212, 172

    def __init__(self, watcher, discord_hwnd):
        import discord_overlay as host
        self.host, self.w, self.dhwnd = host, watcher, discord_hwnd
        super().__init__(watcher.root)
        self.C = {"bg": host.C_BG, "bg2": host.C_BG2, "dark": host.C_DARK, "text": host.C_TEXT,
                  "muted": host.C_MUTED, "acc": host.C_BLURPLE}
        self.title(T("lib_title") + " — Discord Auto-Compress")
        try:
            import appicon
            appicon.set_window_icon(self)
        except Exception:
            pass
        self.configure(bg=self.C["bg"])
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self._imgs = []
        self.bind("<Escape>", lambda e: self.destroy())
        self._build()
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        W, H = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{(sw - W) // 2}+{max(20, (sh - H) // 2 - 40)}")
        self.focus_force()

    def _build(self):
        C = self.C
        top = tk.Frame(self, bg=C["dark"])
        top.pack(fill="x")
        tk.Label(top, text="🎬  " + T("lib_title"), bg=C["dark"], fg=C["text"],
                 font=(self.host.FONT, 13, "bold")).pack(side="left", padx=14, pady=10)
        tk.Label(top, text=HOTKEY_TEXT, bg=C["dark"], fg=C["muted"],
                 font=(self.host.FONT, 9)).pack(side="left")
        for txt, cmd in ((T("lib_folder"), self._open_folder), (T("lib_new"), self._new)):
            b = tk.Label(top, text=txt, bg=C["acc"] if txt == T("lib_new") else C["bg2"], fg="#ffffff",
                         font=(self.host.FONT, 10, "bold"), padx=12, pady=6, cursor="hand2")
            b.pack(side="right", padx=(0, 10), pady=8)
            b.bind("<Button-1>", lambda e, c=cmd: c())
        tk.Label(self, text=T("lib_hint"), bg=C["bg"], fg=C["muted"],
                 font=(self.host.FONT, 9)).pack(anchor="w", padx=16, pady=(8, 2))
        files = items()
        if not files:
            tk.Label(self, text=T("lib_empty"), bg=C["bg"], fg=C["muted"], font=(self.host.FONT, 11),
                     width=52, height=6).pack(padx=20, pady=20)
            return
        rows = min(3, (len(files) + self.COLS - 1) // self.COLS)
        cv = tk.Canvas(self, bg=C["bg"], highlightthickness=0,
                       width=self.COLS * (self.CW + 10) + 10, height=rows * (self.CH + 10) + 10)
        cv.pack(padx=6, pady=(4, 12))
        body = tk.Frame(cv, bg=C["bg"])
        cv.create_window(0, 0, window=body, anchor="nw")
        body.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        wheel = lambda e: cv.yview_scroll(int(-e.delta / 120) * 2, "units")
        cv.bind("<MouseWheel>", wheel)
        for i, p in enumerate(files):
            self._card(body, p, i // self.COLS, i % self.COLS, wheel)

    def _card(self, parent, path, r, c, wheel):
        C = self.C
        f = tk.Frame(parent, bg=C["bg2"], width=self.CW, height=self.CH, cursor="hand2")
        f.grid(row=r, column=c, padx=5, pady=5)
        f.pack_propagate(False)
        pic = tk.Label(f, bg="#111214", fg=C["muted"], font=(self.host.FONT, 26),
                       text="🎵" if path.lower().endswith((".mp3", ".m4a")) else "…")
        pic.pack(padx=10, pady=(10, 4))
        nm = os.path.basename(path)
        nm = nm[20:] if len(nm) > 20 and nm[4] == "-" else nm      # без дати-префікса
        if len(nm) > 28:
            nm = nm[:26] + "…"
        tk.Label(f, text=nm, bg=C["bg2"], fg=C["text"], font=(self.host.FONT, 9, "bold"),
                 anchor="w").pack(fill="x", padx=10)
        try:
            mb = os.path.getsize(path) / 1048576
            when = time.strftime("%d.%m %H:%M", time.localtime(os.path.getmtime(path)))
        except OSError:
            mb, when = 0, ""
        row = tk.Frame(f, bg=C["bg2"])
        row.pack(fill="x", padx=10, pady=(2, 8))
        tk.Label(row, text=f"{mb:.1f} МБ · {when}", bg=C["bg2"], fg=C["muted"],
                 font=(self.host.FONT, 8)).pack(side="left")
        for txt, cmd, tip in (("✂", lambda: self._edit(path), "edit"), ("▶", lambda: os.startfile(path), "play")):
            b = tk.Label(row, text=txt, bg=C["dark"], fg=C["text"], font=(self.host.FONT, 10), padx=6,
                         cursor="hand2")
            b.pack(side="right", padx=(4, 0))
            b.bind("<Button-1>", lambda e, cm=cmd: (cm(), "break")[1])
        for wdg in (f, pic):
            wdg.bind("<Button-1>", lambda e, p=path: self._paste(p))
        for wdg in (f, pic, row):
            wdg.bind("<MouseWheel>", wheel)

        def load():
            t = _thumb(path)
            if t:
                self.after(0, lambda: self._set_pic(pic, t))
        threading.Thread(target=load, daemon=True).start()

    def _set_pic(self, lbl, png):
        try:
            im = tk.PhotoImage(file=png)
            self._imgs.append(im)
            lbl.config(image=im, text="")
        except tk.TclError:
            pass

    def _paste(self, path):
        h = self.host
        try:
            h.set_clipboard_files([path])
            if hasattr(self.w, "mark_self_clipboard"):
                self.w.mark_self_clipboard()
        except Exception:
            pass
        self.destroy()
        if self.dhwnd:
            try:
                h.user32.SetForegroundWindow(self.dhwnd)
                self.w.root.after(200, h.send_ctrl_v)
                return
            except Exception:
                pass
        try:
            self.w.notify(T("lib_title"), T("lib_copied"))
        except Exception:
            pass

    def _edit(self, path):
        self.destroy()
        open_editor(self.w, path, self.dhwnd)

    def _new(self):
        self.destroy()
        pick_and_edit(self.w, None, self.dhwnd)

    def _open_folder(self):
        try:
            os.startfile(lib_dir())
        except Exception:
            pass
