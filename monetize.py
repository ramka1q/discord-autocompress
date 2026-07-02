#!/usr/bin/env python3
"""
monetize.py — посилання підтримки/донату + продажу готового .exe («Pro»).
Автор заповнює URL-и через «Set support links.bat» (або вручну тут).
Порожній рядок = кнопка ховається. Відкриваємо через os.startfile (Windows,
дефолтний браузер) — лише stdlib, щоб точно йшло онлайн у старому exe.
"""
import os

# Заповнюється автором (Set support links.bat). Порожнє = кнопка не показується.
SUPPORT_URL = ""
PRO_URL = ""


def open_url(url):
    """Відкриває URL у браузері. True при успіху."""
    url = (url or "").strip()
    if not url:
        return False
    try:
        os.startfile(url)                       # Windows -> дефолтний браузер
        return True
    except Exception:
        try:
            import subprocess
            subprocess.Popen(["cmd", "/c", "start", "", url])
            return True
        except Exception:
            return False


def has_support():
    return bool(SUPPORT_URL.strip())


def has_pro():
    return bool(PRO_URL.strip())
