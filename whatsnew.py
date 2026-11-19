#!/usr/bin/env python3
"""
whatsnew.py — вікно «Що нового», яке програма показує ОДИН раз після оновлення.
Анімація: проявлення вікна, конфеті, значок «вистрибує» з хвилями навколо,
заголовок проявляється, пункти змін по черзі виїжджають справа. Кнопки:
«Детальніше на сайті» (сторінка релізу на GitHub), «Подивитись у програмі»
(вкладка «Що нового» в меню) і «Показати» біля кожного пункту (відкриває місце
в меню, де ця зміна). Лише stdlib (tkinter + random/time — є в старому exe).
"""
import math
import random
import time

import tkinter as tk

import changelog
import i18n
import monetize
import themes
import ui

KEY = "#010203"          # прозорий колір кутів вікна
F = themes.FONT


class WhatsNew(tk.Toplevel):
    W = 560
    ROW = 64

    def __init__(self, master, lang, theme, on_open_tab=None, entry=None, since=None):
        """since — версія, З ЯКОЇ оновились: показуємо зміни всіх версій після неї."""
        super().__init__(master)
        self.lang, self.P = lang, themes.palette(theme)
        self.on_open_tab = on_open_tab
        self.entries = [entry] if entry else (changelog.since(since) if since else changelog.CHANGES[:1])
        self.since = since if len(self.entries) > 1 else None
        self.entry = self.entries[0]
        self.items = []
        for e in self.entries:
            for icon, title, desc, tab in changelog.items(e, lang):
                if len(self.entries) > 1:
                    title = f"{title}  · v{e['v']}"
                self.items.append((icon, title, desc, tab))
        self.H = 236 + len(self.items) * self.ROW + 96
        self._closed = False
        self._t0 = time.monotonic()
        self._rng = random.Random(7)

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        self.configure(bg=KEY)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.H = min(self.H, sh - 60)
        self._x, self._y = (sw - self.W) // 2, max(10, (sh - self.H) // 2 - 10)
        self.geometry(f"{self.W}x{self.H}+{self._x}+{self._y + 26}")
        self.c = tk.Canvas(self, width=self.W, height=self.H, bg=KEY, highlightthickness=0)
        self.c.pack()
        # висота кожного пункту — під його текст (довгий опис на 3+ рядки не вилазить за картку)
        self._lay = self._measure_rows()
        H = 236 + sum(h for h in self._lay) + (self.ROW - 54) * len(self._lay) + 96
        full, hidden = list(self.items), 0
        while H > sh - 60 and len(full) - hidden > 1:   # не влазить в екран -> решта у вкладці
            hidden += 1
            self.items = full[:len(full) - hidden] + [("➕", self.T("wn_more", n=hidden),
                                                      self.T("wn_more_d"), "whatsnew")]
            self._lay = self._measure_rows()
            H = 236 + sum(self._lay) + (self.ROW - 54) * len(self._lay) + 96
        self.H = min(H, sh - 60)
        self._y = max(10, (sh - self.H) // 2 - 10)
        self.geometry(f"{self.W}x{self.H}+{self._x}+{self._y + 26}")
        self.c.config(height=self.H)
        self.bind("<Escape>", lambda e: self.close())

        self._card()
        self._header()
        self._rows = []
        self._confetti = []
        self._spawn_confetti(90)
        self._ripples = []
        self._buttons_shown = False
        self.attributes("-alpha", 0.0)
        self._tick()

    def T(self, key, **kw):
        return i18n.tr(self.lang, key, **kw)

    # ------------------------------------------------------------ статика -- #
    def _card(self):
        c, P, W, H = self.c, self.P, self.W, self.H
        for i, t in ((6, 0.55), (3, 0.35)):
            ui.round_rect(c, 2 + i - 2, 2 + i, W - i, H - 2 + i - 6, 28,
                          fill=ui.darken(P["bg"], t), outline="")
        ui.round_rect(c, 2, 2, W - 4, H - 8, 28, fill=P["bg"],
                      outline=ui.mix(P["bg"], P["text"], 0.10), tags="drag")
        sky = ui.sky(c, "sky_card_wide.png") if ui.is_mono(P) else None
        if sky:
            c.create_image(W - 2, 0, image=sky, anchor="ne", tags=("drag", "skyimg"))
            ui.animate_sky(c, ui.sky_frames(c, "sky_card_wide.png"),
                           lambda im: c.itemconfigure("skyimg", image=im))
        # м'яке кольорове сяйво зверху
        glow = ui.mix(P["accent"], ui.accent2(P), 0.5)
        for i in range(12 if not sky else 0, 0, -1):
            t = i / 12.0
            rx, ry = 200 * t + 30, 110 * t + 20
            c.create_oval(W / 2 - rx, 70 - ry, W / 2 + rx, 70 + ry, outline="",
                          fill=ui.mix(P["bg"], glow, 0.16 * (1 - t) ** 1.4 + 0.01), tags="drag")
        c.create_rectangle(0, 0, W, 2, fill=KEY, outline="")
        if not sky:
            ui.grad_round_rect(c, 30, 3, W - 32, 7, 2, P["accent"], ui.accent2(P))
        # хрестик
        cx, cy = W - 34, 30
        c.create_oval(cx - 14, cy - 14, cx + 14, cy + 14, fill=P["bg"], outline="", tags=("x", "xbg"))
        c.create_text(cx, cy, text="✕", fill=P["muted"], font=(F, 10, "bold"), tags=("x", "xfg"))
        c.tag_bind("x", "<Enter>", lambda e: (c.itemconfig("xbg", fill=P["red"]),
                                              c.itemconfig("xfg", fill="#ffffff")))
        c.tag_bind("x", "<Leave>", lambda e: (c.itemconfig("xbg", fill=P["bg"]),
                                              c.itemconfig("xfg", fill=P["muted"])))
        c.tag_bind("x", "<Button-1>", lambda e: self.close())
        c.tag_bind("drag", "<Button-1>", self._drag_start)
        c.tag_bind("drag", "<B1-Motion>", self._drag)

    def _header(self):
        P, c = self.P, self.c
        d, t = changelog.fmt_date(self.entry["date"])
        if self.since:
            title = self.T("wn_title_from", a=self.since, v=self.entry["v"])
            sub = self.T("wn_sub_many", n=len(self.entries))
        else:
            title, sub = self.T("wn_title", v=self.entry["v"]), self.T("wn_sub", d=d, t=t)
        self._title = c.create_text(self.W / 2, 160, text=title, fill=P["bg"],
                                    font=ui.title_font(title, 19) if ui.is_mono(P) else (F, 19, "bold"))
        self._sub = c.create_text(self.W / 2, 190, text=sub,
                                  fill=P["bg"], font=(F, 10))

    # --------------------------------------------------------- анімація --- #
    def _spawn_confetti(self, n):
        P = self.P
        cols = [P["accent"], ui.accent2(P), P["green"], P["warn"], P["red"], "#ffffff"]
        for _ in range(n):
            x = self._rng.uniform(20, self.W - 20)
            y = self._rng.uniform(-self.H * 0.6, -10)
            w = self._rng.uniform(4, 9)
            h = self._rng.uniform(3, 6)
            col = self._rng.choice(cols)
            shape = self._rng.random()
            if shape < 0.35:
                it = self.c.create_oval(x, y, x + w, y + w, fill=col, outline="")
            else:
                it = self.c.create_rectangle(x, y, x + w, y + h, fill=col, outline="")
            self._confetti.append({"id": it, "vx": self._rng.uniform(-1.2, 1.2),
                                   "vy": self._rng.uniform(2.5, 5.5),
                                   "sway": self._rng.uniform(0, 6.28), "w": w, "h": h})

    def _tick(self):
        if self._closed:
            return
        ms = (time.monotonic() - self._t0) * 1000.0
        try:
            self._frame(ms)
        except tk.TclError:
            return
        self.after(16, self._tick)

    def _frame(self, ms):
        P, c = self.P, self.c
        # 1) поява вікна: проявлення + виїзд знизу
        k = min(1.0, ms / 260.0)
        e = ui.ease_out(k)
        self.attributes("-alpha", e)
        if k < 1.0:
            self.geometry(f"+{self._x}+{int(self._y + 26 * (1 - e))}")
        # 2) значок «вистрибує» (0.3 -> 1.12 -> 1.0) + хвилі навколо
        cx, cy = self.W / 2, 82
        kp = max(0.0, min(1.0, (ms - 120) / 520.0))
        if kp < 1.0 or not getattr(self, "_logo_done", False):
            if kp < 0.7:
                sc = 0.3 + 0.82 * ui.ease_out(kp / 0.7)
            else:
                sc = 1.12 - 0.12 * ui.ease_out((kp - 0.7) / 0.3)
            size = max(8, int(round(68 * sc / 2) * 2))
            c.delete("logo")
            if kp > 0:
                ui.logo(c, cx - size / 2, cy - size / 2, size, P, tags="logo")
            self._logo_done = kp >= 1.0
        if ms > 300 and (not self._ripples or ms - self._ripples[-1]["t"] > 1100):
            self._ripples.append({"t": ms, "id": None})
        for r in list(self._ripples):
            age = (ms - r["t"]) / 1600.0
            if r["id"]:
                c.delete(r["id"])
            if age >= 1:
                self._ripples.remove(r)
                continue
            rad = 38 + 34 * ui.ease_out(age)
            col = ui.mix(ui.mix(P["accent"], ui.accent2(P), age), P["bg"], age)
            r["id"] = c.create_oval(cx - rad, cy - rad, cx + rad, cy + rad, outline=col,
                                    width=2)
            c.tag_lower(r["id"], self._title)   # хвилі — під текстом і значком
        # 3) заголовок і підзаголовок проявляються
        kt = max(0.0, min(1.0, (ms - 380) / 380.0))
        c.itemconfig(self._title, fill=ui.mix(P["bg"], P["text"], ui.ease_out(kt)))
        c.coords(self._title, self.W / 2, 160 + 10 * (1 - ui.ease_out(kt)))
        ks = max(0.0, min(1.0, (ms - 520) / 380.0))
        c.itemconfig(self._sub, fill=ui.mix(P["bg"], P["muted"], ui.ease_out(ks)))
        # 4) пункти змін по черзі виїжджають справа
        for i, it in enumerate(self.items):
            t0 = 700 + i * 140
            if ms < t0:
                continue
            if i >= len(self._rows):
                self._rows.append(self._make_row(i, it))
            kr = min(1.0, (ms - t0) / 360.0)
            self._place_row(self._rows[i], ui.ease_out(kr))
        # 5) кнопки — коли всі пункти на місці
        if not self._buttons_shown and ms > 700 + len(self.items) * 140 + 200:
            self._show_buttons()
        # 6) конфеті
        for p in list(self._confetti):
            p["vy"] = min(7.0, p["vy"] + 0.06)
            p["sway"] += 0.12
            dx = p["vx"] + 0.9 * math.sin(p["sway"])
            c.move(p["id"], dx, p["vy"])
            x1, y1, x2, y2 = c.coords(p["id"])
            if y1 > self.H:
                c.delete(p["id"])
                self._confetti.remove(p)

    # ---------------------------------------------------------- пункти --- #
    def _text_w(self, tab):
        return self.W - 98 - (178 if tab else 54)

    def _measure_rows(self):
        """Висота картки кожного пункту за реальним розміром тексту (мін. 54)."""
        out = []
        for icon, title, desc, tab in self.items:
            w = self._text_w(tab)
            a = self.c.create_text(0, 0, text=title, anchor="nw", font=(F, 11, "bold"), width=w)
            b = self.c.create_text(0, 0, text=desc, anchor="nw", font=(F, 9), width=w)
            ha = self.c.bbox(a)[3] - self.c.bbox(a)[1]
            hb = self.c.bbox(b)[3] - self.c.bbox(b)[1]
            self.c.delete(a, b)
            out.append(max(54, ha + hb + 20))
        return out

    def _row_top(self, i):
        return 236 + sum(self._lay[:i]) + (self.ROW - 54) * i + 6 - 27

    def _make_row(self, i, it):
        P, c = self.P, self.c
        icon, title, desc, tab = it
        top = self._row_top(i)
        h = self._lay[i]
        y = top + h / 2
        tag = f"row{i}"
        bg = ui.mix(P["bg"], P["text"], 0.045)
        row = {"y": y, "tag": tag, "bg": bg, "tab": tab, "btn": None,
               "bgid": ui.round_rect(c, 30, top, self.W - 32, top + h, 16, fill=P["bg"],
                                     outline="", tags=tag)}
        row["ring"] = c.create_oval(48, y - 18, 84, y + 18, fill=P["bg"], outline=P["bg"], width=2,
                                    tags=tag)
        row["icon"] = c.create_text(66, y, text=icon, font=(F, 14), fill=P["bg"], tags=tag)
        wtxt = self._text_w(tab)
        row["title"] = c.create_text(98, top + 9, text=title, anchor="nw", fill=P["bg"],
                                     font=(F, 11, "bold"), width=wtxt, tags=tag)
        tb = c.bbox(row["title"])
        row["desc"] = c.create_text(98, tb[3] + 1, text=desc, anchor="nw", fill=P["bg"],
                                    font=(F, 9), width=wtxt, tags=tag)
        row["x"] = 0.0
        return row

    def _place_row(self, row, k):
        P, c = self.P, self.c
        dx = 40 * (1 - k)
        if abs(dx - row["x"]) > 0.01:
            c.move(row["tag"], dx - row["x"], 0)
            if row["btn"]:
                c.move(row["btn"], dx - row["x"], 0)
            row["x"] = dx
        c.itemconfig(row["bgid"], fill=ui.mix(P["bg"], row["bg"], k))
        acc = ui.mix(P["accent"], ui.accent2(P), (row["y"] - 236) / max(1, self.H - 330))
        c.itemconfig(row["ring"], outline=ui.mix(P["bg"], acc, k),
                     fill=ui.mix(P["bg"], ui.mix(P["panel"], acc, 0.18), k))
        c.itemconfig(row["icon"], fill=ui.mix(P["bg"], P["text"], k))
        c.itemconfig(row["title"], fill=ui.mix(P["bg"], P["text"], k))
        c.itemconfig(row["desc"], fill=ui.mix(P["bg"], P["muted"], k))
        if k >= 1.0 and row["tab"] and not row["btn"]:
            b = ui.Button(self.c, self.T("wn_show"), lambda t=row["tab"]: self._open(t), P,
                          kind="ghost", height=28, size=9)
            b.configure(bg=row["bg"])
            b._draw()
            row["btn"] = c.create_window(self.W - 46, row["y"], window=b, anchor="e")

    def _show_buttons(self):
        self._buttons_shown = True
        P = self.P
        y = self.H - 50
        fr = tk.Frame(self.c, bg=P["bg"])
        ui.Button(fr, self.T("wn_site"), lambda: (monetize.open_url(changelog.release_url(self.entry["v"])),
                                                   self.close()), P, kind="primary",
                  width=220).pack(side="left", padx=6)
        ui.Button(fr, self.T("wn_inapp"), lambda: self._open("whatsnew"), P, kind="ghost",
                  width=220).pack(side="left", padx=6)
        self.c.create_window(self.W / 2, y, window=fr)

    def _open(self, tab):
        cb = self.on_open_tab
        self.close()
        if cb:
            try:
                cb(tab)
            except Exception:
                pass

    # ----------------------------------------------------------- сервіс --- #
    def close(self):
        if self._closed:
            return
        self._closed = True
        ui.fade_out(self, 140, self._destroy)

    def _destroy(self):
        try:
            self.destroy()
        except tk.TclError:
            pass

    def _drag_start(self, e):
        self._d = (e.x, e.y)

    def _drag(self, e):
        self._x = self.winfo_x() + e.x - self._d[0]
        self._y = self.winfo_y() + e.y - self._d[1]
        self.geometry(f"+{self._x}+{self._y}")
