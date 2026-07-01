#!/usr/bin/env python3
"""
appicon.py — намальований у коді значок програми (без PIL).
Малює блакитно-фіолетовий (blurple) заокруглений квадрат зі стрілкою «стиснути в диск»
і пише справжній .ico + дає HICON для системного трею. Тільки стандартна бібліотека.
"""
import os
import struct
import tempfile

_ACCENT = (0x58, 0x65, 0xf2)   # blurple (r,g,b)
_WHITE = (0xff, 0xff, 0xff)


def _in_round(x, y, w, h, r):
    cx = min(max(x, r), w - 1 - r)
    cy = min(max(y, r), h - 1 - r)
    dx, dy = x - cx, y - cy
    return dx * dx + dy * dy <= r * r


def _draw(s):
    """Повертає піксельний масив (r,g,b,a), рядки зверху-вниз, розмір s×s."""
    r = int(s * 0.24)
    px = []
    for y in range(s):
        for x in range(s):
            if not _in_round(x, y, s, s, r):
                px.append((0, 0, 0, 0))
                continue
            fx, fy = x / s, y / s
            white = False
            # стовп стрілки
            if 0.22 <= fy <= 0.52 and 0.43 <= fx <= 0.57:
                white = True
            # вістря стрілки (трикутник донизу)
            if 0.44 <= fy <= 0.66:
                half = (0.66 - fy) / 0.22 * 0.21
                if abs(fx - 0.5) <= half:
                    white = True
            # смужка «диск» знизу
            if 0.72 <= fy <= 0.80 and 0.28 <= fx <= 0.72:
                white = True
            px.append((*(_WHITE if white else _ACCENT), 255))
    return px


def _ico_image(s):
    """BITMAPINFOHEADER + XOR(BGRA) + AND-маска для одного розміру."""
    px = _draw(s)
    hdr = struct.pack("<IiiHHIIiiII", 40, s, s * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    xor = bytearray()
    for row in range(s - 1, -1, -1):           # знизу-вгору
        for col in range(s):
            r, g, b, a = px[row * s + col]
            xor += bytes((b, g, r, a))
    and_stride = ((s + 31) // 32) * 4
    andmask = bytearray()
    for row in range(s - 1, -1, -1):
        bits = bytearray(and_stride)
        for col in range(s):
            if px[row * s + col][3] == 0:       # прозорий -> 1
                bits[col // 8] |= 0x80 >> (col % 8)
        andmask += bits
    return hdr + bytes(xor) + bytes(andmask)


def _build_ico(sizes=(16, 32, 48)):
    images = [_ico_image(s) for s in sizes]
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for s, img in zip(sizes, images):
        bw = 0 if s >= 256 else s
        out += struct.pack("<BBBBHHII", bw, bw, 0, 0, 1, 32, len(img), offset)
        offset += len(img)
    for img in images:
        out += img
    return out


_CACHE = None


def ico_path() -> str:
    """Створює .ico у temp (один раз) і повертає шлях."""
    global _CACHE
    if _CACHE and os.path.exists(_CACHE):
        return _CACHE
    p = os.path.join(tempfile.gettempdir(), "discord_autocompress.ico")
    try:
        with open(p, "wb") as f:
            f.write(_build_ico())
        _CACHE = p
    except OSError:
        pass
    return _CACHE or p


def get_hicon(size=32):
    """HICON із згенерованого .ico (для трею). None при помилці."""
    try:
        import ctypes
        LR_LOADFROMFILE = 0x00000010
        IMAGE_ICON = 1
        h = ctypes.windll.user32.LoadImageW(
            None, ico_path(), IMAGE_ICON, size, size, LR_LOADFROMFILE)
        return h or None
    except Exception:
        return None


def set_window_icon(win):
    """Ставить значок вікна Tk (best-effort)."""
    try:
        win.iconbitmap(ico_path())
    except Exception:
        pass


if __name__ == "__main__":
    print("icon written to:", ico_path())
