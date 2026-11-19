#!/usr/bin/env python3
"""
ui.py — спільна дизайн-система інтерфейсу (overlay, меню, пілюля, редактор).
Градієнти, заокруглені картки, перемикачі-тумблери, сегментовані кнопки, повзунок,
кругове кільце прогресу, плавна поява вікон і «рідні» заокруглені кути Windows 11.
Усе малюється на tk.Canvas — тільки стандартна бібліотека (tkinter + ctypes),
БЕЗ tkinter.font/PIL, щоб працювало онлайн і в старому .exe.
"""
import ctypes
import math

import tkinter as tk

import themes

FONT = themes.FONT


# --------------------------------------------------------------- кольори --- #
def _rgb(c):
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _hex(r, g, b):
    return "#%02x%02x%02x" % (max(0, min(255, int(r))), max(0, min(255, int(g))),
                              max(0, min(255, int(b))))


def mix(c1, c2, t):
    """Колір між c1 і c2 (t=0 -> c1, t=1 -> c2)."""
    try:
        a, b = _rgb(c1), _rgb(c2)
    except (ValueError, IndexError):
        return c1
    return _hex(*(a[i] + (b[i] - a[i]) * t for i in range(3)))


def lighten(c, t=0.15):
    return mix(c, "#ffffff", t)


def darken(c, t=0.15):
    return mix(c, "#000000", t)


def luminance(c):
    try:
        r, g, b = _rgb(c)
    except (ValueError, IndexError):
        return 0
    return 0.299 * r + 0.587 * g + 0.114 * b


def ink(bg):
    """Білий чи темний текст — для контрасту на будь-якому тлі."""
    return "#10121a" if luminance(bg) > 160 else "#ffffff"


def accent2(P):
    return P.get("accent2") or lighten(P["accent"], 0.3)


# ------------------------------------------------------- дизайн Moon --- #
def is_mono(P):
    return bool(P and P.get("mono"))


def _latin(text):
    return all(ord(ch) < 0x250 or not ch.isalpha() for ch in str(text))


def title_font(text, size, P=None):
    """Великі заголовки: Instrument Serif курсив (кирилиця — Cormorant курсив)."""
    if P is not None and not is_mono(P):
        return (FONT, size, "bold")
    if _latin(text):
        return (themes.SERIF_LAT, int(size * 1.45), "italic")
    return (themes.SERIF_CYR, int(size * 1.4), "italic")


def tag_font(size=9):
    """Дрібні підписи секцій ВЕЛИКИМИ ЛІТЕРАМИ: JetBrains Mono, жирність 600."""
    return (themes.MONO_FONT, size, "bold")


def tag_text(text):
    return str(text).upper()


_SKY = {}
SKY_FRAMES = 12


def sky_frames(widget, name="sky_head.png"):
    """Кадри фону «місяць + промені» (смужка PNG з assets/ -> SKY_FRAMES картинок).
    Порожній список — картинки немає (тоді просто без місяця)."""
    key = (name, str(widget.winfo_toplevel().tk))
    fr = _SKY.get(key)
    if fr is None:
        import os
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", name)
        fr = []
        try:
            st = tk.PhotoImage(master=widget, file=p)
            w, h = st.width() // SKY_FRAMES, st.height()
            for k in range(SKY_FRAMES):
                im = tk.PhotoImage(master=widget, width=w, height=h)
                im.tk.call(im, "copy", st, "-from", k * w, 0, (k + 1) * w, h)
                fr.append(im)
            del st
        except (tk.TclError, OSError, ZeroDivisionError):
            fr = []
        _SKY[key] = fr
    return fr


def sky(widget, name="sky_head.png"):
    fr = sky_frames(widget, name)
    return fr[0] if fr else None


