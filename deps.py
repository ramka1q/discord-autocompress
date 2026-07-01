#!/usr/bin/env python3
"""
deps.py — перевірка та АВТО-встановлення потрібних компонентів (ffmpeg/ffprobe/ffplay)
через winget. Друг натискає одну кнопку — і все ставиться саме. Тільки стандартна бібліотека.
"""
import os
import shutil
import subprocess
import threading

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
TOOLS = ["ffmpeg", "ffprobe", "ffplay"]
WINGET_ID = "Gyan.FFmpeg"


def refresh_path():
    """Перечитує PATH із реєстру (машинний + користувацький) у поточний процес —
    щоб щойно встановлений ffmpeg став видимим БЕЗ перезапуску програми."""
    try:
        import winreg
        parts = []
        for root, key in (
            (winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, r"Environment"),
        ):
            try:
                with winreg.OpenKey(root, key) as k:
                    val, _ = winreg.QueryValueEx(k, "Path")
                    if val:
                        parts.append(os.path.expandvars(val))
            except OSError:
                pass
        if parts:
            os.environ["PATH"] = os.pathsep.join(parts) + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


def check(refresh=False) -> dict:
    """{'ffmpeg':True/False, ...}. refresh=True -> спершу перечитати PATH із реєстру."""
    if refresh:
        refresh_path()
    return {t: bool(shutil.which(t)) for t in TOOLS}


def all_ok(refresh=False) -> bool:
    return all(check(refresh).values())


def have_winget() -> bool:
    return bool(shutil.which("winget"))


def install(log_cb=None, done_cb=None):
    """Ставить ffmpeg (Gyan.FFmpeg) через winget у фоні.
    log_cb(str) — рядок логу; done_cb(ok: bool) — коли завершилось."""
    def _log(s):
        if log_cb:
            try:
                log_cb(s)
            except Exception:
                pass

    def work():
        if not have_winget():
            _log("winget на цьому ПК не знайдено.")
            _log("Постав «App Installer» з Microsoft Store — або встанови ffmpeg вручну.")
            if done_cb:
                done_cb(False)
            return
        _log("Запускаю: winget install " + WINGET_ID)
        _log("(перший раз може тривати 1–3 хв — качається ffmpeg)")
        cmd = ["winget", "install", "-e", "--id", WINGET_ID,
               "--accept-source-agreements", "--accept-package-agreements",
               "--disable-interactivity"]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace",
                                    creationflags=NO_WINDOW)
            for line in proc.stdout:
                line = line.strip()
                # winget сипле спінером/прогрес-барами — лишаємо лише змістовні рядки
                if line and not set(line) <= set("-\\|/█▒░ .%"):
                    _log(line)
            proc.wait()
        except Exception as e:
            _log("Помилка запуску winget: " + str(e)[:100])
            if done_cb:
                done_cb(False)
            return
        refresh_path()
        ok = all_ok()
        _log("Готово ✓ — усе на місці." if ok else
             "Схоже, ffmpeg ще не в PATH. Спробуй «Перевірити ще раз» або перезапусти програму.")
        if done_cb:
            done_cb(ok)

    threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    print("winget:", have_winget())
    print("stan:", check(refresh=True))
