#!/usr/bin/env python3
"""
optimize_test.py — тест «чи оптимізована програма» на цій машині.
Перевіряє наявність ffmpeg/ffprobe/ffplay, кількість ядер CPU і РЕАЛЬНУ швидкість
кодування (генерує коротке тестове відео через ffmpeg і міряє fps).
Повертає список рядків-результатів + загальний вердикт. Тільки стандартна бібліотека.
"""
import os
import shutil
import subprocess
import tempfile
import time

import dc_core

NO_WINDOW = dc_core.NO_WINDOW


def _cpu_count():
    try:
        return os.cpu_count() or 1
    except Exception:
        return 1


def run(progress_cb=None):
    """Повертає dict: {'lines': [(icon,text)...], 'verdict': str, 'ok': bool, 'score': int}."""
    lines = []
    score = 0
    max_score = 4

    def p(v):
        if progress_cb:
            progress_cb(v)

    # 1) ffmpeg / ffprobe
    p(10)
    have_ff = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
    if have_ff:
        lines.append(("✓", "ffmpeg і ffprobe знайдено"))
        score += 1
    else:
        lines.append(("✗", "ffmpeg НЕ знайдено — встанови: winget install Gyan.FFmpeg"))

    # 2) ffplay (для вбудованого плеєра/обрізки)
    p(20)
    if shutil.which("ffplay"):
        lines.append(("✓", "ffplay є (вбудований плеєр працюватиме)"))
        score += 1
    else:
        lines.append(("⚠", "ffplay відсутній — плеєр обрізки не працюватиме"))

    # 3) ядра CPU
    p(30)
    cores = _cpu_count()
    if cores >= 4:
        lines.append(("✓", f"CPU ядер: {cores} — вистачає для швидкого кодування"))
        score += 1
    else:
        lines.append(("⚠", f"CPU ядер: {cores} — кодування буде повільнішим"))

    # 4) реальний бенчмарк кодування
    if not have_ff:
        lines.append(("✗", "Бенчмарк пропущено (немає ffmpeg)"))
        p(100)
        verdict = "Потрібен ffmpeg — програма не працюватиме без нього."
        return {"lines": lines, "verdict": verdict, "ok": False, "score": score, "max": max_score}

    p(40)
    tmp = os.path.join(tempfile.gettempdir(), "dac_bench.mp4")
    fps = None
    try:
        # 5 секунд 720p тестового відео -> кодуємо x264 medium, міряємо швидкість
        t0 = time.monotonic()
        r = subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=5",
             "-c:v", "libx264", "-preset", "medium", "-b:v", "1500k", tmp],
            capture_output=True, creationflags=NO_WINDOW)
        dt = time.monotonic() - t0
        p(90)
        if r.returncode == 0 and dt > 0:
            fps = 150 / dt   # 5с×30к = 150 кадрів
    except Exception:
        pass
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

    if fps is None:
        lines.append(("✗", "Бенчмарк кодування не вдався"))
    elif fps >= 120:
        lines.append(("✓", f"Швидкість кодування: {fps:.0f} к/с — відмінно (швидше за реалтайм)"))
        score += 1
    elif fps >= 60:
        lines.append(("✓", f"Швидкість кодування: {fps:.0f} к/с — добре"))
        score += 1
    else:
        lines.append(("⚠", f"Швидкість кодування: {fps:.0f} к/с — повільно, стиснення довге"))

    p(100)
    if score >= max_score:
        verdict = "Все оптимально ✓ — програма працюватиме швидко."
        ok = True
    elif score >= 2:
        verdict = "Працездатно, але є що покращити (див. ⚠ вище)."
        ok = True
    else:
        verdict = "Є проблеми — виправ пункти з ✗."
        ok = False
    return {"lines": lines, "verdict": verdict, "ok": ok, "score": score, "max": max_score}


if __name__ == "__main__":
    res = run(lambda v: None)
    for icon, text in res["lines"]:
        print(icon, text)
    print("---", res["verdict"], f"({res['score']}/{res['max']})")