def animate_sky(widget, frames, setter, ms=150):
    """Місяць ледь плаває, промені гойдаються: по колу міняємо кадри (лише зміна картинки —
    майже не навантажує). Зупиняється сам, коли віджет закрито."""
    if not frames:
        return
    st = {"k": 0}

    def tick():
        try:
            if not widget.winfo_exists():
                return
            st["k"] = (st["k"] + 1) % len(frames)
            setter(frames[st["k"]])
            widget.after(ms, tick)
        except tk.TclError:
            pass
    widget.after(ms, tick)


def glow_round(c, x1, y1, x2, y2, r, steps=((3, "#0f0f0f"), (6, "#0a0a0a"), (9, "#060606")), tags=()):
    """Імітація світіння навколо кнопки (білий 6–12% на чорному): кільця назовні."""
    for d, col in reversed(steps):
        round_rect(c, x1 - d, y1 - d, x2 + d, y2 + d, r + d, fill=col, outline="", tags=tags)


# ------------------------------------------------------------- геометрія --- #
def rr_pts(x1, y1, x2, y2, r):
    """Точки заокругленого прямокутника для create_polygon(..., smooth=True)."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


def round_rect(c, x1, y1, x2, y2, r, **kw):
    return c.create_polygon(rr_pts(x1, y1, x2, y2, r), smooth=True, **kw)


def grad_round_rect(c, x1, y1, x2, y2, r, c1, c2, tags=(), step=1, vertical=False):
    """Заокруглений прямокутник з ГРАДІЄНТОМ: тонкі лінії, обрізані по формі кутів."""
    r = max(0.0, min(r, (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    if vertical:
        y = y1
        while y < y2:
            t = (y - y1) / max(1.0, y2 - y1)
            dy = 0.0
            if y < y1 + r:
                dy = r - math.sqrt(max(0.0, r * r - (y1 + r - y) ** 2))
            elif y > y2 - r:
                dy = r - math.sqrt(max(0.0, r * r - (y - (y2 - r)) ** 2))
            c.create_line(x1 + dy, y + step / 2.0, x2 - dy, y + step / 2.0, fill=mix(c1, c2, t),
                          width=step, tags=tags)
            y += step
        return
    x = x1
    while x < x2:
        t = (x - x1) / max(1.0, x2 - x1)
        dx = 0.0
        if x < x1 + r:
            dx = r - math.sqrt(max(0.0, r * r - (x1 + r - x) ** 2))
        elif x > x2 - r:
            dx = r - math.sqrt(max(0.0, r * r - (x - (x2 - r)) ** 2))
        c.create_line(x + step / 2.0, y1 + dx, x + step / 2.0, y2 - dx, fill=mix(c1, c2, t),
                      width=step, tags=tags)
        x += step


def grad_ring(c, cx, cy, R, width, frac, c1, c2, track, tags=(), segs=72):
    """Кругове кільце прогресу з градієнтом (від 12-ї години за годинниковою)."""
    c.create_oval(cx - R, cy - R, cx + R, cy + R, outline=track, width=width, tags=tags)
    frac = max(0.0, min(1.0, frac))
    n = int(segs * frac)
    ext = 360.0 / segs
    for i in range(n):
        start = 90 - i * ext
        c.create_arc(cx - R, cy - R, cx + R, cy + R, start=start, extent=-(ext + 0.8),
                     style="arc", outline=mix(c1, c2, i / max(1, segs - 1)),
                     width=width, tags=tags)
    rem = frac * segs - n          # частковий останній сегмент — плавний рух
    if rem > 0.05 and n < segs:
        c.create_arc(cx - R, cy - R, cx + R, cy + R, start=90 - n * ext, extent=-ext * rem,
                     style="arc", outline=mix(c1, c2, n / max(1, segs - 1)),
                     width=width, tags=tags)


def measure(widget, text, size, bold=True):
    """Ширина тексту в px через Tcl `font measure` (без tkinter.font)."""
    try:
        return int(widget.tk.call("font", "measure",
                                  (FONT, size, "bold" if bold else "normal"), text))
    except Exception:
        return int(len(text) * size * 0.7)


def fit_size(widget, text, maxw, base, bold=True, minimum=8):
    for s in range(base, minimum, -1):
        if measure(widget, text, s, bold) <= maxw:
            return s
    return minimum


def ellipsize(widget, text, maxw, size, bold=False):
    if measure(widget, text, size, bold) <= maxw:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if measure(widget, text[:mid] + "…", size, bold) <= maxw:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + "…"


# ------------------------------------------------------- вікна Windows ---- #
def win_chrome(win, taskbar=True, rounded=True, dark=True):
    """Рамкове вікно (overrideredirect) у панелі завдань і Alt+Tab, з рідними
    заокругленими кутами й тінню Windows 11. Тихо нічого не робить на старих ОС."""
    try:
        win.update_idletasks()
        u32 = ctypes.windll.user32
        hwnd = u32.GetParent(win.winfo_id()) or win.winfo_id()
        if taskbar:
            GWL_EXSTYLE, WS_EX_APPWINDOW, WS_EX_TOOLWINDOW = -20, 0x00040000, 0x00000080
            style = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            u32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            # перепоказ, щоб Explorer помітив новий стиль
            win.withdraw()
            win.after(10, win.deiconify)
        dwm = ctypes.windll.dwmapi
        if rounded:   # DWMWA_WINDOW_CORNER_PREFERENCE=33, DWMWCP_ROUND=2
            v = ctypes.c_int(2)
            dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(v), ctypes.sizeof(v))
        if dark:      # DWMWA_USE_IMMERSIVE_DARK_MODE=20
            v = ctypes.c_int(1)
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(v), ctypes.sizeof(v))
    except Exception:
        pass


def round_corners(win):
    """Лише рідні заокруглені кути Win11 (для вікон з -transparentcolor не потрібно)."""
    win_chrome(win, taskbar=False, rounded=True, dark=False)


def fade_in(win, ms=160, target=1.0, on_done=None):
    """Плавна поява вікна (alpha 0 -> target)."""
    steps = max(1, ms // 16)

    def tick(i=1):
        try:
            win.attributes("-alpha", target * i / steps)
        except tk.TclError:
            return
        if i < steps:
            win.after(16, lambda: tick(i + 1))
        elif on_done:
            on_done()
    try:
        win.attributes("-alpha", 0.0)
    except tk.TclError:
        return
    win.after(10, tick)


def fade_out(win, ms=120, on_done=None):
    steps = max(1, ms // 16)
    try:
        a0 = float(win.attributes("-alpha"))
    except (tk.TclError, ValueError):
        a0 = 1.0

    def tick(i=1):
        try:
            win.attributes("-alpha", max(0.0, a0 * (1 - i / steps)))
        except tk.TclError:
            if on_done:
                on_done()
            return
        if i < steps:
            win.after(16, lambda: tick(i + 1))
        elif on_done:
            on_done()
    tick()


def ease_out(t):
    return 1 - (1 - t) ** 3


# ------------------------------------------------------------- віджети ---- #
class Button(tk.Canvas):
    """Кнопка-пігулка: градієнтна (primary), тихa (ghost) або червона (danger).
    Має .config(text=, state=) як tk.Button."""

    def __init__(self, parent, text, cmd, P, kind="primary", width=0, height=38,
                 size=10, icon=""):
        self.P, self._txt, self._cmd, self.kind = P, text, cmd, kind
        self._icon = icon
        self._h, self._fs, self._minw = height, size, width
        self._state, self._hover, self._down = "normal", False, False
        try:
            pbg = parent.cget("bg")
        except tk.TclError:
            pbg = P["bg"]
        super().__init__(parent, height=height, bg=pbg, highlightthickness=0, cursor="hand2",
                         takefocus=0)
        self._draw()
        self.bind("<Enter>", lambda e: self._set(hover=True))
        self.bind("<Leave>", lambda e: self._set(hover=False, down=False))
        self.bind("<ButtonPress-1>", lambda e: self._set(down=True))
        self.bind("<ButtonRelease-1>", self._release)

    def _label(self):
        return (self._icon + "  " + self._txt) if self._icon else self._txt

    def _width(self):
        if self._minw and self._minw > 0 and self.kind != "auto":
            return max(self._minw, measure(self, self._label(), self._fs) + 28)
        return measure(self, self._label(), self._fs) + (24 if self._h < 34 else 34)

    def _set(self, hover=None, down=None):
        if hover is not None:
            self._hover = hover
        if down is not None:
            self._down = down
        self._draw()

    def _release(self, e):
        was = self._down
        self._down = False
        self._draw()
        if was and self._state == "normal" and self._cmd and \
                0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self._cmd()

    def _draw(self):
        P = self.P
        w = self._width()
        tk.Canvas.configure(self, width=w)
        self.delete("all")
        h = self._h
        r = h / 2 - 1
        off = 1 if self._down else 0
        if self._state != "normal":
            round_rect(self, 1, 1, w - 1, h - 1, r, fill=P["dark"], outline="")
            fg = mix(P["muted"], P["dark"], 0.35)
        elif self.kind == "primary" and P.get("mono"):
            # головна: чорна, рамка 1 px чисто біла, обідок 3 px і біле світіння навколо
            g = ((3, "#141414"), (6, "#0c0c0c"), (9, "#070707")) if self._hover else                 ((3, "#0f0f0f"), (5, "#090909"), (7, "#050505"))
            m = 7
            glow_round(self, m, m + off, w - m, h - m + off, r - m, g)
            round_rect(self, m, m + off, w - m, h - m + off, r - m, fill="#000000", outline="#ffffff")
            fg = "#ffffff"
        elif self.kind == "primary":
            a1, a2 = P["accent"], accent2(P)
            if self._hover:
                a1, a2 = lighten(a1, 0.12), lighten(a2, 0.12)
            if self._down:
                a1, a2 = darken(a1, 0.1), darken(a2, 0.1)
            grad_round_rect(self, 1, 1 + off, w - 1, h - 1, r, a1, a2)
            fg = ink(mix(a1, a2, 0.5))
        elif self.kind == "danger":
            c = lighten(P["red"], 0.1) if self._hover else P["red"]
            round_rect(self, 1, 1 + off, w - 1, h - 1, r, fill=c, outline="")
            fg = "#ffffff"
        elif self.kind == "success":
            c = lighten(P["green"], 0.1) if self._hover else P["green"]
            round_rect(self, 1, 1 + off, w - 1, h - 1, r, fill=c, outline="")
            fg = ink(c)
        elif P.get("mono"):  # звичайна кнопка Moon: радіус 12, фон білий 6%, рамка білий 24%
            up = 1 if self._hover and not self._down else 0     # при наведенні «піднімається»
            round_rect(self, 1, 1 + off - up, w - 1, h - 1 + off - up, min(12, r), 
                       fill="#151515" if self._hover else P.get("btn_fill", "#0f0f0f"),
                       outline="#5a5a5a" if self._hover else P.get("btn_line", "#3d3d3d"))
            fg = P["text"]
            off -= up
        else:  # ghost
            base = P.get("card", P["panel"])
            c = mix(base, P["accent"], 0.18) if self._hover else base
            round_rect(self, 1, 1 + off, w - 1, h - 1, r, fill=c,
                       outline=mix(base, P["text"], 0.12))
            fg = P["text"]
        self.create_text(w / 2, h / 2 + off, text=self._label(), fill=fg,
                         font=(FONT, self._fs, "bold"))

    def config(self, cnf=None, **kw):
        redraw = False
        if "text" in kw:
            t = kw.pop("text")
            if t != self._txt:
                self._txt, redraw = t, True
        if "state" in kw:
            st = str(kw.pop("state"))
            if st != self._state:
                self._state, redraw = st, True
                tk.Canvas.configure(self, cursor="hand2" if st == "normal" else "")
        if "command" in kw:
            self._cmd = kw.pop("command")
        for k in ("bg", "fg", "activebackground", "activeforeground"):
            kw.pop(k, None)
        if kw or cnf:
            tk.Canvas.configure(self, cnf, **kw)
        if redraw:
            self._draw()

    configure = config

    def cget(self, key):
        if key == "text":
            return self._txt
        if key == "state":
            return self._state
        return tk.Canvas.cget(self, key)


class Toggle(tk.Canvas):
    """Тумблер-перемикач (як у Discord/iOS) з плавною анімацією. Прив'язаний до BooleanVar."""
    W, H = 44, 24

    def __init__(self, parent, var, P, command=None):
        self.P, self.var, self.command = P, var, command
        try:
            pbg = parent.cget("bg")
        except tk.TclError:
            pbg = P["bg"]
        super().__init__(parent, width=self.W, height=self.H, bg=pbg,
                         highlightthickness=0, cursor="hand2", takefocus=0)
        self._pos = 1.0 if self._val() else 0.0
        self._anim = None
        self._draw()
        self.bind("<Button-1>", self._click)
        self._trace = var.trace_add("write", lambda *a: self._animate())
        self.bind("<Destroy>", self._unbind)

    def _unbind(self, _e):
        try:
            self.var.trace_remove("write", self._trace)
        except Exception:
            pass

    def _val(self):
        try:
            return bool(self.var.get())
        except tk.TclError:
            return False

    def _click(self, _e=None):
        self.var.set(not self._val())
        if self.command:
            self.command()

    def _animate(self):
        target = 1.0 if self._val() else 0.0
        if self._anim:
            try:
                self.after_cancel(self._anim)
            except Exception:
                pass

        def step():
            d = target - self._pos
            if abs(d) < 0.04:
                self._pos = target
                self._anim = None
                self._draw()
                return
            self._pos += d * 0.35
            self._draw()
            self._anim = self.after(14, step)
        try:
            step()
        except tk.TclError:
            pass

    def _draw(self):
        P = self.P
        self.delete("all")
        off = mix(P["dark"], P["muted"], 0.35)
        t = self._pos
        if P.get("mono"):   # біла доріжка з чорною кнопкою (увімкнено) / темна з сірою (вимкнено)
            tr = mix("#262626", "#f4f4f4", t)
            round_rect(self, 1, 1, self.W - 1, self.H - 1, self.H / 2 - 1, fill=tr,
                       outline=mix("#3a3a3a", "#f4f4f4", t))
            R = self.H / 2 - 4
            cx = 4 + R + t * (self.W - 8 - 2 * R)
            cy = self.H / 2
            self.create_oval(cx - R, cy - R, cx + R, cy + R, fill=mix("#9a9a9a", "#050505", t), outline="")
            return
        if t > 0.5:
            grad_round_rect(self, 1, 1, self.W - 1, self.H - 1, self.H / 2 - 1,
                            mix(off, P["accent"], t), mix(off, accent2(P), t))
        else:
            round_rect(self, 1, 1, self.W - 1, self.H - 1, self.H / 2 - 1,
                       fill=mix(off, P["accent"], t), outline="")
        R = self.H / 2 - 4
        cx = 4 + R + t * (self.W - 8 - 2 * R)
        cy = self.H / 2
        self.create_oval(cx - R, cy - R, cx + R, cy + R, fill="#ffffff", outline="")


