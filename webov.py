#!/usr/bin/env python3
"""
webov.py — вікно стиснення (оверлей над Discord) у веб-дизайні Moon.

Логіку не дублюємо: працює звичайний Tk-оверлей (discord_overlay.Overlay), але його вікно
сховане. Те, що він малює на своєму canvas (тексти, кнопки, чипи, кільце прогресу, поле
вводу), ~30 разів/с перетворюється на «сцену» (JSON) і показується у вікні Edge з живою
луною (webui/index.html#overlay). Кліки з веб-сторінки викликають ті самі команди кнопок.

Вікно Edge для оверлея запускається ЗАЗДАЛЕГІДЬ (сховане), тому після Ctrl+V воно
з'являється одразу, без очікування запуску браузера.
"""
import ctypes
import json
import os
import subprocess
import time

import dc_core

user32 = ctypes.windll.user32
TITLE = "DAC Overlay"
_st = {"proc": None, "hwnd": None, "cur": None, "launched": 0.0}

GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_CAPTION, WS_THICKFRAME, WS_SYSMENU = 0x00C00000, 0x00040000, 0x00080000
WS_MINIMIZEBOX, WS_MAXIMIZEBOX = 0x00020000, 0x00010000
WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = 0x00000080, 0x00040000
HWND_TOPMOST = -1
SWP_NOACTIVATE, SWP_SHOWWINDOW, SWP_FRAMECHANGED, SWP_HIDEWINDOW = 0x10, 0x40, 0x20, 0x80


def _find():
    from webui import _find_window
    h = _find_window(TITLE)
    if not h:
        # шукаємо і сховане вікно (IsWindowVisible = False)
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def cb(hwnd, _):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if buf.value == TITLE:
                    found.append(hwnd)
            return True
        user32.EnumWindows(cb, 0)
        h = found[0] if found else None
    return h


