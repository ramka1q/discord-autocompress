#!/usr/bin/env python3
"""
deps.py — перевірка та АВТО-встановлення потрібних компонентів (ffmpeg/ffprobe/ffplay)
через winget. Друг натискає одну кнопку — і все ставиться саме. Тільки стандартна бібліотека.
"""
import os
import re
import shutil
import subprocess
import threading

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
TOOLS = ["ffmpeg", "ffprobe", "ffplay"]
WINGET_ID = "Gyan.FFmpeg"


def _winget_ffmpeg_dirs():
    """Тека bin ffmpeg, куди winget кладе Gyan.FFmpeg (пошук лише через os — без залежностей).
    Дає запасний варіант, якщо реєстр недоступний."""
    dirs = []
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages")
    try:
        for name in os.listdir(base):
            if not name.lower().startswith("gyan.ffmpeg"):
                continue
            for root, _dirs, files in os.walk(os.path.join(base, name)):
                if "ffmpeg.exe" in files and os.path.basename(root).lower() == "bin":
                    dirs.append(root)
    except Exception:
        pass
    return dirs


def refresh_path():
    """Робить щойно встановлений ffmpeg видимим БЕЗ перезапуску програми:
    1) перечитує PATH із реєстру (машинний + користувацький);
    2) запасний шлях — власна тека ffmpeg від winget (працює навіть без winreg)."""
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
    # запасний варіант: додаємо теку ffmpeg від winget напряму
    cur = os.environ.get("PATH", "")
    for d in _winget_ffmpeg_dirs():
        if d not in cur:
            os.environ["PATH"] = d + os.pathsep + cur
            cur = os.environ["PATH"]


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


# ---- встановлення з ВІДСОТКАМИ скачування (для тесту оптимізації) ----
_UNIT = {"b": 1, "kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3}
_RX_BYTES = re.compile(r"([\d.,]+)\s*(B|KB|MB|GB)\s*/\s*([\d.,]+)\s*(B|KB|MB|GB)", re.I)
_RX_PCT = re.compile(r"(\d{1,3})\s*%")


def _num(s):
    """'12.3' / '12,3' / '1,024.5' -> float."""
    s = s.strip()
    if "." in s:
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    return float(s)


def parse_progress_stream(stream, progress_cb=None, log_cb=None):
    """Читає stdout winget ПОСИМВОЛЬНО (прогрес приходить через \\r, не \\n),
    парсить відсотки з «12.3 MB / 90.4 MB» або «45%» і шле progress_cb(0..99).
    Змістовні рядки (не спінер/прогрес-бар) шле в log_cb."""
    buf = ""
    while True:
        ch = stream.read(1)
        if not ch:
            break
        if ch not in "\r\n":
            buf += ch
            continue
        line = buf.strip()
        buf = ""
        if not line:
            continue
        is_progress = False
        m = _RX_BYTES.search(line)
        if m:
            is_progress = True
            if progress_cb:
                try:
                    cur = _num(m.group(1)) * _UNIT[m.group(2).lower()]
                    tot = _num(m.group(3)) * _UNIT[m.group(4).lower()]
                    if tot > 0:
                        progress_cb(min(99, cur / tot * 100))
                except Exception:
                    pass
        else:
            m = _RX_PCT.search(line)
            if m:
                is_progress = True
                if progress_cb:
                    try:
                        progress_cb(min(99, int(m.group(1))))
                    except Exception:
                        pass
        # прогрес-рядки і спінер у лог не шлемо — там лише змістовне
        if log_cb and not is_progress and not set(line) <= set("-\\|/█▒░ .%"):
            log_cb(line)


def install_progress(progress_cb=None, log_cb=None, done_cb=None):
    """Як install(), але ще й шле ВІДСОТКИ скачування: progress_cb(0..100).
    Усі колбеки викликаються з фонового потоку — у GUI маршалити через after()."""
    def _p(v):
        if progress_cb:
            try:
                progress_cb(v)
            except Exception:
                pass

    def _log(s):
        if log_cb:
            try:
                log_cb(s)
            except Exception:
                pass

    def work():
        if not have_winget():
            _log("winget на цьому ПК не знайдено.")
            if done_cb:
                done_cb(False)
            return
        _p(0)
        cmd = ["winget", "install", "-e", "--id", WINGET_ID,
               "--accept-source-agreements", "--accept-package-agreements",
               "--disable-interactivity"]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace",
                                    creationflags=NO_WINDOW)
            parse_progress_stream(proc.stdout, _p, _log)
            proc.wait()
        except Exception as e:
            _log("Помилка запуску winget: " + str(e)[:100])
            if done_cb:
                done_cb(False)
            return
        refresh_path()
        ok = all_ok()
        _p(100)
        if done_cb:
            done_cb(ok)

    threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    print("winget:", have_winget())
    print("stan:", check(refresh=True))
