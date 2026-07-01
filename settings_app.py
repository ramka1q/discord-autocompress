#!/usr/bin/env python3
"""
settings_app.py — красиве меню налаштувань у стилі Discord.
Кастомний заголовок (значок + згорнути + закрити), бічна навігація з вкладками,
живий вибір теми й мови, перевірка оновлень і тест оптимізації.
Відкривається як Toplevel на прихованому root вартового (або як окреме вікно).
Тільки стандартна бібліотека Tk.
"""
import threading

import tkinter as tk

import appicon
import i18n
import themes

APP_VERSION = "2.0"


class SettingsApp:
    W, H = 760, 560

    def __init__(self, master, cfg, on_save, on_apply=None, on_close=None):
        """cfg — робоча копія конфіга; on_save(cfg) — зберегти; on_apply(cfg) —
        миттєво застосувати тему/мову (overlay+трей); on_close() — закрити."""
        self.cfg = dict(cfg)
        self.on_save = on_save
        self.on_apply = on_apply
        self.on_close_cb = on_close
        self.lang = self.cfg.get("lang", "uk")
        self.P = themes.palette(self.cfg.get("theme", "discord"))
        self._or_active = True
        self._active_tab = "general"

        self.win = tk.Toplevel(master) if master is not None else tk.Tk()
        self.win.title(i18n.tr(self.lang, "app_title"))
        self.win.geometry(f"{self.W}x{self.H}")
        self.win.minsize(680, 480)
        self.win.configure(bg=self.P["dark"])
        appicon.set_window_icon(self.win)
        self._center()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.after(300, lambda: self.win.attributes("-topmost", False))
        self.win.bind("<Map>", self._on_map)

        self._build()

    # ---------- вікно ----------
    def _center(self):
        self.win.update_idletasks()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.win.geometry(f"{self.W}x{self.H}+{(sw - self.W)//2}+{(sh - self.H)//2}")

    def _minimize(self):
        self.win.overrideredirect(False)
        self._or_active = False
        self.win.iconify()

    def _on_map(self, _e):
        if not self._or_active and str(self.win.state()) == "normal":
            self.win.overrideredirect(True)
            self._or_active = True

    def _close(self):
        if self.on_close_cb:
            self.on_close_cb()
        else:
            try:
                self.win.destroy()
            except Exception:
                pass

    def T(self, key, **kw):
        return i18n.tr(self.lang, key, **kw)

    # ---------- фабрики віджетів ----------
    def _btn(self, parent, text, cmd, primary=True, small=False):
        P = self.P
        bg, hov = (P["accent"], P["accent_h"]) if primary else (P["panel"], P["dark"])
        b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=P["text"],
                      activebackground=hov, activeforeground=P["text"], relief="flat",
                      font=(themes.FONT, 9 if small else 11, "bold"), bd=0,
                      padx=12 if small else 18, pady=6 if small else 9, cursor="hand2")
        b.bind("<Enter>", lambda e: b.config(bg=hov))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

    def _lbl(self, parent, text, size=10, bold=False, muted=False, bg=None):
        P = self.P
        return tk.Label(parent, text=text, bg=bg or P["bg"],
                        fg=P["muted"] if muted else P["text"],
                        font=(themes.FONT, size, "bold" if bold else "normal"))

    # ---------- каркас ----------
    def _build(self):
        for w in self.win.winfo_children():
            w.destroy()
        P = self.P
        # --- кастомний заголовок ---
        title = tk.Frame(self.win, bg=P["title_bg"], height=40)
        title.pack(fill="x")
        title.pack_propagate(False)
        tk.Label(title, text="  ◆  " + self.T("app_title"), bg=P["title_bg"], fg=P["text"],
                 font=(themes.FONT, 11, "bold")).pack(side="left", padx=6)
        for w in (title,):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        xbtn = tk.Button(title, text="✕", command=self._close, bg=P["title_bg"], fg=P["muted"],
                         activebackground=P["red"], activeforeground="#fff", relief="flat",
                         bd=0, font=(themes.FONT, 12), width=4, cursor="hand2")
        xbtn.pack(side="right", fill="y")
        xbtn.bind("<Enter>", lambda e: xbtn.config(bg=P["red"], fg="#fff"))
        xbtn.bind("<Leave>", lambda e: xbtn.config(bg=P["title_bg"], fg=P["muted"]))
        mbtn = tk.Button(title, text="—", command=self._minimize, bg=P["title_bg"], fg=P["muted"],
                         activebackground=P["panel"], activeforeground=P["text"], relief="flat",
                         bd=0, font=(themes.FONT, 12), width=4, cursor="hand2")
        mbtn.pack(side="right", fill="y")
        mbtn.bind("<Enter>", lambda e: mbtn.config(bg=P["panel"], fg=P["text"]))
        mbtn.bind("<Leave>", lambda e: mbtn.config(bg=P["title_bg"], fg=P["muted"]))

        # --- тіло: сайдбар + контент ---
        body = tk.Frame(self.win, bg=P["bg"])
        body.pack(fill="both", expand=True)
        self.side = tk.Frame(body, bg=P["sidebar"], width=190)
        self.side.pack(side="left", fill="y")
        self.side.pack_propagate(False)
        self.content = tk.Frame(body, bg=P["bg"])
        self.content.pack(side="left", fill="both", expand=True)

        self._nav = {}
        tabs = [("general", "tab_general", "⚙"), ("media", "tab_media", "🎞"),
                ("appearance", "tab_appearance", "🎨"), ("updates", "tab_updates", "⭳"),
                ("performance", "tab_performance", "⚡"), ("about", "tab_about", "ⓘ")]
        tk.Frame(self.side, bg=P["sidebar"], height=10).pack()
        for key, tkey, icon in tabs:
            self._nav_btn(key, f"  {icon}  " + self.T(tkey))

        # --- футер із «Зберегти» ---
        footer = tk.Frame(self.win, bg=P["title_bg"], height=52)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        self.status = tk.Label(footer, text="", bg=P["title_bg"], fg=P["green"],
                               font=(themes.FONT, 10, "bold"))
        self.status.pack(side="left", padx=16)
        self._btn(footer, self.T("save"), self._save).pack(side="right", padx=16, pady=8)

        self._show_tab(self._active_tab)

    def _nav_btn(self, key, text):
        P = self.P
        active = key == self._active_tab
        b = tk.Button(self.side, text=text, anchor="w", command=lambda: self._show_tab(key),
                      bg=P["accent"] if active else P["sidebar"],
                      fg="#fff" if active else P["text"],
                      activebackground=P["accent_h"] if active else P["panel"],
                      activeforeground=P["text"], relief="flat", bd=0,
                      font=(themes.FONT, 11, "bold" if active else "normal"),
                      padx=14, pady=10, cursor="hand2")
        b.pack(fill="x", padx=8, pady=2)
        if not active:
            b.bind("<Enter>", lambda e: b.config(bg=P["panel"]))
            b.bind("<Leave>", lambda e: b.config(bg=P["sidebar"]))
        self._nav[key] = b

    def _drag_start(self, e):
        self._dx, self._dy = e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y()

    def _drag_move(self, e):
        self.win.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    # ---------- вкладки ----------
    def _show_tab(self, key):
        try:
            self.cfg = self._collect()   # не втрачати незбережені зміни при перемиканні
        except Exception:
            pass
        self._active_tab = key
        for k, b in self._nav.items():
            act = k == key
            b.config(bg=self.P["accent"] if act else self.P["sidebar"],
                     fg="#fff" if act else self.P["text"],
                     font=(themes.FONT, 11, "bold" if act else "normal"))
        for w in self.content.winfo_children():
            w.destroy()
        {"general": self._tab_general, "media": self._tab_media,
         "appearance": self._tab_appearance, "updates": self._tab_updates,
         "performance": self._tab_performance, "about": self._tab_about}[key]()

    def _pad(self):
        f = tk.Frame(self.content, bg=self.P["bg"])
        f.pack(fill="both", expand=True, padx=26, pady=20)
        return f

    def _header(self, parent, text):
        self._lbl(parent, text, size=15, bold=True).pack(anchor="w", pady=(0, 14))

    def _check(self, parent, text, var):
        P = self.P
        tk.Checkbutton(parent, text=text, variable=var, bg=P["bg"], fg=P["text"],
                       selectcolor=P["dark"], activebackground=P["bg"], activeforeground=P["text"],
                       font=(themes.FONT, 11), anchor="w").pack(anchor="w", pady=3)

    def _tab_general(self):
        f = self._pad()
        self._header(f, self.T("limit_title"))
        self.v_target = tk.IntVar(value=self.cfg.get("target_mb", 10))
        for tkey, mb in (("limit_10", 10), ("limit_25", 25), ("limit_50", 50), ("limit_500", 500)):
            tk.Radiobutton(f, text=self.T(tkey), variable=self.v_target, value=mb,
                           bg=self.P["bg"], fg=self.P["text"], selectcolor=self.P["dark"],
                           activebackground=self.P["bg"], activeforeground=self.P["text"],
                           font=(themes.FONT, 11)).pack(anchor="w", padx=6, pady=2)

        tk.Frame(f, bg=self.P["bg"], height=12).pack()
        self.v_auto = tk.BooleanVar(value=self.cfg.get("auto_scale", True))
        self.v_block = tk.BooleanVar(value=self.cfg.get("block_paste", True))
        self.v_paste = tk.BooleanVar(value=self.cfg.get("auto_paste", True))
        self._check(f, self.T("opt_autoscale"), self.v_auto)
        self._check(f, self.T("opt_block"), self.v_block)
        self._check(f, self.T("opt_paste"), self.v_paste)

        row = tk.Frame(f, bg=self.P["bg"]); row.pack(anchor="w", pady=(12, 0))
        self._lbl(row, self.T("audio_kbps")).pack(side="left")
        self.v_audio = tk.IntVar(value=self.cfg.get("audio_kbps", 128))
        tk.Spinbox(row, from_=0, to=320, increment=32, width=6, textvariable=self.v_audio,
                   font=(themes.FONT, 11)).pack(side="left", padx=8)

    def _tab_media(self):
        f = self._pad()
        self._header(f, self.T("media_title"))
        self.v_cv = tk.BooleanVar(value=self.cfg.get("compress_video", True))
        self.v_ci = tk.BooleanVar(value=self.cfg.get("compress_images", True))
        self.v_ca = tk.BooleanVar(value=self.cfg.get("compress_audio", True))
        self._check(f, self.T("media_video"), self.v_cv)
        self._check(f, self.T("media_image"), self.v_ci)
        self._check(f, self.T("media_audio"), self.v_ca)

        tk.Frame(f, bg=self.P["bg"], height=16).pack()
        self._lbl(f, self.T("keep_title"), size=12, bold=True).pack(anchor="w", pady=(0, 6))
        self.v_keep = tk.StringVar(value=self.cfg.get("keep_local", "ask"))
        for tkey, val in (("keep_ask", "ask"), ("keep_always", "always"), ("keep_never", "never")):
            tk.Radiobutton(f, text=self.T(tkey), variable=self.v_keep, value=val,
                           bg=self.P["bg"], fg=self.P["text"], selectcolor=self.P["dark"],
                           activebackground=self.P["bg"], activeforeground=self.P["text"],
                           font=(themes.FONT, 11)).pack(anchor="w", padx=6, pady=2)

    def _tab_appearance(self):
        f = self._pad()
        self._header(f, self.T("theme_title"))
        self.v_theme = tk.StringVar(value=self.cfg.get("theme", "discord"))
        trow = tk.Frame(f, bg=self.P["bg"]); trow.pack(anchor="w", pady=(0, 6))
        for name in themes.order():
            pal = themes.palette(name)
            card = tk.Frame(trow, bg=pal["bg"], highlightthickness=3, cursor="hand2",
                            highlightbackground=(self.P["accent"] if name == self.v_theme.get()
                                                 else pal["dark"]))
            card.pack(side="left", padx=8)
            tk.Label(card, text=pal["name"], bg=pal["bg"], fg=pal["text"],
                     font=(themes.FONT, 11, "bold")).pack(padx=16, pady=(12, 4))
            sw = tk.Frame(card, bg=pal["bg"]); sw.pack(pady=(0, 12))
            for c in ("accent", "green", "warn", "red"):
                tk.Frame(sw, bg=pal[c], width=16, height=16).pack(side="left", padx=2)
            for w in (card, ) + tuple(card.winfo_children()):
                w.bind("<Button-1>", lambda e, n=name: self._pick_theme(n))

        tk.Frame(f, bg=self.P["bg"], height=18).pack()
        self._lbl(f, self.T("lang_title"), size=12, bold=True).pack(anchor="w", pady=(0, 6))
        self.v_lang = tk.StringVar(value=self.lang)
        for code in i18n.LANGS:
            tk.Radiobutton(f, text=i18n.LANG_NAMES[code], variable=self.v_lang, value=code,
                           command=lambda c=code: self._pick_lang(c),
                           bg=self.P["bg"], fg=self.P["text"], selectcolor=self.P["dark"],
                           activebackground=self.P["bg"], activeforeground=self.P["text"],
                           font=(themes.FONT, 11)).pack(anchor="w", padx=6, pady=2)

    def _pick_theme(self, name):
        self.cfg["theme"] = name
        self.P = themes.palette(name)
        self._apply_live()
        self.win.configure(bg=self.P["dark"])
        self._build()

    def _pick_lang(self, code):
        self.cfg["lang"] = code
        self.lang = code
        self._apply_live()
        self._build()

    def _apply_live(self):
        if self.on_apply:
            try:
                self.on_apply(self.cfg)
            except Exception:
                pass

    def _tab_updates(self):
        f = self._pad()
        self._header(f, self.T("tab_updates"))
        self._lbl(f, self.T("update_hint"), muted=True).pack(anchor="w", pady=(0, 14))
        self.upd_status = self._lbl(f, "", size=11, bold=True)
        self.upd_status.pack(anchor="w", pady=(0, 12))
        self.upd_btn = self._btn(f, self.T("check_updates"), self._check_updates)
        self.upd_btn.pack(anchor="w")

    def _check_updates(self):
        self.upd_btn.config(state="disabled")
        self.upd_status.config(text=self.T("checking"), fg=self.P["muted"])

        def work():
            try:
                import update
                ok, changed = update.check()
            except Exception:
                ok, changed = False, 0
            self.win.after(0, lambda: self._upd_done(ok, changed))
        threading.Thread(target=work, daemon=True).start()

    def _upd_done(self, ok, changed):
        try:
            self.upd_btn.config(state="normal")
            if not ok:
                self.upd_status.config(text=self.T("update_fail"), fg=self.P["red"])
            elif changed > 0:
                self.upd_status.config(text=self.T("updated_n", n=changed), fg=self.P["green"])
            else:
                self.upd_status.config(text=self.T("up_to_date"), fg=self.P["green"])
        except tk.TclError:
            pass

    def _tab_performance(self):
        f = self._pad()
        self._header(f, self.T("tab_performance"))
        self._lbl(f, self.T("perf_hint"), muted=True).pack(anchor="w", pady=(0, 12))
        self.perf_btn = self._btn(f, self.T("perf_run"), self._run_perf)
        self.perf_btn.pack(anchor="w")
        self.perf_box = tk.Frame(f, bg=self.P["bg"]); self.perf_box.pack(anchor="w", fill="x", pady=(14, 0))

    def _run_perf(self):
        self.perf_btn.config(state="disabled", text=self.T("perf_running"))
        for w in self.perf_box.winfo_children():
            w.destroy()

        def work():
            try:
                import optimize_test
                res = optimize_test.run(lambda v: None)
            except Exception as e:
                res = {"lines": [("✗", str(e)[:60])], "verdict": "—", "ok": False}
            self.win.after(0, lambda: self._perf_done(res))
        threading.Thread(target=work, daemon=True).start()

    def _perf_done(self, res):
        try:
            self.perf_btn.config(state="normal", text=self.T("perf_run"))
            colmap = {"✓": self.P["green"], "⚠": self.P["warn"], "✗": self.P["red"]}
            for icon, text in res["lines"]:
                row = tk.Frame(self.perf_box, bg=self.P["bg"]); row.pack(anchor="w", fill="x", pady=2)
                tk.Label(row, text=icon, bg=self.P["bg"], fg=colmap.get(icon, self.P["text"]),
                         font=(themes.FONT, 12, "bold"), width=2).pack(side="left")
                tk.Label(row, text=text, bg=self.P["bg"], fg=self.P["text"],
                         font=(themes.FONT, 10), anchor="w", justify="left").pack(side="left")
            v = res.get("verdict", "")
            tk.Label(self.perf_box, text=v, bg=self.P["bg"],
                     fg=self.P["green"] if res.get("ok") else self.P["warn"],
                     font=(themes.FONT, 11, "bold"), wraplength=440, justify="left"
                     ).pack(anchor="w", pady=(10, 0))
        except tk.TclError:
            pass

    def _tab_about(self):
        f = self._pad()
        self._header(f, self.T("app_title") + f"  v{APP_VERSION}")
        about = {
            "uk": "Автостиснення відео, фото та звуку під ліміт Discord.\n"
                  "Живе у треї (приховані значки). ПКМ по значку — меню або вихід.\n\n"
                  "Як друг оновлює програму:\n"
                  "  • автоматично при кожному запуску (тягне свіже з GitHub);\n"
                  "  • або кнопкою «Перевірити оновлення» на вкладці Оновлення;\n"
                  "  • або запустивши «Update now.bat».",
            "ru": "Автосжатие видео, фото и звука под лимит Discord.\n"
                  "Живёт в трее (скрытые значки). ПКМ по значку — меню или выход.\n\n"
                  "Как друг обновляет программу:\n"
                  "  • автоматически при каждом запуске (тянет свежее с GitHub);\n"
                  "  • или кнопкой «Проверить обновления» на вкладке Обновления;\n"
                  "  • или запустив «Update now.bat».",
            "en": "Auto-compress video, images and audio under the Discord limit.\n"
                  "Lives in the tray (hidden icons). Right-click — menu or quit.\n\n"
                  "How a friend updates the app:\n"
                  "  • automatically on every launch (pulls latest from GitHub);\n"
                  "  • or the ‘Check for updates’ button on the Updates tab;\n"
                  "  • or by running ‘Update now.bat’.",
        }[self.lang]
        tk.Label(f, text=about, bg=self.P["bg"], fg=self.P["text"], font=(themes.FONT, 11),
                 justify="left", anchor="w").pack(anchor="w")

    # ---------- збереження ----------
    def _collect(self):
        c = dict(self.cfg)
        if hasattr(self, "v_target"):
            c.update(target_mb=self.v_target.get(), auto_scale=self.v_auto.get(),
                     block_paste=self.v_block.get(), auto_paste=self.v_paste.get(),
                     audio_kbps=self.v_audio.get())
        if hasattr(self, "v_cv"):
            c.update(compress_video=self.v_cv.get(), compress_images=self.v_ci.get(),
                     compress_audio=self.v_ca.get(), keep_local=self.v_keep.get())
        c["theme"] = self.cfg.get("theme", "discord")
        c["lang"] = self.cfg.get("lang", "uk")
        return c

    def _save(self):
        self.cfg = self._collect()
        try:
            self.on_save(self.cfg)
        except Exception:
            pass
        if self.on_apply:
            self._apply_live()
        try:
            self.status.config(text=self.T("saved"))
            self.win.after(2000, lambda: self.status.config(text=""))
        except tk.TclError:
            pass

    def mainloop(self):
        self.win.mainloop()
