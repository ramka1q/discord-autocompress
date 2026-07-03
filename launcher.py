#!/usr/bin/env python3
"""
Launcher + Інсталятор + Деінсталятор (бутстрап для .exe)
========================================================
Цей файл збирається в один DiscordAutoCompress.exe (PyInstaller). Exe НЕСЕ в собі
Python, тож користувачу НЕ треба нічого встановлювати. Режими:

  • СВІЖИЙ exe (скачаний, ще не встановлений) -> ГРАФІЧНИЙ ІНСТАЛЯТОР:
    вибір папки, скачує ВСІ файли програми з GitHub у видиму папку (не «просто exe»),
    ярлики (робочий стіл / автозапуск / меню Пуск), реєструє деінсталятор у
    «Програми та засоби» Windows.
  • exe у ВСТАНОВЛЕНІЙ папці (поруч маркер .installed) -> запускає програму;
    файли коду лежать ПОРУЧ з exe — все видно.
  • `--uninstall` -> ДЕІНСТАЛЯТОР: прибирає ярлики/реєстр і видаляє папку.
  • СТАРА установка (код у %LOCALAPPDATA%\\DiscordAutoCompress, без маркера) —
    працює як раніше, нічого не ламається.
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
import tkinter.filedialog as _fd
import tkinter.colorchooser   # noqa: F401
import tkinter.font           # noqa: F401
import ctypes             # noqa: F401
import ctypes.wintypes    # noqa: F401
import subprocess
import threading
import queue              # noqa: F401
import tempfile           # noqa: F401
import shutil
import time               # noqa: F401
import re                 # noqa: F401
import math               # noqa: F401
import datetime           # noqa: F401
import struct             # noqa: F401  (appicon малює .ico)
import zlib               # noqa: F401  (appicon пакує PNG у .ico)
import winreg

APP_TITLE = "Discord Auto-Compress"
REPO_RAW = os.environ.get(
    "DAC_REPO_RAW",
    "https://raw.githubusercontent.com/ramka1q/discord-autocompress/main"
)
# стара (легасі) тека коду — для установок, зроблених ДО появи інсталятора
LEGACY_APPDIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                             "DiscordAutoCompress")
DEFAULT_DIR = os.path.join(os.path.expanduser("~"), "DiscordAutoCompress")
MARKER = ".installed"
UNINST_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\DiscordAutoCompress"
TIMEOUT = 20
NO_WINDOW = 0x08000000


def exe_path() -> str:
    return os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)


def exe_dir() -> str:
    return os.path.dirname(exe_path())


def is_installed_here() -> bool:
    return getattr(sys, "frozen", False) and os.path.exists(os.path.join(exe_dir(), MARKER))


def _fetch(rel: str) -> bytes:
    url = REPO_RAW.rstrip("/") + "/" + "/".join(urllib.parse.quote(p) for p in rel.split("/"))
    req = urllib.request.Request(url, headers={"User-Agent": "DAC-Launcher/2.0",
                                               "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def sync_code(appdir: str, log=None):
    """Тягне .py-файли програми з GitHub у appdir. Повертає к-ть оновлених (-1 = без мережі)."""
    try:
        manifest = json.loads(_fetch("manifest.json").decode("utf-8"))
    except Exception:
        return -1
    files = [f for f in manifest.get("files", []) if f.endswith(".py")]
    n = 0
    for i, rel in enumerate(files):
        try:
            data = _fetch(rel)
        except Exception:
            continue
        dst = os.path.join(appdir, rel)
        try:
            os.makedirs(os.path.dirname(dst) or appdir, exist_ok=True)
            if os.path.exists(dst) and open(dst, "rb").read() == data:
                continue
            with open(dst + ".new", "wb") as f:
                f.write(data)
            os.replace(dst + ".new", dst)
            n += 1
            if log:
                log(f"  ✓ {rel}  ({i + 1}/{len(files)})")
        except OSError:
            pass
    return n


# ------------------------------------------------------------- ярлики ------ #
def _ps(script: str):
    subprocess.run(["powershell", "-NoProfile", "-Command", script],
                   creationflags=NO_WINDOW, capture_output=True)


def make_lnk(lnk: str, target: str, args: str = "", desc: str = APP_TITLE):
    ps = ("$sh=New-Object -ComObject WScript.Shell;"
          "$s=$sh.CreateShortcut('%s');$s.TargetPath='%s';$s.Arguments='%s';"
          "$s.WorkingDirectory='%s';$s.WindowStyle=7;$s.Description='%s';$s.Save()"
          % (lnk, target, args, os.path.dirname(target), desc))
    _ps(ps)


def _startup_lnk():
    return os.path.join(os.environ.get("APPDATA", ""),
                        r"Microsoft\Windows\Start Menu\Programs\Startup",
                        "Discord Auto-Compress.lnk")


def _desktop_lnk():
    return os.path.join(os.path.expanduser("~"), "Desktop", "Discord Auto-Compress.lnk")


def _startmenu_dir():
    return os.path.join(os.environ.get("APPDATA", ""),
                        r"Microsoft\Windows\Start Menu\Programs", "Discord Auto-Compress")


# ------------------------------------------------- реєстр (Програми та засоби) --- #
def register_uninstall(dstdir: str, exe: str):
    try:
        size_kb = 0
        for root_, _, fs in os.walk(dstdir):
            for f in fs:
                try:
                    size_kb += os.path.getsize(os.path.join(root_, f)) // 1024
                except OSError:
                    pass
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINST_KEY)
        for name, val in (("DisplayName", APP_TITLE),
                          ("DisplayIcon", exe),
                          ("UninstallString", f'"{exe}" --uninstall'),
                          ("InstallLocation", dstdir),
                          ("Publisher", "ramka1q"),
                          ("DisplayVersion", "1.0")):
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(k)
    except OSError:
        pass


def unregister_uninstall():
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINST_KEY)
    except OSError:
        pass


# ------------------------------------------------------------ встановлення --- #
def install_to(dstdir: str, desktop=True, autostart=True, shortcuts=True, log=None,
               lang=None):
    """Ставить програму у dstdir: копія exe + всі .py з GitHub (видимі файли) +
    маркер + ярлики + реєстрація деінсталятора. Повертає (ok, повідомлення).
    lang — вибрана в інсталяторі мова: пишеться у конфіг ПРОГРАМИ (щоб вона
    одразу стартувала цією мовою)."""
    log = log or (lambda s: None)
    T = INST_L.get(lang or "uk", INST_L["en"])
    dstdir = os.path.abspath(dstdir)
    try:
        os.makedirs(dstdir, exist_ok=True)
    except OSError as e:
        return False, T["err_dir"] + str(e)

    dst_exe = os.path.join(dstdir, "DiscordAutoCompress.exe")
    src = exe_path()
    if getattr(sys, "frozen", False) and os.path.normcase(src) != os.path.normcase(dst_exe):
        log(T["copying"])
        try:
            shutil.copy2(src, dst_exe)
        except OSError as e:
            return False, T["err_copy"] + str(e)
    elif not getattr(sys, "frozen", False):
        dst_exe = src   # dev-режим (тести): «exe» = цей .py

    log(T["downloading"])
    n = sync_code(dstdir, log)
    if not os.path.exists(os.path.join(dstdir, "discord_overlay.py")):
        return False, T["err_net"]
    log(T["files_ok"].format(n=max(0, n)))

    # маркер установки (пам'ятає вибір автозапуску)
    try:
        with open(os.path.join(dstdir, MARKER), "w", encoding="utf-8") as f:
            json.dump({"autostart": bool(autostart), "desktop": bool(desktop)}, f)
        open(os.path.join(dstdir, ".autoupdate"), "w").close()
    except OSError:
        pass
    if lang:
        _write_lang(lang)   # мова з інсталятора -> конфіг програми (зберігається і в ній)

    if shortcuts and getattr(sys, "frozen", False):
        log(T["mk_short"])
        if desktop:
            make_lnk(_desktop_lnk(), dst_exe)
        if autostart:
            make_lnk(_startup_lnk(), dst_exe, "--background")
        try:
            sm = _startmenu_dir()
            os.makedirs(sm, exist_ok=True)
            make_lnk(os.path.join(sm, "Discord Auto-Compress.lnk"), dst_exe)
            make_lnk(os.path.join(sm, "Uninstall Discord Auto-Compress.lnk"),
                     dst_exe, "--uninstall", desc="Uninstall")
        except OSError:
            pass
        log(T["reg"])
        register_uninstall(dstdir, dst_exe)
    return True, dst_exe


# ------------------------------------------------------------- видалення ---- #
def _kill_other_instances():
    """Глушить запущені копії програми (але НЕ цей процес-деінсталятор)."""
    _ps("Get-Process DiscordAutoCompress -ErrorAction SilentlyContinue | "
        f"Where-Object {{$_.Id -ne {os.getpid()}}} | Stop-Process -Force")


def do_uninstall(dstdir: str, purge_cfg=False, shortcuts=True, delete_dir=True):
    """Прибирає ярлики/реєстр/(налаштування) і планує видалення папки після виходу."""
    _kill_other_instances()
    if shortcuts:
        for p in (_startup_lnk(), _desktop_lnk()):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
        shutil.rmtree(_startmenu_dir(), ignore_errors=True)
        unregister_uninstall()
    if purge_cfg:
        home = os.path.expanduser("~")
        for f in (".discord_overlay.json", ".discord_overlay_stats.json",
                  ".discord_done_sound.wav"):
            try:
                p = os.path.join(home, f)
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
    if delete_dir and os.path.exists(os.path.join(dstdir, MARKER)):
        # папку видаляємо ПІСЛЯ виходу процесу (exe не може видалити сам себе живим)
        subprocess.Popen('ping 127.0.0.1 -n 4 >nul & rd /s /q "%s"' % dstdir,
                         shell=True, creationflags=NO_WINDOW)


# ------------------------------------------------- мова інсталятора/програми --- #
CONFIG_NAME = ".discord_overlay.json"

INST_L = {
    "uk": dict(win="Встановлення", sub="Інсталятор скачає всі файли програми у вибрану папку\n(все видно, без прихованих тек) і додасть деінсталятор.",
               folder="Папка встановлення:", browse="Огляд…",
               desk="Ярлик на робочому столі",
               auto="Запускати разом з Windows (фонове стиснення)",
               install="Встановити  ⬇", cancel="Скасувати", installing="Встановлюю…",
               done="Готово! Програма встановлена ✓", installed_in="Встановлено у: ",
               launch="Запустити зараз  ▶", close="Закрити",
               copying="Копіюю програму…", downloading="Скачую файли програми з GitHub…",
               files_ok="Готово: файли на місці (оновлено {n}).",
               mk_short="Створюю ярлики…", reg="Реєструю в «Програми та засоби»…",
               err_dir="Не вдалося створити папку: ", err_copy="Не вдалося скопіювати exe: ",
               err_net="Не вдалося скачати файли — перевір інтернет і спробуй ще раз.",
               u_q="Видалити Discord Auto-Compress?",
               u_body="Буде прибрано ярлики, автозапуск і папку:\n",
               u_purge="Видалити також мої налаштування і статистику",
               u_del="Видалити", u_done="Видалено. Папка зникне за кілька секунд. 👋"),
    "ru": dict(win="Установка", sub="Инсталлятор скачает все файлы программы в выбранную папку\n(всё видно, без скрытых папок) и добавит деинсталлятор.",
               folder="Папка установки:", browse="Обзор…",
               desk="Ярлык на рабочем столе",
               auto="Запускать вместе с Windows (фоновое сжатие)",
               install="Установить  ⬇", cancel="Отмена", installing="Устанавливаю…",
               done="Готово! Программа установлена ✓", installed_in="Установлено в: ",
               launch="Запустить сейчас  ▶", close="Закрыть",
               copying="Копирую программу…", downloading="Скачиваю файлы программы с GitHub…",
               files_ok="Готово: файлы на месте (обновлено {n}).",
               mk_short="Создаю ярлыки…", reg="Регистрирую в «Программы и компоненты»…",
               err_dir="Не удалось создать папку: ", err_copy="Не удалось скопировать exe: ",
               err_net="Не удалось скачать файлы — проверь интернет и попробуй ещё раз.",
               u_q="Удалить Discord Auto-Compress?",
               u_body="Будут убраны ярлыки, автозапуск и папка:\n",
               u_purge="Удалить также мои настройки и статистику",
               u_del="Удалить", u_done="Удалено. Папка исчезнет через пару секунд. 👋"),
    "en": dict(win="Setup", sub="The installer downloads all program files into the chosen folder\n(everything visible, no hidden dirs) and adds an uninstaller.",
               folder="Install folder:", browse="Browse…",
               desk="Desktop shortcut",
               auto="Start with Windows (background compression)",
               install="Install  ⬇", cancel="Cancel", installing="Installing…",
               done="Done! The app is installed ✓", installed_in="Installed to: ",
               launch="Launch now  ▶", close="Close",
               copying="Copying the app…", downloading="Downloading program files from GitHub…",
               files_ok="All files in place (updated {n}).",
               mk_short="Creating shortcuts…", reg="Registering in Apps & Features…",
               err_dir="Could not create the folder: ", err_copy="Could not copy the exe: ",
               err_net="Could not download files — check your internet and try again.",
               u_q="Uninstall Discord Auto-Compress?",
               u_body="Shortcuts, autostart and this folder will be removed:\n",
               u_purge="Also delete my settings and statistics",
               u_del="Uninstall", u_done="Removed. The folder disappears in a few seconds. 👋"),
}
LANG_NAMES = (("uk", "Українська"), ("ru", "Русский"), ("en", "English"))


def _sys_lang() -> str:
    try:
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return {0x22: "uk", 0x19: "ru"}.get(lid, "en")
    except Exception:
        return "en"


def _cfg_lang() -> str:
    """Мова з конфіга програми (якщо вже є), інакше — мова Windows."""
    try:
        with open(os.path.join(os.path.expanduser("~"), CONFIG_NAME), encoding="utf-8") as f:
            lang = json.load(f).get("lang")
        if lang in INST_L:
            return lang
    except Exception:
        pass
    return _sys_lang()


def _write_lang(lang: str, home: str = None):
    """Зберігає вибрану мову в конфіг ПРОГРАМИ (utf-8 БЕЗ BOM — BOM валить json.load).
    Конфіг частковий — load_config сам доллє решту дефолтів."""
    p = os.path.join(home or os.path.expanduser("~"), CONFIG_NAME)
    try:
        cfg = {}
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                cfg = json.load(f)
        cfg["lang"] = lang
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)
        return True
    except Exception:
        return False


# --------------------------------------------------------- GUI інсталятора --- #
BG, PANEL, DARK = "#313338", "#2b2d31", "#1e1f22"
ACCENT, ACCENT_H, TEXT, MUTED = "#5865f2", "#4752c4", "#f2f3f5", "#b5bac1"
GREEN, RED = "#3ba55d", "#f23f43"
F = "Segoe UI"


def _win(title, w, h):
    r = tkinter.Tk()
    r.title(title)
    r.configure(bg=BG)
    r.resizable(False, False)
    sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
    r.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
    r.attributes("-topmost", True)
    return r


def _btn(parent, text, cmd, primary=True):
    bg, hov = (ACCENT, ACCENT_H) if primary else (PANEL, DARK)
    b = tkinter.Button(parent, text=text, command=cmd, bg=bg, fg=TEXT,
                       activebackground=hov, activeforeground=TEXT, relief="flat",
                       font=(F, 10, "bold"), bd=0, padx=16, pady=8, cursor="hand2")
    b.bind("<Enter>", lambda e: b.config(bg=hov))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b


def run_installer():
    state = {"lang": _cfg_lang(), "busy": False}
    path_var_holder = {}
    r = _win(f"Setup — {APP_TITLE}", 560, 512)
    v_desk = tkinter.BooleanVar(value=True)
    v_auto = tkinter.BooleanVar(value=True)
    path_var = tkinter.StringVar(value=DEFAULT_DIR)
    body = tkinter.Frame(r, bg=BG)
    body.pack(fill="both", expand=True)
    lines = []

    def render():
        T = INST_L[state["lang"]]
        r.title(f'{T["win"]} — {APP_TITLE}')
        for w in body.winfo_children():
            w.destroy()
        # ---- вибір мови: перше, що бачить юзер; вибір зберігається і в програмі ----
        lrow = tkinter.Frame(body, bg=BG); lrow.pack(pady=(14, 0))
        for code, name in LANG_NAMES:
            act = code == state["lang"]
            b = tkinter.Button(lrow, text=name, relief="flat", bd=0, cursor="hand2",
                               bg=ACCENT if act else PANEL, fg=TEXT,
                               activebackground=ACCENT_H, activeforeground=TEXT,
                               font=(F, 9, "bold"), padx=12, pady=4,
                               command=lambda c=code: switch(c))
            b.pack(side="left", padx=3)
        tkinter.Label(body, text="⬇  Discord Auto-Compress", bg=BG, fg=TEXT,
                      font=(F, 16, "bold")).pack(pady=(10, 2))
        tkinter.Label(body, text=T["sub"], bg=BG, fg=MUTED, font=(F, 9),
                      justify="center").pack()

        row = tkinter.Frame(body, bg=BG); row.pack(fill="x", padx=24, pady=(14, 4))
        tkinter.Label(row, text=T["folder"], bg=BG, fg=TEXT,
                      font=(F, 9, "bold")).pack(anchor="w")
        row2 = tkinter.Frame(body, bg=BG); row2.pack(fill="x", padx=24)
        ent = tkinter.Entry(row2, textvariable=path_var, bg=DARK, fg=TEXT,
                            insertbackground=TEXT, relief="flat", font=(F, 10))
        ent.pack(side="left", fill="x", expand=True, ipady=6)

        def browse():
            d = _fd.askdirectory(parent=r)
            if d:
                path_var.set(os.path.join(os.path.abspath(d), "DiscordAutoCompress")
                             if os.path.basename(d).lower() != "discordautocompress" else d)
        _btn(row2, T["browse"], browse, primary=False).pack(side="left", padx=(8, 0))

        for v, t in ((v_desk, T["desk"]), (v_auto, T["auto"])):
            tkinter.Checkbutton(body, text=t, variable=v, bg=BG, fg=TEXT, selectcolor=DARK,
                                activebackground=BG, activeforeground=TEXT,
                                font=(F, 9), cursor="hand2").pack(anchor="w", padx=24, pady=1)

        logbox = tkinter.Text(body, height=7, bg=DARK, fg=MUTED, relief="flat",
                              font=("Consolas", 8), state="disabled")
        logbox.pack(fill="x", padx=24, pady=(10, 6))
        status = tkinter.Label(body, text="", bg=BG, fg=MUTED, font=(F, 9, "bold"))
        status.pack()
        btns = tkinter.Frame(body, bg=BG); btns.pack(pady=8)
        ib = _btn(btns, T["install"], lambda: start())
        ib.pack(side="left", padx=6)
        _btn(btns, T["cancel"], r.destroy, primary=False).pack(side="left", padx=6)

        def pump():
            try:
                if lines:
                    logbox.config(state="normal")
                    while lines:
                        logbox.insert("end", lines.pop(0) + "\n")
                    logbox.see("end")
                    logbox.config(state="disabled")
                r.after(150, pump)
            except tkinter.TclError:
                pass
        pump()

        def start():
            if state["busy"]:
                return
            state["busy"] = True
            ib.config(state="disabled")
            status.config(text=T["installing"], fg=TEXT)

            def work():
                ok, msg = install_to(path_var.get().strip() or DEFAULT_DIR,
                                     desktop=v_desk.get(), autostart=v_auto.get(),
                                     log=lines.append, lang=state["lang"])
                def done():
                    state["busy"] = False
                    if ok:
                        status.config(text=T["done"], fg=GREEN)
                        lines.append(T["installed_in"] + os.path.dirname(msg))
                        for w in btns.winfo_children():
                            w.destroy()
                        def launch():
                            try:
                                subprocess.Popen([msg], cwd=os.path.dirname(msg),
                                                 close_fds=True)
                            except OSError:
                                pass
                            r.destroy()
                        _btn(btns, T["launch"], launch).pack(side="left", padx=6)
                        _btn(btns, T["close"], r.destroy, primary=False).pack(side="left", padx=6)
                    else:
                        status.config(text=msg, fg=RED)
                        ib.config(state="normal")
                r.after(0, done)
            threading.Thread(target=work, daemon=True).start()

    def switch(code):
        if not state["busy"] and code != state["lang"]:
            state["lang"] = code
            render()

    path_var_holder["v"] = path_var
    render()
    r.mainloop()


def run_uninstaller():
    d = exe_dir()
    T = INST_L[_cfg_lang()]   # мовою, яку юзер обрав при встановленні/у програмі
    r = _win(f'{T["u_del"]} — {APP_TITLE}', 480, 260)
    tkinter.Label(r, text="🗑  " + T["u_q"], bg=BG, fg=TEXT,
                  font=(F, 14, "bold")).pack(pady=(24, 4))
    tkinter.Label(r, text=T["u_body"] + d, bg=BG, fg=MUTED, font=(F, 9),
                  justify="center").pack()
    v_purge = tkinter.BooleanVar(value=False)
    tkinter.Checkbutton(r, text=T["u_purge"], variable=v_purge, bg=BG, fg=TEXT,
                        selectcolor=DARK, activebackground=BG, activeforeground=TEXT,
                        font=(F, 9), cursor="hand2").pack(pady=10)
    btns = tkinter.Frame(r, bg=BG); btns.pack(pady=6)

    def go():
        do_uninstall(d, purge_cfg=v_purge.get())
        for w in btns.winfo_children():
            w.destroy()
        tkinter.Label(r, text=T["u_done"], bg=BG, fg=GREEN,
                      font=(F, 10, "bold")).pack()
        r.after(1800, r.destroy)

    b = _btn(btns, T["u_del"], go)
    b.config(bg=RED, activebackground="#c93235")
    b.bind("<Enter>", lambda e: b.config(bg="#c93235"))
    b.bind("<Leave>", lambda e: b.config(bg=RED))
    b.pack(side="left", padx=6)
    _btn(btns, T["cancel"], r.destroy, primary=False).pack(side="left", padx=6)
    r.mainloop()


# ------------------------------------------------------------- запуск app --- #
def ensure_autostart(appdir: str, installed: bool):
    """Startup-ярлик: у встановленому режимі — шануємо вибір з інсталятора;
    у легасі — стара поведінка (завжди лагодимо ярлик на поточний exe)."""
    if not getattr(sys, "frozen", False):
        return
    want = True
    if installed:
        try:
            with open(os.path.join(appdir, MARKER), encoding="utf-8") as f:
                want = bool(json.load(f).get("autostart", True))
        except Exception:
            want = True
    if not want:
        return
    try:
        lnk = _startup_lnk()
        exe = sys.executable
        ps = ("$p='%s';"
              "$sh=New-Object -ComObject WScript.Shell;"
              "$cur=if(Test-Path $p){$s=$sh.CreateShortcut($p);$s.TargetPath+'|'+$s.Arguments}else{''};"
              "if($cur -ne '%s|--background'){"
              "$s=$sh.CreateShortcut($p);$s.TargetPath='%s';$s.Arguments='--background';"
              "$s.WorkingDirectory='%s';$s.WindowStyle=7;"
              "$s.Description='Discord Auto-Compress';$s.Save()}"
              % (lnk, exe, exe, os.path.dirname(exe)))
        _ps(ps)
    except Exception:
        pass


def have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffplay") and shutil.which("ffprobe"))


def run_app(appdir: str, installed: bool):
    os.makedirs(appdir, exist_ok=True)
    sync_code(appdir)
    ensure_autostart(appdir, installed)
    try:
        open(os.path.join(appdir, ".autoupdate"), "w").close()
    except OSError:
        pass

    if not os.path.exists(os.path.join(appdir, "discord_overlay.py")):
        r = tkinter.Tk(); r.withdraw()
        _mb.showerror(APP_TITLE, "Для першого запуску потрібен інтернет "
                                 "(завантаження програми з GitHub).")
        return

    if not have_ffmpeg():
        r = tkinter.Tk(); r.withdraw()
        _mb.showwarning(APP_TITLE,
                        "Не знайдено ffmpeg/ffplay.\n"
                        "Відкрий Налаштування → Встановлення, там є кнопка "
                        "«Встановити все автоматично».")

    sys.path.insert(0, appdir)
    os.chdir(appdir)
    import discord_overlay
    discord_overlay.run_app(open_settings="--background" not in sys.argv)


def main():
    if "--uninstall" in sys.argv:
        run_uninstaller()
        return
    if is_installed_here():
        run_app(exe_dir(), installed=True)
        return
    if getattr(sys, "frozen", False):
        legacy = os.path.exists(os.path.join(LEGACY_APPDIR, "discord_overlay.py"))
        # свіжий exe (нема ні установки, ні легасі-коду) або явний --install -> інсталятор
        if "--install" in sys.argv or (not legacy and "--background" not in sys.argv):
            run_installer()
            return
        run_app(LEGACY_APPDIR, installed=False)   # легасі-режим — як раніше
        return
    run_app(LEGACY_APPDIR, installed=False)       # dev-запуск з .py


if __name__ == "__main__":
    # приховані тест-режими (без GUI) — для перевірки установки/видалення
    try:      # консоль Windows (cp1251) падає на ✓ у принтах — робимо вивід стійким
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if "--test-install" in sys.argv:
        d = sys.argv[sys.argv.index("--test-install") + 1]
        ok, msg = install_to(d, desktop=False, autostart=False, shortcuts=False,
                             log=lambda s: print(s))
        print("INSTALL", "OK" if ok else "FAIL", msg)
        sys.exit(0 if ok else 2)
    if "--test-lang" in sys.argv:
        i = sys.argv.index("--test-lang")
        lang, home = sys.argv[i + 1], sys.argv[i + 2]
        ok = _write_lang(lang, home)
        print("WRITE", ok,
              open(os.path.join(home, CONFIG_NAME), encoding="utf-8").read())
        sys.exit(0 if ok else 2)
    if "--test-uninstall" in sys.argv:
        d = sys.argv[sys.argv.index("--test-uninstall") + 1]
        do_uninstall(d, purge_cfg=False, shortcuts=False, delete_dir=True)
        print("UNINSTALL scheduled for", d)
        sys.exit(0)
    if "--selftest" in sys.argv:
        os.makedirs(LEGACY_APPDIR, exist_ok=True)
        sync_code(LEGACY_APPDIR)
        pys = [f for f in os.listdir(LEGACY_APPDIR) if f.endswith(".py")]
        print("APPDIR:", LEGACY_APPDIR)
        print("downloaded .py:", sorted(pys))
        print("discord_overlay.py present:",
              os.path.exists(os.path.join(LEGACY_APPDIR, "discord_overlay.py")))
        print("ffmpeg present:", have_ffmpeg())
        sys.exit(0)
    if "--importtest" in sys.argv:
        os.makedirs(LEGACY_APPDIR, exist_ok=True)
        sync_code(LEGACY_APPDIR)
        sys.path.insert(0, LEGACY_APPDIR)
        os.chdir(LEGACY_APPDIR)
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
