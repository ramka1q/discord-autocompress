#!/usr/bin/env python3
"""
edit_inspector.py — панель властивостей справа від плеєра (як у CapCut).
Показує налаштування того, що вибрано на таймлайні: кліп / накладка / текст / звук.
Повзунки тягнуться мишкою (подвійний клік — скинути), кожна зміна = один крок undo.
Тільки стандартна бібліотека (tkinter).
"""
import tkinter as tk

import edit_fx as fx


def _mix(c1, c2, t):
    try:
        a = [int(c1.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
        b = [int(c2.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    except (ValueError, IndexError):
        return c1
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(a[i] + (b[i] - a[i]) * t))) for i in range(3))


class Slider(tk.Canvas):
    """Повзунок: назва зліва, значення справа, доріжка знизу. Клік/тяг — змінити,
    подвійний клік — скинути на дефолт."""

    def __init__(self, parent, P, label, lo, hi, get, set_, fmt, default, on_start, width):
        super().__init__(parent, width=width, height=44, bg=P["bg2"], highlightthickness=0,
                         cursor="hand2")
        self.P, self._label, self._lo, self._hi = P, label, float(lo), float(hi)
        self._get, self._setf, self._fmt, self._def = get, set_, fmt, default
        self._on_start, self._sw, self._hot = on_start, width, False
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", lambda e: self._hov(False))
        self.bind("<Double-Button-1>", self._reset)
        self.bind("<Enter>", lambda e: self._hov(True))
        self.bind("<Leave>", lambda e: self._hov(False))
        self.redraw()

    def _hov(self, on):
        self._hot = on
        self.redraw()

    def _val_at(self, x):
        f = max(0.0, min(1.0, (x - 10) / float(self._sw - 20)))
        return self._lo + f * (self._hi - self._lo)

    def _press(self, ev):
        if self._on_start:
            self._on_start()
        self._setf(self._val_at(ev.x))
        self.redraw()

    def _move(self, ev):
        self._setf(self._val_at(ev.x))
        self.redraw()

    def _reset(self, _ev):
        if self._on_start:
            self._on_start()
        self._setf(self._def)
        self.redraw()

    def redraw(self):
        P = self.P
        try:
            self.delete("all")
        except tk.TclError:
            return
        v = float(self._get())
        self.create_text(10, 11, text=self._label, anchor="w", fill=P["text"], font=(P["font"], 9))
        self.create_text(self._sw - 10, 11, text=self._fmt(v), anchor="e",
                         fill=(P["accent"] if abs(v - self._def) > 1e-6 else P["muted"]),
                         font=(P["font"], 9, "bold"))
        x1, x2, y = 10, self._sw - 10, 31
        f = (v - self._lo) / max(1e-9, (self._hi - self._lo))
        kx = x1 + max(0.0, min(1.0, f)) * (x2 - x1)
        d0 = (self._def - self._lo) / max(1e-9, (self._hi - self._lo))
        dx = x1 + max(0.0, min(1.0, d0)) * (x2 - x1)
        self.create_line(x1, y, x2, y, fill=_mix(P["bg2"], P["text"], 0.18), width=4, capstyle="round")
        self.create_line(min(dx, kx), y, max(dx, kx) + 0.1, y, fill=P["accent"], width=4, capstyle="round")
        self.create_line(dx, y - 4, dx, y + 4, fill=_mix(P["bg2"], P["text"], 0.35))
        r = 7 if self._hot else 6
        self.create_oval(kx - r, y - r, kx + r, y + r, fill="#ffffff", outline="")


class Chips(tk.Frame):
    """Ряд кнопок-«чіпсів» для вибору одного значення (швидкість, фільтр, стиль…)."""

    def __init__(self, parent, P, options, get, set_, per_row=4):
        super().__init__(parent, bg=P["bg2"])
        self.P, self._get, self._setf = P, get, set_
        self._labels = []
        for i, (val, lab) in enumerate(options):
            l = tk.Label(self, text=lab, font=(P["font"], 9), padx=4, pady=4, cursor="hand2",
                         bg=P["dark"], fg=P["text"])
            l.grid(row=i // per_row, column=i % per_row, padx=2, pady=2, sticky="ew")
            l.bind("<Button-1>", lambda e, v=val: self._pick(v))
            l.bind("<Enter>", lambda e, l=l, v=val: l.config(
                bg=self.P["accent"] if self._get() == v else _mix(self.P["dark"], self.P["text"], 0.12)))
            l.bind("<Leave>", lambda e: self.update_sel())
            self._labels.append((val, l))
        for c in range(per_row):
            self.columnconfigure(c, weight=1, uniform="chips")
        self.update_sel()

    def _pick(self, v):
        self._setf(v)
        self.update_sel()

    def update_sel(self):
        cur = self._get()
        for val, l in self._labels:
            on = val == cur
            try:
                l.config(bg=self.P["accent"] if on else self.P["dark"],
                         fg="#ffffff" if on else self.P["text"])
            except tk.TclError:
                pass


class Swatches(tk.Canvas):
    def __init__(self, parent, P, colors, get, set_, width):
        super().__init__(parent, width=width, height=34, bg=P["bg2"], highlightthickness=0,
                         cursor="hand2")
        self.P, self._colors, self._get, self._setf, self._sw = P, colors, get, set_, width
        self.bind("<Button-1>", self._click)
        self.redraw()

    def _pos(self, i):
        step = (self._sw - 20) / float(len(self._colors))
        return 10 + step * (i + 0.5)

    def _click(self, ev):
        best = min(range(len(self._colors)), key=lambda i: abs(self._pos(i) - ev.x))
        self._setf(self._colors[best])
        self.redraw()

    def redraw(self):
        self.delete("all")
        cur = (self._get() or "").lower()
        for i, c in enumerate(self._colors):
            x, y = self._pos(i), 17
            if c.lower() == cur:
                self.create_oval(x - 14, y - 14, x + 14, y + 14, outline=self.P["accent"], width=2)
            self.create_oval(x - 10, y - 10, x + 10, y + 10, fill=c,
                             outline=_mix(self.P["bg2"], self.P["text"], 0.35))


class Inspector(tk.Frame):
    """Права панель. sync() перебудовує вміст, коли змінився вибраний об'єкт."""
    W = 290

    def __init__(self, parent, ed, P, E):
        super().__init__(parent, bg=P["bg2"], width=self.W)
        self.pack_propagate(False)
        self.ed, self.P, self.E = ed, P, E
        self._key = None
        self._sliders = []
        self.head = tk.Label(self, text="", bg=P["bg2"], fg=P["text"], anchor="w",
                             font=(P["font"], 11, "bold"))
        self.head.pack(fill="x", padx=14, pady=(12, 2))
        self.sub = tk.Label(self, text="", bg=P["bg2"], fg=P["muted"], anchor="w",
                            font=(P["font"], 8))
        self.sub.pack(fill="x", padx=14, pady=(0, 6))
        self.cv = tk.Canvas(self, bg=P["bg2"], highlightthickness=0)
        self.cv.pack(fill="both", expand=True)
        self.body = tk.Frame(self.cv, bg=P["bg2"])
        self._win = self.cv.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfigure(self._win, width=e.width))
        self.cv.bind("<MouseWheel>", self._wheel)

    # ---------------------------------------------------------- службове -- #
    def _wheel(self, ev):
        try:
            if self.body.winfo_reqheight() > self.cv.winfo_height():
                self.cv.yview_scroll(int(-ev.delta / 120) * 3, "units")
        except tk.TclError:
            pass
        return "break"

    def _bind_wheel(self, w):
        if not isinstance(w, tk.Text):
            w.bind("<MouseWheel>", self._wheel, add="+")
        for ch in w.winfo_children():
            self._bind_wheel(ch)

    def _section(self, text):
        tk.Label(self.body, text=text.upper(), bg=self.P["bg2"], fg=self.P["muted"], anchor="w",
                 font=(self.P["font"], 8, "bold")).pack(fill="x", padx=14, pady=(10, 2))

    def _slider(self, label, lo, hi, get, set_, fmt, default):
        def setter(v):
            set_(v)
            self.ed._prop_changed()
        s = Slider(self.body, self.P, label, lo, hi, get, setter, fmt, default,
                   self.ed._push_undo, self.W - 16)
        s.pack(padx=4, pady=0)
        self._sliders.append(s)
        return s

    def _chips(self, options, get, set_, per_row=4, undo=True):
        def setter(v):
            if get() == v:
                return
            if undo:
                self.ed._push_undo()
            set_(v)
            self.ed._prop_changed()
        c = Chips(self.body, self.P, options, get, setter, per_row)
        c.pack(fill="x", padx=12, pady=(2, 4))
        return c

    def _row(self, buttons):
        f = tk.Frame(self.body, bg=self.P["bg2"])
        f.pack(fill="x", padx=12, pady=(6, 2))
        for text, cmd in buttons:
            self.ed._btn(f, text, cmd, primary=False, small=True).pack(side="left", padx=2, pady=2)
        return f

    def _vol_slider(self, obj, has_mute, peak_of=None):
        """Гучність 0..10000%: ліва половина повзунка — до 100%, права — експериментальний «угар».
        Процент = справжній множник амплітуди (100% = як є, 10000% = ×100 = +40 dB).
        peak_of — словник (джерело/звук), де лежить виміряний пік: з нього рахуємо,
        до скількох % звук ще ЧИСТИЙ (далі цифровий максимум 0 dBFS -> кліпінг)."""
        peak = None
        if peak_of is not None:
            peak = peak_of.get("peak_db")
            if "peak_db" not in peak_of:
                self.ed._measure_peak(peak_of)
        clean = None if peak is None else 10 ** (-peak / 20.0)
        def get():
            v = 0.0 if (has_mute and obj.get("mute")) else float(obj.get("vol", 1.0))
            return fx.vol_pos(v)

        def set_(pos):
            v = fx.pos_vol(pos)
            if abs(v - 1.0) < 0.03:        # липне до 100%
                v = 1.0
            obj["vol"] = v
            if has_mute:
                obj["mute"] = v < 0.005

        def fmt(pos):
            v = fx.pos_vol(pos)
            t = fx.vol_label(v)
            if clean is not None and v > clean * 1.01:
                t += " ⚠"
            return t
        sl = self._slider(self.E("ins_volume_x"), 0.0, 1.0, get, set_, fmt, 0.5)
        if peak_of is not None:
            if peak is None:
                txt = self.E("ins_vol_measuring")
            elif peak <= -90:
                txt = self.E("ins_vol_silent")
            else:
                txt = self.E("ins_vol_clean", p=fx.vol_label(clean), db=f"{peak:.1f}")
            tk.Label(self.body, text=txt, bg=self.P["bg2"], fg=self.P["muted"], anchor="w",
                     font=(self.P["font"], 8)).pack(fill="x", padx=14, pady=(0, 4))
        return sl

    def _afx(self, obj, can_speed):
        """Ефекти звуку: пресети (Slowed+Reverb, Nightcore, бас-буст, earrape), ефект, тон, бас, реверб."""
        E, ed = self.E, self.ed
        self._section(E("ins_afx"))

        def set_preset(key):
            pr = fx.AUDIO_PRESETS[key]
            for k in fx.AFX_KEYS:
                obj[k] = pr[k]
            if "vol" in pr:
                obj["vol"] = pr["vol"]
                obj.pop("mute", None) if "mute" not in obj else obj.__setitem__("mute", False)
            obj["apreset"] = key
            if can_speed and pr.get("speed") is not None:
                ed._set_speed(pr["speed"], undo=False)
            self.after_idle(lambda: self.sync(force=True))   # оновити повзунки
        self._chips([(k, E("ap_" + k)) for k in fx.AUDIO_PRESETS],
                    lambda: obj.get("apreset", "none" if fx.afx_default(obj) else None),
                    set_preset, per_row=3)
        self._chips([(k, E("ae_" + k)) for k in fx.AUDIO_EFFECTS],
                    lambda: fx.g(obj, "aeff"),
                    lambda v: (obj.__setitem__("aeff", v), obj.__setitem__("apreset", None)), per_row=5)

        def setter(key, snap=None):
            def f(v):
                v = float(v)
                if snap:
                    v = round(v / snap) * snap
                obj[key] = v
                obj["apreset"] = None
            return f
        self._slider(E("ins_pitch"), -12.0, 12.0, lambda: float(fx.g(obj, "pitch")), setter("pitch", 0.5),
                     lambda v: f"{v:+.1f}", 0.0)
        self._slider(E("ins_bass"), 0.0, 30.0, lambda: float(fx.g(obj, "bass")), setter("bass", 0.5),
                     lambda v: f"+{v:.0f} dB" + ("  💥" if v >= 15 else ""), 0.0)
        self._slider(E("ins_reverb"), 0.0, 1.0, lambda: float(fx.g(obj, "rev")), setter("rev"),
                     self._pct, 0.0)

    def _pct(self, v):
        return f"{int(round(v * 100))}%"

    def _sec(self, v):
        return f"{v:.1f} s"

    def _signed(self, v):
        return f"{int(round(v * 100)):+d}"

    def _setp(self, obj, key, cast=float):
        return lambda v: obj.__setitem__(key, cast(v))

    def refresh_values(self):
        for s in self._sliders:
            try:
                s.redraw()
            except tk.TclError:
                pass

    # -------------------------------------------------------------- вміст -- #
    def sync(self, force=False):
        key = self.ed._sel_key()
        if key == self._key and not force:
            return
        self._key = key
        for w in self.body.winfo_children():
            w.destroy()
        self._sliders = []
        self.cv.yview_moveto(0)
        kind = key[0] if key else None
        try:
            if kind == "txt":
                self._build_text(self.ed.texts[key[1]])
            elif kind == "ovl":
                self._build_ovl(self.ed.ovls[key[1]])
            elif kind == "snd":
                self._build_snd(self.ed.snds[key[1]])
            elif kind == "clip":
                self._build_clip(self.ed._sel_piece())
            else:
                self.head.config(text="")
                self.sub.config(text="")
        except (IndexError, tk.TclError):
            pass
        self._bind_wheel(self.body)

    def _src_name(self, src):
        n = src["name"]
        return n if len(n) <= 34 else n[:32] + "…"

    def _look(self, p):
        E = self.E
        self._section(E("ins_filter"))
        self._chips([(f, E("flt_" + f)) for f in fx.FILTERS],
                    lambda: fx.g(p, "flt"), self._setp(p, "flt", str))
        self._section(E("ins_adjust"))
        self._slider(E("ins_bright"), -0.3, 0.3, lambda: fx.g(p, "br"), self._setp(p, "br"),
                     lambda v: f"{int(round(v / 0.3 * 100)):+d}", 0.0)
        self._slider(E("ins_contrast"), 0.5, 1.5, lambda: fx.g(p, "ct"), self._setp(p, "ct"),
                     lambda v: f"{int(round((v - 1) * 200)):+d}", 1.0)
        self._slider(E("ins_sat"), 0.0, 2.0, lambda: fx.g(p, "sat"), self._setp(p, "sat"),
                     lambda v: f"{int(round((v - 1) * 100)):+d}", 1.0)

    def _fades(self, obj, maxd):
        E = self.E
        hi = max(0.2, min(3.0, maxd / 2.0))
        self._slider(E("ins_fade_in"), 0.0, hi, lambda: float(obj.get("fin", 0.0)),
                     self._setp(obj, "fin"), self._sec, 0.0)
        self._slider(E("ins_fade_out"), 0.0, hi, lambda: float(obj.get("fout", 0.0)),
                     self._setp(obj, "fout"), self._sec, 0.0)

    def _build_clip(self, p):
        E, ed = self.E, self.ed
        src = ed._src(p)
        self.head.config(text=("🖼  " if src["kind"] == "image" else "🎬  ") + E("ins_clip"))
        self.sub.config(text=self._src_name(src))
        dur = (p["e"] - p["s"]) / p["speed"]
        if src["kind"] == "video":
            self._section(E("ins_speed"))
            self._chips([(v, f"{v:g}×") for v in (0.25, 0.5, 1.0, 1.5, 2.0, 3.0)],
                        lambda: p["speed"], lambda v: ed._set_speed(v, undo=False), per_row=6)
        self._section(E("ins_sound_fade"))
        if src["kind"] == "video" and src["has_audio"]:
            self._vol_slider(p, True, src)
        self._fades(p, dur)
        if src["kind"] == "video":
            self._row([("🎞 " + (E("ins_revideo") if fx.g(p, "novideo") else E("ins_novideo")),
                        ed._toggle_novideo)])
        if src["kind"] == "video" and src["has_audio"]:
            self._afx(p, can_speed=True)
        if ed.sel > 0:
            self._section(E("ins_trans"))
            self._chips([(None, E("tr_none"))] + [(t, E("tr_" + t)) for t in fx.TRANSITIONS],
                        lambda: (p.get("tr") or {}).get("type"),
                        lambda v: ed._set_tr(ed.sel, v, undo=False), per_row=3)

            def set_d(v):
                if p.get("tr"):
                    p["tr"] = dict(p["tr"], d=float(v))
            self._slider(E("ins_trans_d"), 0.2, 1.5, lambda: float((p.get("tr") or {}).get("d", 0.5)),
                         set_d, self._sec, 0.5)
        self._look(p)
        self._section(E("ins_transform"))
        self._row([("⟳ 90°", ed._rotate), ("⇋ " + E("ins_flip"), ed._flip),
                   ("⟲ " + E("ins_reset"), ed._reset_look)])

    def _build_ovl(self, o):
        E, ed = self.E, self.ed
        src = ed.sources[o["src"]]
        self.head.config(text="🎭  " + E("ins_overlay"))
        self.sub.config(text=self._src_name(src))
        self._section(E("ins_overlay"))
        self._slider(E("ins_opacity"), 0.0, 1.0, lambda: float(o.get("op", 1.0)),
                     self._setp(o, "op"), self._pct, 1.0)
        if src["kind"] == "video" and src["has_audio"]:
            self._vol_slider(o, True, src)
        self._fades(o, o["e"] - o["s"])
        if src["kind"] == "video" and src["has_audio"]:
            self._afx(o, can_speed=False)
        self._look(o)
        self._section(E("ins_transform"))
        self._row([("⟳ 90°", ed._rotate), ("⇋ " + E("ins_flip"), ed._flip),
                   ("⟲ " + E("ins_reset"), ed._reset_look)])
        self._row([("⬇ " + E("ins_to_track"), ed._ovl_to_track), ("🗑", ed._ovl_del)])

    def _build_text(self, t):
        E, ed, P = self.E, self.ed, self.P
        self.head.config(text="T   " + E("ins_text"))
        self.sub.config(text=E("ins_text_hint"))
        box = tk.Text(self.body, height=3, wrap="word", bg=P["dark"], fg=P["text"],
                      insertbackground=P["text"], relief="flat", font=(P["font"], 11),
                      padx=8, pady=6, highlightthickness=1, highlightbackground=P["dark"],
                      highlightcolor=P["accent"], undo=False)
        box.pack(fill="x", padx=14, pady=(4, 4))
        box.insert("1.0", t["text"])
        self.text_box = box
        state = {"pushed": False}

        def on_focus(_e):
            state["pushed"] = False

        def on_key(_e):
            txt = box.get("1.0", "end-1c")
            if txt == t["text"]:
                return
            if not state["pushed"]:
                ed._push_undo()
                state["pushed"] = True
            t["text"] = txt
            ed._prop_changed()

        def on_modified(_e):
            # будь-яка зміна вмісту (клавіші, вставка, програмно) -> застосувати
            try:
                if box.edit_modified():
                    box.edit_modified(False)
                    on_key(None)
            except tk.TclError:
                pass
        box.edit_modified(False)
        box.bind("<FocusIn>", on_focus)
        box.bind("<KeyRelease>", on_key)
        box.bind("<<Modified>>", on_modified)
        self._section(E("ins_style"))
        self._chips([(s, E("st_" + s)) for s in fx.TEXT_STYLES], lambda: t.get("style", "outline"),
                    self._setp(t, "style", str), per_row=3)
        self._section(E("ins_color"))
        sw = Swatches(self.body, P, fx.TEXT_COLORS, lambda: t.get("color", "#ffffff"), None, self.W - 16)

        def set_col(c):
            if c == t.get("color"):
                return
            ed._push_undo()
            t["color"] = c
            ed._prop_changed()
        sw._setf = set_col
        sw.pack(padx=4)
        self._slider(E("ins_size"), 0.03, 0.25, lambda: float(t["size"]) * float(t.get("zoom", 1.0)),
                     lambda v: (t.__setitem__("size", float(v)), t.__setitem__("zoom", 1.0)),
                     lambda v: f"{int(round(v * 100))}", 0.085)
        self._section(E("ins_pos"))
        self._chips([(-0.36, E("pos_top")), (0.0, E("pos_mid")), (0.30, E("pos_bottom"))],
                    lambda: round(float(t["ny"]), 2) if abs(t["nx"]) < 1e-6 else None,
                    lambda v: (t.__setitem__("ny", float(v)), t.__setitem__("nx", 0.0)), per_row=3)
        self._section(E("ins_anim"))
        self._fades(t, t["dur"])
        self._row([("📄 " + E("ins_dup"), ed._txt_dup), ("🗑", ed._txt_del)])

    def _build_snd(self, s):
        E, ed = self.E, self.ed
        self.head.config(text="🎵  " + E("ins_sound"))
        self.sub.config(text=s["name"] if len(s["name"]) <= 34 else s["name"][:32] + "…")
        self._section(E("ins_sound_fade"))
        self._vol_slider(s, False, s)
        self._fades(s, s["dur"])
        self._afx(s, can_speed=False)
        self._row([("▶ " + E("ins_listen"), lambda: ed._preview_sound(s)),
                   ("🗑", lambda: ed._del_snd(ed.snds.index(s)) if s in ed.snds else None)])
