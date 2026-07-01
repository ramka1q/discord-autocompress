#!/usr/bin/env python3
"""
Discord Video Compressor
========================
Стискає відео точно під ліміт завантаження Discord, щоб кліп з гри / запис екрана
заходив у чат. Працює через ffmpeg (двопрохідне кодування H.264 з розрахунком
бітрейту під заданий розмір).

Ліміти Discord:
    10 МБ  — без Nitro
    25 МБ  — буст рівень 2 / старі акаунти
    50 МБ  — Nitro Basic
    500 МБ — Nitro

Потрібен ffmpeg + ffprobe у PATH (https://ffmpeg.org). Решта — стандартна
бібліотека Python 3.8+ (tkinter входить у комплект).

Запуск:  python discord_compressor.py
"""

import os
import re
import subprocess
import threading

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_TITLE = "Discord Video Compressor"
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

PRESETS = [
    ("Без Nitro — 10 МБ", 10),
    ("25 МБ", 25),
    ("Nitro Basic — 50 МБ", 50),
    ("Nitro — 500 МБ", 500),
]
SCALES = [("Оригінал", 0), ("1080p", 1080), ("720p", 720), ("480p", 480)]
TIME_RE = re.compile(r"out_time=(\d+):(\d+):(\d+\.\d+)")


def ffprobe_info(path: str) -> dict:
    """Повертає {'duration', 'width', 'height', 'has_audio'} або кидає виняток."""
    def probe(args):
        out = subprocess.run(["ffprobe", "-v", "error", *args],
                             capture_output=True, text=True, creationflags=NO_WINDOW)
        return out.stdout.strip()

    duration = float(probe(["-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", path]) or 0)
    wh = probe(["-select_streams", "v:0", "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0", path])
    width = height = 0
    if "x" in wh:
        try:
            width, height = (int(x) for x in wh.split("x")[:2])
        except ValueError:
            pass
    acodec = probe(["-select_streams", "a:0", "-show_entries", "stream=codec_type",
                    "-of", "default=noprint_wrappers=1:nokey=1", path])
    return {"duration": duration, "width": width, "height": height,
            "has_audio": acodec.strip() == "audio"}


