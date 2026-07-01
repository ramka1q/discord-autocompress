#!/usr/bin/env python3
"""
themes.py — кольорові палітри інтерфейсу.
Одна палітра = звичайний dict із ключами, які юзають overlay і settings_app.
Три теми: Discord (темна фіолетова), Doki Doki (рожева пастель),
Vrutik Aero (скляна блакитна, як Windows 7 Aero Glass).
Тільки стандартна бібліотека — жодних залежностей.
"""

FONT = "Segoe UI"

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

THEMES = {
    "discord": {
        "name": "Discord",
        "bg": "#313338", "panel": "#2b2d31", "dark": "#1e1f22",
        "accent": "#5865f2", "accent_h": "#4752c4",
        "text": "#f2f3f5", "muted": "#b5bac1",
        "green": "#23a55a", "red": "#ed4245", "warn": "#faa61a",
        "header": "#5865f2", "sidebar": "#2b2d31", "title_bg": "#1e1f22",
    },
    "dokidoki": {
        "name": "Doki Doki",
        "bg": "#3a2733", "panel": "#4a2f40", "dark": "#2a1b25",
        "accent": "#ff5aa8", "accent_h": "#e0458f",
        "text": "#ffe9f4", "muted": "#d9a9c4",
        "green": "#7ee0a2", "red": "#ff5c6c", "warn": "#ffcf6b",
        "header": "#ff5aa8", "sidebar": "#4a2f40", "title_bg": "#2a1b25",
    },
    "vrutik_aero": {
        "name": "Vrutik Aero",
        "bg": "#dbeafe", "panel": "#c3ddf7", "dark": "#a9cbef",
        "accent": "#2f80ed", "accent_h": "#1f66c9",
        "text": "#0b2545", "muted": "#3d5a80",
        "green": "#1e9e57", "red": "#d94141", "warn": "#e08a00",
        "header": "#7fb3f0", "sidebar": "#c9e0f7", "title_bg": "#bcd6f2",
    },
}

DEFAULT = "discord"


def palette(name: str) -> dict:
    """Повертає палітру за назвою (fallback -> Discord)."""
    return THEMES.get(name, THEMES[DEFAULT])


def order() -> list:
    """Порядок тем для меню."""
    return ["discord", "dokidoki", "vrutik_aero"]
