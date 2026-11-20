#!/usr/bin/env python3
"""
edit_inspector.py — панель властивостей справа від плеєра (як у CapCut).
Показує налаштування того, що вибрано на таймлайні: кліп / накладка / текст / звук.
Повзунки тягнуться мишкою (подвійний клік — скинути), кожна зміна = один крок undo.
Тільки стандартна бібліотека (tkinter).
"""
import tkinter as tk
import themes

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


class NumField(tk.Frame):
    """Підпис + числове поле (як X / Y / Rotate у відеоредакторах). Enter / вихід із поля —
    застосувати; коліщатко або стрілки вгору/вниз — крок (Shift — x10)."""

    def __init__(self, parent, P, label, get, set_, step=1.0, fmt="{:.0f}", lo=-1e9, hi=1e9, width=7):
        super().__init__(parent, bg=P["bg2"])
        self.P, self._get, self._setf, self._step, self._fmt = P, get, set_, step, fmt
        self._lo, self._hi = lo, hi
        if label:
            tk.Label(self, text=label, bg=P["bg2"], fg=P["muted"], font=(P["font"], 8)).pack(side="left", padx=(0, 4))
        self.var = tk.StringVar()
        self.ent = tk.Entry(self, textvariable=self.var, width=width, justify="center", relief="flat",
                            bg=P["dark"], fg=P["text"], insertbackground=P["text"], font=(P["font"], 9),
                            highlightthickness=1, highlightbackground=P["dark"], highlightcolor=P["accent"])
        self.ent.pack(side="left", ipady=3)
        self.ent.bind("<Return>", self._commit)
        self.ent.bind("<FocusOut>", self._commit)
        self.ent.bind("<MouseWheel>", lambda e: self._bump(1 if e.delta > 0 else -1, e) or "break")
        self.ent.bind("<Up>", lambda e: self._bump(1, e) or "break")
        self.ent.bind("<Down>", lambda e: self._bump(-1, e) or "break")
        self.redraw()

    def redraw(self):
        try:
            if self.focus_get() is not self.ent:
                self.var.set(self._fmt.format(float(self._get())))
        except (tk.TclError, KeyError):
            pass

    def _apply(self, v):
        v = max(self._lo, min(self._hi, v))
        self._setf(v)
        try:
            self.var.set(self._fmt.format(float(self._get())))
        except tk.TclError:
            pass

    def _commit(self, _e=None):
        try:
            v = float(self.var.get().replace(",", ".").replace("%", "").replace("\u00b0", ""))
        except ValueError:
            self.redraw()
            return
        if abs(v - float(self._get())) > 1e-6:
            self._apply(v)

    def _bump(self, d, ev):
        k = 10.0 if (ev.state & 0x1) else 1.0
        self._apply(float(self._get()) + d * self._step * k)