class Compressor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("680x520")
        self.minsize(600, 480)

        self.in_path = tk.StringVar()
        self.info: dict | None = None
        self.size_var = tk.IntVar(value=10)
        self.scale_var = tk.IntVar(value=720)
        self.audio_kbps = tk.IntVar(value=128)
        self.worker: threading.Thread | None = None
        self.cancel_flag = False
        self.proc: subprocess.Popen | None = None

        self._build_ui()
        self._check_ffmpeg()

    # ---------------------------------------------------------------- UI ---- #
    def _build_ui(self):
        p = ttk.Frame(self, padding=12)
        p.pack(fill="both", expand=True)

        # файл
        fr = ttk.LabelFrame(p, text="Відео", padding=8)
        fr.pack(fill="x")
        row = ttk.Frame(fr); row.pack(fill="x")
        ttk.Entry(row, textvariable=self.in_path).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Огляд…", command=self.pick_file).pack(side="left", padx=6)
        self.info_lbl = ttk.Label(fr, text="Файл не обрано.", foreground="#888")
        self.info_lbl.pack(anchor="w", pady=(6, 0))

        # ліміт
        lim = ttk.LabelFrame(p, text="Цільовий розмір (ліміт Discord)", padding=8)
        lim.pack(fill="x", pady=8)
        for text, mb in PRESETS:
            ttk.Radiobutton(lim, text=text, variable=self.size_var, value=mb,
                            command=self._update_estimate).pack(anchor="w")
        crow = ttk.Frame(lim); crow.pack(anchor="w", pady=(4, 0))
        ttk.Radiobutton(crow, text="Свій:", variable=self.size_var, value=-1,
                        command=self._update_estimate).pack(side="left")
        self.custom_mb = ttk.Entry(crow, width=6); self.custom_mb.insert(0, "8")
        self.custom_mb.pack(side="left", padx=4)
        self.custom_mb.bind("<KeyRelease>", lambda e: self._update_estimate())
        ttk.Label(crow, text="МБ").pack(side="left")

        # якість
        q = ttk.LabelFrame(p, text="Роздільність та звук", padding=8)
        q.pack(fill="x")
        srow = ttk.Frame(q); srow.pack(anchor="w")
        ttk.Label(srow, text="Розмір кадру:").pack(side="left")
        for text, val in SCALES:
            ttk.Radiobutton(srow, text=text, variable=self.scale_var, value=val).pack(side="left", padx=4)
        arow = ttk.Frame(q); arow.pack(anchor="w", pady=(6, 0))
        ttk.Label(arow, text="Аудіо-бітрейт (kbps):").pack(side="left")
        ttk.Spinbox(arow, from_=0, to=320, increment=32, width=6,
                    textvariable=self.audio_kbps, command=self._update_estimate).pack(side="left", padx=4)
        ttk.Label(arow, text="(0 = без звуку)").pack(side="left")

        # оцінка
        self.est_lbl = ttk.Label(p, text="", foreground="#5865F2")
        self.est_lbl.pack(anchor="w", pady=6)

        # прогрес
        self.progress = ttk.Progressbar(p, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=4)
        self.status = ttk.Label(p, text="Готово.", foreground="#888")
        self.status.pack(anchor="w")

        # кнопки
        btns = ttk.Frame(p); btns.pack(fill="x", pady=(8, 0))
        self.go_btn = ttk.Button(btns, text="Стиснути ▶", command=self.start)
        self.go_btn.pack(side="left")
        self.cancel_btn = ttk.Button(btns, text="Скасувати", command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=6)
        self.open_btn = ttk.Button(btns, text="Відкрити теку", command=self.open_folder, state="disabled")
        self.open_btn.pack(side="right")

    def _check_ffmpeg(self):
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, creationflags=NO_WINDOW)
            subprocess.run(["ffprobe", "-version"], capture_output=True, creationflags=NO_WINDOW)
        except FileNotFoundError:
            messagebox.showerror(APP_TITLE,
                "Не знайдено ffmpeg/ffprobe у PATH.\n"
                "Встанови з https://ffmpeg.org або:  winget install Gyan.FFmpeg")

    # ---------------------------------------------------------- логіка ----- #
    def _target_mb(self) -> float:
        if self.size_var.get() == -1:
            try:
                return max(1.0, float(self.custom_mb.get()))
            except ValueError:
                return 8.0
        return float(self.size_var.get())

    def pick_file(self):
        path = filedialog.askopenfilename(
            title="Обери відео",
            filetypes=[("Відео", "*.mp4 *.mkv *.mov *.avi *.webm *.flv *.m4v *.wmv"),
                       ("Усі файли", "*.*")])
        if not path:
            return
        self.in_path.set(path)
        try:
            self.info = ffprobe_info(path)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Не вдалося прочитати відео:\n{e}")
            self.info = None
            return
        size_mb = os.path.getsize(path) / 1024 / 1024
        d = self.info["duration"]
        self.info_lbl.config(
            text=f"{self.info['width']}×{self.info['height']}, "
                 f"{int(d // 60)}:{int(d % 60):02d}, {size_mb:.1f} МБ"
                 + ("" if self.info["has_audio"] else ", без звуку"))
        self._update_estimate()

    def _calc_video_kbps(self) -> int | None:
        if not self.info or self.info["duration"] <= 0:
            return None
        target_bits = self._target_mb() * 8 * 1024 * 1024 * 0.97  # 3% запас на контейнер
        audio_bits = (self.audio_kbps.get() * 1000 * self.info["duration"]
                      if self.info["has_audio"] else 0)
        video_bps = (target_bits - audio_bits) / self.info["duration"]
        return int(video_bps / 1000)

    def _update_estimate(self):
        v = self._calc_video_kbps()
        if v is None:
            self.est_lbl.config(text="")
            return
        if v < 100:
            self.est_lbl.config(
                text=f"⚠ Відео-бітрейт ~{v} kbps — замало. Зменш розмір кадру / звук "
                     f"або збільш ліміт.", foreground="#ed4245")
        else:
            self.est_lbl.config(
                text=f"Розрахунок: відео ~{v} kbps + аудіо {self.audio_kbps.get()} kbps "
                     f"→ ≈{self._target_mb():g} МБ", foreground="#5865F2")

    # ------------------------------------------------------- стиснення ----- #
    def start(self):
        if self.worker and self.worker.is_alive():
            return
        path = self.in_path.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning(APP_TITLE, "Спершу обери відео."); return
        v_kbps = self._calc_video_kbps()
        if v_kbps is None:
            messagebox.showwarning(APP_TITLE, "Не вдалося визначити тривалість відео."); return
        if v_kbps < 50:
            messagebox.showwarning(APP_TITLE,
                "Бітрейт занизький — результат буде нечитабельний. "
                "Збільш ліміт або зменш роздільність/звук."); return

        base, _ = os.path.splitext(path)
        out_path = f"{base}_discord_{int(self._target_mb())}mb.mp4"
        self.out_path = out_path
        self.cancel_flag = False
        self.go_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.open_btn.config(state="disabled")
        self.progress.config(value=0)

        self.worker = threading.Thread(
            target=self._run, args=(path, out_path, v_kbps), daemon=True)
        self.worker.start()

    def _run(self, path, out_path, v_kbps):
        scale = self.scale_var.get()
        vf = []
        if scale:
            vf = ["-vf", f"scale=-2:{scale}"]  # -2 = парна ширина, збереже пропорції
        a_kbps = self.audio_kbps.get()
        has_audio = self.info["has_audio"] and a_kbps > 0
        duration = self.info["duration"]
        passlog = os.path.join(os.path.dirname(out_path) or ".", "_d2p_passlog")

        common = ["ffmpeg", "-y", "-i", path, "-c:v", "libx264",
                  "-b:v", f"{v_kbps}k", "-preset", "medium", *vf]

        try:
            # ---- pass 1 ----
            self._set_status("Прохід 1/2 (аналіз)…")
            rc = self._spawn(common + ["-pass", "1", "-passlogfile", passlog,
                                       "-an", "-f", "null", os.devnull], duration, 0, 50)
            if self.cancel_flag:
                return self._finish(cancelled=True)
            if rc != 0:
                return self._finish(error="Прохід 1 завершився з помилкою.")

            # ---- pass 2 ----
            self._set_status("Прохід 2/2 (кодування)…")
            audio_args = (["-c:a", "aac", "-b:a", f"{a_kbps}k"] if has_audio else ["-an"])
            rc = self._spawn(common + ["-pass", "2", "-passlogfile", passlog,
                                       *audio_args, "-movflags", "+faststart", out_path],
                             duration, 50, 100)
            if self.cancel_flag:
                return self._finish(cancelled=True)
            if rc != 0:
                return self._finish(error="Прохід 2 завершився з помилкою.")

            final_mb = os.path.getsize(out_path) / 1024 / 1024
            self._finish(ok=True, final_mb=final_mb)
        finally:
            for ext in (".log", ".log.mbtree", "-0.log", "-0.log.mbtree"):
                f = passlog + ext
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except OSError:
                        pass

    def _spawn(self, cmd, duration, base_pct, end_pct) -> int:
        cmd = cmd + ["-progress", "pipe:1", "-nostats", "-loglevel", "error"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, creationflags=NO_WINDOW)
        for line in self.proc.stdout:
            if self.cancel_flag:
                self.proc.terminate()
                break
            m = TIME_RE.search(line)
            if m and duration > 0:
                h, mn, s = m.groups()
                done = int(h) * 3600 + int(mn) * 60 + float(s)
                pct = base_pct + min(1.0, done / duration) * (end_pct - base_pct)
                self.after(0, lambda v=pct: self.progress.config(value=v))
        self.proc.wait()
        return self.proc.returncode

    def _set_status(self, text):
        self.after(0, lambda: self.status.config(text=text, foreground="#888"))

    def _finish(self, ok=False, error=None, cancelled=False, final_mb=0.0):
        def ui():
            self.go_btn.config(state="normal")
            self.cancel_btn.config(state="disabled")
            if cancelled:
                self.status.config(text="Скасовано.", foreground="#d29922")
                self.progress.config(value=0)
                if hasattr(self, "out_path") and os.path.exists(self.out_path):
                    try:
                        os.remove(self.out_path)
                    except OSError:
                        pass
            elif error:
                self.status.config(text="❌ " + error, foreground="#ed4245")
                messagebox.showerror(APP_TITLE, error)
            elif ok:
                self.progress.config(value=100)
                limit = self._target_mb()
                fits = "✅ влізе" if final_mb <= limit else "⚠ трохи більше ліміту"
                self.status.config(
                    text=f"Готово: {os.path.basename(self.out_path)} — {final_mb:.2f} МБ ({fits})",
                    foreground="#3ba55d")
                self.open_btn.config(state="normal")
        self.after(0, ui)

    def cancel(self):
        self.cancel_flag = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self._set_status("Скасування…")

    def open_folder(self):
        if hasattr(self, "out_path") and os.path.exists(self.out_path):
            subprocess.run(["explorer", "/select,", os.path.normpath(self.out_path)])


if __name__ == "__main__":
    Compressor().mainloop()
