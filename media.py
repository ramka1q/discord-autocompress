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
    base, _ = os.path.splitext(path)
    return f"{base}_discord_{int(target_mb)}mb.webp"


def audio_out_name(path: str, target_mb: float) -> str:
    base, _ = os.path.splitext(path)
    return f"{base}_discord_{int(target_mb)}mb.mp3"


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
    # спершу пробуємо повний розмір, далі поступово зменшуємо сторону
    scales = [1.0, 0.85, 0.7, 0.55, 0.4, 0.3]
    qualities = [92, 85, 78, 70, 60, 50, 40]
    total = len(scales) * len(qualities)
    step = 0
    best = None
    for sc in scales:
        vf = []
        if w and sc < 1.0:
            vf = ["-vf", f"scale={max(16, int(w * sc))}:-1"]
        for q in qualities:
            if should_cancel and should_cancel():
                return False, "Скасовано.", 0.0
            step += 1
            if progress_cb:
                progress_cb(min(99.0, step / total * 100.0))
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", path, *vf, "-c:v", "libwebp",
                 "-quality", str(q), "-compression_level", "6", out_path],
                capture_output=True, creationflags=NO_WINDOW)
            if r.returncode != 0 or not os.path.exists(out_path):
                continue
            mb = os.path.getsize(out_path) / 1024 / 1024
            best = mb
            if mb <= ceiling:
                if progress_cb:
                    progress_cb(100.0)
                return True, "OK", mb
    if best is not None:
        return True, "OK", best   # не влізло ідеально, але це найменше, що вийшло
    return False, "Не вдалося стиснути фото.", 0.0


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
        return False, "Не вдалося прочитати тривалість.", 0.0
    ceiling_bits = dc_core.target_ceiling(target_mb) * 8 * 1024 * 1024
    kbps = int(ceiling_bits / dur / 1000)
    kbps = max(32, min(cap_kbps, kbps))

    for attempt in range(4):
        if should_cancel and should_cancel():
            return False, "Скасовано.", 0.0
        if progress_cb:
            progress_cb(min(95.0, 25.0 * (attempt + 1)))
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-vn", "-c:a", "libmp3lame",
             "-b:a", f"{kbps}k", out_path],
            capture_output=True, creationflags=NO_WINDOW)
        if r.returncode != 0 or not os.path.exists(out_path):
            return False, "ffmpeg не зміг перекодувати звук.", 0.0
        mb = os.path.getsize(out_path) / 1024 / 1024
        if mb <= dc_core.target_ceiling(target_mb) or kbps <= 32:
            if progress_cb:
                progress_cb(100.0)
            return True, "OK", mb
        kbps = max(32, int(kbps * (dc_core.target_ceiling(target_mb) / mb) * 0.95))
    return True, "OK", mb