class Tabs(tk.Canvas):
    """Рядок вкладок з підкресленням активної (Video / Audio / Speed / Animation / Adjust)
    або сегменти на всю ширину (In / Out / Combo)."""

    def __init__(self, parent, P, items, get, set_, height=30, seg=False):
        super().__init__(parent, height=height, bg=P["bg2"], highlightthickness=0, cursor="hand2")
        self.P, self._items, self._get, self._setf, self._seg = P, items, get, set_, seg
        self._hits = []
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Button-1>", self._click)

    def _click(self, ev):
        for x1, x2, k in self._hits:
            if x1 <= ev.x <= x2:
                if k != self._get():
                    self._setf(k)
                return

    def redraw(self):
        P = self.P
        try:
            self.delete("all")
            W, H = self.winfo_width(), int(self.cget("height"))
        except tk.TclError:
            return
        if W < 20:
            return
        self._hits = []
        cur = self._get()
        if self._seg:
            n = max(1, len(self._items))
            self.create_rectangle(2, 2, W - 2, H - 2, fill=P["dark"], outline="")
            for i, (k, lab) in enumerate(self._items):
                x1, x2 = 2 + (W - 4) * i / n, 2 + (W - 4) * (i + 1) / n
                if k == cur:
                    self.create_rectangle(x1 + 2, 4, x2 - 2, H - 4, fill=_mix(P["dark"], P["text"], 0.16),
                                          outline="")
                self.create_text((x1 + x2) / 2, H / 2, text=lab, fill=P["text"] if k == cur else P["muted"],
                                 font=(P["font"], 9, "bold" if k == cur else "normal"))
                self._hits.append((x1, x2, k))
            return
        # вміщаємо всі вкладки в ширину панелі: якщо не влазять — менший шрифт і проміжки
        fs, gap = 9, 16
        for fs, gap in ((9, 16), (9, 10), (8, 8), (7, 6)):
            tot = 0
            for _k, lab in self._items:
                t = self.create_text(0, -50, text=lab, anchor="w", font=(P["font"], fs, "bold"))
                b = self.bbox(t)
                tot += (b[2] - b[0]) + gap
                self.delete(t)
            if tot + 12 <= W:
                break
        x = max(6, (W - tot) / 2 + gap / 2) if tot + 12 <= W else 6
        for k, lab in self._items:
            tid = self.create_text(x, H / 2 - 2, text=lab, anchor="w", font=(P["font"], fs, "bold"),
                                   fill=P["accent"] if k == cur else P["text"])
            x1, _y1, x2, _y2 = self.bbox(tid)
            if k == cur:
                self.create_line(x1, H - 3, x2, H - 3, fill=P["accent"], width=2)
            self._hits.append((x1 - gap / 2, x2 + gap / 2, k))
            x = x2 + gap
        self.create_line(0, H - 1, W, H - 1, fill=_mix(P["bg2"], P["text"], 0.1))


class AnimTile(tk.Canvas):
    """Плитка анімації з живим прев'ю: під мишкою картинка рухається так само, як рухатиметься
    кліп (ті самі формули, що й у ffmpeg). Без мишки — нерухома (не вантажить процесор)."""
    SZ = 60

    def __init__(self, parent, P, kind, key, label, on_pick, selected):
        super().__init__(parent, width=self.SZ, height=self.SZ + 16, bg=P["bg2"], highlightthickness=0,
                         cursor="hand2")
        self.P, self.kind, self.key, self.sel, self.label = P, kind, key, selected, label
        self._t, self._after, self._hot = 0.0, None, False
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<Button-1>", lambda e: on_pick(key))
        self.draw(self._rest())

    def _rest(self):
        return {"in": 0.55, "out": 0.45}.get(self.kind, 0.4)

    def _hover(self, on):
        self._hot = on
        if on and self._after is None:
            self._t = 0.0
            self._tick()
        elif not on:
            self.draw(self._rest())

    def _tick(self):
        self._after = None
        if not self._hot:
            return
        self._t += 1 / 30.0
        if self.kind == "combo":
            x = self._t % 3.0
        else:
            x = min(1.0, (self._t % 1.6) / 0.8)      # 0.8 с руху + пауза
        self.draw(x)
        try:
            self._after = self.after(33, self._tick)
        except tk.TclError:
            pass

    def draw(self, x):
        import math
        P, s = self.P, self.SZ
        try:
            self.delete("all")
        except tk.TclError:
            return
        bd = P["accent"] if self.sel else (_mix(P["bg2"], P["text"], 0.3) if self._hot else P["dark"])
        if not self.key:
            self.create_rectangle(1, 1, s - 1, s - 1, fill="#0b0b0b", outline=bd, width=2 if self.sel else 1)
            self.create_oval(s / 2 - 13, s / 2 - 13, s / 2 + 13, s / 2 + 13, outline=P["muted"], width=2)
            self.create_line(s / 2 - 9, s / 2 + 9, s / 2 + 9, s / 2 - 9, fill=P["muted"], width=2)
        else:
            self.create_rectangle(1, 1, s - 1, s - 1, fill="#0b0b0b", outline="")
            S, X, Y, A, B, F = fx.anim_sample(self.kind, self.key, x)
            B, F = max(0.0, min(1.0, B)), max(0.0, min(1.0, F))
            w, h = 40 * S, 26 * S
            cx, cy = s / 2 + X * 40, s / 2 + Y * 26
            ca, sa = math.cos(A), math.sin(A)
            pts = []
            for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
                pts += [cx + dx * ca - dy * sa, cy + dx * sa + dy * ca]
            base = _mix("#000000", _mix(P["accent"], "#ffffff", B), F)
            sun = _mix("#000000", _mix("#ffd166", "#ffffff", B), F)
            self.create_polygon(pts, fill=base, outline="")
            r = 5 * S
            ox, oy = 8 * S, -4 * S
            sx, sy = cx + ox * ca - oy * sa, cy + ox * sa + oy * ca
            self.create_oval(sx - r, sy - r, sx + r, sy + r, fill=sun, outline="")
            # все, що вилізло за плитку, ховаємо рамкою кольору панелі
            pad = 40
            self.create_rectangle(-pad, -pad, s + pad, 0, fill=P["bg2"], outline="")
            self.create_rectangle(-pad, s, s + pad, s + pad, fill=P["bg2"], outline="")
            self.create_rectangle(-pad, 0, 0, s, fill=P["bg2"], outline="")
            self.create_rectangle(s, 0, s + pad, s, fill=P["bg2"], outline="")
            self.create_rectangle(1, 1, s - 1, s - 1, outline=bd, width=2 if self.sel else 1)
        lab = self.label if len(self.label) <= 11 else self.label[:10] + "\u2026"
        self.create_text(s / 2, s + 8, text=lab, fill=P["accent"] if self.sel else P["text"],
                         font=(P["font"], 8))


