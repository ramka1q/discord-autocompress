#!/usr/bin/env python3
"""
settings_app.py — меню налаштувань.
Вікно без системної рамки (але з кнопкою в панелі завдань і заокругленими кутами
Windows 11): власний заголовок, бічна навігація, вміст на заокруглених картках,
тумблери, сегментовані перемикачі, повзунок, прев'ю тем. Кожна зміна зберігається
автоматично. Відкривається як Toplevel на прихованому root вартового.
Тільки стандартна бібліотека Tk (див. ui.py).
"""
import ctypes
import os
import shutil
import subprocess
import threading
import time

import tkinter as tk
import tkinter.filedialog as filedialog

import appicon
import dc_core
import deps
import i18n
import jokes
import monetize
import stats
import themes
import ui
import changelog

APP_VERSION = changelog.VERSION
# коли вийшла ця версія (дата і час публікації на GitHub) — з changelog.py
APP_RELEASED = changelog.RELEASED
REPO_URL = "https://github.com/ramka1q/discord-autocompress"
F = themes.FONT


class SettingsApp:
    W, H = 920, 640
    SIDE_W = 224

    def __init__(self, master, cfg, on_save, on_apply=None, on_close=None, on_restart=None,
                 tab=None, on_editor=None, on_gallery=None):
        """cfg — робоча копія конфіга; on_save(cfg) — зберегти; on_apply(cfg) —
        миттєво застосувати тему/мову (overlay+трей); on_close() — закрити;
        on_restart() — перезапустити всю програму (для кнопки після оновлення)."""
        self.cfg = dict(cfg)
        self.on_save = on_save
        self.on_apply = on_apply
        self.on_close_cb = on_close
        self.on_restart = on_restart
        self.on_editor, self.on_gallery = on_editor, on_gallery   # редактор / «Мої монтажі»
        self.lang = self.cfg.get("lang", "en")
        self.P = themes.palette(self.cfg.get("theme", "mono"))
        self._or_active = True
        # якщо чогось бракує (ffmpeg) — одразу відкриваємо вкладку «Встановлення»
        self._active_tab = tab or ("general" if deps.all_ok() else "setup")
        self._bench_busy = False
        self._toast_after = None
        self._upd_state = None          # результат перевірки оновлень (переживає перемикання вкладок)

        self.win = tk.Toplevel(master) if master is not None else tk.Tk()
        self.win.title(i18n.tr(self.lang, "app_title"))
        sh = self.win.winfo_screenheight()
        self.H = min(self.H, sh - 80)
        self.win.configure(bg=self.P["bg"])
        appicon.set_window_icon(self.win)
        self._center()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.after(300, lambda: self.win.attributes("-topmost", False))
        self.win.bind("<Map>", self._on_map)
        self.win.bind("<Escape>", lambda e: self._close())

        self._init_vars()      # усі змінні — ОДИН раз (щоб стан не губився між вкладками)
        self._build()
        ui.win_chrome(self.win, taskbar=True, rounded=True, dark=ui.luminance(self.P["bg"]) < 128)
        ui.fade_in(self.win, 180)

    def _init_vars(self):
        """Створює всі змінні налаштувань один раз. Віджети вкладок лише прив'язуються
        до них — тож перемикання вкладок НІКОЛИ не скидає вибране. Кожна зміна —
        авто-збереження (не треба тиснути «Зберегти»)."""
        c, w = self.cfg, self.win
        self.v_target = tk.IntVar(w, int(c.get("target_mb", 20)))
        self.v_auto = tk.BooleanVar(w, c.get("auto_scale", True))
        self.v_block = tk.BooleanVar(w, c.get("block_paste", True))
        self.v_paste = tk.BooleanVar(w, c.get("auto_paste", True))
        self.v_audio = tk.IntVar(w, c.get("audio_kbps", 128))
        self.v_cv = tk.BooleanVar(w, c.get("compress_video", True))
        self.v_ci = tk.BooleanVar(w, c.get("compress_images", True))
        self.v_ca = tk.BooleanVar(w, c.get("compress_audio", True))
        self.v_keep = tk.StringVar(w, c.get("keep_local", "ask"))
        self.v_shrink = tk.BooleanVar(w, c.get("offer_shrink", True))
        self.v_sound = tk.BooleanVar(w, c.get("sound_done", True))
        self.v_notify = tk.BooleanVar(w, c.get("notify_done", True))
        self.v_encoder = tk.StringVar(w, c.get("encoder", "auto"))
        self._sound_file = c.get("sound_file", "")                # свій .wav звук (пусто = звук Windows)
        self.v_theme = tk.StringVar(w, c.get("theme", "mono"))
        self.v_lang = tk.StringVar(w, c.get("lang", "en"))
        for v in (self.v_target, self.v_auto, self.v_block, self.v_paste, self.v_audio,
                  self.v_cv, self.v_ci, self.v_ca, self.v_keep, self.v_shrink, self.v_sound,
                  self.v_notify, self.v_encoder):
            v.trace_add("write", lambda *a: self._autosave())

    def _autosave(self):
        self.cfg = self._collect()
        try:
            self.on_save(self.cfg)
        except Exception:
            pass
        self._toast(self.T("saved"))

    def T(self, key, **kw):
        return i18n.tr(self.lang, key, **kw)

    def _released(self):
        """«вийшла 01.11.2026 о 19:40» поточною мовою."""
        try:
            d, t = APP_RELEASED.split()
            y, m, dd = d.split("-")
            return self.T("released", d=f"{dd}.{m}.{y}", t=t)
        except ValueError:
            return APP_RELEASED

    # ---------- вікно ----------
    def _center(self):
        self.win.update_idletasks()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.win.geometry(f"{self.W}x{self.H}+{(sw - self.W)//2}+{max(0, (sh - self.H)//2 - 20)}")

    def _minimize(self):
        self.win.overrideredirect(False)
        self._or_active = False
        self.win.iconify()

    def _on_map(self, _e):
        if not self._or_active and str(self.win.state()) == "normal":
            self.win.overrideredirect(True)
            self._or_active = True
            self.win.after(30, lambda: ui.win_chrome(
                self.win, taskbar=True, rounded=True, dark=ui.luminance(self.P["bg"]) < 128))

    def _close(self):
        try:
            self._autosave()      # нічого не губимо
        except Exception:
            pass

        def done():
            if self.on_close_cb:
                self.on_close_cb()
            else:
                try:
                    self.win.destroy()
                except Exception:
                    pass
        ui.fade_out(self.win, 110, done)

    def _drag_start(self, e):
        self._dx, self._dy = e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y()

    def _drag_move(self, e):
        self.win.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    # ---------- дрібні фабрики ----------
    def _btn(self, parent, text, cmd, primary=True, small=False, kind=None):
        return ui.Button(parent, text, cmd, self.P, kind=kind or ("primary" if primary else "ghost"),
                         height=32 if small else 38, size=9 if small else 10)

    def _lbl(self, parent, text, size=10, bold=False, muted=False, bg=None, wrap=0):
        P = self.P
        lb = tk.Label(parent, text=text, bg=bg or parent.cget("bg"),
                      fg=P["muted"] if muted else P["text"], justify="left", anchor="w",
                      font=(F, size, "bold" if bold else "normal"))
        if wrap:
            lb.config(wraplength=wrap)
        return lb

    def _card(self, parent, title=None, sub=None, pady=(0, 14)):
        card = ui.Card(parent, self.P, pad=18)
        card.pack(fill="x", pady=pady)
        if title and ui.is_mono(self.P):        # підпис секції: JetBrains Mono ВЕЛИКИМИ
            tk.Label(card.body, text=ui.tag_text(title), bg=card.fill, fg=self.P["text"],
                     font=ui.tag_font(9), anchor="w", justify="left").pack(anchor="w")
        elif title:
            self._lbl(card.body, title, size=12, bold=True).pack(anchor="w")
        if sub:
            self._lbl(card.body, sub, size=9, muted=True, wrap=self._content_w() - 60)\
                .pack(anchor="w", pady=(2, 0))
        if title or sub:
            tk.Frame(card.body, bg=card.fill, height=12).pack()
        return card.body

    def _content_w(self):
        return self.W - self.SIDE_W - 2 * 30

    def _setting_row(self, parent, title, desc, var, first=False):
        """Рядок «назва + опис ......... [тумблер]»."""
        P = self.P
        if not first:
            tk.Frame(parent, bg=ui.mix(parent.cget("bg"), P["text"], 0.07), height=1)\
                .pack(fill="x", pady=10)
        row = tk.Frame(parent, bg=parent.cget("bg"))
        row.pack(fill="x")
        ui.Toggle(row, var, P).pack(side="right", padx=(12, 0))
        txt = tk.Frame(row, bg=row.cget("bg"))
        txt.pack(side="left", fill="x", expand=True)
        self._lbl(txt, title, size=10, bold=True).pack(anchor="w")
        if desc:
            self._lbl(txt, desc, size=9, muted=True, wrap=self._content_w() - 140)\
                .pack(anchor="w", pady=(1, 0))
        return row

    # ---------- тост «Збережено ✓» ----------
    def _toast(self, text):
        try:
            c = self._toast_cv
            c.delete("all")
            w = ui.measure(c, text, 9) + 30
            c.config(width=w)
            ui.round_rect(c, 1, 1, w - 1, 27, 13, fill=ui.mix(self.P["card"], self.P["green"], 0.25),
                          outline="")
            c.create_text(w / 2, 14, text=text, fill=self.P["text"], font=(F, 9, "bold"))
            c.place(relx=1.0, rely=1.0, x=-22, y=-18, anchor="se")
            tk.Misc.tkraise(c)
            if self._toast_after:
                self.win.after_cancel(self._toast_after)
            def _hide(c=c):
                self._toast_after = None
                try:
                    if c.winfo_exists():
                        c.place_forget()
                except tk.TclError:
                    pass
            self._toast_after = self.win.after(1400, _hide)
        except (tk.TclError, AttributeError):
            pass

    # ---------- каркас ----------
    def _build(self):
        for w in self.win.winfo_children():
            w.destroy()
        P = self.P
        self.win.configure(bg=P["bg"])
        # --- власний заголовок ---
        title = tk.Canvas(self.win, bg=P["title_bg"], height=46, highlightthickness=0)
        title.pack(fill="x")
        ui.logo(title, 16, 11, 24, P, tags="drag")
        mono = ui.is_mono(P)
        tf = ui.title_font(self.T("app_title"), 11, P)
        tid_ = title.create_text(50, 23, text=self.T("app_title"), anchor="w", fill=P["text"],
                                 font=tf, tags="drag")
        bb = title.bbox(tid_)
        vx = bb[2] + 10
        vtxt = f"v{APP_VERSION}"
        vf = ui.tag_font(8) if mono else (F, 8, "bold")
        vw = int(title.tk.call("font", "measure", vf, vtxt)) + 14
        if mono:
            ui.round_rect(title, vx, 14, vx + vw, 32, 9, fill="#000000", outline=P["btn_line"], tags="drag")
        else:
            ui.grad_round_rect(title, vx, 15, vx + vw, 31, 8, P["accent"], ui.accent2(P), tags="drag")
        title.create_text(vx + vw / 2, 23, text=vtxt, fill=P["text"] if mono else ui.ink(P["accent"]),
                          font=vf, tags="drag")
        title.create_text(vx + vw + 10, 23, text=self._released(), anchor="w", fill=P["muted"],
                          font=(F, 8), tags="drag")
        title.tag_bind("drag", "<Button-1>", self._drag_start)
        title.tag_bind("drag", "<B1-Motion>", self._drag_move)
        title.bind("<Button-1>", self._drag_start)
        title.bind("<B1-Motion>", self._drag_move)
        self._title_buttons(title)

        # --- тіло: сайдбар + контент ---
        body = tk.Frame(self.win, bg=P["bg"])
        body.pack(fill="both", expand=True)
        self.side = tk.Frame(body, bg=P["sidebar"], width=self.SIDE_W)
        self.side.pack(side="left", fill="y")
        self.side.pack_propagate(False)
        self.content = tk.Frame(body, bg=P["bg"])
        self.content.pack(side="left", fill="both", expand=True)
        self._toast_cv = tk.Canvas(self.content, height=28, bg=P["bg"], highlightthickness=0)

        self._nav = {}
        self._tabs = [("general", "tab_general", "⚙"), ("gpu", "tab_gpu", "🎮"),
                      ("media", "tab_media", "🎞"),
                      ("stats", "tab_stats", "📊"), ("appearance", "tab_appearance", "🎨"),
                      ("whatsnew", "tab_whatsnew", "✨"),
                      ("setup", "tab_setup", "🧩"), ("updates", "tab_updates", "⟳"),
                      ("performance", "tab_performance", "⚡"), ("facts", "tab_facts", "💡"),
                      ("about", "tab_about", "ⓘ")]
        tk.Frame(self.side, bg=P["sidebar"], height=14).pack()
        for key, tkey, icon in self._tabs:
            self._nav_item(key, icon, self.T(tkey))
        self._side_status()
        self._show_tab(self._active_tab)

    def _title_buttons(self, title):
        P = self.P
        W = self.W
        for i, (glyph, cmd, hov) in enumerate((("✕", self._close, P["red"]),
                                               ("—", self._minimize, ui.mix(P["title_bg"], P["text"], 0.12)))):
            x2 = W - i * 46
            tag = f"tb{i}"
            title.create_rectangle(x2 - 46, 0, x2, 46, fill=P["title_bg"], outline="",
                                   tags=(tag, tag + "bg"))
            title.create_text(x2 - 23, 23, text=glyph, fill=P["muted"], font=(F, 11),
                              tags=(tag, tag + "fg"))
            title.tag_bind(tag, "<Enter>", lambda e, t=tag, h=hov: (
                title.itemconfig(t + "bg", fill=h),
                title.itemconfig(t + "fg", fill="#ffffff" if t == "tb0" else P["text"])))
            title.tag_bind(tag, "<Leave>", lambda e, t=tag: (
                title.itemconfig(t + "bg", fill=P["title_bg"]),
                title.itemconfig(t + "fg", fill=P["muted"])))
            title.tag_bind(tag, "<ButtonRelease-1>", lambda e, c=cmd: c())

    def _nav_item(self, key, icon, text):
        """Пункт бічного меню: заокруглена підсвітка + градієнтна смужка у активного."""
        P = self.P
        w, h = self.SIDE_W - 20, 36
        cv = tk.Canvas(self.side, width=w, height=h, bg=P["sidebar"], highlightthickness=0,
                       cursor="hand2")
        cv.pack(padx=10, pady=1)
        cv._hover = False

        def draw():
            cv.delete("all")
            act = key == self._active_tab
            if act:
                ui.round_rect(cv, 0, 2, w, h - 2, 10, fill=ui.mix(P["sidebar"], P["accent"], 0.22),
                              outline="")
                ui.grad_round_rect(cv, 4, 10, 8, h - 10, 2, P["accent"], ui.accent2(P),
                                   vertical=True, step=1)
            elif cv._hover:
                ui.round_rect(cv, 0, 2, w, h - 2, 10, fill=ui.mix(P["sidebar"], P["text"], 0.07),
                              outline="")
            fg = P["text"] if (act or cv._hover) else P["muted"]
            cv.create_text(24, h / 2, text=icon, fill=fg, font=(F, 12))
            cv.create_text(44, h / 2, text=text, anchor="w", fill=fg,
                           font=(F, 10, "bold" if act else "normal"))
            # «!» — новий розділ, який ще не відкривали (вкладка «Відеокарта»)
            if key == "gpu" and not self.cfg.get("gpu_seen"):
                bx = w - 20
                cv.create_oval(bx - 10, h / 2 - 10, bx + 10, h / 2 + 10, fill=P["warn"], outline="")
                cv.create_text(bx, h / 2, text="!", fill=ui.ink(P["warn"]), font=(F, 11, "bold"))

        cv.bind("<Enter>", lambda e: (setattr(cv, "_hover", True), draw()))
        cv.bind("<Leave>", lambda e: (setattr(cv, "_hover", False), draw()))
        cv.bind("<Button-1>", lambda e: self._show_tab(key))
        draw()
        self._nav[key] = draw

    def _side_status(self):
        """Внизу сайдбара: індикатор «працює у фоні» + підказка автозбереження."""
        P = self.P
        box = tk.Frame(self.side, bg=P["sidebar"])
        box.pack(side="bottom", fill="x", padx=12, pady=14)
        card = ui.Card(box, P, pad=12, fill=ui.mix(P["sidebar"], P["dark"], 0.45))
        card.pack(fill="x")
        row = tk.Frame(card.body, bg=card.fill)
        row.pack(anchor="w")
        dot = tk.Canvas(row, width=12, height=12, bg=card.fill, highlightthickness=0)
        dot.pack(side="left", padx=(0, 6))
        dot.create_oval(1, 1, 11, 11, fill=P["green"], outline="")
        self._lbl(row, self.T("st_status_on"), size=9, bold=True).pack(side="left")
        self._lbl(card.body, self.T("st_status_hint"), size=8, muted=True).pack(anchor="w", pady=(3, 0))
        self._lbl(box, self.T("autosave_hint"), size=8, muted=True, wrap=self.SIDE_W - 30)\
            .pack(anchor="w", pady=(10, 0))

    # ---------- вкладки ----------
    def _show_tab(self, key):
        try:
            self.cfg = self._collect()   # не втрачати незбережені зміни при перемиканні
        except Exception:
            pass
        self._active_tab = key
        if key == "gpu" and not self.cfg.get("gpu_seen"):
            self.cfg["gpu_seen"] = True       # «!» зникає, щойно вкладку відкрили
            self._autosave()
        for draw in self._nav.values():
            draw()
        for w in self.content.winfo_children():
            if w is not self._toast_cv:
                w.destroy()
        titles = {"general": ("tab_general", "st_general_sub"),
                  "media": ("tab_media", "st_media_sub"),
                  "stats": ("stats_title", "st_stats_sub"),
                  "appearance": ("tab_appearance", "st_appearance_sub"),
                  "setup": ("setup_title", "setup_hint"),
                  "updates": ("tab_updates", "update_hint"),
                  "performance": ("tab_performance", "perf_hint"),
                  "facts": ("facts_title", "facts_hint"),
                  "about": ("tab_about", None),
                  "gpu": ("tab_gpu", "st_gpu_sub"),
                  "whatsnew": ("tab_whatsnew", "st_whatsnew_sub")}
        tkey, skey = titles[key]
        if ui.is_mono(self.P):
            self._moon_head(self.T(tkey), self.T(skey) if skey else "")
        else:
            head = tk.Frame(self.content, bg=self.P["bg"])
            head.pack(fill="x", padx=30, pady=(24, 14))
            self._lbl(head, self.T(tkey), size=19, bold=True).pack(anchor="w")
            if skey:
                self._lbl(head, self.T(skey), size=10, muted=True, wrap=self._content_w())\
                    .pack(anchor="w", pady=(2, 0))
        self.scroll = ui.ScrollArea(self.content, self.P["bg"])
        self.scroll.pack(fill="both", expand=True, padx=(30, 6), pady=(0, 12))
        f = tk.Frame(self.scroll.inner, bg=self.P["bg"])
        f.pack(fill="both", expand=True, padx=(0, 18))
        getattr(self, "_tab_" + key)(f)
        tk.Misc.tkraise(self._toast_cv)

    def _moon_head(self, title, sub):
        """Шапка сторінки в дизайні Moon: місяць з променями справа вгорі, заголовок
        Instrument Serif курсивом, підзаголовок сірим."""
        P = self.P
        H = 132
        cv = tk.Canvas(self.content, height=H, bg=P["bg"], highlightthickness=0)
        cv.pack(fill="x")
        frames = ui.sky_frames(cv, "sky_head.png")
        img = frames[0] if frames else None
        ui.animate_sky(cv, frames, lambda im: cv.itemconfigure("sky", image=im))

        def draw(_e=None):
            try:
                cv.delete("all")
            except tk.TclError:
                return
            w = max(300, cv.winfo_width())
            if img:
                cv.create_image(w, 0, image=img, anchor="ne", tags="sky")
            cv.create_text(30, 26, text=ui.tag_text(self.T("app_title")), anchor="nw",
                           fill=P["dim"], font=ui.tag_font(8))
            cv.create_text(28, 42, text=title, anchor="nw", fill=P["text"],
                           font=ui.title_font(title, 24))
            if sub:
                cv.create_text(30, 98, text=sub, anchor="nw", fill=P["muted"], font=(F, 10),
                               width=max(200, w - 330))
        cv.bind("<Configure>", draw)

    # ===== Загальне =====
    def _tab_general(self, f):
        P = self.P
        d = stats.load()
        # --- «герой»: що робить програма просто зараз ---
        hero = tk.Canvas(f, height=124, bg=P["bg"], highlightthickness=0)
        hero.pack(fill="x", pady=(0, 14))

        def draw_hero(_e=None):
            try:
                hero.delete("all")
            except tk.TclError:
                return
            w = max(200, hero.winfo_width())
            if ui.is_mono(P):     # Moon: чорна панель з тонкою рамкою, без кольору
                ui.round_rect(hero, 1, 1, w - 1, 123, 22, fill=P["card"], outline=P["line"])
                hero.create_line(24, 2, w - 24, 2, fill="#0f0f0f")
                for i in range(5):
                    r = 36 + i * 20
                    hero.create_oval(w - 70 - r, 62 - r, w - 70 + r, 62 + r,
                                     outline=ui.mix(P["card"], "#ffffff", 0.05 + 0.02 * (4 - i)), width=1)
                ui.logo(hero, w - 102, 30, 64, P)
                hero.create_text(24, 18, text=self.T("st_ready"), anchor="nw", fill=P["text"],
                                 font=ui.title_font(self.T("st_ready"), 15))
                hero.create_text(24, 68, text=self.T("st_ready_body", mb=f"{self.v_target.get():g}"),
                                 anchor="w", fill=P["muted"], font=(F, 9), width=w - 170)
                if d.get("files"):
                    u, g = self.T("unit_mb"), self.T("unit_gb")
                    hero.create_text(24, 104, anchor="w", fill=P["text"], font=ui.tag_font(8),
                                     text=self.T("st_ready_stats", files=d.get("files", 0),
                                                 saved=stats.fmt_mb(d.get("saved_mb", 0.0), u, g)).upper())
                return
            ui.grad_round_rect(hero, 0, 0, w, 124, 18, ui.mix(P["card"], P["accent"], 0.55),
                               ui.mix(P["card"], ui.accent2(P), 0.55))
            for i in range(6):   # декоративні кола
                r = 40 + i * 22
                hero.create_oval(w - 70 - r, 62 - r, w - 70 + r, 62 + r,
                                 outline=ui.mix(ui.mix(P["card"], ui.accent2(P), 0.55), "#ffffff", 0.08),
                                 width=1)
            ui.logo(hero, w - 102, 30, 64, P)
            fg = ui.ink(ui.mix(P["card"], P["accent"], 0.55))
            hero.create_text(24, 30, text=self.T("st_ready"), anchor="w", fill=fg, font=(F, 15, "bold"))
            hero.create_text(24, 60, text=self.T("st_ready_body", mb=f"{self.v_target.get():g}"),
                             anchor="w", fill=fg, font=(F, 9), width=w - 170)
            if d.get("files"):
                u, g = self.T("unit_mb"), self.T("unit_gb")
                hero.create_text(24, 100, anchor="w", fill=fg, font=(F, 9, "bold"),
                                 text=self.T("st_ready_stats", files=d.get("files", 0),
                                             saved=stats.fmt_mb(d.get("saved_mb", 0.0), u, g)))
        hero.bind("<Configure>", draw_hero)
        tid = self.v_target.trace_add("write", lambda *a: draw_hero())
        hero.bind("<Destroy>", lambda e: self.v_target.trace_remove("write", tid), add="+")

        if self.on_editor or self.on_gallery:   # редактор просто з меню програми
            ce = self._card(f, self.T("st_editor_title"), self.T("st_editor_sub"))
            row = tk.Frame(ce, bg=ce.cget("bg"))
            row.pack(fill="x", pady=(6, 2))
            if self.on_editor:
                self._btn(row, self.T("st_editor_open"), self.on_editor).pack(side="left", padx=(0, 8))
            if self.on_gallery:
                self._btn(row, self.T("st_editor_gallery"), self.on_gallery, primary=False).pack(side="left")

        c = self._card(f, self.T("limit_title"), self.T("st_limit_sub"))
        opts = [(20, "20 " + self.T("unit_mb")), (25, "25 " + self.T("unit_mb")),
                (50, "50 " + self.T("unit_mb")), (500, "500 " + self.T("unit_mb"))]
        sub = {20: self.T("lim_free"), 25: " ", 50: self.T("lim_basic"), 500: self.T("lim_nitro")}
        ui.Segmented(c, opts, self.v_target, P, sub=sub, min_seg=118).pack(anchor="w")

        c = self._card(f, self.T("st_behavior"))
        self._setting_row(c, self.T("opt_autoscale"), self.T("st_autoscale_d"), self.v_auto, first=True)
        self._setting_row(c, self.T("opt_block"), self.T("st_block_d"), self.v_block)
        self._setting_row(c, self.T("opt_paste"), self.T("st_paste_d"), self.v_paste)

        c = self._card(f, self.T("st_audio"), self.T("st_audio_d"))
        ui.Slider(c, self.v_audio, P, 0, 320, 32, width=380,
                  fmt=lambda v: f"{v} kbps" if v else self.T("audio_off")).pack(anchor="w")

    # ===== Медіа =====
    def _tab_media(self, f):
        c = self._card(f, self.T("media_title"))
        self._setting_row(c, self.T("media_video"), self.T("st_video_d"), self.v_cv, first=True)
        self._setting_row(c, self.T("media_image"), self.T("st_image_d"), self.v_ci)
        self._setting_row(c, self.T("media_audio"), self.T("st_audio2_d"), self.v_ca)

        c = self._card(f, self.T("st_extras"))
        self._setting_row(c, self.T("opt_shrink"), self.T("st_shrink_d"), self.v_shrink, first=True)
        self._setting_row(c, self.T("opt_notify"), self.T("st_notify_d"), self.v_notify)
        self._setting_row(c, self.T("opt_sound"), None, self.v_sound)
        srow = tk.Frame(c, bg=c.cget("bg")); srow.pack(anchor="w", fill="x", pady=(10, 0))
        self._btn(srow, self.T("sound_pick"), self._pick_sound, primary=False, small=True).pack(side="left")
        self._btn(srow, self.T("sound_win"), self._reset_sound, primary=False, small=True)\
            .pack(side="left", padx=8)
        self._sound_lbl = self._lbl(srow, "", size=9, muted=True)
        self._sound_lbl.pack(side="left", padx=4)
        self._refresh_sound_lbl()

        c = self._card(f, self.T("keep_title"), self.T("st_keep_d"))
        ui.Segmented(c, [("ask", self.T("keep_ask")), ("always", self.T("keep_always")),
                         ("never", self.T("keep_never"))], self.v_keep, self.P, min_seg=120)\
            .pack(anchor="w")

    # ===== Статистика =====
    def _tab_stats(self, f):
        """Особиста статистика: скільки файлів/місця зекономлено + історія
        останніх стиснень з кнопкою «скопіювати знову» (без повторного стиснення)."""
        P = self.P
        d = stats.load()
        u, g = self.T("unit_mb"), self.T("unit_gb")
        if d.get("since"):
            try:
                day = time.strftime("%d.%m.%Y", time.localtime(d["since"]))
                self._lbl(f, self.T("stats_since", d=day), size=10, muted=True)\
                    .pack(anchor="w", pady=(0, 10))
            except Exception:
                pass

        # --- три картки з великими цифрами ---
        row = tk.Frame(f, bg=P["bg"]); row.pack(fill="x", pady=(0, 14))
        avg = f"−{stats.avg_percent(d)}%" if d.get("files") else "—"
        for i, (big, small, icon) in enumerate((
                (str(d.get("files", 0)), self.T("stats_files"), "📦"),
                (stats.fmt_mb(d.get("saved_mb", 0.0), u, g), self.T("stats_saved"), "💾"),
                (avg, self.T("stats_avg"), "📉"))):
            cv = tk.Canvas(row, width=10, height=96, bg=P["bg"], highlightthickness=0)
            cv.pack(side="left", fill="x", expand=True, padx=(0 if i == 0 else 6, 0 if i == 2 else 6))

            def draw(_e=None, cv=cv, big=big, small=small, icon=icon):
                cv.delete("all")
                w = max(80, cv.winfo_width())
                ui.round_rect(cv, 0, 0, w, 96, 16, fill=P["card"],
                              outline=ui.mix(P["card"], P["text"], 0.07))
                cv.create_text(18, 24, text=icon, anchor="w", font=(F, 13), fill=P["text"])
                cv.create_text(18, 54, text=big, anchor="w", font=(F, 20, "bold"), fill=P["accent"])
                cv.create_text(18, 79, text=small, anchor="w", font=(F, 9), fill=P["muted"])
            cv.bind("<Configure>", draw)

        # --- за типом ---
        bk = d.get("by_kind", {})
        tot = sum(int(v) for v in bk.values()) or 0
        if tot:
            c = self._card(f, self.T("st_by_type"))
            for icon, k, name in (("🎬", "video", self.T("media_video")), ("🖼", "image", self.T("media_image")),
                                  ("🎵", "audio", self.T("media_audio"))):
                n = int(bk.get(k, 0))
                r = tk.Frame(c, bg=c.cget("bg")); r.pack(fill="x", pady=3)
                self._lbl(r, name, size=9).pack(side="left")
                self._lbl(r, str(n), size=9, bold=True).pack(side="right")
                bar = tk.Canvas(c, height=8, bg=c.cget("bg"), highlightthickness=0)
                bar.pack(fill="x", pady=(0, 6))

                def dbar(_e=None, bar=bar, frac=n / tot):
                    bar.delete("all")
                    w = max(20, bar.winfo_width())
                    ui.round_rect(bar, 0, 0, w, 8, 4, fill=P["dark"], outline="")
                    if frac > 0:
                        ui.grad_round_rect(bar, 0, 0, max(8, w * frac), 8, 4, P["accent"],
                                           ui.accent2(P), step=1)
                bar.bind("<Configure>", dbar)

        # --- історія ---
        c = self._card(f, self.T("stats_hist"))
        hist = d.get("history", [])
        if not hist:
            self._lbl(c, self.T("stats_empty"), size=10, muted=True).pack(anchor="w", pady=6)
            return
        self._lbl(c, self.T("stats_hint"), size=9, muted=True, wrap=self._content_w() - 60)\
            .pack(anchor="w", pady=(0, 8))
        box = tk.Frame(c, bg=P["dark"]); box.pack(fill="x")
        lb = tk.Listbox(box, bg=P["dark"], fg=P["text"],
                        selectbackground=P["accent"], selectforeground=ui.ink(P["accent"]),
                        highlightthickness=0, bd=0, font=(F, 10),
                        activestyle="none", height=min(8, max(3, len(hist))))
        lb.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        self._hist_lb, self._hist_entries = lb, hist
        for e in hist:
            icon = {"video": "🎬", "image": "🖼", "audio": "🎵"}.get(e.get("kind"), "🎬")
            try:
                when = time.strftime("%d.%m %H:%M", time.localtime(e.get("t", 0)))
            except Exception:
                when = ""
            name = e.get("name", "")
            if len(name) > 38:
                name = name[:35] + "…"
            parts = ""
            if int(e.get("parts", 1)) > 1:
                parts = f"  ×{e['parts']} {self.T('stats_parts')}"
            lb.insert("end", f" {when}   {icon}  {name}    "
                             f"{e.get('orig', 0):g} → {e.get('final', 0):g} {u}{parts}")
        lb.bind("<Double-Button-1>", lambda _e: self._hist_copy())
        # колесо над списком крутить список, а не всю сторінку
        lb.bind("<MouseWheel>", lambda e: (lb.yview_scroll(int(-e.delta / 120), "units"), "break")[1])

        row = tk.Frame(c, bg=c.cget("bg")); row.pack(anchor="w", fill="x", pady=(10, 0))
        self._btn(row, self.T("stats_copy"), self._hist_copy, small=True).pack(side="left")
        self._btn(row, self.T("stats_open"), self._hist_open, primary=False, small=True)\
            .pack(side="left", padx=8)
        self._btn(row, self.T("stats_clear"), self._hist_clear, primary=False, small=True)\
            .pack(side="left")
        self._hist_status = self._lbl(row, "", size=9)
        self._hist_status.pack(side="left", padx=10)

    def _hist_sel(self):
        try:
            return self._hist_entries[self._hist_lb.curselection()[0]]
        except Exception:
            return None

    def _hist_paths(self):
        e = self._hist_sel()
        if not e:
            return []
        return [p for p in e.get("paths", []) if p and os.path.isfile(p)]

    def _hist_copy(self):
        """Кладе стиснутий файл назад у буфер — Ctrl+V у Discord і все."""
        if self._hist_sel() is None:
            return self._hist_flash(self.T("stats_pick"), err=True)
        paths = self._hist_paths()
        if not paths:
            return self._hist_flash(self.T("stats_gone"), err=True)
        try:
            import discord_overlay as _ov   # завжди вже завантажений (він відкрив меню)
            _ov.set_clipboard_files(paths)
        except Exception:
            return self._hist_flash(self.T("stats_gone"), err=True)
        self._hist_flash(self.T("stats_copied"))

    def _hist_open(self):
        if self._hist_sel() is None:
            return self._hist_flash(self.T("stats_pick"), err=True)
        paths = self._hist_paths()
        if not paths:
            return self._hist_flash(self.T("stats_gone"), err=True)
        try:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(paths[0])])
        except Exception:
            pass

    def _hist_clear(self):
        stats.clear_history()
        self._show_tab("stats")

    def _hist_flash(self, msg, err=False):
        try:
            self._hist_status.config(text=msg, fg=self.P["red"] if err else self.P["green"])
        except (tk.TclError, AttributeError):
            pass

    # ===== Вигляд =====
    def _tab_appearance(self, f):
        P = self.P
        c = self._card(f, self.T("theme_title"))
        grid = tk.Frame(c, bg=c.cget("bg")); grid.pack(anchor="w")
        for i, name in enumerate(themes.order()):
            self._theme_tile(grid, name).grid(row=0, column=i, padx=(0, 10))

        c = self._card(f, self.T("lang_title"))
        ui.Segmented(c, [(code, i18n.LANG_NAMES[code]) for code in i18n.LANGS], self.v_lang, P,
                     command=lambda: self._pick_lang(self.v_lang.get()), min_seg=120).pack(anchor="w")

    def _theme_tile(self, parent, name):
        """Мініатюра теми: маленьке вікно-оверлей у кольорах цієї теми."""
        pal = themes.palette(name)
        sel = name == self.v_theme.get()
        w, h = 104, 112
        cv = tk.Canvas(parent, width=w, height=h + 24, bg=parent.cget("bg"),
                       highlightthickness=0, cursor="hand2")
        cv._hover = False

        def draw():
            cv.delete("all")
            if sel:
                ui.grad_round_rect(cv, 0, 0, w, h, 16, self.P["accent"], ui.accent2(self.P))
            elif cv._hover:
                ui.round_rect(cv, 0, 0, w, h, 16, fill=ui.mix(parent.cget("bg"), self.P["text"], 0.2),
                              outline="")
            ui.round_rect(cv, 3, 3, w - 3, h - 3, 14, fill=pal["bg"], outline="")
            ui.grad_round_rect(cv, 3, 3, w - 3, 26, 12, pal["accent"], pal.get("accent2", pal["accent"]))
            cv.create_rectangle(3, 18, w - 3, 26, fill=pal["bg"], outline="")
            cv.create_oval(w / 2 - 15, 30, w / 2 + 15, 60, fill=pal["panel"],
                           outline=pal.get("accent2", pal["accent"]), width=2)
            ui.round_rect(cv, 24, 68, w - 24, 74, 3, fill=pal["text"], outline="")
            ui.round_rect(cv, 36, 80, w - 36, 84, 2, fill=pal["muted"], outline="")
            ui.grad_round_rect(cv, 18, 92, w - 18, 108, 8, pal["accent"],
                               pal.get("accent2", pal["accent"]))
            cv.create_text(w / 2, h + 12, text=pal["name"] + ("  ✓" if sel else ""),
                           fill=self.P["text"], font=(F, 9, "bold"))
        cv.bind("<Enter>", lambda e: (setattr(cv, "_hover", True), draw()))
        cv.bind("<Leave>", lambda e: (setattr(cv, "_hover", False), draw()))
        cv.bind("<Button-1>", lambda e: self._pick_theme(name))
        draw()
        return cv

    def _pick_theme(self, name):
        if name == self.cfg.get("theme"):
            return
        self.cfg["theme"] = name
        self.v_theme.set(name)
        self.P = themes.palette(name)
        self._autosave()       # зберегти + застосувати (overlay/трей)
        self._apply_live()
        self._build()
        ui.win_chrome(self.win, taskbar=False, rounded=True, dark=ui.luminance(self.P["bg"]) < 128)

    def _pick_lang(self, code):
        if code == self.lang:
            return
        self.cfg["lang"] = code
        self.lang = code
        self._autosave()
        self._apply_live()
        self._build()

    def _apply_live(self):
        if self.on_apply:
            try:
                self.on_apply(self.cfg)
            except Exception:
                pass

    # ===== Оновлення =====
    def _tab_updates(self, f):
        self._restart_btn = None
        c = self._card(f)
        top = tk.Frame(c, bg=c.cget("bg")); top.pack(fill="x")
        ic = tk.Canvas(top, width=56, height=56, bg=c.cget("bg"), highlightthickness=0)
        ic.pack(side="left", padx=(0, 14))
        ui.logo(ic, 2, 2, 52, self.P)
        txt = tk.Frame(top, bg=c.cget("bg")); txt.pack(side="left", fill="x", expand=True)
        self._lbl(txt, f"Discord Auto-Compress  v{APP_VERSION}", size=12, bold=True).pack(anchor="w")
        self._lbl(txt, self._released(), size=9, muted=True).pack(anchor="w")
        self.upd_status = self._lbl(txt, self.T("upd_idle"), size=10, muted=True)
        self.upd_status.pack(anchor="w", pady=(2, 0))
        self.upd_row = tk.Frame(c, bg=c.cget("bg")); self.upd_row.pack(anchor="w", pady=(16, 0))
        self.upd_btn = self._btn(self.upd_row, self.T("check_updates"), self._check_updates)
        self.upd_btn.pack(side="left")
        if self._upd_state:
            self._upd_done(*self._upd_state)

    def _check_updates(self):
        """Оновити: смужка з відсотками (файли програми + швидкий програвач редактора),
        потім програма сама перезапускається."""
        self.upd_btn.config(state="disabled")
        self.upd_status.config(text=self.T("checking"), fg=self.P["muted"])
        try:
            if getattr(self, "upd_bar", None):
                self.upd_bar.destroy()
        except tk.TclError:
            pass
        self._upd_barw = 440
        self.upd_bar = tk.Canvas(self.upd_row.master, width=self._upd_barw, height=10,
                                 bg=self.upd_row.master.cget("bg"), highlightthickness=0)
        self.upd_bar.pack(anchor="w", pady=(12, 0), before=self.upd_row)
        self._upd_bar_set(0)
        try:
            import mpvplayer
            need_mpv = not mpvplayer.dll_path()
        except Exception:
            mpvplayer, need_mpv = None, False
        files_part = 10 if need_mpv else 100     # програвач важить ~120 МБ — основна частина смужки

        def ui_(fn):
            try:
                self.win.after(0, fn)
            except (tk.TclError, RuntimeError):
                pass

        plan = {"txt": self.T("upd_files")}

        def size_txt(b):
            return f"{b / 1048576:.1f} МБ" if b >= 1048576 else f"{max(1, round(b / 1024))} КБ"

        def got_plan(n, total):
            parts = []
            if n:
                parts.append(self.T("upd_plan_files", n=n) + (f" ({size_txt(total)})" if total else ""))
            if need_mpv:
                parts.append(self.T("upd_plan_player", s=size_txt(mpvplayer.Z_SIZE)))
            plan["txt"] = (self.T("upd_plan", what=" + ".join(parts)) if parts else self.T("checking"))
            ui_(lambda: self._upd_show(plan["txt"], 0))

        def work():
            try:
                import update
                ok, changed = update.check(on_plan=got_plan, progress=lambda p, rel: ui_(
                    lambda: self._upd_show(plan["txt"], p * files_part // 100)))
            except Exception:
                ok, changed = False, 0
            if not ok or not need_mpv:
                return ui_(lambda: self._upd_done(ok, changed))
            ui_(lambda: self._upd_show(plan["txt"], files_part))

            def st(state, pct, src):
                if state == "running":
                    ui_(lambda: self._upd_show(plan["txt"], files_part + pct * (100 - files_part) // 100))
                elif state == "retry":
                    ui_(lambda: self._upd_show(self.T("upd_player_retry", src=src), None))
                elif state == "wait":
                    ui_(lambda: self._upd_show(self.T("upd_player_wait", s=pct), None))

            mpvplayer.ensure_downloaded(on_status=st,
                                        on_done=lambda _ok: ui_(lambda: self._upd_done(True, max(1, changed))))
        threading.Thread(target=work, daemon=True).start()

    def _upd_bar_set(self, pct):
        try:
            b = self.upd_bar
            b.delete("all")
            ui.round_rect(b, 0, 0, self._upd_barw, 10, 5, fill=self.P["dark"], outline="")
            xe = self._upd_barw * max(0, min(100, pct)) / 100
            if xe > 6:
                ui.grad_round_rect(b, 0, 0, xe, 10, 5, self.P["accent"], ui.accent2(self.P), step=1)
        except (tk.TclError, AttributeError):
            pass

    def _upd_show(self, txt, pct):
        """pct=None — лише текст (смужка лишається, де була)."""
        try:
            if pct is None:
                self.upd_status.config(text=txt, fg=self.P["warn"])
            else:
                self._upd_pct = pct
                self.upd_status.config(text=f"{txt}  {int(pct)}%", fg=self.P["text"])
                self._upd_bar_set(pct)
        except (tk.TclError, AttributeError):
            pass

    @staticmethod
    def _disk_version():
        """Версія, що вже ЛЕЖИТЬ на диску (фонове оновлення при запуску могло її поміняти,
        поки програма працює зі старим кодом)."""
        try:
            import re
            here = os.path.dirname(os.path.abspath(changelog.__file__))
            with open(os.path.join(here, "changelog.py"), encoding="utf-8") as f:
                m = re.search(r'\{"v":\s*"([^"]+)"', f.read())
            return m.group(1) if m else None
        except Exception:
            return None

    def _upd_done(self, ok, changed):
        if ok and changed == 0:
            dv = self._disk_version()
            if dv and dv != APP_VERSION:      # файли вже нові, а запущена стара версія
                changed = 1
        self._upd_state = (ok, changed)
        try:
            self.upd_btn.config(state="normal")
            if not ok:
                self.upd_status.config(text=self.T("update_fail"), fg=self.P["red"])
            elif changed > 0:
                self._upd_bar_set(100)
                if self.on_restart:
                    # усе скачано (смужка 100%) -> сам перезапускаю, щоб запрацювала нова версія
                    self.upd_status.config(text=self.T("upd_restarting"), fg=self.P["green"])
                    self.upd_btn.config(state="disabled")
                    self._upd_state = None
                    self.win.after(900, self._do_restart)
                else:
                    self.upd_status.config(text=self.T("updated_n", n=changed), fg=self.P["green"])
            else:
                self._upd_bar_set(100)
                self.upd_status.config(text=self.T("up_to_date"), fg=self.P["green"])
        except tk.TclError:
            pass

    def _do_restart(self):
        if self.on_restart:
            self.on_restart()

    # ===== Швидкодія =====
    def _tab_performance(self, f):
        c = self._card(f)
        self.perf_btn = self._btn(c, self.T("perf_run"), self._run_perf)
        self.perf_btn.pack(anchor="w")
        self.perf_box = tk.Frame(c, bg=c.cget("bg")); self.perf_box.pack(anchor="w", fill="x", pady=(12, 0))

    def _run_perf(self):
        self.perf_btn.config(state="disabled", text=self.T("perf_running"))
        for w in self.perf_box.winfo_children():
            w.destroy()
        # статус + смужка прогресу (для скачування ffmpeg і для самого тесту)
        self.perf_status = self._lbl(self.perf_box, "", size=10, bold=True)
        self.perf_status.pack(anchor="w")
        self._perf_barw = 440
        self.perf_bar = tk.Canvas(self.perf_box, width=self._perf_barw, height=10,
                                  bg=self.perf_box.cget("bg"), highlightthickness=0)
        self.perf_bar.pack(anchor="w", pady=(8, 0))
        self._perf_set("", 0)

        if deps.all_ok(refresh=True):
            return self._perf_test()
        # ffmpeg нема — НЕ показуємо помилки: самі все скачуємо, з відсотками
        self._perf_set(self.T("perf_dl"), 0)
        deps.install_progress(
            progress_cb=lambda v: self.win.after(0, lambda v=v: self._perf_set(self.T("perf_dl"), v)),
            done_cb=lambda ok: self.win.after(0, lambda ok=ok: self._perf_dl_done(ok)))

    def _perf_set(self, txt, pct):
        try:
            self.perf_status.config(text=f"{txt}  {int(pct)}%" if txt else "", fg=self.P["text"])
            b = self.perf_bar
            b.delete("all")
            ui.round_rect(b, 0, 0, self._perf_barw, 10, 5, fill=self.P["dark"], outline="")
            xe = self._perf_barw * max(0, min(100, pct)) / 100
            if xe > 6:
                ui.grad_round_rect(b, 0, 0, xe, 10, 5, self.P["accent"], ui.accent2(self.P), step=1)
        except (tk.TclError, AttributeError):
            pass

    def _perf_dl_done(self, ok):
        if ok:
            self._perf_set(self.T("perf_dl_ok"), 100)
            return self.win.after(600, self._perf_test)   # секунда «Все скачано ✓ 100%» — і тест
        try:
            self.perf_btn.config(state="normal", text=self.T("perf_run"))
            self.perf_status.config(text=self.T("perf_dl_fail"), fg=self.P["warn"])
        except (tk.TclError, AttributeError):
            pass

    def _perf_test(self):
        self._perf_set(self.T("perf_running"), 0)

        def work():
            try:
                import optimize_test
                res = optimize_test.run(lambda v: self.win.after(
                    0, lambda v=v: self._perf_set(self.T("perf_running"), v)), lang=self.lang)
            except Exception as e:
                res = {"lines": [("✗", str(e)[:60])], "verdict": "—", "ok": False}
            self.win.after(0, lambda: self._perf_done(res))
        threading.Thread(target=work, daemon=True).start()

    def _perf_done(self, res):
        try:
            for w in self.perf_box.winfo_children():   # прибрати статус і смужку
                w.destroy()
            self.perf_btn.config(state="normal", text=self.T("perf_run"))
            P = self.P
            bg = self.perf_box.cget("bg")
            colmap = {"✓": P["green"], "⚠": P["warn"], "✗": P["red"]}
            for icon, text in res["lines"]:
                row = tk.Frame(self.perf_box, bg=bg); row.pack(anchor="w", fill="x", pady=3)
                col = colmap.get(icon, P["text"])
                dot = tk.Canvas(row, width=22, height=22, bg=bg, highlightthickness=0)
                dot.pack(side="left", padx=(0, 8))
                dot.create_oval(1, 1, 21, 21, fill=ui.mix(bg, col, 0.25), outline="")
                dot.create_text(11, 11, text=icon, fill=col, font=(F, 9, "bold"))
                self._lbl(row, text, size=10).pack(side="left")
            v = res.get("verdict", "")
            self._lbl(self.perf_box, v, size=11, bold=True, wrap=self._content_w() - 60)\
                .pack(anchor="w", pady=(12, 0))
            self.perf_box.winfo_children()[-1].config(fg=P["green"] if res.get("ok") else P["warn"])
        except tk.TclError:
            pass

    # ===== Факти =====
    def _tab_facts(self, f):
        c = self._card(f)
        for i, fact in enumerate(jokes.facts_for(self.lang)):     # лише читання — редагувати нема чого
            if i:
                tk.Frame(c, bg=ui.mix(c.cget("bg"), self.P["text"], 0.06), height=1).pack(fill="x", pady=7)
            row = tk.Frame(c, bg=c.cget("bg")); row.pack(fill="x")
            self._lbl(row, "💡", size=11).pack(side="left", anchor="n", padx=(0, 10))
            self._lbl(row, fact, size=10, wrap=self._content_w() - 110).pack(side="left", fill="x")

    # ---- свій звук «готово» ----
    def _refresh_sound_lbl(self):
        try:
            has = bool(self._sound_file) and os.path.isfile(self._sound_file)
            self._sound_lbl.config(text=self.T("sound_custom") if has else self.T("sound_windows"))
        except Exception:
            pass

    def _pick_sound(self):
        p = filedialog.askopenfilename(
            parent=self.win, title=self.T("sound_pick"),
            filetypes=[("Audio", "*.wav *.mp3 *.m4a *.ogg *.aac *.flac *.wma"), ("*", "*.*")])
        if not p:
            return
        wav = os.path.join(os.path.expanduser("~"), ".discord_done_sound.wav")
        ok = False
        try:
            if p.lower().endswith(".wav"):
                shutil.copyfile(p, wav); ok = os.path.isfile(wav)
            else:
                ok = dc_core.prepare_sound(p, wav)   # конвертуємо будь-що у .wav через ffmpeg
        except Exception:
            ok = False
        if ok:
            self._sound_file = wav
            self._autosave()
            self._play_preview(wav)
        self._refresh_sound_lbl()

    def _reset_sound(self):
        self._sound_file = ""
        self._autosave()
        self._refresh_sound_lbl()
        try:   # прослухати системний звук
            ctypes.windll.winmm.PlaySoundW(ctypes.c_wchar_p("SystemAsterisk"), None, 0x00010003)
        except Exception:
            pass

    def _play_preview(self, wav):
        try:
            ctypes.windll.winmm.PlaySoundW(ctypes.c_wchar_p(wav), None, 0x00020003)
        except Exception:
            pass

    # ===== Встановлення =====
    def _tab_setup(self, f):
        c = self._card(f, self.T("st_components"))
        self.setup_status = tk.Frame(c, bg=c.cget("bg")); self.setup_status.pack(anchor="w", fill="x")
        btns = tk.Frame(c, bg=c.cget("bg")); btns.pack(anchor="w", pady=(14, 6))
        self.setup_install_btn = self._btn(btns, self.T("setup_install"), self._setup_install)
        self.setup_install_btn.pack(side="left")
        self._btn(btns, self.T("setup_recheck"), self._setup_render, primary=False).pack(side="left", padx=8)
        self.setup_msg = self._lbl(c, "", size=10, bold=True); self.setup_msg.pack(anchor="w", pady=(4, 2))
        self._lbl(c, self.T("setup_manual"), size=9, muted=True).pack(anchor="w")

        c = self._card(f, self.T("st_log"))
        self.setup_log = tk.Text(c, height=7, bg=self.P["dark"], fg=self.P["muted"],
                                 font=("Consolas", 9), relief="flat", bd=0, wrap="word",
                                 insertbackground=self.P["text"], padx=10, pady=8)
        self.setup_log.pack(fill="x")
        self.setup_log.configure(state="disabled")
        self._setup_render()

    def _setup_render(self):
        try:
            for w in self.setup_status.winfo_children():
                w.destroy()
            st = deps.check(refresh=True)
            bg = self.setup_status.cget("bg")
            for name, ok in st.items():
                row = tk.Frame(self.setup_status, bg=bg); row.pack(anchor="w", fill="x", pady=3)
                col = self.P["green"] if ok else self.P["red"]
                dot = tk.Canvas(row, width=22, height=22, bg=bg, highlightthickness=0)
                dot.pack(side="left", padx=(0, 10))
                dot.create_oval(1, 1, 21, 21, fill=ui.mix(bg, col, 0.25), outline="")
                dot.create_text(11, 11, text="✓" if ok else "✗", fill=col, font=(F, 9, "bold"))
                self._lbl(row, name, size=10, bold=True).pack(side="left")
                tag = self.T("setup_present") if ok else self.T("setup_missing")
                self._lbl(row, "  —  " + tag, size=10, muted=True).pack(side="left")
            if all(st.values()):
                self.setup_msg.config(text=self.T("setup_all_ok"), fg=self.P["green"])
                self.setup_install_btn.config(state="disabled")
            else:
                self.setup_msg.config(text="")
                self.setup_install_btn.config(state="normal")
        except tk.TclError:
            pass

    def _setup_install(self):
        try:
            self.setup_install_btn.config(state="disabled", text=self.T("setup_installing"))
        except tk.TclError:
            return
        deps.install(
            log_cb=lambda s: self.win.after(0, lambda s=s: self._setup_log_append(s)),
            done_cb=lambda ok: self.win.after(0, lambda: self._setup_install_done(ok)))

    def _setup_log_append(self, s):
        try:
            self.setup_log.configure(state="normal")
            self.setup_log.insert("end", s + "\n")
            self.setup_log.see("end")
            self.setup_log.configure(state="disabled")
        except tk.TclError:
            pass

    def _setup_install_done(self, ok):
        try:
            self.setup_install_btn.config(state="normal", text=self.T("setup_install"))
        except tk.TclError:
            pass
        self._setup_render()
        try:
            self.setup_msg.config(text=self.T("setup_done_ok") if ok else self.T("setup_done_fail"),
                                  fg=self.P["green"] if ok else self.P["warn"])
        except tk.TclError:
            pass

    # ===== Про програму =====
    def _tab_about(self, f):
        P = self.P
        hero = tk.Canvas(f, height=150, bg=P["bg"], highlightthickness=0)
        hero.pack(fill="x", pady=(0, 14))

        def draw(_e=None):
            hero.delete("all")
            w = max(200, hero.winfo_width())
            ui.round_rect(hero, 0, 0, w, 150, 18, fill=P["card"],
                          outline=ui.mix(P["card"], P["text"], 0.07))
            for i in range(9, 0, -1):
                t = i / 9.0
                r = 46 + 40 * t
                hero.create_oval(70 - r, 75 - r * 0.8, 70 + r, 75 + r * 0.8, outline="",
                                 fill=ui.mix(P["card"], ui.mix(P["accent"], ui.accent2(P), 0.5),
                                             0.22 * (1 - t) ** 1.5))
            ui.logo(hero, 34, 39, 72, P)
            hero.create_text(130, 52, anchor="w", text="Discord Auto-Compress", fill=P["text"],
                             font=(F, 17, "bold"))
            hero.create_text(130, 80, anchor="w", text=self.T("st_tagline"), fill=P["muted"],
                             font=(F, 10), width=w - 150)
            hero.create_text(130, 110, anchor="w", text=f"v{APP_VERSION}  ·  {self._released()}  ·  MIT",
                             fill=P["muted"], font=(F, 9))
        hero.bind("<Configure>", draw)

        c = self._card(f, self.T("st_how"))
        self._lbl(c, self.T("about_body"), size=10, wrap=self._content_w() - 60).pack(anchor="w")

        c = self._card(f, self.T("st_report_title"), self.T("st_report_d"))
        row = tk.Frame(c, bg=c.cget("bg")); row.pack(anchor="w", fill="x")
        self._btn(row, self.T("st_report_btn"), self._make_report).pack(side="left")
        self._report_lbl = self._lbl(row, "", size=9, wrap=self._content_w() - 300)
        self._report_lbl.pack(side="left", padx=12)

        c = self._card(f, self.T("st_donate_title"), self.T("st_donate_d"))
        row = tk.Frame(c, bg=c.cget("bg")); row.pack(anchor="w")
        self._btn(row, self.T("st_donate_btn"), self._open_donate).pack(side="left")
        self._btn(row, "GitHub  ↗", lambda: monetize.open_url(REPO_URL), primary=False)\
            .pack(side="left", padx=8)

    # ===== Звіт про помилку =====
    def _make_report(self):
        self._report_lbl.config(text=self.T("checking"), fg=self.P["muted"])

        def work():
            try:
                import report
                path = report.build(self._collect(), APP_VERSION, self._released())
            except Exception as e:
                path, err = None, str(e)[:80]
            else:
                err = ""
            self.win.after(0, lambda: self._report_done(path, err))
        threading.Thread(target=work, daemon=True).start()

    def _report_done(self, path, err):
        try:
            if not path:
                return self._report_lbl.config(text=self.T("st_report_fail") + " " + err,
                                               fg=self.P["red"])
            try:   # файл — у буфер обміну: Ctrl+V у Discord і звіт відправлено
                import discord_overlay as _ov
                _ov.set_clipboard_files([path])
            except Exception:
                pass
            self._report_lbl.config(text=self.T("st_report_ok"), fg=self.P["green"])
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        except tk.TclError:
            pass

    # ===== Відеокарта =====
    def _tab_gpu(self, f):
        P = self.P
        c = self._card(f, self.T("st_enc_title"), self.T("st_enc_d"))
        ui.Segmented(c, [("auto", self.T("enc_auto")), ("gpu", self.T("enc_gpu")),
                         ("cpu", self.T("enc_cpu"))], self.v_encoder, P, min_seg=130,
                     command=lambda: self.win.after(50, self._gpu_now)).pack(anchor="w")
        self._gpu_now_lbl = self._lbl(c, self.T("st_gpu_checking"), size=10, bold=True)
        self._gpu_now_lbl.pack(anchor="w", pady=(12, 0))

        c = self._card(f, self.T("st_devices"))
        self._dev_box = tk.Frame(c, bg=c.cget("bg")); self._dev_box.pack(fill="x")
        self._lbl(self._dev_box, self.T("st_gpu_checking"), size=10, muted=True).pack(anchor="w")

        c = self._card(f, self.T("st_bench_title"), self.T("st_bench_d"))
        self._bench_btn = self._btn(c, self.T("st_bench_btn"), self._run_bench)
        self._bench_btn.pack(anchor="w")
        self._bench_box = tk.Frame(c, bg=c.cget("bg")); self._bench_box.pack(fill="x", pady=(12, 0))
        if self.cfg.get("bench"):
            self._bench_show(self.cfg["bench"])

        def detect():
            dc_core.hw_encoder()
            self.win.after(0, self._gpu_detected)
        threading.Thread(target=detect, daemon=True).start()

    def _enc_name(self, enc):
        return self.T("enc_cpu_name") if enc in ("x264", "", None) else dc_core.HW_NAMES.get(enc, enc)

    def _gpu_detected(self):
        try:
            hw = dc_core.hw_encoder()
            box = self._dev_box
            for w in box.winfo_children():
                w.destroy()
            bg = box.cget("bg")
            rows = [(True, self.T("enc_cpu_name"), self.T("st_dev_cpu", n=os.cpu_count() or 1))]
            rows.append((bool(hw), dc_core.HW_NAMES.get(hw, self.T("st_dev_gpu_none")),
                         self.T("st_dev_gpu_ok") if hw else self.T("st_dev_gpu_no")))
            for ok, name, note in rows:
                row = tk.Frame(box, bg=bg); row.pack(anchor="w", fill="x", pady=3)
                col = self.P["green"] if ok else self.P["muted"]
                dot = tk.Canvas(row, width=22, height=22, bg=bg, highlightthickness=0)
                dot.pack(side="left", padx=(0, 10))
                dot.create_oval(1, 1, 21, 21, fill=ui.mix(bg, col, 0.25), outline="")
                dot.create_text(11, 11, text="✓" if ok else "—", fill=col, font=(F, 9, "bold"))
                self._lbl(row, name, size=10, bold=True).pack(side="left")
                self._lbl(row, "  —  " + note, size=10, muted=True).pack(side="left")
            self._gpu_now()
        except tk.TclError:
            pass

    def _gpu_now(self):
        """Підпис «Зараз стискає: …» під перемикачем режиму."""
        try:
            mode = self.v_encoder.get()
            hw = dc_core.hw_encoder() if dc_core._HW is not None else None
            if hw is None:
                return
            if mode == "cpu" or not hw:
                enc = "x264"
            elif mode == "gpu":
                enc = hw
            else:
                best = self.cfg.get("encoder_best", "")
                enc = "x264" if best == "x264" else hw
            txt = self.T("st_gpu_now", name=self._enc_name(enc))
            if mode == "gpu" and not hw:
                txt += "  ·  " + self.T("st_dev_gpu_no")
            self._gpu_now_lbl.config(text=txt, fg=self.P["text"])
        except (tk.TclError, AttributeError):
            pass

    def _run_bench(self):
        if self._bench_busy:
            return
        self._bench_busy = True
        self._bench_btn.config(state="disabled", text=self.T("st_bench_running"))
        box = self._bench_box
        for w in box.winfo_children():
            w.destroy()
        self._bench_bar = tk.Canvas(box, width=440, height=10, bg=box.cget("bg"), highlightthickness=0)
        self._bench_bar.pack(anchor="w")
        self._bench_prog(0)

        def work():
            try:
                res = dc_core.benchmark(lambda p: self.win.after(0, lambda p=p: self._bench_prog(p)))
            except Exception as e:
                dc_core.dlog("benchmark EXCEPTION: " + repr(e))
                res = []
            self.win.after(0, lambda: self._bench_done(res))
        threading.Thread(target=work, daemon=True).start()

    def _bench_prog(self, pct):
        try:
            b = self._bench_bar
            b.delete("all")
            ui.round_rect(b, 0, 0, 440, 10, 5, fill=self.P["dark"], outline="")
            xe = 440 * max(0, min(100, pct)) / 100
            if xe > 6:
                ui.grad_round_rect(b, 0, 0, xe, 10, 5, self.P["accent"], ui.accent2(self.P))
        except (tk.TclError, AttributeError):
            pass

    def _bench_done(self, res):
        self._bench_busy = False
        ok = [r for r in res if r.get("sec")]
        if ok:
            self.cfg["encoder_best"] = ok[0]["enc"]
            self.cfg["bench"] = [{"enc": r["enc"], "sec": round(r["sec"], 2) if r.get("sec") else None}
                                 for r in res]
            self.cfg["bench_at"] = time.strftime("%d.%m.%Y %H:%M")
            self._autosave()
        try:
            self._bench_btn.config(state="normal", text=self.T("st_bench_btn"))
            self._bench_show(self.cfg.get("bench") or [])
            self._gpu_now()
        except tk.TclError:
            pass

    def _bench_show(self, res):
        box = self._bench_box
        for w in box.winfo_children():
            w.destroy()
        bg = box.cget("bg")
        P = self.P
        ok = [r for r in res if r.get("sec")]
        if not ok:
            self._lbl(box, self.T("st_bench_fail"), size=10, bold=True).pack(anchor="w")
            return
        slow = max(r["sec"] for r in ok)
        for i, r in enumerate(res):
            row = tk.Frame(box, bg=bg); row.pack(fill="x", pady=4)
            top = tk.Frame(row, bg=bg); top.pack(fill="x")
            name = ("🏆 " if i == 0 and r.get("sec") else "") + self._enc_name(r["enc"])
            self._lbl(top, name, size=10, bold=True).pack(side="left")
            val = f"{r['sec']:.1f} {self.T('unit_sec')}" if r.get("sec") else self.T("st_bench_err")
            self._lbl(top, val, size=10, bold=(i == 0)).pack(side="right")
            bar = tk.Canvas(row, height=8, bg=bg, highlightthickness=0)
            bar.pack(fill="x", pady=(3, 0))

            def draw(_e=None, bar=bar, r=r, first=(i == 0)):
                bar.delete("all")
                w = max(20, bar.winfo_width())
                ui.round_rect(bar, 0, 0, w, 8, 4, fill=P["dark"], outline="")
                if r.get("sec"):
                    fr = r["sec"] / slow
                    if first:
                        ui.grad_round_rect(bar, 0, 0, max(8, w * fr), 8, 4, P["green"],
                                           ui.lighten(P["green"], 0.3))
                    else:
                        ui.round_rect(bar, 0, 0, max(8, w * fr), 8, 4,
                                      fill=ui.mix(P["dark"], P["muted"], 0.6), outline="")
            bar.bind("<Configure>", draw)
        best = ok[0]
        msg = self.T("st_bench_result", name=self._enc_name(best["enc"]))
        if len(ok) > 1:
            msg += "  " + self.T("st_bench_faster", x=f"{slow / best['sec']:.1f}")
        if self.cfg.get("bench_at"):
            msg += "\n" + self.T("st_bench_when", d=self.cfg["bench_at"])
        self._lbl(box, msg, size=10, bold=True, wrap=self._content_w() - 60)\
            .pack(anchor="w", pady=(10, 0))
        box.winfo_children()[-1].config(fg=P["green"])

    # ===== Що нового =====
    def _tab_whatsnew(self, f):
        P = self.P
        row = tk.Frame(f, bg=P["bg"]); row.pack(anchor="w", pady=(0, 14))
        self._btn(row, self.T("wn_replay"), self._replay_news).pack(side="left")
        self._btn(row, self.T("wn_site"), lambda: monetize.open_url(changelog.release_url()),
                  primary=False).pack(side="left", padx=8)
        for entry in changelog.CHANGES:
            d, t = changelog.fmt_date(entry["date"])
            c = self._card(f, f"v{entry['v']}", self.T("released", d=d, t=t))
            for i, (icon, title, desc, tab) in enumerate(changelog.items(entry, self.lang)):
                if i:
                    tk.Frame(c, bg=ui.mix(c.cget("bg"), P["text"], 0.06), height=1).pack(fill="x", pady=8)
                r = tk.Frame(c, bg=c.cget("bg")); r.pack(fill="x")
                self._lbl(r, icon, size=14).pack(side="left", anchor="n", padx=(0, 12))
                if tab and tab != "whatsnew":
                    self._btn(r, self.T("wn_show"), lambda t=tab: self._show_tab(t),
                              primary=False, small=True).pack(side="right", anchor="n", padx=(8, 0))
                tx = tk.Frame(r, bg=c.cget("bg")); tx.pack(side="left", fill="x", expand=True)
                self._lbl(tx, title, size=10, bold=True).pack(anchor="w")
                self._lbl(tx, desc, size=9, muted=True, wrap=self._content_w() - 220).pack(anchor="w")

    def _replay_news(self):
        try:
            import whatsnew
            whatsnew.WhatsNew(self.win, self.lang, self.cfg.get("theme", "mono"),
                              on_open_tab=lambda tab: self._show_tab(tab))
        except Exception as e:
            dc_core.dlog("whatsnew replay FAILED: " + repr(e))

    def _open_donate(self):
        if monetize.has_donate():
            monetize.open_url(monetize.DONATE_URL)

    # ---------- збереження ----------
    def _collect(self):
        # КОЖНЕ поле читаємо ОКРЕМО: якщо якесь tk-поле у поганому стані,
        # інші (зокрема sound_file) ВСЕ ОДНО збережуться.
        c = dict(self.cfg)

        def g(key, var):
            try:
                c[key] = var.get()
            except (tk.TclError, AttributeError, ValueError):
                pass

        g("target_mb", self.v_target); g("auto_scale", self.v_auto)
        g("block_paste", self.v_block); g("auto_paste", self.v_paste)
        g("audio_kbps", self.v_audio)
        g("compress_video", self.v_cv); g("compress_images", self.v_ci)
        g("compress_audio", self.v_ca); g("keep_local", self.v_keep)
        g("offer_shrink", self.v_shrink); g("sound_done", self.v_sound)
        g("notify_done", self.v_notify); g("encoder", self.v_encoder)
        try:   # аудіо-бітрейт завжди в розумних межах (раніше можна було ввести будь-що)
            c["audio_kbps"] = max(0, min(320, int(c.get("audio_kbps", 128))))
        except (TypeError, ValueError):
            c["audio_kbps"] = 128
        try:
            c["sound_file"] = self._sound_file
        except AttributeError:
            pass
        c["theme"] = self.cfg.get("theme", "mono")
        c["lang"] = self.cfg.get("lang", "en")
        return c

    def _save(self):
        # усе й так зберігається саме; лишено для сумісності
        self._autosave()
        self._apply_live()

    def mainloop(self):
        self.win.mainloop()