def _style(hwnd):
    """Без рамки й заголовка, без кнопки на панелі задач, завжди поверх."""
    h = ctypes.c_void_p(hwnd)
    user32.GetWindowLongW.restype = ctypes.c_long
    st = user32.GetWindowLongW(h, GWL_STYLE)
    st &= ~(WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
    user32.SetWindowLongW(h, GWL_STYLE, st)
    ex = user32.GetWindowLongW(h, GWL_EXSTYLE)
    user32.SetWindowLongW(h, GWL_EXSTYLE, (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
    try:      # заокруглені кути Windows 11 + темна рамка
        dwm = ctypes.windll.dwmapi
        for attr, val in ((33, 2), (20, 1), (34, 0x1a1a1a)):
            v = ctypes.c_int(val)
            dwm.DwmSetWindowAttribute(h, attr, ctypes.byref(v), ctypes.sizeof(v))
    except Exception:
        pass


def prelaunch(watcher):
    """Запускає приховане вікно оверлея (раз). False — Edge немає."""
    import webui
    if watcher.cfg.get("web_ui", True) is False:
        return False
    exe = webui.edge_path()
    if not exe:
        return False
    if _st["proc"] and _st["proc"].poll() is None and _find():
        return True
    bridge, port = webui.start(watcher)
    url = f"http://127.0.0.1:{port}/?t={bridge.token}#overlay"
    os.makedirs(webui.PROFILE + "_ov", exist_ok=True)
    args = [exe, f"--app={url}", f"--user-data-dir={webui.PROFILE}_ov", "--window-size=460,452",
            "--window-position=-32000,-32000", "--no-first-run", "--no-default-browser-check",
            "--disable-features=Translate,msEdgeSidebarV2,msUndersideButton,msHubApps",
            "--disable-sync", "--force-dark-mode"]
    si = subprocess.STARTUPINFO()
    si.dwFlags |= 1                # STARTF_USESHOWWINDOW
    si.wShowWindow = 0             # SW_HIDE: вікно створюється, але не показується (без кнопки на панелі)
    try:
        _st["proc"] = subprocess.Popen(args, creationflags=0x08000000, startupinfo=si)
        _st["launched"] = time.monotonic()
    except OSError as e:
        dc_core.dlog("webov launch fail " + repr(e))
        return False
    return True


def window(wait=6.0):
    """hwnd вікна оверлея (чекає, поки Edge його створить)."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < wait:
        h = _find()
        if h:
            if _st["hwnd"] != h:
                _st["hwnd"] = h
                _style(h)
                user32.ShowWindow(ctypes.c_void_p(h), 0)      # ховаємо до першого Ctrl+V
            return h
        time.sleep(0.05)
    return None


def place(x, y, w, h, show=True, activate=False):
    hw = _st.get("hwnd") or _find()
    if not hw:
        return
    if show:
        _style(hw)          # Edge міг повернути свій стиль — знову без рамки й без кнопки на панелі задач
    if show and user32.IsIconic(ctypes.c_void_p(hw)):
        user32.ShowWindow(ctypes.c_void_p(hw), 4)      # SW_SHOWNOACTIVATE — із згорнутого
    fl = SWP_FRAMECHANGED | (SWP_SHOWWINDOW if show else SWP_HIDEWINDOW)
    if not activate:
        fl |= SWP_NOACTIVATE
    user32.SetWindowPos(ctypes.c_void_p(hw), ctypes.c_void_p(HWND_TOPMOST), int(x), int(y), int(w), int(h), fl)


def hide():
    hw = _st.get("hwnd") or _find()
    if hw:
        user32.ShowWindow(ctypes.c_void_p(hw), 0)     # SW_HIDE


def is_own(hwnd):
    return bool(hwnd) and hwnd == _st.get("hwnd")


# ------------------------------------------------------------------ сцена --- #
SKIP = {"chip", "badge", "donering", "ring", "acbar", "card"}


def _font_info(c, item):
    f = c.itemcget(item, "font")
    try:
        act = c.tk.call("font", "actual", f)
        d = dict(zip(act[0::2], act[1::2]))
        fam, size = str(d.get("-family", "")), abs(int(d.get("-size", 10)))
        return fam, size, str(d.get("-weight", "normal")) == "bold", str(d.get("-slant", "roman")) == "italic"
    except Exception:
        return "", 10, False, False


def scene(ov):
    """Знімок поточного екрана оверлея для веб-сторінки."""
    c = ov.canvas
    out = {"H": ov.H, "W": ov.W, "screen": ov._screen, "texts": [], "buttons": [], "chips": [],
           "badge": getattr(ov, "_w_badge", None), "done": getattr(ov, "_w_done", None),
           "ring": None, "entry": None, "ac": getattr(ov, "_w_ac", None)}
    btn_tags = set(ov._btns.keys())
    for item in c.find_withtag("dyn"):
        tags = set(c.gettags(item))
        if c.type(item) != "text" or tags & SKIP or tags & btn_tags:
            continue
        txt = c.itemcget(item, "text")
        if not txt:
            continue
        x, y = c.coords(item)[:2]
        fam, size, bold, italic = _font_info(c, item)
        out["texts"].append({"x": round(x, 1), "y": round(y, 1), "t": txt, "fill": c.itemcget(item, "fill"),
                             "size": size, "bold": bold, "serif": italic or "Serif" in fam or "Cormorant" in fam,
                             "anchor": c.itemcget(item, "anchor"), "w": float(c.itemcget(item, "width") or 0)})
    for tag, b in ov._btns.items():
        out["buttons"].append({"id": tag, "t": b["text"], "cx": b["cx"], "cy": b["cy"], "w": b["w"],
                               "kind": b["kind"]})
    out["chips"] = list(getattr(ov, "_w_chips", []))
    if ov._screen == "progress" and getattr(ov, "_ring", None):
        r = ov._ring
        out["ring"] = {"cx": r["cx"], "cy": r["cy"], "R": r["R"], "pct": round(ov._pct_disp, 1),
                       "eta": getattr(ov, "_eta_txt", "")}
    e = getattr(ov, "mb_entry", None)
    if ov._screen == "input" and e is not None:
        try:
            out["entry"] = {"v": e.get(), "y": 214}
        except Exception:
            pass
    return out


class Mirror:
    """Тримає зв'язок одного оверлея з веб-вікном."""

    def __init__(self, ov, bridge):
        self.ov, self.b = ov, bridge
        self.last = None
        self.shown = False
        self.bridge_cb()
        self.tick()

    def bridge_cb(self):
        self.b.overlay = self

    def tick(self):
        ov = self.ov
        if ov._closed:
            return self.close()
        try:
            sc = scene(ov)
            js = json.dumps(sc, ensure_ascii=False, sort_keys=True)
            if js != self.last:
                self.last = js
                self.b.emit("ov", scene=sc)
            vis = getattr(ov, "_visible", True)       # Discord згорнули / перейшли в інше вікно
            if vis and (not self.shown or sc["H"] != getattr(self, "_h", None)):
                self._h = sc["H"]
                self.show()
            elif not vis and self.shown:
                hide()
                self.shown = False
        except Exception as e:
            dc_core.dlog("webov tick fail " + repr(e))
        ov.after(33, self.tick)

    def show(self):
        ov = self.ov
        if getattr(ov, "_visible", True) is False:
            return
        place(ov._x, ov._y, ov.W, ov.H + 2, show=True)
        self.shown = True

    def set_visible(self, on):
        if on:
            self.show()
        else:
            hide()
            self.shown = False

    def close(self):
        if getattr(self.b, "overlay", None) is self:
            self.b.overlay = None
            self.b.emit("ov", scene=None)
        hide()

    # ---- дії з веб-сторінки (викликаються в потоці Tk) ----
    def click(self, bid):
        b = self.ov._btns.get(bid)
        if b and b.get("cmd"):
            b["cmd"]()

    def chip(self, tag):
        if tag == "custmb":
            self.ov._custom_input()

    def esc(self):
        self.ov._esc()

    def entry(self, value, submit):
        e = getattr(self.ov, "mb_entry", None)
        if e is None:
            return
        try:
            e.delete(0, "end")
            e.insert(0, str(value)[:12])
        except Exception:
            return
        if submit and getattr(self.ov, "_entry_ok", None):
            self.ov._entry_ok()

    def drag(self, dx, dy):
        ov = self.ov
        ov._x += int(dx)
        ov._y += int(dy)
        place(ov._x, ov._y, ov.W, ov.H + 2, show=True)
