#!/usr/bin/env python3
"""
Discord Webhook Studio
----------------------
Десктопний застосунок для надсилання повідомлень та embed'ів у Discord-канал
через вебхук. Бот і токен НЕ потрібні — лише URL вебхука.

Як отримати URL вебхука:
    Канал у Discord -> Налаштування каналу (шестерня) -> Integrations
    -> Webhooks -> New Webhook -> Copy Webhook URL

Залежності: тільки стандартна бібліотека Python 3.8+ (tkinter входить у комплект).
Запуск:  python webhook_studio.py
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

APP_TITLE = "Discord Webhook Studio"
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".discord_webhook_studio.json")
WEBHOOK_RE = re.compile(r"^https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$")


# --------------------------------------------------------------------------- #
#  Низькорівневе надсилання
# --------------------------------------------------------------------------- #
def send_webhook(url: str, payload: dict, timeout: int = 15) -> tuple[bool, str]:
    """Надсилає payload на вебхук. Повертає (успіх, повідомлення)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "WebhookStudio/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"Надіслано (HTTP {resp.status})"
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        return False, f"HTTP {e.code}: {body[:500]}"
    except urllib.error.URLError as e:
        return False, f"Помилка мережі: {e.reason}"
    except Exception as e:  # pragma: no cover
        return False, f"Помилка: {e}"


