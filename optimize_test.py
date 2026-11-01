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

# рядки результатів трьома мовами (раніше були лише українською)
TXT = {
    "uk": dict(ff_ok="ffmpeg і ffprobe знайдено",
               ff_no="ffmpeg НЕ знайдено — встанови: winget install Gyan.FFmpeg",
               fp_ok="ffplay є (вбудований плеєр працюватиме)",
               fp_no="ffplay відсутній — плеєр у редакторі не працюватиме",
               cpu_ok="CPU ядер: {n} — вистачає для швидкого кодування",
               cpu_low="CPU ядер: {n} — кодування буде повільнішим",
               bench_skip="Бенчмарк пропущено (немає ffmpeg)",
               need_ff="Потрібен ffmpeg — програма не працюватиме без нього.",
               bench_fail="Бенчмарк кодування не вдався",
               fps_great="Швидкість кодування: {f} к/с — відмінно (швидше за реалтайм)",
               fps_good="Швидкість кодування: {f} к/с — добре",
               fps_slow="Швидкість кодування: {f} к/с — повільно, стиснення довге",
               v_ok="Все оптимально ✓ — програма працюватиме швидко.",
               v_mid="Працездатно, але є що покращити (див. ⚠ вище).",
               v_bad="Є проблеми — виправ пункти з ✗."),
    "ru": dict(ff_ok="ffmpeg и ffprobe найдены",
               ff_no="ffmpeg НЕ найден — установи: winget install Gyan.FFmpeg",
               fp_ok="ffplay есть (встроенный плеер будет работать)",
               fp_no="ffplay отсутствует — плеер в редакторе не будет работать",
               cpu_ok="Ядер CPU: {n} — хватает для быстрого кодирования",
               cpu_low="Ядер CPU: {n} — кодирование будет медленнее",
               bench_skip="Бенчмарк пропущен (нет ffmpeg)",
               need_ff="Нужен ffmpeg — без него программа не работает.",
               bench_fail="Бенчмарк кодирования не удался",
               fps_great="Скорость кодирования: {f} к/с — отлично (быстрее реалтайма)",
               fps_good="Скорость кодирования: {f} к/с — хорошо",
               fps_slow="Скорость кодирования: {f} к/с — медленно, сжатие долгое",
               v_ok="Всё оптимально ✓ — программа будет работать быстро.",
               v_mid="Работает, но есть что улучшить (см. ⚠ выше).",
               v_bad="Есть проблемы — исправь пункты с ✗."),
    "en": dict(ff_ok="ffmpeg and ffprobe found",
               ff_no="ffmpeg NOT found — install it: winget install Gyan.FFmpeg",
               fp_ok="ffplay found (the built-in player will work)",
               fp_no="ffplay missing — the editor's player won't work",
               cpu_ok="CPU cores: {n} — enough for fast encoding",
               cpu_low="CPU cores: {n} — encoding will be slower",
               bench_skip="Benchmark skipped (no ffmpeg)",
               need_ff="ffmpeg is required — the app can't work without it.",
               bench_fail="Encoding benchmark failed",
               fps_great="Encoding speed: {f} fps — excellent (faster than real time)",
               fps_good="Encoding speed: {f} fps — good",
               fps_slow="Encoding speed: {f} fps — slow, compression will take a while",
               v_ok="Everything is optimal ✓ — the app will be fast.",
               v_mid="Works, but could be better (see ⚠ above).",
               v_bad="There are problems — fix the ✗ items."),
}


def _cpu_count():
    try:
        return os.cpu_count() or 1
    except Exception:
        return 1


def run(progress_cb=None, lang="uk"):
    """Повертає dict: {'lines': [(icon,text)...], 'verdict': str, 'ok': bool, 'score': int}."""
    T = TXT.get(lang, TXT["en"])
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
        lines.append(("✓", T["ff_ok"]))
        score += 1
    else:
        lines.append(("✗", T["ff_no"]))

    # 2) ffplay (для вбудованого плеєра/обрізки)
    p(20)
    if shutil.which("ffplay"):
        lines.append(("✓", T["fp_ok"]))
        score += 1
    else:
        lines.append(("⚠", T["fp_no"]))

    # 3) ядра CPU
    p(30)
    cores = _cpu_count()
    if cores >= 4:
        lines.append(("✓", T["cpu_ok"].format(n=cores)))
        score += 1
    else:
        lines.append(("⚠", T["cpu_low"].format(n=cores)))

    # 4) реальний бенчмарк кодування
    if not have_ff:
        lines.append(("✗", T["bench_skip"]))
        p(100)
        verdict = T["need_ff"]
        return {"lines": lines, "verdict": verdict, "ok": False, "score": score, "max": max_score}

    p(40)
    tmp = os.path.join(tempfile.gettempdir(), "dac_bench_%d.mp4" % os.getpid())
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
        lines.append(("✗", T["bench_fail"]))
    elif fps >= 120:
        lines.append(("✓", T["fps_great"].format(f=f"{fps:.0f}")))
        score += 1
    elif fps >= 60:
        lines.append(("✓", T["fps_good"].format(f=f"{fps:.0f}")))
        score += 1
    else:
        lines.append(("⚠", T["fps_slow"].format(f=f"{fps:.0f}")))

    p(100)
    if score >= max_score:
        verdict = T["v_ok"]
        ok = True
    elif score >= 2:
        verdict = T["v_mid"]
        ok = True
    else:
        verdict = T["v_bad"]
        ok = False
    return {"lines": lines, "verdict": verdict, "ok": ok, "score": score, "max": max_score}


if __name__ == "__main__":
    res = run(lambda v: None)
    for icon, text in res["lines"]:
        print(icon, text)
    print("---", res["verdict"], f"({res['score']}/{res['max']})")
