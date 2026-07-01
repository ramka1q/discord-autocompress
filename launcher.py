#!/usr/bin/env python3
"""
Launcher (бутстрап для .exe)
============================
Цей файл збирається в один DiscordAutoCompress.exe (PyInstaller). Exe НЕСЕ в собі
Python, тож другові НЕ треба нічого встановлювати. При запуску:
  1) тягне свіжий код програми з GitHub у %LOCALAPPDATA%\\DiscordAutoCompress
     (тому авто-оновлення працює як завжди — міняєш код у себе, у друга оновлюється);
  2) вмикає автозапуск (ярлик на сам .exe у теці Startup);
  3) запускає фонового вартового discord_overlay.

Потрібен лише ffmpeg (з ffplay) у PATH — якщо нема, покаже підказку.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

# --- Примусово «затягуємо» у збірку все, що імпортує завантажений з GitHub код.
#     PyInstaller не бачить цих import-ів (код приходить з мережі), тож перелічуємо тут. ---
import tkinter            # noqa: F401
import tkinter.ttk        # noqa: F401
import tkinter.messagebox as _mb
import tkinter.filedialog     # noqa: F401
import tkinter.colorchooser   # noqa: F401
import tkinter.font           # noqa: F401  (щоб майбутній ребілд exe бандлив підмодуль)
import ctypes             # noqa: F401
import ctypes.wintypes    # noqa: F401
import subprocess         # noqa: F401
import threading          # noqa: F401
import queue              # noqa: F401
import tempfile           # noqa: F401
import shutil             # noqa: F401
import time               # noqa: F401
import re                 # noqa: F401
import math               # noqa: F401
import datetime           # noqa: F401
import struct             # noqa: F401  (appicon малює .ico)
import zlib               # noqa: F401  (appicon пакує PNG у .ico)
import winreg             # noqa: F401  (deps перечитує PATH після встановлення ffmpeg)

APP_TITLE = "Discord Auto-Compress"
REPO_RAW = os.environ.get(
    "DAC_REPO_RAW",
    "https://raw.githubusercontent.com/ramka1q/discord-autocompress/main"
)
APPDIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                      "DiscordAutoCompress")
TIMEOUT = 20


def _fetch(rel: str) -> bytes:
    url = REPO_RAW.rstrip("/") + "/" + "/".join(urllib.parse.quote(p) for p in rel.split("/"))
    req = urllib.request.Request(url, headers={"User-Agent": "DAC-Launcher/1.0",
                                               "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def sync_code():
    """Тягне .py-файли програми з GitHub у APPDIR (best-effort; без інтернету — тихо)."""
    try:
        manifest = json.loads(_fetch("manifest.json").decode("utf-8"))
    except Exception:
        return
    for rel in manifest.get("files", []):
        if not rel.endswith(".py"):
            continue
        try:
            data = _fetch(rel)
        except Exception:
            continue
        dst = os.path.join(APPDIR, rel)
        try:
            if os.path.exists(dst) and open(dst, "rb").read() == data:
                continue
            with open(dst + ".new", "wb") as f:
                f.write(data)
            os.replace(dst + ".new", dst)
        except OSError:
            pass


def ensure_autostart():
    """Ярлик на сам .exe у теці Startup (лише для зібраного .exe).
    ЗАВЖДИ переписує ярлик на ПОТОЧНИЙ exe з '--background' — тож при переїзді на новий
    exe автозапуск САМ виправляється (старий ярлик на стару копію більше не заважає)."""
    if not getattr(sys, "frozen", False):
        return
    try:
        startup = os.path.join(os.environ["APPDATA"],
                               r"Microsoft\Windows\Start Menu\Programs\Startup")
        lnk = os.path.join(startup, "Discord Auto-Compress.lnk")
        exe = sys.executable
        # якщо ярлик уже вказує на цей самий exe з --background — не чіпаємо (щоб не смикати диск)
        ps = ("$p='%s';"
              "$sh=New-Object -ComObject WScript.Shell;"
              "$cur=if(Test-Path $p){$s=$sh.CreateShortcut($p);$s.TargetPath+'|'+$s.Arguments}else{''};"
              "if($cur -ne '%s|--background'){"
              "$s=$sh.CreateShortcut($p);$s.TargetPath='%s';$s.Arguments='--background';"
              "$s.WorkingDirectory='%s';$s.WindowStyle=7;"
              "$s.Description='Discord Auto-Compress';$s.Save()}"
              % (lnk, exe, exe, os.path.dirname(exe)))
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       creationflags=0x08000000)  # CREATE_NO_WINDOW
    except Exception:
        pass


def have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffplay") and shutil.which("ffprobe"))


def main():
    os.makedirs(APPDIR, exist_ok=True)
    sync_code()
    ensure_autostart()
    # маркер, щоб і внутрішнє авто-оновлення програми працювало
    try:
        open(os.path.join(APPDIR, ".autoupdate"), "w").close()
    except OSError:
        pass

    if not os.path.exists(os.path.join(APPDIR, "discord_overlay.py")):
        r = tkinter.Tk(); r.withdraw()
        _mb.showerror(APP_TITLE, "Для першого запуску потрібен інтернет "
                                 "(завантаження програми з GitHub).")
        return

    if not have_ffmpeg():
        r = tkinter.Tk(); r.withdraw()
        _mb.showwarning(APP_TITLE,
                        "Не знайдено ffmpeg/ffplay.\n"
                        "Встанови повний ffmpeg:  winget install Gyan.FFmpeg\n"
                        "і запусти програму ще раз.")
        # продовжуємо — раптом з'явиться пізніше; вартовий сам покаже потребу

    sys.path.insert(0, APPDIR)
    os.chdir(APPDIR)
    import discord_overlay
    # єдина точка входу з захистом від другої копії (див. discord_overlay.run_app)
    discord_overlay.run_app(open_settings="--background" not in sys.argv)


if __name__ == "__main__":
    # --selftest: перевірити завантаження коду й вийти (без запуску GUI-вартового)
    if "--selftest" in sys.argv:
        os.makedirs(APPDIR, exist_ok=True)
        sync_code()
        pys = [f for f in os.listdir(APPDIR) if f.endswith(".py")]
        print("APPDIR:", APPDIR)
        print("downloaded .py:", sorted(pys))
        print("discord_overlay.py present:", os.path.exists(os.path.join(APPDIR, "discord_overlay.py")))
        print("ffmpeg present:", have_ffmpeg())
        sys.exit(0)
    # --importtest: перевірити, що в збірці є всі модулі для коду програми
    if "--importtest" in sys.argv:
        os.makedirs(APPDIR, exist_ok=True)
        sync_code()
        sys.path.insert(0, APPDIR)
        os.chdir(APPDIR)
        try:
            import dc_core            # noqa: F401
            import discord_overlay    # noqa: F401
            import editor             # noqa: F401
            import update             # noqa: F401
            import themes             # noqa: F401
            import i18n               # noqa: F401
            import appicon            # noqa: F401
            import media              # noqa: F401
            import tray               # noqa: F401
            import settings_app       # noqa: F401
            import optimize_test      # noqa: F401
            import deps               # noqa: F401
            print("IMPORTTEST OK: core + themes/i18n/appicon/media/tray/settings_app/optimize_test/deps")
            sys.exit(0)
        except Exception as e:
            print("IMPORTTEST FAIL:", repr(e))
            sys.exit(2)
    main()
