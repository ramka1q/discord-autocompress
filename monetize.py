#!/usr/bin/env python3
"""
monetize.py — ОДНЕ посилання донату (безкоштовна підтримка розробника, нічого не дає).
Автор вставляє своє посилання через «Set donate link.bat» (або вручну сюди).
Відкриваємо через os.startfile (Windows, дефолтний браузер) — лише stdlib,
щоб точно йшло онлайн у старому exe. Ніякої підписки/оплати/Pro тут немає.
"""
import os

# Автор вставляє своє посилання донату (напр. https://ko-fi.com/твійнік).
DONATE_URL = ""


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


def has_donate():
    return bool(DONATE_URL.strip())
