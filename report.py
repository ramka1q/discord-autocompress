#!/usr/bin/env python3
"""
report.py — «Надіслати звіт про помилку».
Збирає в ОДИН .txt усе, що потрібно авторові, щоб зрозуміти проблему: версію,
Windows, ffmpeg, відеокарту, налаштування, коротку статистику і хвіст журналу
%TEMP%\\dac_debug.log. Файл кладеться на Робочий стіл (або в TEMP) — друг просто
вставляє його в Discord (Ctrl+V). Лише stdlib (без zipfile — його нема в старому exe).
"""
import json
import os
import subprocess
import sys
import tempfile
import time

import dc_core

LOG_LINES = 400


def _ffmpeg_version():
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-version"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace",
                             creationflags=dc_core.NO_WINDOW, timeout=15).stdout
        return out.splitlines()[0] if out else "?"
    except Exception as e:
        return f"не знайдено ({e!r})"


def _windows():
    try:
        v = sys.getwindowsversion()
        return f"Windows {v.major}.{v.minor} build {v.build}"
    except Exception:
        return sys.platform


def _log_tail():
    try:
        with open(dc_core.DEBUG_LOG, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-LOG_LINES:])
    except OSError:
        return "(журнал порожній)"


def _target_dir():
    for d in (os.path.join(os.path.expanduser("~"), "Desktop"),
              os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop"),
              tempfile.gettempdir()):
        if os.path.isdir(d) and dc_core._dir_writable(d):
            return d
    return tempfile.gettempdir()


def build(cfg, version, released):
    """Пише звіт і повертає шлях до .txt."""
    try:
        import stats
        st = stats.load()
        stats_line = (f"files={st.get('files', 0)} saved_mb={st.get('saved_mb', 0):.1f} "
                      f"by_kind={st.get('by_kind', {})}")
    except Exception as e:
        stats_line = repr(e)
    try:
        import deps
        dep = deps.check()
    except Exception as e:
        dep = repr(e)
    safe_cfg = {k: v for k, v in (cfg or {}).items() if k != "sound_file"}
    hw = dc_core.hw_encoder()
    lines = [
        "Discord Auto-Compress — bug report",
        "=" * 44,
        f"created:   {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"version:   {version} (released {released}), build {dc_core.BUILD}",
        f"system:    {_windows()}, Python {sys.version.split()[0]}, "
        f"{'exe' if getattr(sys, 'frozen', False) else 'source'}, cpu={os.cpu_count()}",
        f"ffmpeg:    {_ffmpeg_version()}",
        f"deps:      {dep}",
        f"gpu:       {dc_core.HW_NAMES.get(hw, 'none')} | mode={dc_core.ENCODER_MODE} "
        f"best={dc_core.ENCODER_BEST or '-'}",
        f"stats:     {stats_line}",
        "",
        "settings:",
        json.dumps(safe_cfg, ensure_ascii=False, indent=1),
        "",
        f"last {LOG_LINES} log lines ({dc_core.DEBUG_LOG}):",
        "-" * 44,
        _log_tail(),
    ]
    path = os.path.join(_target_dir(),
                        time.strftime("DiscordAutoCompress_report_%Y%m%d_%H%M%S.txt"))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path
