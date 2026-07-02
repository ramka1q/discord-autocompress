#!/usr/bin/env python3
"""
stats.py — особиста статистика та історія стиснень.
Записує кожне успішне стиснення (відео/фото/звук/обрізка) у
~/.discord_overlay_stats.json: скільки файлів, скільки МБ зекономлено,
останні файли (щоб можна було скопіювати знову без повторного стиснення).
Тільки стандартна бібліотека (json/os/threading/time — усі є в exe).
"""
import json
import os
import threading
import time

PATH = os.path.join(os.path.expanduser("~"), ".discord_overlay_stats.json")
HIST_MAX = 60
# «ювілеї» зекономленого місця, МБ — на екрані «Готово» показуємо свято
MILESTONES_MB = [100, 250, 500, 1024, 2048, 5120, 10240, 20480, 51200]

_lock = threading.Lock()


def _empty():
    return {"since": 0, "files": 0, "saved_mb": 0.0, "orig_mb": 0.0,
            "by_kind": {}, "history": []}


def load() -> dict:
    d = _empty()
    try:
        with open(PATH, encoding="utf-8") as f:
            d.update(json.load(f))
    except Exception:
        pass
    return d


def _save(d):
    try:
        with open(PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except Exception:
        pass


def record(kind, orig_mb, final_mb, paths, parts=1) -> float:
    """Записує одне успішне стиснення. Повертає «ювілей» у МБ, якщо цим
    стисненням його щойно перетнули (інакше 0)."""
    kind = "video" if kind in ("video", "shrink", "trim", "gif") else (kind or "video")
    with _lock:
        d = load()
        if not d.get("since"):
            d["since"] = int(time.time())
        d["files"] = int(d.get("files", 0)) + 1
        before = float(d.get("saved_mb", 0.0))
        saved = max(0.0, float(orig_mb) - float(final_mb))
        d["saved_mb"] = before + saved
        d["orig_mb"] = float(d.get("orig_mb", 0.0)) + float(orig_mb)
        bk = d.setdefault("by_kind", {})
        bk[kind] = int(bk.get(kind, 0)) + 1
        paths = [p for p in (paths or []) if p]
        d.setdefault("history", []).insert(0, {
            "t": int(time.time()),
            "name": os.path.basename(paths[0]) if paths else "",
            "paths": paths,
            "orig": round(float(orig_mb), 2),
            "final": round(float(final_mb), 2),
            "kind": kind,
            "parts": int(parts)})
        del d["history"][HIST_MAX:]
        _save(d)
    milestone = 0
    for ms in MILESTONES_MB:
        if before < ms <= d["saved_mb"]:
            milestone = ms
    return milestone


def clear_history():
    """Чистить лише список останніх файлів; загальні лічильники лишаються."""
    with _lock:
        d = load()
        d["history"] = []
        _save(d)


def fmt_mb(mb, unit_mb="MB", unit_gb="GB") -> str:
    """54.3 -> '54.3 МБ'; 1234 -> '1.21 ГБ' (одиниці передаються з i18n)."""
    try:
        mb = float(mb)
    except Exception:
        mb = 0.0
    if mb >= 1024:
        return f"{mb / 1024:.2f} {unit_gb}"
    if mb >= 100:
        return f"{mb:.0f} {unit_mb}"
    return f"{mb:.1f} {unit_mb}"


def avg_percent(d=None) -> int:
    """Середній відсоток стиснення за весь час (0, якщо ще нема даних)."""
    d = d or load()
    try:
        orig = float(d.get("orig_mb", 0.0))
        saved = float(d.get("saved_mb", 0.0))
        if orig <= 0:
            return 0
        return int(round(saved / orig * 100))
    except Exception:
        return 0