class Segmented(tk.Canvas):
    """Сегментований перемикач: [ 20 МБ | 25 МБ | 50 МБ ] з плаваючою підсвіткою."""

    def __init__(self, parent, options, var, P, height=40, size=10, sub=None, command=None,
                 min_seg=0):
        """options = [(value, label), ...]; sub = {value: малий підпис}."""
        self.P, self.options, self.var, self.sub = P, options, var, sub or {}
        self.command = command
        self._h, self._fs = (height + (14 if sub else 0)), size
        try:
            pbg = parent.cget("bg")
        except tk.TclError:
            pbg = P["bg"]
        self._segw = max(min_seg, max(measure(parent, str(lbl), size) for _, lbl in options) + 34)
        w = self._segw * len(options) + 8
        super().__init__(parent, width=w, height=self._h, bg=pbg, highlightthickness=0,
                         cursor="hand2", takefocus=0)
        self._hover = None
        self._pos = float(self._index())
        self._anim = None
        self._draw()
        self.bind("<Button-1>", self._click)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self._sethover(None))
        self._trace = var.trace_add("write", lambda *a: self._animate())
        self.bind("<Destroy>", self._unbind)

    def _unbind(self, _e):
        try:
            self.var.trace_remove("write", self._trace)
        except Exception:
            pass

    def _index(self):
        try:
            v = self.var.get()
        except tk.TclError:
            return 0
        for i, (val, _l) in enumerate(self.options):
            if val == v:
                return i
        return -1

    def _seg_at(self, x):
        i = int((x - 4) // self._segw)
        return i if 0 <= i < len(self.options) else None

    def _motion(self, e):
        self._sethover(self._seg_at(e.x))

    def _sethover(self, i):
        if i != self._hover:
            self._hover = i
            self._draw()

    def _click(self, e):
        i = self._seg_at(e.x)
        if i is not None:
            self.var.set(self.options[i][0])
            if self.command:
                self.command()

    def _animate(self):
        target = float(self._index())
        if target < 0:
            self._pos = target
            return self._draw()
        if self._pos < 0:
            self._pos = target
        if self._anim:
            try:
                self.after_cancel(self._anim)
            except Exception:
                pass

        def step():
            d = target - self._pos
            if abs(d) < 0.02:
                self._pos = target
                self._anim = None
                self._draw()
                return
            self._pos += d * 0.3
            self._draw()
            self._anim = self.after(14, step)
        try:
            step()
        except tk.TclError:
            pass

    def _draw(self):
        P = self.P
        self.delete("all")
        w = self._segw * len(self.options) + 8
        h = self._h
        round_rect(self, 0, 0, w, h, 12, fill=P["dark"], outline="")
        if self._pos >= 0:
            x1 = 4 + self._pos * self._segw
            grad_round_rect(self, x1, 4, x1 + self._segw, h - 4, 9, P["accent"], accent2(P))
        sel = self._index()
        for i, (val, lbl) in enumerate(self.options):
            cx = 4 + i * self._segw + self._segw / 2
            on = i == sel
            if not on and i == self._hover:
                round_rect(self, 4 + i * self._segw + 2, 6, 4 + (i + 1) * self._segw - 2, h - 6, 8,
                           fill=mix(P["dark"], P["text"], 0.07), outline="")
            fg = ink(P["accent"]) if on else P["text"]
            s = self.sub.get(val)
            if s:
                self.create_text(cx, h / 2 - 7, text=str(lbl), fill=fg,
                                 font=(FONT, self._fs, "bold"))
                self.create_text(cx, h / 2 + 10, text=s, fill=(fg if on else P["muted"]),
                                 font=(FONT, 8))
            else:
                self.create_text(cx, h / 2, text=str(lbl), fill=fg, font=(FONT, self._fs, "bold"))


class Slider(tk.Canvas):
    """Повзунок з градієнтною доріжкою і кроком (напр. аудіо 0…320 kbps по 32)."""

    def __init__(self, parent, var, P, lo, hi, step=1, width=260, fmt=str, command=None):
        self.P, self.var, self.lo, self.hi, self.stepv = P, var, lo, hi, step
        self.fmt, self.command, self._len = fmt, command, width
        try:
            pbg = parent.cget("bg")
        except tk.TclError:
            pbg = P["bg"]
        super().__init__(parent, width=width + 90, height=30, bg=pbg, highlightthickness=0,
                         cursor="hand2", takefocus=0)
        self._draw()
        self.bind("<Button-1>", self._drag)
        self.bind("<B1-Motion>", self._drag)
        self._trace = var.trace_add("write", lambda *a: self._draw())
        self.bind("<Destroy>", self._unbind)

    def _unbind(self, _e):
        try:
            self.var.trace_remove("write", self._trace)
        except Exception:
            pass

    def _val(self):
        try:
            return max(self.lo, min(self.hi, float(self.var.get())))
        except (tk.TclError, ValueError):
            return self.lo

    def _drag(self, e):
        t = max(0.0, min(1.0, (e.x - 10) / float(self._len - 20)))
        v = self.lo + t * (self.hi - self.lo)
        v = int(round(v / self.stepv) * self.stepv)
        v = max(self.lo, min(self.hi, v))
        try:
            cur = int(self.var.get())
        except (tk.TclError, ValueError):
            cur = None
        if v != cur:
            self.var.set(v)
            if self.command:
                self.command()

    def _draw(self):
        P = self.P
        try:
            self.delete("all")
        except tk.TclError:
            return
        y = 15
        x1, x2 = 10, self._len - 10
        t = (self._val() - self.lo) / float(max(1, self.hi - self.lo))
        xv = x1 + t * (x2 - x1)
        if P.get("mono"):   # доріжка 2 px: пройдене біле, решта білий 20%; ручка 15 px з обідком і світінням
            self.create_line(x1, y, x2, y, fill="#333333", width=2, capstyle="round")
            if xv > x1 + 1:
                self.create_line(x1, y, xv, y, fill="#ffffff", width=2, capstyle="round")
            for rr, col in ((14, "#0b0b0b"), (12, "#1c1c1c"), (10, "#3a3a3a")):
                self.create_oval(xv - rr, y - rr, xv + rr, y + rr, fill=col, outline="")
            self.create_oval(xv - 7.5, y - 7.5, xv + 7.5, y + 7.5, fill="#ffffff", outline="")
            self.create_text(x2 + 18, y, anchor="w", text=self.fmt(int(self._val())),
                             fill=P["text"], font=(themes.MONO_FONT, 10, "bold"))
            return
        round_rect(self, x1, y - 3, x2, y + 3, 3, fill=P["dark"], outline="")
        if xv > x1 + 4:
            grad_round_rect(self, x1, y - 3, xv, y + 3, 3, P["accent"], accent2(P), step=1)
        self.create_oval(xv - 9, y - 9, xv + 9, y + 9, fill="#ffffff",
                         outline=mix(P["accent"], "#ffffff", 0.3), width=2)
        self.create_text(x2 + 16, y, anchor="w", text=self.fmt(int(self._val())),
                         fill=P["text"], font=(FONT, 10, "bold"))


class Card(tk.Frame):
    """Заокруглена картка: Canvas-підложка + внутрішній Frame (.body) для вмісту."""

    def __init__(self, parent, P, pad=16, radius=14, fill=None, outline=None):
        try:
            pbg = parent.cget("bg")
        except tk.TclError:
            pbg = P["bg"]
        super().__init__(parent, bg=pbg)
        self.P, self.pad, self.radius = P, pad, (22 if P.get("mono") else radius)
        self.fill = fill or P.get("card", P["panel"])
        self.outline = outline if outline is not None else (
            P.get("line") or mix(self.fill, P["text"], 0.07))
        self.cv = tk.Canvas(self, bg=pbg, highlightthickness=0, height=10)
        self.cv.pack(fill="both", expand=True)
        self.body = tk.Frame(self.cv, bg=self.fill)
        self._win = self.cv.create_window(pad, pad, window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._fit)
        self.cv.bind("<Configure>", self._fit)

    def _fit(self, _e=None):
        try:
            bw = self.cv.winfo_width()
            bh = self.body.winfo_reqheight() + 2 * self.pad
            self.cv.itemconfigure(self._win, width=max(10, bw - 2 * self.pad))
            if int(self.cv.cget("height")) != bh:
                self.cv.configure(height=bh)
            self.cv.delete("bgshape")
            round_rect(self.cv, 1, 1, bw - 1, bh - 1, self.radius, fill=self.fill,
                       outline=self.outline, tags="bgshape")
            self.cv.tag_lower("bgshape")
        except tk.TclError:
            pass


class ScrollArea(tk.Frame):
    """Вертикально прокручувана область (колесо миші) без системного скролбара:
    тонкий власний індикатор справа з'являється, лише коли є що крутити."""

    def __init__(self, parent, bg):
        super().__init__(parent, bg=bg)
        self.cv = tk.Canvas(self, bg=bg, highlightthickness=0)
        self.cv.pack(side="left", fill="both", expand=True)
        self.bar = tk.Canvas(self, bg=bg, width=6, highlightthickness=0)
        self.bar.pack(side="right", fill="y", padx=(0, 3))
        self.inner = tk.Frame(self.cv, bg=bg)
        self._win = self.cv.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._update)
        self.cv.bind("<Configure>", self._update)
        self._bg = bg
        self.bind_all_wheel()

    def bind_all_wheel(self):
        def wheel(e):
            try:
                w = self.winfo_containing(e.x_root, e.y_root)
            except (tk.TclError, KeyError):
                return
            while w is not None:
                if w is self:
                    break
                w = getattr(w, "master", None)
            if w is None:
                return
            if self.inner.winfo_reqheight() > self.cv.winfo_height():
                self.cv.yview_scroll(int(-e.delta / 120) * 3, "units")
                self._draw_bar()
        self._wheel_id = self.cv.bind_all("<MouseWheel>", wheel, add="+")

    def destroy(self):
        try:
            self.cv.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass
        super().destroy()

    def _update(self, _e=None):
        try:
            self.cv.itemconfigure(self._win, width=self.cv.winfo_width())
            self.cv.configure(scrollregion=(0, 0, self.cv.winfo_width(),
                                            self.inner.winfo_reqheight()))
            self._draw_bar()
        except tk.TclError:
            pass

    def _draw_bar(self):
        try:
            self.bar.delete("all")
            total = self.inner.winfo_reqheight()
            vis = self.cv.winfo_height()
            if total <= vis + 2:
                return
            f0, f1 = self.cv.yview()
            h = self.bar.winfo_height()
            round_rect(self.bar, 1, f0 * h + 2, 5, f1 * h - 2, 2,
                       fill=mix(self._bg, "#ffffff", 0.18), outline="")
        except tk.TclError:
            pass


