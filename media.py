#!/usr/bin/env python3
"""
media.py — стиснення ФОТО і ЗВУКУ під ліміт Discord (через ffmpeg).
Доповнює dc_core (там відео). Тільки стандартна бібліотека + ffmpeg/ffprobe у PATH.
"""
import os
import subprocess

import dc_core

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".gif"}
AUDIO_EXT = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}

NO_WINDOW = dc_core.NO_WINDOW


def kind_of(path: str) -> str:
    """'video' | 'image' | 'audio' | '' — за розширенням файла."""
    ext = os.path.splitext(path)[1].lower()
    if ext in dc_core.VIDEO_EXT:
        return "video"
    if ext in IMAGE_EXT:
        return "image"
    if ext in AUDIO_EXT:
        return "audio"
    return ""


def image_out_name(path: str, target_mb: float) -> str:
    return f"{dc_core.out_base(path)}_discord_{int(target_mb)}mb.webp"


def audio_out_name(path: str, target_mb: float) -> str:
    return f"{dc_core.out_base(path)}_discord_{int(target_mb)}mb.mp3"


def image_dims(path: str):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", path],
            capture_output=True, text=True, creationflags=NO_WINDOW).stdout.strip()
        w, h = (int(v) for v in out.split("x")[:2])
        return w, h
    except Exception:
        return 0, 0


def compress_image(path, out_path, target_mb, progress_cb=None, should_cancel=None):
    """Стискає фото у WebP під ліміт: підбирає якість, за потреби зменшує роздільність.
    Повертає (ok, message, final_mb). WebP тримає прозорість і добре тисне."""
    ceiling = dc_core.target_ceiling(target_mb)
    w, h = image_dims(path)
    # libwebp не приймає сторону >16383 px, а Discord усе одно показує зменшеним ->
    # гігантські скріни одразу обмежуємо 7680 px по довшій стороні
    sc = 1.0
    if w and h and max(w, h) > 7680:
        sc = 7680.0 / max(w, h)
    # анімований GIF -> анімований WebP, що крутиться без кінця (за замовчуванням грав би 1 раз)
    loop = ["-loop", "0"] if path.lower().endswith(".gif") else []
    qualities = [90, 80, 70, 60, 50]
    max_steps = 30
    step = 0
    best = None
    for _round in range(8):
        vf = []
        if w and sc < 1.0:
            vf = ["-vf", f"scale={max(16, int(w * sc))}:-1"]
        mb = None
        for q in qualities:
            if should_cancel and should_cancel():
                return False, dc_core.cancelled_msg(), 0.0
            step += 1
            if progress_cb:
                progress_cb(min(99.0, step / max_steps * 100.0))
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", path, *vf, "-c:v", "libwebp",
                 "-quality", str(q), "-compression_level", "6", *loop, out_path],
                capture_output=True, creationflags=NO_WINDOW)
            if r.returncode != 0 or not os.path.exists(out_path):
                continue
            mb = os.path.getsize(out_path) / 1024 / 1024
            best = mb
            if mb <= ceiling:
                if progress_cb:
                    progress_cb(100.0)
                return True, "OK", mb
            if mb > ceiling * 2.5:
                break      # якість тут не врятує — одразу зменшуємо роздільність
        if mb is None and sc >= 1.0 and not vf:
            break          # ffmpeg взагалі не відкрив файл
        # наступна роздільність — з оцінки, наскільки перевищили (площа ~ розмір файла)
        ratio = (ceiling / mb) ** 0.5 if mb else 0.7
        sc *= max(0.3, min(0.85, ratio * 0.95))
    if best is not None:
        return True, "OK", best   # не влізло ідеально, але це найменше, що вийшло
    return False, dc_core._t("core_img_fail"), 0.0


def audio_info(path: str):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, creationflags=NO_WINDOW).stdout.strip()
        return {"duration": float(out or 0)}
    except Exception:
        return {"duration": 0.0}


def compress_audio(path, out_path, target_mb, cap_kbps=320,
                   progress_cb=None, should_cancel=None):
    """Стискає звук у MP3 під ліміт: бітрейт рахується з тривалості (стеля 320, підлога 32).
    Повертає (ok, message, final_mb)."""
    info = audio_info(path)
    dur = info["duration"]
    if dur <= 0:
        return False, dc_core._t("core_nodur"), 0.0
    ceiling_bits = dc_core.target_ceiling(target_mb) * 8 * 1024 * 1024
    kbps = int(ceiling_bits / dur / 1000)
    kbps = max(32, min(cap_kbps, kbps))

    for attempt in range(4):
        if should_cancel and should_cancel():
            return False, dc_core.cancelled_msg(), 0.0
        if progress_cb:
            progress_cb(min(95.0, 25.0 * (attempt + 1)))
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-vn", "-c:a", "libmp3lame",
             "-b:a", f"{kbps}k", out_path],
            capture_output=True, creationflags=NO_WINDOW)
        if r.returncode != 0 or not os.path.exists(out_path):
            return False, dc_core._t("core_audio_fail"), 0.0
        mb = os.path.getsize(out_path) / 1024 / 1024
        if mb <= dc_core.target_ceiling(target_mb) or kbps <= 32:
            if progress_cb:
                progress_cb(100.0)
            return True, "OK", mb
        kbps = max(32, int(kbps * (dc_core.target_ceiling(target_mb) / mb) * 0.95))
    return True, "OK", mb
