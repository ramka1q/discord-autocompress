#!/usr/bin/env python3
"""
themes.py — кольорові палітри інтерфейсу.
Одна палітра = звичайний dict із ключами, які юзають overlay і settings_app.
Чотири теми: Discord (темна фіолетова), Midnight (глибока ніч з неоновим градієнтом),
Doki Doki (рожева пастель), Frutiger Aero (скляна блакитна, як Windows 7 Aero Glass).
Тільки стандартна бібліотека — жодних залежностей.
"""

import os as _os


def _load_fonts():
    """Шрифти дизайну Mono лежать у fonts/ поруч із програмою — підключаємо їх лише для
    цього процесу (FR_PRIVATE), нічого в систему не ставимо. True — вийшло."""
    d = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "fonts")
    try:
        import ctypes
        add = ctypes.windll.gdi32.AddFontResourceExW
        n = 0
        for f in ("Manrope-Regular.ttf", "Manrope-Bold.ttf", "JetBrainsMono-Regular.ttf",
                  "JetBrainsMono-Bold.ttf", "InstrumentSerif-Italic.ttf", "Cormorant-Italic.ttf"):
            p = _os.path.join(d, f)
            if _os.path.exists(p) and add(ctypes.c_wchar_p(p), 0x10, 0):
                n += 1
        return n >= 4
    except Exception:
        return False


_HAVE = _load_fonts()
FONT = "Manrope" if _HAVE else "Segoe UI"                 # звичайний текст, кнопки
MONO_FONT = "JetBrains Mono" if _HAVE else "Consolas"     # підписи ВЕЛИКИМИ, цифри, час
SERIF_LAT = "Instrument Serif" if _HAVE else "Georgia"    # великі заголовки (латиниця)
SERIF_CYR = "Cormorant Italic DAC" if _HAVE else "Georgia"  # ті самі заголовки кирилицею

# ключі палітри:
#   bg       — головне тло вікна
#   panel    — картки / вторинне тло (кнопки-secondary)
#   dark     — найтемніше (поля вводу, доріжки прогресу)
#   accent   — основний колір (кнопки, смужки)
#   accent_h — accent при наведенні
#   text     — основний текст
#   muted    — приглушений текст
#   green / red / warn — статуси
#   header   — тонка смужка вгорі вікна
#   sidebar  — тло бічної навігації в меню
#   title_bg — тло кастомного заголовка
#   accent2  — другий колір градієнта (кнопки, кільце прогресу, логотип)
#   card     — тло карток у меню / оверлеї

THEMES = {
    "mono": {          # дизайн Moon (3.1): лише чорний, білий і сірий; «колір» = біле світіння
        "name": "Moon",
        "mono": True,
        "bg": "#000000", "panel": "#0a0a0a", "dark": "#000000",
        "accent": "#f5f5f2", "accent_h": "#ffffff",
        "text": "#f5f5f2", "muted": "#9b9b98", "dim": "#5d5d5b",
        "green": "#f5f5f2", "red": "#f5f5f2", "warn": "#d8d8d4",
        "header": "#f5f5f2", "sidebar": "#000000", "title_bg": "#000000",
        "accent2": "#8a8a8a", "card": "#050505",
        "line": "#1a1a1a",        # рамка панелей: білий 10% на чорному
        "btn_line": "#3d3d3d",    # рамка кнопок: білий 24%
        "btn_fill": "#0f0f0f",    # фон кнопок: білий 6%
    },
    "discord": {
        "name": "Discord",
        "bg": "#313338", "panel": "#2b2d31", "dark": "#1e1f22",
        "accent": "#5865f2", "accent_h": "#4752c4",
        "text": "#f2f3f5", "muted": "#b5bac1",
        "green": "#23a55a", "red": "#ed4245", "warn": "#faa61a",
        "header": "#5865f2", "sidebar": "#2b2d31", "title_bg": "#1e1f22",
        "accent2": "#b45cf0", "card": "#383a40",
    },
    "dokidoki": {
        "name": "Doki Doki",
        "bg": "#3a2733", "panel": "#4a2f40", "dark": "#2a1b25",
        "accent": "#ff5aa8", "accent_h": "#e0458f",
        "text": "#ffe9f4", "muted": "#d9a9c4",
        "green": "#7ee0a2", "red": "#ff5c6c", "warn": "#ffcf6b",
        "header": "#ff5aa8", "sidebar": "#4a2f40", "title_bg": "#2a1b25",
        "accent2": "#ff9f6b", "card": "#553648",
    },
    "vrutik_aero": {   # внутрішній ключ лишаємо (у збережених конфігах), назва — Frutiger Aero
        "name": "Frutiger Aero",
        "bg": "#dbeafe", "panel": "#c3ddf7", "dark": "#a9cbef",
        "accent": "#2f80ed", "accent_h": "#1f66c9",
        "text": "#0b2545", "muted": "#3d5a80",
        "green": "#1e9e57", "red": "#d94141", "warn": "#e08a00",
        "header": "#7fb3f0", "sidebar": "#c9e0f7", "title_bg": "#bcd6f2",
        "accent2": "#2ec4e8", "card": "#eef5ff",
    },
    "midnight": {
        "name": "Midnight",
        "bg": "#0f1117", "panel": "#161923", "dark": "#0a0c11",
        "accent": "#7c5cff", "accent_h": "#6a4be6",
        "text": "#eef0ff", "muted": "#9aa1c4",
        "green": "#2fd17c", "red": "#ff5470", "warn": "#ffb547",
        "header": "#7c5cff", "sidebar": "#12141c", "title_bg": "#0a0c11",
        "accent2": "#21c7ff", "card": "#1b1f2c",
    },
}

DEFAULT = "mono"


def palette(name: str) -> dict:
    """Повертає палітру за назвою (fallback -> Discord)."""
    return THEMES.get(name, THEMES[DEFAULT])


def order() -> list:
    """Порядок тем для меню."""
    return ["mono", "discord", "midnight", "dokidoki", "vrutik_aero"]
