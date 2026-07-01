#!/usr/bin/env python3
"""
Discord Toolbox — мега-програма для Discord (без бота й токена)
================================================================
Усе в одному вікні через вебхук:

  1) Надсилання   — повний редактор embed (заголовок, опис, поля, колір, картинки)
  2) Планувальник — відкладені та повторювані повідомлення (поки програма відкрита)
  3) Менеджер     — редагувати / видаляти вже надіслані повідомлення за ID
  4) Утиліти      — генератор часових міток <t:..>, декодер ID (snowflake),
                    оформлювач тексту (markdown), підбір кольору embed

Залежності: ЛИШЕ стандартна бібліотека Python 3.8+ (tkinter входить у комплект).
Запуск:  python discord_toolbox.py
"""

import json
import os
import re
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser

APP_TITLE = "Discord Toolbox"
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".discord_toolbox.json")
WEBHOOK_RE = re.compile(r"^https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$")
DISCORD_EPOCH = 1420070400000  # 2015-01-01, для декодування snowflake


# --------------------------------------------------------------------------- #
#  Мережа
# --------------------------------------------------------------------------- #
def http_request(method: str, url: str, payload: dict | None = None, timeout: int = 15):
    """Універсальний запит. Повертає (ok: bool, data: dict|None, message: str)."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json", "User-Agent": "DiscordToolbox/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            parsed = json.loads(body) if body.strip() else None
            return True, parsed, f"OK (HTTP {resp.status})"
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        return False, None, f"HTTP {e.code}: {body[:400]}"
    except urllib.error.URLError as e:
        return False, None, f"Помилка мережі: {e.reason}"
    except Exception as e:  # pragma: no cover
        return False, None, f"Помилка: {e}"


# --------------------------------------------------------------------------- #
#  Головне вікно
# --------------------------------------------------------------------------- #
class DiscordToolbox(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1040x820")
        self.minsize(880, 680)

        self.embed_color = tk.StringVar(value="#5865F2")
        self.field_rows: list[dict] = []
        self.jobs: list[dict] = []
        self.recent_messages: list[dict] = []  # {"id":..,"label":..}
        self._job_seq = 0

        self._build_ui()
        self._load_config()
        self._refresh_preview()
        self.after(1000, self._tick)  # цикл планувальника
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ============================================================ UI ======== #
    def _build_ui(self):
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        # ---- Спільний рядок: webhook URL ----
        top = ttk.LabelFrame(outer, text="Вебхук (спільний для всіх вкладок)", padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="URL:").grid(row=0, column=0, sticky="w")
        self.url_entry = ttk.Entry(top, show="•")
        self.url_entry.grid(row=0, column=1, sticky="ew", padx=6)
        self.show_url = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Показати", variable=self.show_url,
                        command=self._toggle_url).grid(row=0, column=2, padx=4)
        ttk.Button(top, text="Тест", command=self.on_test).grid(row=0, column=3)
        top.columnconfigure(1, weight=1)

        # ---- Вкладки ----
        nb = ttk.Notebook(outer)
        nb.pack(fill="both", expand=True, pady=(8, 6))
        self.tab_send = ttk.Frame(nb, padding=8); nb.add(self.tab_send, text="1 · Надсилання")
        self.tab_sched = ttk.Frame(nb, padding=8); nb.add(self.tab_sched, text="2 · Планувальник")
        self.tab_manage = ttk.Frame(nb, padding=8); nb.add(self.tab_manage, text="3 · Менеджер")
        self.tab_util = ttk.Frame(nb, padding=8); nb.add(self.tab_util, text="4 · Утиліти")
        self._build_send_tab(self.tab_send)
        self._build_schedule_tab(self.tab_sched)
        self._build_manage_tab(self.tab_manage)
        self._build_utils_tab(self.tab_util)

        # ---- Статусбар ----
        self.status = ttk.Label(outer, text="Готово.", foreground="#888", anchor="w")
        self.status.pack(fill="x")

    # ----------------------------------------------------- Вкладка 1: Send -- #
    def _build_send_tab(self, parent):
        left = ttk.Frame(parent); left.pack(side="left", fill="both", expand=True)
        right = ttk.LabelFrame(parent, text="Превʼю (JSON)", padding=6)
        right.pack(side="right", fill="both", expand=True, padx=(8, 0))

        # відправник
        ident = ttk.Frame(left); ident.pack(fill="x")
        ttk.Label(ident, text="Імʼя:").grid(row=0, column=0, sticky="w")
        self.username_entry = ttk.Entry(ident); self.username_entry.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Label(ident, text="Avatar URL:").grid(row=0, column=2, sticky="w")
        self.avatar_entry = ttk.Entry(ident); self.avatar_entry.grid(row=0, column=3, sticky="ew", padx=6)
        ident.columnconfigure(1, weight=1); ident.columnconfigure(3, weight=1)

        ttk.Label(left, text="Текст (content):").pack(anchor="w", pady=(8, 0))
        self.content_text = tk.Text(left, height=3, wrap="word")
        self.content_text.pack(fill="x")
        self.content_text.bind("<KeyRelease>", lambda e: self._refresh_preview())

        opts = ttk.Frame(left); opts.pack(fill="x", pady=4)
        self.use_embed = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Embed", variable=self.use_embed,
                        command=self._refresh_preview).pack(side="left")
        self.tts = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="TTS", variable=self.tts,
                        command=self._refresh_preview).pack(side="left", padx=8)

        # embed-поля
        emb = ttk.LabelFrame(left, text="Embed", padding=6); emb.pack(fill="x")
        self.embed_entries: dict[str, ttk.Entry] = {}
        rows = [("title", "Заголовок"), ("url", "URL заголовка"),
                ("author_name", "Автор"), ("author_icon", "Іконка автора (URL)"),
                ("image", "Картинка (URL)"), ("thumbnail", "Мініатюра (URL)"),
                ("footer", "Підвал"), ("footer_icon", "Іконка підвалу (URL)")]
        for i, (key, label) in enumerate(rows):
            r, c = divmod(i, 2)
            ttk.Label(emb, text=label + ":").grid(row=r, column=c * 2, sticky="w", pady=1)
            e = ttk.Entry(emb, width=24); e.grid(row=r, column=c * 2 + 1, sticky="ew", padx=4, pady=1)
            e.bind("<KeyRelease>", lambda ev: self._refresh_preview())
            self.embed_entries[key] = e
        emb.columnconfigure(1, weight=1); emb.columnconfigure(3, weight=1)

        ttk.Label(left, text="Опис:").pack(anchor="w", pady=(6, 0))
        self.desc_text = tk.Text(left, height=4, wrap="word")
        self.desc_text.pack(fill="x")
        self.desc_text.bind("<KeyRelease>", lambda e: self._refresh_preview())

        crow = ttk.Frame(left); crow.pack(fill="x", pady=6)
        ttk.Label(crow, text="Колір:").pack(side="left")
        self.color_swatch = tk.Label(crow, width=4, bg=self.embed_color.get(), relief="solid", bd=1)
        self.color_swatch.pack(side="left", padx=6)
        ttk.Button(crow, text="Обрати", command=self.on_pick_color).pack(side="left")
        self.add_timestamp = tk.BooleanVar(value=True)
        ttk.Checkbutton(crow, text="Час", variable=self.add_timestamp,
                        command=self._refresh_preview).pack(side="left", padx=12)

        fwrap = ttk.LabelFrame(left, text="Поля", padding=6); fwrap.pack(fill="both", expand=True)
        ttk.Button(fwrap, text="+ Поле", command=self.add_field).pack(anchor="w")
        self.fields_container = ttk.Frame(fwrap); self.fields_container.pack(fill="both", expand=True, pady=4)

        actions = ttk.Frame(left); actions.pack(fill="x", pady=(6, 0))
        ttk.Button(actions, text="Зберегти шаблон", command=self.on_save_template).pack(side="left")
        ttk.Button(actions, text="Завантажити", command=self.on_load_template).pack(side="left", padx=4)
        self.send_btn = ttk.Button(actions, text="Надіслати ▶", command=self.on_send)
        self.send_btn.pack(side="right")

        self.preview = tk.Text(right, width=40, wrap="word", state="disabled",
                               bg="#2b2d31", fg="#dbdee1", font=("Consolas", 9), relief="flat")
        self.preview.pack(fill="both", expand=True)

    # ------------------------------------------------- Вкладка 2: Schedule -- #
    def _build_schedule_tab(self, parent):
        info = ttk.Label(parent, wraplength=900, foreground="#888",
                         text="Планувальник надсилає ПОТОЧНЕ повідомлення з вкладки «Надсилання». "
                              "Спершу скомпонуй повідомлення там, потім додай завдання тут. "
                              "Завдання працюють, доки програма відкрита.")
        info.pack(anchor="w", pady=(0, 8))

        form = ttk.LabelFrame(parent, text="Нове завдання", padding=8); form.pack(fill="x")
        ttk.Label(form, text="Назва:").grid(row=0, column=0, sticky="w")
        self.job_label = ttk.Entry(form, width=30); self.job_label.grid(row=0, column=1, sticky="w", padx=6)

        self.job_mode = tk.StringVar(value="delay")
        ttk.Radiobutton(form, text="Через", variable=self.job_mode, value="delay").grid(row=1, column=0, sticky="w")
        self.job_delay = ttk.Entry(form, width=8); self.job_delay.insert(0, "10")
        self.job_delay.grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(form, text="хвилин (одноразово)").grid(row=1, column=2, sticky="w")

        ttk.Radiobutton(form, text="Кожні", variable=self.job_mode, value="every").grid(row=2, column=0, sticky="w")
        self.job_every = ttk.Entry(form, width=8); self.job_every.insert(0, "60")
        self.job_every.grid(row=2, column=1, sticky="w", padx=6)
        ttk.Label(form, text="хвилин (повторювано)").grid(row=2, column=2, sticky="w")

        ttk.Radiobutton(form, text="О", variable=self.job_mode, value="at").grid(row=3, column=0, sticky="w")
        self.job_at = ttk.Entry(form, width=8); self.job_at.insert(0, "18:00")
        self.job_at.grid(row=3, column=1, sticky="w", padx=6)
        ttk.Label(form, text="год:хв сьогодні/завтра (одноразово)").grid(row=3, column=2, sticky="w")

        ttk.Button(form, text="＋ Додати завдання", command=self.on_add_job).grid(row=4, column=1, sticky="w", pady=6)

        listf = ttk.LabelFrame(parent, text="Активні завдання", padding=6); listf.pack(fill="both", expand=True, pady=8)
        self.jobs_tree = ttk.Treeview(listf, columns=("name", "when", "next"), show="headings", height=8)
        for c, t, w in (("name", "Назва", 200), ("when", "Розклад", 200), ("next", "Наступне", 200)):
            self.jobs_tree.heading(c, text=t); self.jobs_tree.column(c, width=w)
        self.jobs_tree.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(listf, command=self.jobs_tree.yview); sb.pack(side="right", fill="y")
        self.jobs_tree.config(yscrollcommand=sb.set)
        ttk.Button(parent, text="✕ Скасувати вибране", command=self.on_cancel_job).pack(anchor="w")

    # --------------------------------------------------- Вкладка 3: Manage -- #
    def _build_manage_tab(self, parent):
        info = ttk.Label(parent, wraplength=900, foreground="#888",
                         text="Редагувати/видаляти можна лише повідомлення, надіслані ЦИМ вебхуком. "
                              "Після надсилання на вкладці 1 ID зʼявляється у списку нижче автоматично.")
        info.pack(anchor="w", pady=(0, 8))

        row = ttk.Frame(parent); row.pack(fill="x")
        ttk.Label(row, text="ID повідомлення:").pack(side="left")
        self.msg_id_entry = ttk.Entry(row, width=24); self.msg_id_entry.pack(side="left", padx=6)
        ttk.Label(row, text="Нещодавні:").pack(side="left")
        self.recent_combo = ttk.Combobox(row, width=40, state="readonly", values=[])
        self.recent_combo.pack(side="left", padx=6)
        self.recent_combo.bind("<<ComboboxSelected>>", self._on_pick_recent)

        ttk.Label(parent, text="Новий текст (content) для редагування:").pack(anchor="w", pady=(8, 0))
        self.edit_text = tk.Text(parent, height=5, wrap="word"); self.edit_text.pack(fill="x")
        self.edit_use_current = tk.BooleanVar(value=False)
        ttk.Checkbutton(parent, text="Замінити на ПОТОЧНИЙ embed з вкладки «Надсилання»",
                        variable=self.edit_use_current).pack(anchor="w", pady=4)

        btns = ttk.Frame(parent); btns.pack(fill="x", pady=8)
        ttk.Button(btns, text="✎ Редагувати", command=self.on_edit_message).pack(side="left")
        ttk.Button(btns, text="🗑 Видалити", command=self.on_delete_message).pack(side="left", padx=6)

    # --------------------------------------------------- Вкладка 4: Utils --- #
    def _build_utils_tab(self, parent):
        nb = ttk.Notebook(parent); nb.pack(fill="both", expand=True)

        # -- Часові мітки --
        t1 = ttk.Frame(nb, padding=8); nb.add(t1, text="Часова мітка")
        ttk.Label(t1, text="Дата й час (РРРР-ММ-ДД ГГ:ХХ), порожньо = зараз:").pack(anchor="w")
        self.ts_input = ttk.Entry(t1, width=24); self.ts_input.pack(anchor="w", pady=4)
        ttk.Button(t1, text="Згенерувати", command=self.on_gen_timestamp).pack(anchor="w")
        self.ts_output = tk.Text(t1, height=10, wrap="word", font=("Consolas", 9))
        self.ts_output.pack(fill="both", expand=True, pady=6)

        # -- Декодер ID --
        t2 = ttk.Frame(nb, padding=8); nb.add(t2, text="Декодер ID")
        ttk.Label(t2, text="Discord ID (snowflake) користувача/повідомлення/каналу:").pack(anchor="w")
        self.snow_input = ttk.Entry(t2, width=30); self.snow_input.pack(anchor="w", pady=4)
        ttk.Button(t2, text="Декодувати", command=self.on_decode_snowflake).pack(anchor="w")
        self.snow_output = tk.Text(t2, height=8, wrap="word", font=("Consolas", 9))
        self.snow_output.pack(fill="both", expand=True, pady=6)

        # -- Оформлювач тексту --
        t3 = ttk.Frame(nb, padding=8); nb.add(t3, text="Оформлення")
        ttk.Label(t3, text="Введи текст, виділи частину й натисни стиль:").pack(anchor="w")
        self.md_text = tk.Text(t3, height=8, wrap="word"); self.md_text.pack(fill="both", expand=True, pady=4)
        bar = ttk.Frame(t3); bar.pack(fill="x")
        for label, wrap in (("Жирний", "**"), ("Курсив", "*"), ("Підкр.", "__"),
                            ("Закрес.", "~~"), ("Код", "`"), ("Спойлер", "||")):
            ttk.Button(bar, text=label, command=lambda w=wrap: self._md_wrap(w)).pack(side="left", padx=2)
        ttk.Button(bar, text="Блок коду", command=lambda: self._md_wrap("```\n", "\n```")).pack(side="left", padx=2)

        # -- Колір --
        t4 = ttk.Frame(nb, padding=8); nb.add(t4, text="Колір")
        ttk.Button(t4, text="Обрати колір", command=self.on_util_color).pack(anchor="w", pady=4)
        self.util_swatch = tk.Label(t4, width=20, height=3, relief="solid", bd=1, bg="#5865F2")
        self.util_swatch.pack(anchor="w", pady=4)
        self.util_color_out = tk.Text(t4, height=4, wrap="word", font=("Consolas", 9))
        self.util_color_out.pack(fill="x", pady=6)

    # ============================================== Спільна логіка embed === #
    def add_field(self, name="", value="", inline=True):
        row = ttk.Frame(self.fields_container); row.pack(fill="x", pady=2)
        name_e = ttk.Entry(row, width=16); name_e.insert(0, name); name_e.pack(side="left")
        val_e = ttk.Entry(row); val_e.insert(0, value); val_e.pack(side="left", padx=4, fill="x", expand=True)
        inline_v = tk.BooleanVar(value=inline)
        ttk.Checkbutton(row, text="inline", variable=inline_v).pack(side="left")
        entry = {"frame": row, "name": name_e, "value": val_e, "inline": inline_v}

        def remove():
            row.destroy(); self.field_rows.remove(entry); self._refresh_preview()

        ttk.Button(row, text="✕", width=3, command=remove).pack(side="left", padx=2)
        name_e.bind("<KeyRelease>", lambda e: self._refresh_preview())
        val_e.bind("<KeyRelease>", lambda e: self._refresh_preview())
        inline_v.trace_add("write", lambda *a: self._refresh_preview())
        self.field_rows.append(entry); self._refresh_preview()

    def _build_payload(self) -> dict:
        payload: dict = {}
        content = self.content_text.get("1.0", "end").strip()
        if content:
            payload["content"] = content
        if self.username_entry.get().strip():
            payload["username"] = self.username_entry.get().strip()
        if self.avatar_entry.get().strip():
            payload["avatar_url"] = self.avatar_entry.get().strip()
        if self.tts.get():
            payload["tts"] = True
        if self.use_embed.get():
            embed = self._build_embed()
            if embed:
                payload["embeds"] = [embed]
        return payload

    def _build_embed(self) -> dict:
        embed: dict = {}
        e = self.embed_entries
        if e["title"].get().strip():
            embed["title"] = e["title"].get().strip()
        if e["url"].get().strip():
            embed["url"] = e["url"].get().strip()
        desc = self.desc_text.get("1.0", "end").strip()
        if desc:
            embed["description"] = desc
        try:
            embed["color"] = int(self.embed_color.get().lstrip("#"), 16)
        except ValueError:
            pass
        if e["author_name"].get().strip():
            a = {"name": e["author_name"].get().strip()}
            if e["author_icon"].get().strip():
                a["icon_url"] = e["author_icon"].get().strip()
            embed["author"] = a
        if e["image"].get().strip():
            embed["image"] = {"url": e["image"].get().strip()}
        if e["thumbnail"].get().strip():
            embed["thumbnail"] = {"url": e["thumbnail"].get().strip()}
        if e["footer"].get().strip():
            f = {"text": e["footer"].get().strip()}
            if e["footer_icon"].get().strip():
                f["icon_url"] = e["footer_icon"].get().strip()
            embed["footer"] = f
        if self.add_timestamp.get():
            embed["timestamp"] = datetime.now(timezone.utc).isoformat()
        fields = []
        for fr in self.field_rows:
            n, v = fr["name"].get().strip(), fr["value"].get().strip()
            if n and v:
                fields.append({"name": n, "value": v, "inline": fr["inline"].get()})
        if fields:
            embed["fields"] = fields
        return embed

    def _refresh_preview(self):
        self.preview.config(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", json.dumps(self._build_payload(), indent=2, ensure_ascii=False))
        self.preview.config(state="disabled")

    # ============================================== Дрібні UI-хелпери ====== #
    def _toggle_url(self):
        self.url_entry.config(show="" if self.show_url.get() else "•")

    def on_pick_color(self):
        _, hexcol = colorchooser.askcolor(self.embed_color.get(), title="Колір embed")
        if hexcol:
            self.embed_color.set(hexcol); self.color_swatch.config(bg=hexcol); self._refresh_preview()

    def _set_status(self, text, color="#888"):
        self.status.config(text=text, foreground=color)

    def _get_url(self, allow_invalid=False) -> str | None:
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning(APP_TITLE, "Вкажіть URL вебхука зверху."); return None
        if not WEBHOOK_RE.match(url) and not allow_invalid:
            if not messagebox.askyesno(APP_TITLE, "URL не схожий на Discord-вебхук. Продовжити?"):
                return None
        return url

    # ============================================== Надсилання ============= #
    def on_test(self):
        url = self._get_url()
        if url:
            self._async(lambda: http_request("POST", url, {"content": "✅ Discord Toolbox: зʼєднання працює!"}),
                        ok_msg="Тест надіслано")

    def on_send(self):
        url = self._get_url()
        if not url:
            return
        payload = self._build_payload()
        if not payload.get("content") and not payload.get("embeds"):
            messagebox.showwarning(APP_TITLE, "Повідомлення порожнє."); return
        self._save_config()
        send_url = url + ("&" if "?" in url else "?") + "wait=true"  # щоб отримати ID

        def task():
            ok, data, msg = http_request("POST", send_url, payload)
            if ok and isinstance(data, dict) and data.get("id"):
                self.after(0, lambda: self._register_message(data["id"], payload))
            return ok, data, msg

        self._async(task, ok_msg="Надіслано", btn=self.send_btn)

    def _register_message(self, mid: str, payload: dict):
        label = (payload.get("content") or
                 (payload.get("embeds", [{}])[0].get("title")) or "повідомлення")
        label = f"{mid} — {label[:40]}"
        self.recent_messages.insert(0, {"id": mid, "label": label})
        self.recent_messages = self.recent_messages[:20]
        self.recent_combo.config(values=[m["label"] for m in self.recent_messages])

    # ============================================== Планувальник =========== #
    def on_add_job(self):
        url = self._get_url()
        if not url:
            return
        payload = self._build_payload()
        if not payload.get("content") and not payload.get("embeds"):
            messagebox.showwarning(APP_TITLE, "Спершу скомпонуй повідомлення на вкладці «Надсилання»."); return

        mode = self.job_mode.get()
        now = datetime.now()
        try:
            if mode == "delay":
                mins = float(self.job_delay.get()); next_run = now.timestamp() + mins * 60
                when_txt = f"через {mins:g} хв"; interval = None
            elif mode == "every":
                mins = float(self.job_every.get())
                if mins <= 0:
                    raise ValueError
                interval = mins * 60; next_run = now.timestamp() + interval
                when_txt = f"кожні {mins:g} хв"
            else:  # at
                hh, mm = map(int, self.job_at.get().strip().split(":"))
                target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                next_run = target.timestamp()
                if next_run <= now.timestamp():
                    next_run += 86400  # вже минуло сьогодні -> завтра
                when_txt = f"о {hh:02d}:{mm:02d}"; interval = None
        except (ValueError, IndexError):
            messagebox.showwarning(APP_TITLE, "Невірний формат часу."); return

        self._job_seq += 1
        label = self.job_label.get().strip() or f"Завдання {self._job_seq}"
        job = {"id": self._job_seq, "label": label, "url": url, "payload": payload,
               "interval": interval, "next_run": next_run, "when_txt": when_txt}
        item = self.jobs_tree.insert("", "end", values=(label, when_txt,
                                     datetime.fromtimestamp(next_run).strftime("%Y-%m-%d %H:%M:%S")))
        job["item"] = item
        self.jobs.append(job)
        self._set_status(f"Завдання додано: {label} ({when_txt})", "#3ba55d")

    def on_cancel_job(self):
        sel = self.jobs_tree.selection()
        if not sel:
            return
        for item in sel:
            self.jobs = [j for j in self.jobs if j.get("item") != item]
            self.jobs_tree.delete(item)
        self._set_status("Завдання скасовано.", "#d29922")

    def _tick(self):
        now = datetime.now().timestamp()
        for job in list(self.jobs):
            if now >= job["next_run"]:
                url = job["url"] + ("&" if "?" in job["url"] else "?") + "wait=true"
                threading.Thread(
                    target=lambda u=url, p=job["payload"], j=job: self._fire_job(u, p, j),
                    daemon=True).start()
                if job["interval"]:
                    job["next_run"] = now + job["interval"]
                    self.jobs_tree.item(job["item"], values=(
                        job["label"], job["when_txt"],
                        datetime.fromtimestamp(job["next_run"]).strftime("%Y-%m-%d %H:%M:%S")))
                else:
                    self.jobs = [j for j in self.jobs if j is not job]
                    if self.jobs_tree.exists(job["item"]):
                        self.jobs_tree.delete(job["item"])
        self.after(1000, self._tick)

    def _fire_job(self, url, payload, job):
        ok, data, msg = http_request("POST", url, payload)
        if ok and isinstance(data, dict) and data.get("id"):
            self.after(0, lambda: self._register_message(data["id"], payload))
        self.after(0, lambda: self._set_status(
            f"{'✅' if ok else '❌'} [{job['label']}] {msg}", "#3ba55d" if ok else "#ed4245"))

    # ============================================== Менеджер =============== #
    def _on_pick_recent(self, _evt):
        idx = self.recent_combo.current()
        if 0 <= idx < len(self.recent_messages):
            self.msg_id_entry.delete(0, "end")
            self.msg_id_entry.insert(0, self.recent_messages[idx]["id"])

    def _message_url(self, suffix=""):
        url = self._get_url()
        mid = self.msg_id_entry.get().strip()
        if not url:
            return None
        if not mid.isdigit():
            messagebox.showwarning(APP_TITLE, "Вкажіть числовий ID повідомлення."); return None
        base = url.split("?")[0]
        return f"{base}/messages/{mid}{suffix}"

    def on_edit_message(self):
        msg_url = self._message_url()
        if not msg_url:
            return
        payload = {}
        new_text = self.edit_text.get("1.0", "end").strip()
        if new_text:
            payload["content"] = new_text
        if self.edit_use_current.get():
            emb = self._build_embed()
            if emb:
                payload["embeds"] = [emb]
        if not payload:
            messagebox.showwarning(APP_TITLE, "Нема чого редагувати (порожній текст і embed)."); return
        self._async(lambda: http_request("PATCH", msg_url, payload), ok_msg="Повідомлення оновлено")

    def on_delete_message(self):
        msg_url = self._message_url()
        if not msg_url:
            return
        if not messagebox.askyesno(APP_TITLE, "Видалити це повідомлення безповоротно?"):
            return
        self._async(lambda: http_request("DELETE", msg_url), ok_msg="Повідомлення видалено")

    # ============================================== Утиліти ================ #
    def on_gen_timestamp(self):
        raw = self.ts_input.get().strip()
        try:
            dt = datetime.now() if not raw else datetime.strptime(raw, "%Y-%m-%d %H:%M")
        except ValueError:
            messagebox.showwarning(APP_TITLE, "Формат: РРРР-ММ-ДД ГГ:ХХ"); return
        unix = int(dt.timestamp())
        styles = {"t": "коротко час", "T": "час із сек", "d": "коротко дата",
                  "D": "повна дата", "f": "дата+час", "F": "повна дата+час", "R": "відносно"}
        out = f"Unix: {unix}\n\nСкопіюй у Discord:\n"
        for s, desc in styles.items():
            out += f"  <t:{unix}:{s}>   — {desc}\n"
        self.ts_output.delete("1.0", "end"); self.ts_output.insert("1.0", out)

    def on_decode_snowflake(self):
        raw = self.snow_input.get().strip()
        if not raw.isdigit():
            messagebox.showwarning(APP_TITLE, "ID має бути числом."); return
        sid = int(raw)
        ms = (sid >> 22) + DISCORD_EPOCH
        dt = datetime.fromtimestamp(ms / 1000)
        out = (f"Створено: {dt.strftime('%Y-%m-%d %H:%M:%S')} (локальний час)\n"
               f"Unix (мс): {ms}\n"
               f"Worker ID: {(sid >> 17) & 0x1F}\n"
               f"Process ID: {(sid >> 12) & 0x1F}\n"
               f"Increment: {sid & 0xFFF}")
        self.snow_output.delete("1.0", "end"); self.snow_output.insert("1.0", out)

    def _md_wrap(self, left, right=None):
        right = right if right is not None else left
        try:
            sel = self.md_text.get("sel.first", "sel.last")
            self.md_text.delete("sel.first", "sel.last")
            self.md_text.insert("insert", f"{left}{sel}{right}")
        except tk.TclError:
            self.md_text.insert("insert", f"{left}{right}")

    def on_util_color(self):
        _, hexcol = colorchooser.askcolor(title="Колір")
        if not hexcol:
            return
        self.util_swatch.config(bg=hexcol)
        dec = int(hexcol.lstrip("#"), 16)
        self.util_color_out.delete("1.0", "end")
        self.util_color_out.insert("1.0", f"HEX: {hexcol}\nDecimal (для embed color): {dec}")

    # ============================================== Загальний async ======== #
    def _async(self, task, ok_msg="OK", btn=None):
        if btn:
            btn.config(state="disabled")
        self._set_status("Виконую…", "#d29922")

        def worker():
            res = task()
            ok, _, msg = res if isinstance(res, tuple) else (res[0], None, res[2])
            self.after(0, lambda: self._after_async(ok, msg, ok_msg, btn))

        threading.Thread(target=worker, daemon=True).start()

    def _after_async(self, ok, msg, ok_msg, btn):
        if btn:
            btn.config(state="normal")
        if ok:
            self._set_status(f"✅ {ok_msg}", "#3ba55d")
        else:
            self._set_status(f"❌ {msg}", "#ed4245")
            messagebox.showerror(APP_TITLE, msg)

    # ============================================== Шаблони / конфіг ======= #
    def _collect_template(self) -> dict:
        return {
            "username": self.username_entry.get(), "avatar": self.avatar_entry.get(),
            "content": self.content_text.get("1.0", "end").rstrip("\n"),
            "use_embed": self.use_embed.get(), "tts": self.tts.get(),
            "color": self.embed_color.get(), "add_timestamp": self.add_timestamp.get(),
            "embed": {k: e.get() for k, e in self.embed_entries.items()},
            "description": self.desc_text.get("1.0", "end").rstrip("\n"),
            "fields": [{"name": fr["name"].get(), "value": fr["value"].get(),
                        "inline": fr["inline"].get()} for fr in self.field_rows],
        }

    def _apply_template(self, t: dict):
        self.username_entry.delete(0, "end"); self.username_entry.insert(0, t.get("username", ""))
        self.avatar_entry.delete(0, "end"); self.avatar_entry.insert(0, t.get("avatar", ""))
        self.content_text.delete("1.0", "end"); self.content_text.insert("1.0", t.get("content", ""))
        self.use_embed.set(t.get("use_embed", True)); self.tts.set(t.get("tts", False))
        self.embed_color.set(t.get("color", "#5865F2")); self.color_swatch.config(bg=self.embed_color.get())
        self.add_timestamp.set(t.get("add_timestamp", True))
        for k, e in self.embed_entries.items():
            e.delete(0, "end"); e.insert(0, t.get("embed", {}).get(k, ""))
        self.desc_text.delete("1.0", "end"); self.desc_text.insert("1.0", t.get("description", ""))
        for fr in list(self.field_rows):
            fr["frame"].destroy()
        self.field_rows.clear()
        for f in t.get("fields", []):
            self.add_field(f.get("name", ""), f.get("value", ""), f.get("inline", True))
        self._refresh_preview()

    def on_save_template(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("JSON", "*.json")], title="Зберегти шаблон")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._collect_template(), f, indent=2, ensure_ascii=False)
            self._set_status(f"Збережено: {os.path.basename(path)}", "#3ba55d")

    def on_load_template(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")], title="Завантажити шаблон")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                self._apply_template(json.load(f))
            self._set_status(f"Завантажено: {os.path.basename(path)}", "#3ba55d")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Помилка: {e}")

    def _save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({"url": self.url_entry.get().strip(),
                           "username": self.username_entry.get(),
                           "avatar": self.avatar_entry.get()}, f)
        except Exception:
            pass

    def _load_config(self):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                c = json.load(f)
            self.url_entry.insert(0, c.get("url", ""))
            self.username_entry.insert(0, c.get("username", ""))
            self.avatar_entry.insert(0, c.get("avatar", ""))
        except Exception:
            pass

    def _on_close(self):
        if self.jobs and not messagebox.askyesno(
                APP_TITLE, f"Є {len(self.jobs)} активних завдань планувальника. "
                           "Після виходу вони не виконаються. Вийти?"):
            return
        self.destroy()


if __name__ == "__main__":
    DiscordToolbox().mainloop()
