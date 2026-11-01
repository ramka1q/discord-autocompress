#!/usr/bin/env python3
"""
themes.py — кольорові палітри інтерфейсу.
Одна палітра = звичайний dict із ключами, які юзають overlay і settings_app.
Чотири теми: Discord (темна фіолетова), Midnight (глибока ніч з неоновим градієнтом),
Doki Doki (рожева пастель), Frutiger Aero (скляна блакитна, як Windows 7 Aero Glass).
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
#   accent2  — другий колір градієнта (кнопки, кільце прогресу, логотип)
#   card     — тло карток у меню / оверлеї

THEMES = {
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

DEFAULT = "discord"


def palette(name: str) -> dict:
    """Повертає палітру за назвою (fallback -> Discord)."""
    return THEMES.get(name, THEMES[DEFAULT])


def order() -> list:
    """Порядок тем для меню."""
    return ["discord", "midnight", "dokidoki", "vrutik_aero"]