class Inspector(tk.Frame):
    """Права панель. sync() перебудовує вміст, коли змінився вибраний об'єкт."""
    W = 312

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
        self._tab = {}                   # активна вкладка для кожного типу об'єкта
        self._akind = "in"               # Animation: In / Out / Combo
        self._acat = "all"
        self._nums = []
        self.tabbar = tk.Frame(self, bg=P["bg2"])
        self.tabbar.pack(fill="x")
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
        mono = self.P.get("mono")
        tk.Label(self.body, text=text.upper(), bg=self.P["bg2"], fg=self.P["text"] if mono else self.P["muted"],
                 anchor="w", font=(themes.MONO_FONT if mono else self.P["font"], 8, "bold"))            .pack(fill="x", padx=14, pady=(10, 2))

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
                obj[k] = pr.get(k, fx.PIECE_DEFAULTS[k])
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
        self._section(E("ins_enhance_a"))
        self._chips([(False, E("ins_off")), (True, E("ins_dn"))], lambda: bool(fx.g(obj, "dn")),
                    lambda v: obj.__setitem__("dn", v), per_row=2)
        self._chips([(False, E("ins_off")), (True, E("ins_venh"))], lambda: bool(fx.g(obj, "venh")),
                    lambda v: obj.__setitem__("venh", v), per_row=2)

    def _pct(self, v):
        return f"{int(round(v * 100))}%"

    def _sec(self, v):
        return f"{v:.1f} s"

    def _signed(self, v):
        return f"{int(round(v * 100)):+d}"

    def _setp(self, obj, key, cast=float):
        return lambda v: obj.__setitem__(key, cast(v))

    def refresh_values(self):
        for s in self._sliders + self._nums:
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
        self._rebuild(keep_scroll=False)

    def _rebuild(self, keep_scroll=True):
        key = self._key
        try:
            y0 = self.cv.yview()[0] if keep_scroll else 0.0
        except tk.TclError:
            y0 = 0.0
        for w in self.body.winfo_children() + self.tabbar.winfo_children():
            w.destroy()
        self._sliders, self._nums = [], []
        kind = key[0] if key else None
        try:
            if kind == "txt":
                self._build_text(self.ed.texts[key[1]])
            elif kind == "ovl":
                self._tabs_for("ovl", self.ed.ovls[key[1]])
            elif kind == "snd":
                self._build_snd(self.ed.snds[key[1]])
            elif kind == "clip":
                self._tabs_for("clip", self.ed._sel_piece())
            else:
                self.head.config(text="")
                self.sub.config(text="")
        except (IndexError, tk.TclError):
            pass
        self._bind_wheel(self.body)
        try:
            self.update_idletasks()
            self.cv.yview_moveto(y0)
        except tk.TclError:
            pass

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

    # ------------------------------------------------- вкладки кліпа / накладки -- #
    def _tabs_for(self, kind, p):
        E, ed = self.E, self.ed
        src = ed.sources[p["src"]]
        video = src["kind"] == "video"
        icon = "\U0001f3ad  " if kind == "ovl" else ("\U0001f5bc  " if not video else "\U0001f3ac  ")
        self.head.config(text=icon + (E("ins_overlay") if kind == "ovl" else E("ins_clip")))
        self.sub.config(text=self._src_name(src))
        tabs = [("video", E("tab_ed_video"))]
        if video and src["has_audio"]:
            tabs.append(("audio", E("tab_ed_audio")))
        if video and kind == "clip":
            tabs.append(("speed", E("tab_ed_speed")))
        if kind == "clip":
            tabs.append(("anim", E("tab_ed_anim")))
        tabs.append(("adjust", E("tab_ed_adjust")))
        keys = [k for k, _ in tabs]
        cur = self._tab.get(kind, "video")
        if cur not in keys:
            cur = "video"

        def pick(k):
            self._tab[kind] = k
            self._rebuild(keep_scroll=False)
        Tabs(self.tabbar, self.P, tabs, lambda: cur, pick, height=32).pack(fill="x", padx=2)
        getattr(self, "_tab_" + cur)(kind, p, src)

    def _keyframes(self, p):
        """Ключові кадри: ◆ у точці плейхеда, ◀ ▶ — до сусіднього ключа, очистити."""
        E, ed, P = self.E, self.ed, self.P
        self._section(E("ins_kf"))
        on = ed._kf_at()
        self._row([("\u25c6 " + (E("ins_kf_del") if on else E("ins_kf_add")), ed._kf_toggle),
                   ("\u25c0", lambda: ed._kf_jump(-1)), ("\u25b6", lambda: ed._kf_jump(1)),
                   ("\u2715 " + E("ins_kf_clear"), ed._kf_clear)])
        n = len(fx.kf_times(p))
        tk.Label(self.body, text=E("ins_kf_hint", n=n), bg=P["bg2"], fg=P["muted"], anchor="w",
                 justify="left", wraplength=self.W - 30, font=(P["font"], 8)).pack(fill="x", padx=14, pady=(0, 4))

    def _crop(self, p):
        E = self.E
        self._section(E("ins_crop"))
        for k in fx.CROP_KEYS:
            self._slider(E("ins_" + k), 0.0, 0.45, (lambda k=k: float(fx.g(p, k))), self._setp(p, k),
                         self._pct, 0.0)

    def _keymask(self, p):
        E = self.E
        self._section(E("ins_chroma"))
        cols = [(None, E("ck_none")), ("#00ff00", E("ck_green")), ("#0000ff", E("ck_blue")),
                ("#000000", E("ck_black")), ("#ffffff", E("ck_white"))]
        self._chips(cols, lambda: p.get("ck"), lambda v: p.__setitem__("ck", v), per_row=5)
        self._slider(E("ins_ck_sim"), 0.02, 0.8, lambda: float(p.get("cks", 0.3)), self._setp(p, "cks"),
                     self._pct, 0.3)
        self._section(E("ins_mask"))
        self._chips([(m, E("mask_" + m)) for m in fx.MASKS], lambda: p.get("mask") or "none",
                    lambda v: p.__setitem__("mask", v), per_row=4)
        self._chips([(False, E("mask_normal")), (True, E("mask_invert"))], lambda: bool(p.get("minv")),
                    lambda v: p.__setitem__("minv", v), per_row=2)

    def _tab_video(self, kind, p, src):
        E, ed = self.E, self.ed
        if kind == "clip":
            self._keyframes(p)
        self._transform(kind, p)
        if kind == "clip":
            self._slider(E("ins_opacity"), 0.0, 1.0, lambda: float(fx.g(p, "opa")),
                         self._setp(p, "opa"), self._pct, 1.0)
        if kind == "ovl":
            self._section(E("ins_overlay"))
            self._slider(E("ins_opacity"), 0.0, 1.0, lambda: float(p.get("op", 1.0)),
                         self._setp(p, "op"), self._pct, 1.0)
            if len(ed.ovls) > 1 and ed.sel_ovl is not None:
                self._section(E("ins_layer", n=ed.sel_ovl + 1, m=len(ed.ovls)))
                self._row([("\u2912 " + E("ins_layer_top"), lambda: ed._ovl_layer(1, True)),
                           ("\u2191 " + E("ins_layer_up"), lambda: ed._ovl_layer(1)),
                           ("\u2193 " + E("ins_layer_down"), lambda: ed._ovl_layer(-1)),
                           ("\u2913 " + E("ins_layer_bottom"), lambda: ed._ovl_layer(-1, True))])
            self._keyframes(p)
            self._keymask(p)
        self._crop(p)
        self._section(E("ins_fades"))
        self._fades(p, (p["e"] - p["s"]) / p.get("speed", 1.0))
        if kind == "clip" and src["kind"] == "video":
            self._row([("\U0001f39e " + (E("ins_revideo") if fx.g(p, "novideo") else E("ins_novideo")),
                        ed._toggle_novideo)])
        if kind == "clip" and ed.sel > 0:
            self._section(E("ins_trans"))
            self._chips([(None, E("tr_none"))] + [(t, E("tr_" + t)) for t in fx.TRANSITIONS],
                        lambda: (p.get("tr") or {}).get("type"),
                        lambda v: ed._set_tr(ed.sel, v, undo=False), per_row=3)

            def set_d(v):
                if p.get("tr"):
                    p["tr"] = dict(p["tr"], d=float(v))
            self._slider(E("ins_trans_d"), 0.2, 1.5, lambda: float((p.get("tr") or {}).get("d", 0.5)),
                         set_d, self._sec, 0.5)
        if kind == "ovl":
            self._row([("\u2b07 " + E("ins_to_track"), ed._ovl_to_track), ("\U0001f5d1", ed._ovl_del)])

    def _transform(self, kind, p):
        """Transform: Scale (повзунок + число), Position X / Y, Rotate."""
        E, ed, P = self.E, self.ed, self.P
        self._section(E("ins_transform2"))
        cw, ch = getattr(ed, "_ccw", 1920), getattr(ed, "_cch", 1080)

        def changed():
            ed._prop_changed()
            try:
                ed._draw_tfbox()
            except Exception:
                pass

        def setter(key):
            def f(v):
                ed._push_undo()
                p[key] = float(v)
                changed()
                self.refresh_values()
            return f

        def set_zoom(v):
            p["zoom"] = round(float(v), 3)
            for n in self._nums:
                n.redraw()
            try:
                ed._draw_tfbox()
            except Exception:
                pass
        self._slider(E("ins_scale"), 0.1, 4.0, lambda: float(p.get("zoom", 1.0)), set_zoom, self._pct, 1.0)
        row = tk.Frame(self.body, bg=P["bg2"])
        row.pack(fill="x", padx=14, pady=(4, 2))
        tk.Label(row, text=E("ins_position"), bg=P["bg2"], fg=P["text"], font=(P["font"], 9)).pack(side="left")
        ny = NumField(row, P, "Y", lambda: float(p.get("ny", 0.0)) * ch,
                      lambda v: setter("ny")(float(v) / ch), step=1)
        ny.pack(side="right")
        nx = NumField(row, P, "X", lambda: float(p.get("nx", 0.0)) * cw,
                      lambda v: setter("nx")(float(v) / cw), step=1)
        nx.pack(side="right", padx=(0, 8))
        self._nums += [nx, ny]
        if kind == "clip":
            row2 = tk.Frame(self.body, bg=P["bg2"])
            row2.pack(fill="x", padx=14, pady=(6, 2))
            tk.Label(row2, text=E("ins_rotate"), bg=P["bg2"], fg=P["text"], font=(P["font"], 9)).pack(side="left")
            rt = NumField(row2, P, "", lambda: float(p.get("ang", 0.0)),
                          lambda v: setter("ang")(((float(v) + 180.0) % 360.0) - 180.0), step=1,
                          fmt="{:.1f}\u00b0", lo=-360, hi=360)
            rt.pack(side="right")
            self._nums.append(rt)
        self._row([("\u27f3 90\u00b0", ed._rotate), ("\u21cb " + E("ins_flip"), ed._flip),
                   ("\u27f2 " + E("ins_reset"), ed._reset_look)])

    def _tab_audio(self, kind, p, src):
        E = self.E
        self._section(E("ins_volume_x"))
        self._vol_slider(p, True, src)
        self._afx(p, can_speed=kind == "clip")

    def _tab_speed(self, kind, p, src):
        E, ed = self.E, self.ed
        self._section(E("ins_speed"))
        base = lambda: float(p.get("cbase", p["speed"])) if p.get("curve") else p["speed"]
        self._chips([(v, f"{v:g}\u00d7") for v in (0.25, 0.5, 1.0, 1.5, 2.0, 3.0)],
                    base, lambda v: ed._set_speed(v, undo=False), per_row=6)

        def set_sp(v):
            v = max(0.1, round(float(v) * 20) / 20.0)
            if abs(v - base()) > 1e-6:
                ed._set_speed(v, undo=False)
        self._slider(E("ins_speed_x"), 0.1, 5.0, lambda: float(base()), set_sp,
                     lambda v: f"{v:.2f}\u00d7", 1.0)
        self._section(E("ins_curve"))
        self._chips([(None, E("cv_none"))] + [(k, E("cv_" + k)) for k in fx.CURVES],
                    lambda: p.get("curve"), lambda v: ed._set_curve(v), per_row=4)
        dur = (p["e"] - p["s"]) / p["speed"]
        tk.Label(self.body, text=E("ins_speed_dur", d=f"{dur:.1f}"), bg=self.P["bg2"], fg=self.P["muted"],
                 anchor="w", font=(self.P["font"], 8)).pack(fill="x", padx=14, pady=(0, 4))

    def _tab_adjust(self, kind, p, src):
        self._look(p)
        E = self.E
        sg = lambda v: f"{int(round(v * 100)):+d}"
        self._slider(E("ins_temp"), -1.0, 1.0, lambda: float(fx.g(p, "temp")), self._setp(p, "temp"), sg, 0.0)
        self._slider(E("ins_tint"), -1.0, 1.0, lambda: float(fx.g(p, "tint")), self._setp(p, "tint"), sg, 0.0)
        self._slider(E("ins_hue"), -180.0, 180.0, lambda: float(fx.g(p, "hue")), self._setp(p, "hue"),
                     lambda v: f"{v:+.0f}\u00b0", 0.0)
        self._slider(E("ins_hl"), -1.0, 1.0, lambda: float(fx.g(p, "hl")), self._setp(p, "hl"), sg, 0.0)
        self._slider(E("ins_sh"), -1.0, 1.0, lambda: float(fx.g(p, "sh")), self._setp(p, "sh"), sg, 0.0)
        self._slider(E("ins_sharp"), 0.0, 1.0, lambda: float(fx.g(p, "sharp")), self._setp(p, "sharp"),
                     self._pct, 0.0)
        self._slider(E("ins_vig"), 0.0, 1.0, lambda: float(fx.g(p, "vig")), self._setp(p, "vig"), self._pct, 0.0)
        self._slider(E("ins_grain"), 0.0, 1.0, lambda: float(fx.g(p, "grain")), self._setp(p, "grain"),
                     self._pct, 0.0)
        self._section(E("ins_enhance_v"))
        for k in ("stab", "deflick", "mblur"):
            self._chips([(False, E("ins_off")), (True, E("ins_" + k))], (lambda k=k: bool(fx.g(p, k))),
                        (lambda v, k=k: p.__setitem__(k, v)), per_row=2)
        self._section(self.E("mp_effects"))
        self._chips([(v, self.E("vfx_" + v)) for v in fx.VFX], lambda: fx.g(p, "vfx"),
                    self._setp(p, "vfx", str), per_row=3)

    def _tab_anim(self, kind, p, src):
        """Animation: In / Out / Combo, категорії і сітка плиток з живим прев'ю."""
        E, ed, P = self.E, self.ed, self.P
        slot = {"in": "ain", "out": "aout", "combo": "acombo"}

        def set_kind(k):
            self._akind = k
            self._rebuild()
        Tabs(self.body, P, [("in", E("anim_in")), ("out", E("anim_out")), ("combo", E("anim_combo"))],
             lambda: self._akind, set_kind, height=30, seg=True).pack(fill="x", padx=12, pady=(10, 6))
        cats = tk.Frame(self.body, bg=P["bg2"])
        cats.pack(fill="x", padx=12, pady=(0, 6))
        for i, c in enumerate(fx.ANIM_CATS):
            on = c == self._acat
            lab = tk.Label(cats, text=E("acat_" + c), bg=P["accent"] if on else P["dark"],
                           fg="#ffffff" if on else P["text"], font=(P["font"], 8), padx=6, pady=2,
                           cursor="hand2")
            lab.grid(row=i // 3, column=i % 3, padx=2, pady=2, sticky="ew")
            lab.bind("<Button-1>", lambda e, c=c: (setattr(self, "_acat", c), self._rebuild()))
        for col in range(3):
            cats.columnconfigure(col, weight=1, uniform="acat")
        kind_ = self._akind
        cur = (p.get(slot[kind_]) or {}).get("type")
        table = fx.anim_table(kind_)
        items = [(None, E("anim_none"))] + [(k, E("an_" + k)) for k, (cat, _e) in table.items()
                                              if self._acat in ("all", cat)]

        def pick(k):
            ed._push_undo()
            if k is None:
                p[slot[kind_]] = None
            else:
                d = float((p.get(slot[kind_]) or {}).get("d", fx.ANIM_DEF_D))
                p[slot[kind_]] = {"type": k, "d": d}      # новий словник (undo ділить старий)
                if kind_ == "combo":                      # Combo замінює In/Out і навпаки
                    p["ain"] = p["aout"] = None
                else:
                    p["acombo"] = None
            ed._prop_changed()
            self._rebuild()
            try:
                ed._anim_preview(p, kind_)
            except Exception:
                pass
        grid = tk.Frame(self.body, bg=P["bg2"])
        grid.pack(fill="x", padx=8, pady=(2, 4))
        per = 4
        for i, (k, lab) in enumerate(items):
            AnimTile(grid, P, kind_, k, lab, pick, k == cur).grid(row=i // per, column=i % per, padx=3, pady=3)
        if kind_ != "combo" and cur:
            dur = (p["e"] - p["s"]) / p.get("speed", 1.0)

            def set_d(v):
                a = p.get(slot[kind_])
                if a:
                    p[slot[kind_]] = dict(a, d=round(float(v), 2))
            self._slider(E("anim_dur"), 0.1, max(0.2, min(3.0, dur)),
                         lambda: float((p.get(slot[kind_]) or {}).get("d", fx.ANIM_DEF_D)),
                         set_d, self._sec, fx.ANIM_DEF_D)
        tk.Label(self.body, text=E("anim_hint"), bg=P["bg2"], fg=P["muted"], anchor="w", justify="left",
                 wraplength=self.W - 30, font=(P["font"], 8)).pack(fill="x", padx=14, pady=(4, 8))

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
        self._section(E("ins_font"))
        self._chips([(f, E("font_" + f)) for f in fx.fonts_available()], lambda: t.get("font") or "segoe",
                    self._setp(t, "font", str), per_row=4)
        self._section(E("ins_style"))
        self._chips([(s, E("st_" + s)) for s in fx.TEXT_STYLES], lambda: t.get("style", "outline"),
                    self._setp(t, "style", str), per_row=4)
        self._section(E("ins_stroke_col"))
        sw2 = Swatches(self.body, P, fx.TEXT_COLORS, lambda: t.get("stroke") or "#000000", None, self.W - 16)

        def set_stroke(c):
            ed._push_undo()
            t["stroke"] = c
            ed._prop_changed()
        sw2._setf = set_stroke
        sw2.pack(padx=4)
        self._section(E("ins_bg_col"))
        sw3 = Swatches(self.body, P, fx.TEXT_COLORS, lambda: t.get("bgc") or "#000000", None, self.W - 16)

        def set_bg(c):
            ed._push_undo()
            t["bgc"] = c
            if t.get("style") != "box":
                t["style"] = "box"
            ed._prop_changed()
            self.after_idle(lambda: self.sync(force=True))
        sw3._setf = set_bg
        sw3.pack(padx=4)
        self._section(E("ins_color"))
        sw = Swatches(self.body, P, fx.TEXT_COLORS, lambda: t.get("color", "#ffffff"), None, self.W - 16)

        self._row([("\U0001f5e3 " + E("ins_tts"), lambda: ed._tts(t))])

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
        for slot, table, key in (("tin", fx.TEXT_IN, "ta_in"), ("tout", fx.TEXT_OUT, "ta_out"),
                                 ("tloop", fx.TEXT_LOOP, "ta_loop")):
            self._section(E(key))

            def setter(v, slot=slot):
                if v is None:
                    t.pop(slot, None)
                else:
                    t[slot] = {"type": v, "d": float((t.get(slot) or {}).get("d", 0.6))}
            self._chips([(None, E("tr_none"))] + [(k, E("tan_" + k)) for k in table],
                        (lambda slot=slot: (t.get(slot) or {}).get("type")), setter, per_row=4)
            if slot != "tloop":
                def set_d(v, slot=slot):
                    if t.get(slot):
                        t[slot] = dict(t[slot], d=float(v))
                self._slider(E("ins_anim_d"), 0.1, 3.0, (lambda slot=slot: float((t.get(slot) or {}).get("d", 0.6))),
                             set_d, self._sec, 0.6)
        self._row([("📄 " + E("ins_dup"), ed._txt_dup), ("🗑", ed._txt_del)])

    def _build_snd(self, s):
        E, ed = self.E, self.ed
        self.head.config(text="🎵  " + E("ins_sound"))
        self.sub.config(text=s["name"] if len(s["name"]) <= 34 else s["name"][:32] + "…")
        self._section(E("ins_sound_fade"))
        self._vol_slider(s, False, s)
        self._fades(s, s["dur"])
        self._afx(s, can_speed=False)
        self._section(E("ins_beats"))
        self._row([("\U0001f941 " + E("ins_beats_auto"), lambda: ed._beats_detect(s)),
                   ("\uff0b " + E("ins_beat_mark"), lambda: ed._beat_mark(s)),
                   ("\u2715", lambda: ed._beats_clear(s))])
        self._row([("▶ " + E("ins_listen"), lambda: ed._preview_sound(s)),
                   ("🗑", lambda: ed._del_snd(ed.snds.index(s)) if s in ed.snds else None)])
