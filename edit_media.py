#!/usr/bin/env python3
"""
edit_media.py — ліва панель редактора (як у відеоредакторах): згори вкладки
Медіа · Аудіо · Текст · Переходи · Фільтри, під ними — плитки.
  • Медіа: «Імпорт» / «Запис», плитки доданих відео й фото (клік — вибрати кліп,
    «+» або подвійний клік — ще раз у кінець монтажу);
  • Аудіо: додати музику / записати голос, список доданих звуків;
  • Текст: готові стилі титрів (клік — новий текст на плейхеді);
  • Переходи / Фільтри: клік — застосувати до вибраного кліпа.
Тільки стандартна бібліотека (tkinter).
"""
import tkinter as tk
from tkinter import filedialog

import edit_fx as fx


def _mix(c1, c2, t):
    try:
        a = [int(c1.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
        b = [int(c2.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    except (ValueError, IndexError):
        return c1
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(a[i] + (b[i] - a[i]) * t))) for i in range(3))


def _dur(t):
    t = max(0, int(round(t)))
    return f"{t // 60:02d}:{t % 60:02d}"


# приблизний вигляд фільтра на плитці (колір «кадру»)
_FLT_COL = {"none": ("#3a6f8f", "#e8c26a"), "bw": ("#5a5a5a", "#d0d0d0"), "vivid": ("#1f8fc9", "#ffcf3a"),
            "warm": ("#8a5a3a", "#ffc070"), "cool": ("#2f6a9a", "#bfe4ff"), "vintage": ("#7a6a4a", "#e0c890"),
            "film": ("#2f4f5f", "#e8d8a0"), "fade": ("#6f8a9a", "#efe2c4")}
_TR_ICON = {"fade": "◐", "fadeblack": "●", "fadewhite": "○", "slideleft": "⇠", "wipeleft": "▌",
            "smoothleft": "≋", "circleopen": "◎", "zoomin": "⤢", "pixelize": "▦", "radial": "◔"}


class MediaPanel(tk.Frame):
    W = 300
    CATS = [("media", "▣"), ("audio", "♪"), ("text", "T"), ("stickers", "☺"), ("effects", "✦"),
            ("trans", "⧓"), ("filters", "◑")]

    def __init__(self, parent, ed, P, E):
        super().__init__(parent, bg=P["bg2"], width=self.W)
        self.pack_propagate(False)
        self.ed, self.P, self.E = ed, P, E
        self.cat = "media"
        self._sig = None
        # ---- верхній рядок категорій (іконка + підпис) ----
        self.bar = tk.Canvas(self, height=50, bg=P["bg2"], highlightthickness=0, cursor="hand2")
        self.bar.pack(fill="x")
        self.bar.bind("<Configure>", lambda e: self._draw_bar())
        self.bar.bind("<Button-1>", self._bar_click)
        tk.Frame(self, bg=_mix(P["bg2"], P["text"], 0.08), height=1).pack(fill="x")
        # ---- прокручуваний вміст ----
        self.cv = tk.Canvas(self, bg=P["bg2"], highlightthickness=0)
        self.cv.pack(fill="both", expand=True)
        self.body = tk.Frame(self.cv, bg=P["bg2"])
        self._win = self.cv.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfigure(self._win, width=e.width))
        self.cv.bind("<MouseWheel>", self._wheel)
        self.refresh(force=True)

    # ------------------------------------------------------------ службове -- #
    def _wheel(self, ev):
        try:
            if self.body.winfo_reqheight() > self.cv.winfo_height():
                self.cv.yview_scroll(int(-ev.delta / 120) * 3, "units")
        except tk.TclError:
            pass
        return "break"

    def _bind_wheel(self, w):
        w.bind("<MouseWheel>", self._wheel, add="+")
        for ch in w.winfo_children():
            self._bind_wheel(ch)

    def _draw_bar(self):
        P, c = self.P, self.bar
        try:
            c.delete("all")
            W = c.winfo_width()
        except tk.TclError:
            return
        n = len(self.CATS)
        for i, (k, ic) in enumerate(self.CATS):
            x = W * (i + 0.5) / n
            on = k == self.cat
            col = P["accent"] if on else P["text"]
            c.create_text(x, 17, text=ic, fill=col, font=(P["font"], 13, "bold"))
            c.create_text(x, 37, text=self.E("mp_" + k), fill=col, font=(P["font"], 8))
            if on:
                c.create_line(x - 16, 48, x + 16, 48, fill=P["accent"], width=2)

    def _bar_click(self, ev):
        try:
            W = self.bar.winfo_width()
        except tk.TclError:
            return
        i = int(ev.x / max(1, W) * len(self.CATS))
        i = max(0, min(len(self.CATS) - 1, i))
        k = self.CATS[i][0]
        if k != self.cat:
            self.cat = k
            self._draw_bar()
            self.refresh(force=True)

    def _signature(self):
        ed = self.ed
        sel = ed._sel_key() if hasattr(ed, "_sel_key") else None
        return (self.cat, len(ed.sources), tuple(s.get("strip") is not None for s in ed.sources),
                len(ed.snds), tuple(ed.pieces[i]["src"] for i in ed.order), getattr(ed, "_empty", False),
                sel[0] if sel else None, ed.sel)

    def refresh(self, force=False):
        """Перебудувати вміст, якщо щось змінилось (викликає редактор після змін доріжки)."""
        sig = self._signature()
        if sig == self._sig and not force:
            return
        self._sig = sig
        for w in self.body.winfo_children():
            w.destroy()
        try:
            getattr(self, "_cat_" + self.cat)()
        except tk.TclError:
            pass
        self._bind_wheel(self.body)

    def _btn(self, parent, text, cmd, primary=False):
        P = self.P
        b = tk.Label(parent, text=text, bg=P["accent"] if primary else P["dark"],
                     fg="#ffffff" if primary else P["text"], font=(P["font"], 9, "bold"),
                     padx=10, pady=5, cursor="hand2")
        b.bind("<Button-1>", lambda e: cmd())
        hov = _mix(P["accent"], "#ffffff", 0.15) if primary else _mix(P["dark"], P["text"], 0.12)
        base = b.cget("bg")
        b.bind("<Enter>", lambda e: b.config(bg=hov))
        b.bind("<Leave>", lambda e: b.config(bg=base))
        return b

    def _title(self, text):
        tk.Label(self.body, text=text, bg=self.P["bg2"], fg=self.P["muted"], anchor="w",
                 font=(self.P["font"], 8, "bold")).pack(fill="x", padx=12, pady=(10, 4))

    def _hint(self, text):
        tk.Label(self.body, text=text, bg=self.P["bg2"], fg=self.P["muted"], anchor="w", justify="left",
                 wraplength=self.W - 30, font=(self.P["font"], 8)).pack(fill="x", padx=12, pady=(4, 6))

    def _grid(self):
        g = tk.Frame(self.body, bg=self.P["bg2"])
        g.pack(fill="x", padx=8, pady=2)
        return g

    def _tile(self, grid, i, per, draw, label, on_click, on_double=None, selected=False, badge=None):
        """Плитка 86×60 з підписом; draw(canvas, w, h) малює вміст."""
        P = self.P
        w, h = 86, 58
        c = tk.Canvas(grid, width=w, height=h + 16, bg=P["bg2"], highlightthickness=0, cursor="hand2")
        c.grid(row=i // per, column=i % per, padx=3, pady=3)
        c.create_rectangle(1, 1, w - 1, h - 1, fill="#0d0d0d", outline="")
        try:
            draw(c, w, h)
        except Exception:
            pass
        bd = c.create_rectangle(1, 1, w - 1, h - 1, outline=P["accent"] if selected else P["dark"],
                                width=2 if selected else 1)
        if badge:
            c.create_rectangle(w - 34, 3, w - 3, 15, fill="#000000", outline="")
            c.create_text(w - 18, 9, text=badge, fill="#ffffff", font=(P["font"], 7))
        lab = label if len(label) <= 14 else label[:13] + "…"
        c.create_text(w / 2, h + 8, text=lab, fill=P["accent"] if selected else P["text"], font=(P["font"], 8))
        c.bind("<Button-1>", lambda e: on_click())
        if on_double:
            c.bind("<Double-Button-1>", lambda e: on_double())
        if not selected:
            c.bind("<Enter>", lambda e: c.itemconfigure(bd, outline=_mix(P["bg2"], P["text"], 0.35)))
            c.bind("<Leave>", lambda e: c.itemconfigure(bd, outline=P["dark"]))
        return c

    # ------------------------------------------------------------- Медіа -- #
    def _cat_media(self):
        ed, E = self.ed, self.E
        top = tk.Frame(self.body, bg=self.P["bg2"])
        top.pack(fill="x", padx=12, pady=(12, 4))
        self._btn(top, "⊕  " + E("mp_import"), ed._add_dialog, primary=True).pack(side="left")
        self._btn(top, "🎙  " + E("mp_record"), ed._toggle_rec).pack(side="left", padx=6)
        srcs = [(i, s) for i, s in enumerate(ed.sources)
                if s["kind"] in ("video", "image") and not (getattr(ed, "_empty", False) and i == 0)]
        if not srcs:
            self._hint(E("mp_empty"))
            return
        self._title(E("mp_all").upper())
        used = {ed.pieces[ix]["src"] for ix in ed.order} | {o["src"] for o in ed.ovls}
        cur_src = ed._sel_piece()["src"] if ed.order else None
        g = self._grid()
        for n, (i, s) in enumerate(srcs):
            def draw(c, w, h, s=s):
                strip = s.get("strip")
                if strip:
                    im = strip[min(len(strip) - 1, len(strip) // 3)]
                    c.create_image(w / 2, h / 2, image=im)
                    c.thumb_ref = im      # своє посилання: редактор міняє стрічку на детальнішу,
                    #                       і без нього стара картинка зникла б (чорна плитка)
                else:
                    c.create_text(w / 2, h / 2, text="🎬" if s["kind"] == "video" else "🖼",
                                  fill=self.P["muted"], font=(self.P["font"], 16))
                if i in used:
                    c.create_rectangle(3, 3, 40, 15, fill="#000000", outline="")
                    c.create_text(21, 9, text=E("mp_added"), fill="#ffffff", font=(self.P["font"], 7))
            badge = _dur(s["dur"]) if s["kind"] == "video" else None
            self._tile(g, n, 3, draw, s["name"], lambda i=i: ed._media_pick(i),
                       on_double=lambda i=i: ed._media_append(i), selected=i == cur_src, badge=badge)
        self._hint(E("mp_media_hint"))

    # ------------------------------------------------------------- Аудіо -- #
    def _cat_audio(self):
        ed, E, P = self.ed, self.E, self.P
        top = tk.Frame(self.body, bg=P["bg2"])
        top.pack(fill="x", padx=12, pady=(12, 4))

        def add_audio():
            paths = filedialog.askopenfilenames(
                parent=ed, title=E("mp_add_music"),
                filetypes=[("Audio", "*.mp3 *.wav *.m4a *.ogg *.aac *.flac *.wma *.opus"), ("*", "*.*")])
            if paths:
                ed._add_files(list(paths))
                self.refresh(force=True)
        self._btn(top, "♪  " + E("mp_add_music"), add_audio, primary=True).pack(side="left")
        self._btn(top, "🎙  " + E("mp_record"), ed._toggle_rec).pack(side="left", padx=6)
        if not ed.snds:
            self._hint(E("mp_audio_empty"))
            return
        self._title(E("mp_sounds").upper())
        sel = ed._sel_snd
        for i, sn in enumerate(ed.snds):
            on = i == sel
            row = tk.Frame(self.body, bg=P["accent"] if on else P["dark"], cursor="hand2")
            row.pack(fill="x", padx=12, pady=2)
            nm = sn["name"] if len(sn["name"]) <= 26 else sn["name"][:25] + "…"
            a = tk.Label(row, text="♪  " + nm, bg=row.cget("bg"), fg="#ffffff" if on else P["text"],
                         font=(P["font"], 9), anchor="w")
            a.pack(side="left", fill="x", expand=True, padx=8, pady=6)
            b = tk.Label(row, text=_dur(sn["dur"]), bg=row.cget("bg"), fg="#ffffff" if on else P["muted"],
                         font=(P["font"], 8))
            b.pack(side="right", padx=8)
            for w in (row, a, b):
                w.bind("<Button-1>", lambda e, i=i: ed._media_pick_snd(i))

    # ------------------------------------------------------------- Текст -- #
    def _cat_stickers(self):
        ed, E, P = self.ed, self.E, self.P
        self._title(E("mp_stickers").upper())
        g = self._grid()
        for n, code in enumerate(fx.STICKERS):
            ch = fx.sticker_char(code)
            c = tk.Label(g, text=ch, bg=P["bg2"], fg=P["text"], font=("Segoe UI Emoji", 20), cursor="hand2",
                         width=2)
            c.grid(row=n // 6, column=n % 6, padx=2, pady=2)
            c.bind("<Button-1>", lambda e, code=code: ed._add_sticker(code))
            c.bind("<Enter>", lambda e, c=c: c.config(bg=_mix(P["bg2"], P["text"], 0.15)))
            c.bind("<Leave>", lambda e, c=c: c.config(bg=P["bg2"]))
        self._hint(E("mp_sticker_hint"))

    def _cat_text(self):
        ed, E, P = self.ed, self.E, self.P
        self._title(E("mp_text_tpl").upper())
        g0 = self._grid()
        for n, (key, tpl) in enumerate(fx.TEXT_TEMPLATES):
            def draw(c, w, h, tpl=tpl):
                fam = {"impact": "Impact", "comic": "Comic Sans MS", "georgia": "Georgia", "consolas": "Consolas",
                       "script": "Segoe Script", "verdana": "Verdana", "arial": "Arial"}.get(tpl.get("font"), P["font"])
                f = (fam, 14, "bold")
                x, y = w / 2, h / 2
                if tpl.get("style") == "box":
                    c.create_rectangle(x - 30, y - 13, x + 30, y + 13, fill=tpl.get("bgc", "#000000"), outline="")
                else:
                    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (2, 2)):
                        c.create_text(x + dx, y + dy, text="Abc", fill=tpl.get("stroke", "#000000"), font=f)
                c.create_text(x, y, text="Abc", fill=tpl.get("color", "#ffffff"), font=f)
            self._tile(g0, n, 3, draw, E("tpl_" + key), lambda tpl=tpl: ed._media_add_tpl(tpl))
        self._title(E("mp_text_styles").upper())
        presets = [("outline", "#ffffff", E("st_outline")), ("box", "#ffffff", E("st_box")),
                   ("shadow", "#ffffff", E("st_shadow")), ("outline", "#ffd23f", E("mp_txt_yellow")),
                   ("outline", "#ff4d4d", E("mp_txt_red")), ("box", "#4cc9ff", E("mp_txt_blue")),
                   ("shadow", "#33c27f", E("mp_txt_green")), ("outline", "#ff7ad9", E("mp_txt_pink")),
                   ("box", "#000000", E("mp_txt_dark"))]
        g = self._grid()
        for n, (st, col, lab) in enumerate(presets):
            def draw(c, w, h, st=st, col=col):
                x, y = w / 2, h / 2
                f = (P["font"], 17, "bold")
                if st == "box":
                    c.create_rectangle(x - 26, y - 14, x + 26, y + 14, fill="#000000" if col != "#000000" else "#e9e9e9",
                                       outline="")
                elif st == "shadow":
                    c.create_text(x + 2, y + 2, text="Aa", fill="#000000", font=f)
                else:
                    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                        c.create_text(x + dx, y + dy, text="Aa", fill="#000000", font=f)
                c.create_text(x, y, text="Aa", fill=col, font=f)
            self._tile(g, n, 3, draw, lab, lambda st=st, col=col: ed._media_add_text(st, col))
        self._hint(E("mp_text_hint"))

    # ---------------------------------------------------------- Переходи -- #
    def _cat_trans(self):
        ed, E, P = self.ed, self.E, self.P
        if len(ed.order) < 2:
            self._hint(E("mp_trans_need2"))
            return
        slot = ed.sel if ed.sel > 0 else 1
        cur = (ed.pieces[ed.order[slot]].get("tr") or {}).get("type")
        self._title(E("mp_trans_for", n=slot).upper())
        g = self._grid()
        items = [(None, E("tr_none"))] + [(t, E("tr_" + t)) for t in fx.TRANSITIONS]
        for n, (t, lab) in enumerate(items):
            def draw(c, w, h, t=t):
                c.create_rectangle(4, 4, w / 2, h - 4, fill="#3a6f8f", outline="")
                c.create_rectangle(w / 2, 4, w - 4, h - 4, fill="#8f5a3a", outline="")
                c.create_text(w / 2, h / 2, text=_TR_ICON.get(t, "∅"), fill="#ffffff",
                              font=(P["font"], 16, "bold"))
            self._tile(g, n, 3, draw, lab, lambda t=t, slot=slot: ed._media_set_tr(slot, t), selected=t == cur)
        self._hint(E("mp_trans_hint"))

    # ------------------------------------------------------------ Ефекти -- #
    def _cat_effects(self):
        ed, E, P = self.ed, self.E, self.P
        if not ed.order:
            return
        p = ed._look_target()
        cur = fx.g(p, "vfx")
        self._title(E("mp_effects").upper())
        g = self._grid()
        ic = {"none": "∅", "glitch": "▚", "vhs": "📼", "oldfilm": "🎞", "blur": "◌", "shake": "〰",
              "chromatic": "◈", "flash": "⚡", "rainbow": "🌈", "invert": "◑", "sepia": "☕",
              "edge": "✎", "pixel": "▦", "sharpen": "◆", "posterize": "▤", "bloom": "✺", "noise": "░"}
        for n, v in enumerate(fx.VFX):
            def draw(c, w, h, v=v):
                c.create_rectangle(3, 3, w - 3, h - 3, fill="#2a2440", outline="")
                c.create_text(w / 2, h / 2, text=ic.get(v, "✦"), fill="#ffffff", font=(P["font"], 17))
            self._tile(g, n, 3, draw, E("vfx_" + v), lambda v=v: ed._media_set_vfx(v), selected=v == cur)
        self._hint(E("mp_vfx_hint"))

    # ----------------------------------------------------------- Фільтри -- #
    def _cat_filters(self):
        ed, E = self.ed, self.E
        if not ed.order:
            return
        p = ed._look_target()
        cur = fx.g(p, "flt")
        self._title(E("ins_filter").upper())
        g = self._grid()
        for n, f in enumerate(fx.FILTERS):
            def draw(c, w, h, f=f):
                sky, sun = _FLT_COL.get(f, _FLT_COL["none"])
                c.create_rectangle(3, 3, w - 3, h - 3, fill=sky, outline="")
                c.create_polygon(3, h - 3, w * 0.4, h * 0.45, w * 0.7, h - 3, fill=_mix(sky, "#000000", 0.45),
                                 outline="")
                c.create_oval(w * 0.62, h * 0.18, w * 0.82, h * 0.18 + w * 0.2, fill=sun, outline="")
            self._tile(g, n, 3, draw, E("flt_" + f), lambda f=f: ed._media_set_flt(f), selected=f == cur)
        self._hint(E("mp_flt_hint"))