_LOGO_CACHE = {}


def logo(c, x, y, s, P=None, tags=()):
    """Значок програми — ТОЙ САМИЙ, що в треї/на ярлику (appicon: синій заокруглений
    квадрат зі стрілкою в «диск»), просто потрібного розміру. P лишено для сумісності."""
    s = int(s)
    if is_mono(P):          # Moon: чорний квадрат з білою рамкою і білою стрілкою в «лоток»
        ids = [round_rect(c, x, y, x + s, y + s, s * 0.28, fill="#000000", outline="#f5f5f2",
                          width=max(1, s / 28), tags=tags)]
        lw = max(1.5, s / 13)
        cx = x + s / 2
        ids.append(c.create_line(cx, y + s * .22, cx, y + s * .6, fill="#f5f5f2", width=lw,
                                 capstyle="round", tags=tags))
        ids.append(c.create_line(cx - s * .17, y + s * .45, cx, y + s * .62, cx + s * .17, y + s * .45,
                                 fill="#f5f5f2", width=lw, capstyle="round", joinstyle="round", tags=tags))
        ids.append(c.create_line(x + s * .25, y + s * .74, x + s * .75, y + s * .74, fill="#f5f5f2",
                                 width=lw, capstyle="round", tags=tags))
        return ids[0]
    img = _LOGO_CACHE.get(s)
    if img is None:
        try:
            import base64
            import appicon
            img = tk.PhotoImage(data=base64.b64encode(appicon._png_bytes(s)))
        except Exception:
            return None
        _LOGO_CACHE[s] = img
    return c.create_image(x, y, image=img, anchor="nw", tags=tags)