# --------------------------------------------------------------------------- #
#  Головне вікно
# --------------------------------------------------------------------------- #
class WebhookStudio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x780")
        self.minsize(820, 640)

        self.embed_color = tk.StringVar(value="#5865F2")  # Discord blurple
        self.field_rows: list[dict] = []

        self._build_ui()
        self._load_config()
        self._refresh_preview()

    # ---------------------------------------------------------------- UI ---- #
    def _build_ui(self):
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        # --- Верх: webhook url + кнопки ---
        top = ttk.LabelFrame(outer, text="Вебхук", padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="URL вебхука:").grid(row=0, column=0, sticky="w")
        self.url_entry = ttk.Entry(top, width=80, show="•")
        self.url_entry.grid(row=0, column=1, sticky="ew", padx=6)
        self.show_url = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Показати", variable=self.show_url,
                        command=self._toggle_url).grid(row=0, column=2, padx=4)
        ttk.Button(top, text="Тест", command=self.on_test).grid(row=0, column=3, padx=2)
        top.columnconfigure(1, weight=1)

        # override username / avatar
        ttk.Label(top, text="Імʼя відправника:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.username_entry = ttk.Entry(top)
        self.username_entry.grid(row=1, column=1, sticky="ew", padx=6, pady=(6, 0))
        ttk.Label(top, text="Avatar URL:").grid(row=2, column=0, sticky="w")
        self.avatar_entry = ttk.Entry(top)
        self.avatar_entry.grid(row=2, column=1, sticky="ew", padx=6)

        # --- Середина: ліворуч редактор, праворуч превʼю ---
        mid = ttk.Frame(outer)
        mid.pack(fill="both", expand=True, pady=8)

        editor = ttk.Frame(mid)
        editor.pack(side="left", fill="both", expand=True)
        self._build_editor(editor)

        preview = ttk.LabelFrame(mid, text="Превʼю (JSON payload)", padding=6)
        preview.pack(side="right", fill="both", expand=True, padx=(8, 0))
        self.preview = tk.Text(preview, width=42, wrap="word", state="disabled",
                               bg="#2b2d31", fg="#dbdee1", insertbackground="#fff",
                               font=("Consolas", 9), relief="flat")
        self.preview.pack(fill="both", expand=True)

        # --- Низ: дії ---
        bottom = ttk.Frame(outer)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Зберегти шаблон", command=self.on_save_template).pack(side="left")
        ttk.Button(bottom, text="Завантажити шаблон", command=self.on_load_template).pack(side="left", padx=4)
        ttk.Label(bottom, text="Затримка (сек):").pack(side="left", padx=(16, 2))
        self.delay_entry = ttk.Entry(bottom, width=6)
        self.delay_entry.insert(0, "0")
        self.delay_entry.pack(side="left")
        self.send_btn = ttk.Button(bottom, text="Надіслати ▶", command=self.on_send)
        self.send_btn.pack(side="right")
        self.status = ttk.Label(bottom, text="Готово.", foreground="#888")
        self.status.pack(side="right", padx=10)

    def _build_editor(self, parent):
        nb = ttk.Notebook(parent)
        nb.pack(fill="both", expand=True)

        # ---- Вкладка: повідомлення ----
        tab_msg = ttk.Frame(nb, padding=8)
        nb.add(tab_msg, text="Повідомлення")
        ttk.Label(tab_msg, text="Текст (content, до 2000 символів):").pack(anchor="w")
        self.content_text = tk.Text(tab_msg, height=5, wrap="word")
        self.content_text.pack(fill="x")
        self.content_text.bind("<KeyRelease>", lambda e: self._refresh_preview())

        self.use_embed = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab_msg, text="Додати embed", variable=self.use_embed,
                        command=self._refresh_preview).pack(anchor="w", pady=(8, 0))
        self.tts = tk.BooleanVar(value=False)
        ttk.Checkbutton(tab_msg, text="TTS (озвучити повідомлення)", variable=self.tts,
                        command=self._refresh_preview).pack(anchor="w")

        # ---- Вкладка: embed ----
        tab_embed = ttk.Frame(nb, padding=8)
        nb.add(tab_embed, text="Embed")
        self._build_embed_tab(tab_embed)

    def _build_embed_tab(self, parent):
        g = ttk.Frame(parent)
        g.pack(fill="x")
        self.embed_entries: dict[str, ttk.Entry] = {}
        rows = [
            ("title", "Заголовок"),
            ("url", "Посилання заголовка (URL)"),
            ("author_name", "Автор: імʼя"),
            ("author_icon", "Автор: іконка (URL)"),
            ("image", "Велика картинка (URL)"),
            ("thumbnail", "Мініатюра (URL)"),
            ("footer", "Підвал (footer)"),
            ("footer_icon", "Іконка підвалу (URL)"),
        ]
        for i, (key, label) in enumerate(rows):
            ttk.Label(g, text=label + ":").grid(row=i, column=0, sticky="w", pady=1)
            e = ttk.Entry(g, width=46)
            e.grid(row=i, column=1, sticky="ew", padx=6, pady=1)
            e.bind("<KeyRelease>", lambda ev: self._refresh_preview())
            self.embed_entries[key] = e
        g.columnconfigure(1, weight=1)

        ttk.Label(parent, text="Опис (description):").pack(anchor="w", pady=(8, 0))
        self.desc_text = tk.Text(parent, height=6, wrap="word")
        self.desc_text.pack(fill="x")
        self.desc_text.bind("<KeyRelease>", lambda e: self._refresh_preview())

        # колір + timestamp
        crow = ttk.Frame(parent)
        crow.pack(fill="x", pady=6)
        ttk.Label(crow, text="Колір:").pack(side="left")
        self.color_swatch = tk.Label(crow, width=4, bg=self.embed_color.get(), relief="solid", bd=1)
        self.color_swatch.pack(side="left", padx=6)
        ttk.Button(crow, text="Обрати колір", command=self.on_pick_color).pack(side="left")
        self.add_timestamp = tk.BooleanVar(value=True)
        ttk.Checkbutton(crow, text="Додати поточний час", variable=self.add_timestamp,
                        command=self._refresh_preview).pack(side="left", padx=16)

        # поля (fields)
        fwrap = ttk.LabelFrame(parent, text="Поля (fields)", padding=6)
        fwrap.pack(fill="both", expand=True, pady=6)
        ttk.Button(fwrap, text="+ Додати поле", command=self.add_field).pack(anchor="w")
        self.fields_container = ttk.Frame(fwrap)
        self.fields_container.pack(fill="both", expand=True, pady=4)

    # ------------------------------------------------------------ fields ---- #
    def add_field(self, name="", value="", inline=True):
        row = ttk.Frame(self.fields_container)
        row.pack(fill="x", pady=2)
        name_e = ttk.Entry(row, width=18)
        name_e.insert(0, name)
        name_e.pack(side="left")
        val_e = ttk.Entry(row, width=30)
        val_e.insert(0, value)
        val_e.pack(side="left", padx=4, fill="x", expand=True)
        inline_v = tk.BooleanVar(value=inline)
        ttk.Checkbutton(row, text="inline", variable=inline_v).pack(side="left")

        entry = {"frame": row, "name": name_e, "value": val_e, "inline": inline_v}

        def remove():
            row.destroy()
            self.field_rows.remove(entry)
            self._refresh_preview()

        ttk.Button(row, text="✕", width=3, command=remove).pack(side="left", padx=2)
        name_e.bind("<KeyRelease>", lambda e: self._refresh_preview())
        val_e.bind("<KeyRelease>", lambda e: self._refresh_preview())
        inline_v.trace_add("write", lambda *a: self._refresh_preview())
        self.field_rows.append(entry)
        self._refresh_preview()

    # ------------------------------------------------------------ helpers --- #
    def _toggle_url(self):
        self.url_entry.config(show="" if self.show_url.get() else "•")

    def on_pick_color(self):
        rgb, hexcol = colorchooser.askcolor(self.embed_color.get(), title="Колір embed")
        if hexcol:
            self.embed_color.set(hexcol)
            self.color_swatch.config(bg=hexcol)
            self._refresh_preview()

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
            embed: dict = {}
            e = self.embed_entries
            if e["title"].get().strip():
                embed["title"] = e["title"].get().strip()
            if e["url"].get().strip():
                embed["url"] = e["url"].get().strip()
            desc = self.desc_text.get("1.0", "end").strip()
            if desc:
                embed["description"] = desc

            # колір -> int
            try:
                embed["color"] = int(self.embed_color.get().lstrip("#"), 16)
            except ValueError:
                pass

            if e["author_name"].get().strip():
                author = {"name": e["author_name"].get().strip()}
                if e["author_icon"].get().strip():
                    author["icon_url"] = e["author_icon"].get().strip()
                embed["author"] = author
            if e["image"].get().strip():
                embed["image"] = {"url": e["image"].get().strip()}
            if e["thumbnail"].get().strip():
                embed["thumbnail"] = {"url": e["thumbnail"].get().strip()}
            if e["footer"].get().strip():
                footer = {"text": e["footer"].get().strip()}
                if e["footer_icon"].get().strip():
                    footer["icon_url"] = e["footer_icon"].get().strip()
                embed["footer"] = footer
            if self.add_timestamp.get():
                embed["timestamp"] = datetime.now(timezone.utc).isoformat()

            fields = []
            for fr in self.field_rows:
                n = fr["name"].get().strip()
                v = fr["value"].get().strip()
                if n and v:
                    fields.append({"name": n, "value": v, "inline": fr["inline"].get()})
            if fields:
                embed["fields"] = fields

            if embed:
                payload["embeds"] = [embed]

        return payload

    def _refresh_preview(self):
        payload = self._build_payload()
        self.preview.config(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", json.dumps(payload, indent=2, ensure_ascii=False))
        self.preview.config(state="disabled")

    def _set_status(self, text, color="#888"):
        self.status.config(text=text, foreground=color)

    # --------------------------------------------------------------- actions #
    def _validate(self) -> str | None:
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning(APP_TITLE, "Вкажіть URL вебхука.")
            return None
        if not WEBHOOK_RE.match(url):
            if not messagebox.askyesno(
                APP_TITLE,
                "URL не схожий на стандартний Discord-вебхук.\nВсе одно спробувати надіслати?",
            ):
                return None
        payload = self._build_payload()
        if not payload.get("content") and not payload.get("embeds"):
            messagebox.showwarning(APP_TITLE, "Повідомлення порожнє — додайте текст або embed.")
            return None
        return url

    def on_test(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning(APP_TITLE, "Вкажіть URL вебхука.")
            return
        self._async_send(url, {"content": "✅ Тест зʼєднання — Discord Webhook Studio працює!"})

    def on_send(self):
        url = self._validate()
        if not url:
            return
        try:
            delay = max(0, int(self.delay_entry.get().strip() or "0"))
        except ValueError:
            messagebox.showwarning(APP_TITLE, "Затримка має бути цілим числом секунд.")
            return
        payload = self._build_payload()
        self._save_config()
        if delay:
            self._set_status(f"Надсилання через {delay} с…", "#d29922")
            self.after(delay * 1000, lambda: self._async_send(url, payload))
        else:
            self._async_send(url, payload)

    def _async_send(self, url, payload):
        self.send_btn.config(state="disabled")
        self._set_status("Надсилання…", "#d29922")

        def worker():
            ok, msg = send_webhook(url, payload)
            self.after(0, lambda: self._after_send(ok, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _after_send(self, ok, msg):
        self.send_btn.config(state="normal")
        if ok:
            self._set_status("✅ " + msg, "#3ba55d")
        else:
            self._set_status("❌ " + msg, "#ed4245")
            messagebox.showerror(APP_TITLE, msg)

    # ------------------------------------------------------------ templates - #
    def _collect_template(self) -> dict:
        return {
            "username": self.username_entry.get(),
            "avatar": self.avatar_entry.get(),
            "content": self.content_text.get("1.0", "end").rstrip("\n"),
            "use_embed": self.use_embed.get(),
            "tts": self.tts.get(),
            "color": self.embed_color.get(),
            "add_timestamp": self.add_timestamp.get(),
            "embed": {k: e.get() for k, e in self.embed_entries.items()},
            "description": self.desc_text.get("1.0", "end").rstrip("\n"),
            "fields": [
                {"name": fr["name"].get(), "value": fr["value"].get(), "inline": fr["inline"].get()}
                for fr in self.field_rows
            ],
        }

    def _apply_template(self, t: dict):
        self.username_entry.delete(0, "end"); self.username_entry.insert(0, t.get("username", ""))
        self.avatar_entry.delete(0, "end"); self.avatar_entry.insert(0, t.get("avatar", ""))
        self.content_text.delete("1.0", "end"); self.content_text.insert("1.0", t.get("content", ""))
        self.use_embed.set(t.get("use_embed", True))
        self.tts.set(t.get("tts", False))
        self.embed_color.set(t.get("color", "#5865F2"))
        self.color_swatch.config(bg=self.embed_color.get())
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
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")],
            title="Зберегти шаблон")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._collect_template(), f, indent=2, ensure_ascii=False)
        self._set_status(f"Шаблон збережено: {os.path.basename(path)}", "#3ba55d")

    def on_load_template(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json")], title="Завантажити шаблон")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                self._apply_template(json.load(f))
            self._set_status(f"Шаблон завантажено: {os.path.basename(path)}", "#3ba55d")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Не вдалося завантажити: {e}")

    # ------------------------------------------------------------- config --- #
    def _save_config(self):
        """Зберігає лише URL/імʼя/аватар, щоб не вводити щоразу."""
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "url": self.url_entry.get().strip(),
                    "username": self.username_entry.get(),
                    "avatar": self.avatar_entry.get(),
                }, f)
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


if __name__ == "__main__":
    app = WebhookStudio()
    app.mainloop()
