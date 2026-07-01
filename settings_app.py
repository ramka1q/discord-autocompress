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
import deps
import i18n
import themes

APP_VERSION = "2.0"


class SettingsApp:
    W, H = 760, 560

    def __init__(self, master, cfg, on_save, on_apply=None, on_close=None, on_restart=None):
        """cfg — робоча копія конфіга; on_save(cfg) — зберегти; on_apply(cfg) —
        миттєво застосувати тему/мову (overlay+трей); on_close() — закрити;
        on_restart() — перезапустити всю програму (для кнопки після оновлення)."""
        self.cfg = dict(cfg)
        self.on_save = on_save
        self.on_apply = on_apply
        self.on_close_cb = on_close
        self.on_restart = on_restart
        self.lang = self.cfg.get("lang", "uk")
        self.P = themes.palette(self.cfg.get("theme", "discord"))
        self._or_active = True
        # якщо чогось бракує (ffmpeg) — одразу відкриваємо вкладку «Встановлення»
        self._active_tab = "general" if deps.all_ok() else "setup"

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

        self._init_vars()      # усі змінні — ОДИН раз (щоб стан не губився між вкладками)
        self._build()

    def _init_vars(self):
        """Створює всі змінні налаштувань один раз. Віджети вкладок лише прив'язуються
        до них — тож перемикання вкладок НІКОЛИ не скидає вибране. Кожна зміна —
        авто-збереження (не треба тиснути «Зберегти»)."""
        c, w = self.cfg, self.win
        self.v_target = tk.IntVar(w, c.get("target_mb", 10))
        self.v_auto = tk.BooleanVar(w, c.get("auto_scale", True))
        self.v_block = tk.BooleanVar(w, c.get("block_paste", True))
        self.v_paste = tk.BooleanVar(w, c.get("auto_paste", True))
        self.v_audio = tk.IntVar(w, c.get("audio_kbps", 128))
        self.v_cv = tk.BooleanVar(w, c.get("compress_video", True))
        self.v_ci = tk.BooleanVar(w, c.get("compress_images", True))
        self.v_ca = tk.BooleanVar(w, c.get("compress_audio", True))
        self.v_keep = tk.StringVar(w, c.get("keep_local", "ask"))
        self.v_shrink = tk.BooleanVar(w, c.get("offer_shrink", True))
        self.v_theme = tk.StringVar(w, c.get("theme", "discord"))
        self.v_lang = tk.StringVar(w, c.get("lang", "uk"))
        for v in (self.v_target, self.v_auto, self.v_block, self.v_paste, self.v_audio,
                  self.v_cv, self.v_ci, self.v_ca, self.v_keep, self.v_shrink):
            v.trace_add("write", lambda *a: self._autosave())

    def _autosave(self):
        self.cfg = self._collect()
        try:
            self.on_save(self.cfg)
        except Exception:
            pass
        self._flash_saved()

    def _flash_saved(self):
        try:
            self.status.config(text=self.T("saved"))
            if getattr(self, "_flash_after", None):
                self.win.after_cancel(self._flash_after)
            self._flash_after = self.win.after(1500, lambda: self.status.config(text=""))
        except (tk.TclError, AttributeError):
            pass

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
        try:
            self._autosave()      # нічого не губимо навіть якщо не тиснув «Зберегти»
        except Exception:
            pass
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
                ("appearance", "tab_appearance", "🎨"), ("setup", "tab_setup", "⬇"),
                ("updates", "tab_updates", "⭳"), ("performance", "tab_performance", "⚡"),
                ("about", "tab_about", "ⓘ")]
        tk.Frame(self.side, bg=P["sidebar"], height=10).pack()
        for key, tkey, icon in tabs:
            self._nav_btn(key, f"  {icon}  " + self.T(tkey))

        # --- футер із «Зберегти» ---
        footer = tk.Frame(self.win, bg=P["title_bg"], height=52)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        tk.Label(footer, text=self.T("autosave_hint"), bg=P["title_bg"], fg=P["muted"],
                 font=(themes.FONT, 9)).pack(side="left", padx=16)
        self.status = tk.Label(footer, text="", bg=P["title_bg"], fg=P["green"],
                               font=(themes.FONT, 10, "bold"))
        self.status.pack(side="left")
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
         "appearance": self._tab_appearance, "setup": self._tab_setup,
         "updates": self._tab_updates, "performance": self._tab_performance,
         "about": self._tab_about}[key]()

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

    def _radio(self, parent, text, var, value):
        P = self.P
        tk.Radiobutton(parent, text=text, variable=var, value=value,
                       bg=P["bg"], fg=P["text"], selectcolor=P["dark"],
                       activebackground=P["bg"], activeforeground=P["text"],
                       font=(themes.FONT, 11)).pack(anchor="w", padx=6, pady=2)

    def _tab_general(self):
        f = self._pad()
        self._header(f, self.T("limit_title"))
        for tkey, mb in (("limit_10", 10), ("limit_25", 25), ("limit_50", 50), ("limit_500", 500)):
            self._radio(f, self.T(tkey), self.v_target, mb)

        tk.Frame(f, bg=self.P["bg"], height=12).pack()
        self._check(f, self.T("opt_autoscale"), self.v_auto)
        self._check(f, self.T("opt_block"), self.v_block)
        self._check(f, self.T("opt_paste"), self.v_paste)

        row = tk.Frame(f, bg=self.P["bg"]); row.pack(anchor="w", pady=(12, 0))
        self._lbl(row, self.T("audio_kbps")).pack(side="left")
        tk.Spinbox(row, from_=0, to=320, increment=32, width=6, textvariable=self.v_audio,
                   font=(themes.FONT, 11)).pack(side="left", padx=8)

    def _tab_media(self):
        f = self._pad()
        self._header(f, self.T("media_title"))
        self._check(f, self.T("media_video"), self.v_cv)
        self._check(f, self.T("media_image"), self.v_ci)
        self._check(f, self.T("media_audio"), self.v_ca)
        self._check(f, self.T("opt_shrink"), self.v_shrink)

        tk.Frame(f, bg=self.P["bg"], height=16).pack()
        self._lbl(f, self.T("keep_title"), size=12, bold=True).pack(anchor="w", pady=(0, 6))
        for tkey, val in (("keep_ask", "ask"), ("keep_always", "always"), ("keep_never", "never")):
            self._radio(f, self.T(tkey), self.v_keep, val)

    def _tab_appearance(self):
        f = self._pad()
        self._header(f, self.T("theme_title"))
        trow = tk.Frame(f, bg=self.P["bg"]); trow.pack(anchor="w", pady=(0, 6))
        for name in themes.order():
            pal = themes.palette(name)
            sel = name == self.v_theme.get()
            card = tk.Frame(trow, bg=pal["bg"], highlightthickness=3, cursor="hand2",
                            highlightbackground=(self.P["accent"] if sel else pal["dark"]),
                            highlightcolor=(self.P["accent"] if sel else pal["dark"]))
            card.pack(side="left", padx=8)
            mark = "  ✓" if sel else ""
            tk.Label(card, text=pal["name"] + mark, bg=pal["bg"], fg=pal["text"],
                     font=(themes.FONT, 11, "bold")).pack(padx=16, pady=(12, 4))
            sw = tk.Frame(card, bg=pal["bg"]); sw.pack(pady=(0, 12))
            for c in ("accent", "green", "warn", "red"):
                tk.Frame(sw, bg=pal[c], width=16, height=16).pack(side="left", padx=2)
            for w in (card, ) + tuple(card.winfo_children()):
                w.bind("<Button-1>", lambda e, n=name: self._pick_theme(n))

        tk.Frame(f, bg=self.P["bg"], height=18).pack()
        self._lbl(f, self.T("lang_title"), size=12, bold=True).pack(anchor="w", pady=(0, 6))
        for code in i18n.LANGS:
            tk.Radiobutton(f, text=i18n.LANG_NAMES[code], variable=self.v_lang, value=code,
                           command=lambda c=code: self._pick_lang(c),
                           bg=self.P["bg"], fg=self.P["text"], selectcolor=self.P["dark"],
                           activebackground=self.P["bg"], activeforeground=self.P["text"],
                           font=(themes.FONT, 11)).pack(anchor="w", padx=6, pady=2)

    def _pick_theme(self, name):
        self.cfg["theme"] = name
        self.v_theme.set(name)
        self.P = themes.palette(name)
        self.win.configure(bg=self.P["dark"])
        self._autosave()       # зберегти + застосувати (overlay/трей)
        self._apply_live()
        self._build()

    def _pick_lang(self, code):
        self.cfg["lang"] = code
        self.lang = code
        self.v_lang.set(code)
        self._autosave()
        self._apply_live()
        self._build()

    def _apply_live(self):
        if self.on_apply:
            try:
                self.on_apply(self.cfg)
            except Exception:
                pass

    def _tab_updates(self):
        self._restart_btn = None
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
                # знайшли оновлення -> пропонуємо перезапуск (щоб застосувати свіжий код)
                if self.on_restart and not getattr(self, "_restart_btn", None):
                    self._restart_btn = self._btn(self.upd_btn.master, self.T("restart_now"),
                                                  self._do_restart)
                    self._restart_btn.pack(anchor="w", pady=(10, 0))
            else:
                self.upd_status.config(text=self.T("up_to_date"), fg=self.P["green"])
        except tk.TclError:
            pass

    def _do_restart(self):
        if self.on_restart:
            self.on_restart()

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

    def _tab_setup(self):
        f = self._pad()
        self._header(f, self.T("setup_title"))
        self._lbl(f, self.T("setup_hint"), muted=True).pack(anchor="w", pady=(0, 10))
        self.setup_status = tk.Frame(f, bg=self.P["bg"]); self.setup_status.pack(anchor="w", fill="x")

        btns = tk.Frame(f, bg=self.P["bg"]); btns.pack(anchor="w", pady=(12, 6))
        self.setup_install_btn = self._btn(btns, self.T("setup_install"), self._setup_install)
        self.setup_install_btn.pack(side="left")
        self._btn(btns, self.T("setup_recheck"), self._setup_render, primary=False).pack(side="left", padx=8)

        self.setup_msg = self._lbl(f, "", size=11, bold=True); self.setup_msg.pack(anchor="w", pady=(2, 4))
        self._lbl(f, self.T("setup_manual"), size=9, muted=True).pack(anchor="w")

        self.setup_log = tk.Text(f, height=7, bg=self.P["dark"], fg=self.P["muted"],
                                 font=("Consolas", 9), relief="flat", bd=0, wrap="word",
                                 insertbackground=self.P["text"])
        self.setup_log.pack(anchor="w", fill="both", expand=True, pady=(10, 0))
        self.setup_log.configure(state="disabled")
        self._setup_render()

    def _setup_render(self):
        try:
            for w in self.setup_status.winfo_children():
                w.destroy()
            st = deps.check(refresh=True)
            for name, ok in st.items():
                row = tk.Frame(self.setup_status, bg=self.P["bg"]); row.pack(anchor="w", pady=2)
                tk.Label(row, text="✓" if ok else "✗", bg=self.P["bg"],
                         fg=self.P["green"] if ok else self.P["red"],
                         font=(themes.FONT, 12, "bold"), width=2).pack(side="left")
                tag = self.T("setup_present") if ok else self.T("setup_missing")
                tk.Label(row, text=f"{name} — {tag}", bg=self.P["bg"], fg=self.P["text"],
                         font=(themes.FONT, 11)).pack(side="left")
            if all(st.values()):
                self.setup_msg.config(text=self.T("setup_all_ok"), fg=self.P["green"])
                self.setup_install_btn.config(state="disabled")
            else:
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
        # усі змінні існують від __init__, тож читаємо напряму (без hasattr-пасток)
        c = dict(self.cfg)
        try:
            c.update(target_mb=self.v_target.get(), auto_scale=self.v_auto.get(),
                     block_paste=self.v_block.get(), auto_paste=self.v_paste.get(),
                     audio_kbps=self.v_audio.get(),
                     compress_video=self.v_cv.get(), compress_images=self.v_ci.get(),
                     compress_audio=self.v_ca.get(), keep_local=self.v_keep.get(),
                     offer_shrink=self.v_shrink.get())
        except (tk.TclError, AttributeError):
            pass
        c["theme"] = self.cfg.get("theme", "discord")
        c["lang"] = self.cfg.get("lang", "uk")
        return c

    def _save(self):
        # усе й так зберігається саме; кнопка лишається як явне підтвердження
        self._autosave()
        self._apply_live()

    def mainloop(self):
        self.win.mainloop()
