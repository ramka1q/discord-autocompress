#!/usr/bin/env python3
"""
Discord Auto-Compress Watcher
=============================
Фоновий «вартовий»: стежить за теками і коли там зʼявляється відео БІЛЬШЕ за ліміт
Discord — сам вискакує й пропонує стиснути його до ідеального розміру (одним кліком).

Працює, доки вікно відкрите (можна згорнути). Потрібен ffmpeg у PATH.
Запуск:  python discord_autowatch.py
"""
import os
import threading
import time

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import dc_core

APP_TITLE = "Discord Auto-Compress"
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".discord_autowatch.json")
PRESETS = [("10 МБ (без Nitro)", 10), ("25 МБ", 25), ("50 МБ (Nitro Basic)", 50), ("500 МБ (Nitro)", 500)]


def default_folders() -> list[str]:
    home = os.path.expanduser("~")
    found = []
    for name in ("Videos", "Відео", "Downloads", "Завантаження", "Desktop", "Робочий стіл"):
        p = os.path.join(home, name)
        if os.path.isdir(p):
            found.append(p)
    return found[:3] or [home]


class AutoWatcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("640x560")
        self.minsize(560, 480)

        self.folders: list[str] = []
        self.target_mb = tk.IntVar(value=10)
        self.audio_kbps = tk.IntVar(value=128)
        self.auto_scale = tk.BooleanVar(value=True)

        self.watching = False
        self.handled: set[str] = set()       # вже оброблені / пропущені
        self.pending: dict[str, int] = {}    # шлях -> останній розмір (чекаємо стабілізації)
        self.start_time = 0.0
        self.active_popup = False

        self._build_ui()
        self._load_config()
        if not dc_core.have_ffmpeg():
            messagebox.showerror(APP_TITLE,
                "Не знайдено ffmpeg.\nВстанови:  winget install Gyan.FFmpeg")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------------------------------------------------------- UI ---- #
    def _build_ui(self):
        p = ttk.Frame(self, padding=12); p.pack(fill="both", expand=True)

        # теки
        ff = ttk.LabelFrame(p, text="Теки під наглядом", padding=8); ff.pack(fill="x")
        self.folders_list = tk.Listbox(ff, height=4); self.folders_list.pack(fill="x")
        brow = ttk.Frame(ff); brow.pack(fill="x", pady=(4, 0))
        ttk.Button(brow, text="＋ Додати теку", command=self.add_folder).pack(side="left")
        ttk.Button(brow, text="－ Прибрати", command=self.remove_folder).pack(side="left", padx=6)

        # ліміт
        lim = ttk.LabelFrame(p, text="Ідеальний розмір (ліміт Discord)", padding=8); lim.pack(fill="x", pady=8)
        for text, mb in PRESETS:
            ttk.Radiobutton(lim, text=text, variable=self.target_mb, value=mb).pack(side="left", padx=6)

        opt = ttk.Frame(p); opt.pack(fill="x")
        ttk.Checkbutton(opt, text="Авто-підбір роздільності (щоб не муляло)",
                        variable=self.auto_scale).pack(side="left")
        ttk.Label(opt, text="Аудіо kbps:").pack(side="left", padx=(16, 2))
        ttk.Spinbox(opt, from_=0, to=320, increment=32, width=5,
                    textvariable=self.audio_kbps).pack(side="left")

        # керування
        ctl = ttk.Frame(p); ctl.pack(fill="x", pady=10)
        self.toggle_btn = ttk.Button(ctl, text="▶ Почати стежити", command=self.toggle)
        self.toggle_btn.pack(side="left")
        self.state_lbl = ttk.Label(ctl, text="Зупинено.", foreground="#888")
        self.state_lbl.pack(side="left", padx=10)

        # лог
        lf = ttk.LabelFrame(p, text="Журнал", padding=6); lf.pack(fill="both", expand=True)
        self.log = tk.Text(lf, height=10, state="disabled", wrap="word",
                           bg="#2b2d31", fg="#dbdee1", font=("Consolas", 9), relief="flat")
        self.log.pack(fill="both", expand=True)

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log.config(state="normal")
        self.log.insert("end", f"[{ts}] {msg}\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # ----------------------------------------------------------- теки ------- #
    def _refresh_folders(self):
        self.folders_list.delete(0, "end")
        for f in self.folders:
            self.folders_list.insert("end", f)

    def add_folder(self):
        d = filedialog.askdirectory(title="Обери теку для нагляду")
        if d and d not in self.folders:
            self.folders.append(d); self._refresh_folders()

    def remove_folder(self):
        sel = self.folders_list.curselection()
        if sel:
            del self.folders[sel[0]]; self._refresh_folders()

    # --------------------------------------------------------- стеження ----- #
    def toggle(self):
        if self.watching:
            self.watching = False
            self.toggle_btn.config(text="▶ Почати стежити")
            self.state_lbl.config(text="Зупинено.", foreground="#888")
            self._log("Стеження зупинено.")
            return
        if not self.folders:
            messagebox.showwarning(APP_TITLE, "Додай хоча б одну теку."); return
        self.watching = True
        self.start_time = time.time()
        self.pending.clear()
        self.toggle_btn.config(text="⏸ Зупинити")
        self.state_lbl.config(text="Стежу…", foreground="#3ba55d")
        self._save_config()
        self._log(f"Стежу за {len(self.folders)} теками. Ліміт {self.target_mb.get()} МБ.")
        threading.Thread(target=self._watch_loop, daemon=True).start()

    def _watch_loop(self):
        while self.watching:
            try:
                self._scan_once()
            except Exception as e:  # не падати на дрібницях
                self.after(0, lambda e=e: self._log(f"⚠ {e}"))
            time.sleep(3)

    def _scan_once(self):
        limit = self.target_mb.get()
        limit_bytes = limit * 1024 * 1024
        for folder in list(self.folders):
            if not os.path.isdir(folder):
                continue
            for entry in os.scandir(folder):
                if not entry.is_file():
                    continue
                path = entry.path
                ext = os.path.splitext(path)[1].lower()
                if ext not in dc_core.VIDEO_EXT:
                    continue
                if "_discord_" in os.path.basename(path):  # наш власний результат
                    continue
                if path in self.handled:
                    continue
                try:
                    st = entry.stat()
                except OSError:
                    continue
                if st.st_mtime < self.start_time - 1:  # старі файли ігноруємо
                    continue
                if st.st_size <= limit_bytes:
                    continue
                # чекаємо, доки файл допишеться (розмір стабільний 2 цикли)
                if self.pending.get(path) != st.st_size:
                    self.pending[path] = st.st_size
                    continue
                # стабільний і завеликий -> пропонуємо
                self.handled.add(path)
                self.pending.pop(path, None)
                self.after(0, lambda p=path, s=st.st_size: self._offer(p, s))

    # --------------------------------------------------------- попап -------- #
    def _offer(self, path, size_bytes):
        if self.active_popup:
            # якщо вже відкрито попап — повернемо файл у чергу на наступний раз
            self.handled.discard(path)
            self.pending.pop(path, None)
            return
        size_mb = size_bytes / 1024 / 1024
        name = os.path.basename(path)
        self._log(f"Знайдено завелике відео: {name} ({size_mb:.1f} МБ)")
        self.active_popup = True

        win = tk.Toplevel(self); win.title("Завелике відео")
        win.geometry("440x180"); win.attributes("-topmost", True)
        win.grab_set()
        ttk.Label(win, text="🎬 " + name, font=("", 11, "bold")).pack(pady=(14, 2), padx=12)
        ttk.Label(win, text=f"{size_mb:.1f} МБ — більше за ліміт {self.target_mb.get()} МБ").pack()
        ttk.Label(win, text=f"Стиснути до ≈{self.target_mb.get()} МБ?",
                  foreground="#5865F2").pack(pady=6)
        brow = ttk.Frame(win); brow.pack(pady=10)

        def do_compress():
            win.destroy(); self.active_popup = False
            self._start_compress(path)

        def skip():
            win.destroy(); self.active_popup = False
            self._log(f"Пропущено: {name}")

        ttk.Button(brow, text="Стиснути ▶", command=do_compress).pack(side="left", padx=6)
        ttk.Button(brow, text="Пропустити", command=skip).pack(side="left", padx=6)
        win.protocol("WM_DELETE_WINDOW", skip)

    # ------------------------------------------------------- стиснення ------ #
    def _start_compress(self, path):
        try:
            info = dc_core.ffprobe_info(path)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Не вдалося прочитати відео:\n{e}"); return

        target = float(self.target_mb.get())
        scale = dc_core.pick_auto_scale(info, target, self.audio_kbps.get()) if self.auto_scale.get() else 0
        out_path = dc_core.output_name(path, target)

        prog = tk.Toplevel(self); prog.title("Стиснення…")
        prog.geometry("420x140"); prog.attributes("-topmost", True)
        ttk.Label(prog, text=os.path.basename(path), font=("", 10, "bold")).pack(pady=(14, 4), padx=12)
        sc_txt = "оригінал" if scale == 0 else f"{scale}p"
        ttk.Label(prog, text=f"Ціль {target:g} МБ · {sc_txt}", foreground="#888").pack()
        bar = ttk.Progressbar(prog, mode="determinate", maximum=100); bar.pack(fill="x", padx=16, pady=10)
        cancel = {"flag": False}
        ttk.Button(prog, text="Скасувати",
                   command=lambda: cancel.update(flag=True)).pack()

        def progress_cb(pct):
            self.after(0, lambda: bar.config(value=pct))

        def worker():
            ok, msg, final_mb = dc_core.compress(
                path, out_path, target, scale, self.audio_kbps.get(), info,
                progress_cb=progress_cb, should_cancel=lambda: cancel["flag"])
            self.after(0, lambda: done(ok, msg, final_mb))

        def done(ok, msg, final_mb):
            prog.destroy()
            if cancel["flag"]:
                self._log("Скасовано.")
                if os.path.exists(out_path):
                    try: os.remove(out_path)
                    except OSError: pass
                return
            if ok:
                fits = "✅ влізе" if final_mb <= target else "⚠ трохи більше"
                self._log(f"Готово: {os.path.basename(out_path)} — {final_mb:.2f} МБ ({fits})")
                if messagebox.askyesno(APP_TITLE,
                        f"Готово: {final_mb:.2f} МБ ({fits}).\nВідкрити теку з файлом?"):
                    self._reveal(out_path)
            else:
                self._log(f"❌ {msg}")
                messagebox.showerror(APP_TITLE, msg)

        threading.Thread(target=worker, daemon=True).start()

    def _reveal(self, path):
        if os.path.exists(path):
            import subprocess
            subprocess.run(["explorer", "/select,", os.path.normpath(path)])

    # ----------------------------------------------------------- конфіг ----- #
    def _save_config(self):
        try:
            import json
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({"folders": self.folders, "target_mb": self.target_mb.get(),
                           "audio_kbps": self.audio_kbps.get(),
                           "auto_scale": self.auto_scale.get()}, f, ensure_ascii=False)
        except Exception:
            pass

    def _load_config(self):
        try:
            import json
            with open(CONFIG_PATH, encoding="utf-8") as f:
                c = json.load(f)
            self.folders = [d for d in c.get("folders", []) if os.path.isdir(d)]
            self.target_mb.set(c.get("target_mb", 10))
            self.audio_kbps.set(c.get("audio_kbps", 128))
            self.auto_scale.set(c.get("auto_scale", True))
        except Exception:
            pass
        if not self.folders:
            self.folders = default_folders()
        self._refresh_folders()

    def _on_close(self):
        if self.watching and not messagebox.askyesno(
                APP_TITLE, "Вартовий працює. Якщо закрити — стеження зупиниться. Вийти?"):
            return
        self.destroy()


if __name__ == "__main__":
    AutoWatcher().mainloop()
