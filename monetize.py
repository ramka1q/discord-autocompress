#!/usr/bin/env python3
"""
monetize.py — a SINGLE free donation link (support the developer, gives nothing back).
The author sets the link via "Set donate link.bat" (or by hand here).
Opened with os.startfile (Windows default browser) — stdlib only, so it works
online in the old exe. No subscription, no payment, no "Pro" here.
"""
import os

# The author pastes their donation link here (e.g. https://ko-fi.com/yourname).
DONATE_URL = ""


def open_url(url):
    """Open the URL in the default browser. True on success."""
    url = (url or "").strip()
    if not url:
        return False
    try:
        os.startfile(url)                       # Windows -> default browser
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
