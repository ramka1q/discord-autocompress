#!/usr/bin/env python3
"""
appicon.py — намальований у коді значок програми (без PIL).
Малює блакитно-фіолетовий (blurple) заокруглений квадрат зі стрілкою «стиснути в диск»
і пише справжній .ico + дає HICON для системного трею. Тільки стандартна бібліотека.
"""
import ctypes
import os
import struct
import tempfile
import zlib

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


def _png_bytes(s):
    """PNG (RGBA) для великих розмірів значка (256 у ICO прийнято зберігати як PNG)."""
    px = _draw(s)
    raw = bytearray()
    for y in range(s):
        raw.append(0)                      # фільтр рядка = none
        for x in range(s):
            r, g, b, a = px[y * s + x]
            raw += bytes((r, g, b, a))

    def chunk(typ, data):
        body = typ + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xffffffff)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", s, s, 8, 6, 0, 0, 0)   # 8-біт, RGBA
    idat = zlib.compress(bytes(raw), 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def _build_ico(sizes=(16, 24, 32, 48, 64, 128, 256)):
    # маленькі — BMP (XOR+AND), 256 — PNG (стандарт для великих значків Windows)
    images = [_png_bytes(s) if s >= 256 else _ico_image(s) for s in sizes]
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
    """Ставить значок вікна Tk (best-effort) і нашу назву на панелі завдань."""
    try:
        win.iconbitmap(ico_path())
    except Exception:
        pass
    try:
        win.update_idletasks()
        hw = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        brand_window(hw)
    except Exception:
        pass


# ---- назва програми на панелі завдань / у списку переходів (ПКМ по кнопці) ----
# Веб-вікна — це Edge у режимі застосунку, тож Windows підписував їх «Microsoft Edge», а exe без
# опису версії. Кожному нашому вікну ставимо власний AppUserModelID + назву, значок і команду
# перезапуску — тоді на панелі завдань «Discord Auto-Compress» з нашим значком.
APP_ID = "ramka1q.DiscordAutoCompress"
APP_NAME = "Discord Auto-Compress"


class _GUID(ctypes.Structure):
    _fields_ = [("d1", ctypes.c_ulong), ("d2", ctypes.c_ushort), ("d3", ctypes.c_ushort),
                ("d4", ctypes.c_ubyte * 8)]


class _PKEY(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", ctypes.c_ulong)]


class _PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort),
                ("r3", ctypes.c_ushort), ("p", ctypes.c_void_p), ("p2", ctypes.c_void_p)]


def _guid(d1, d2, d3, d4):
    g = _GUID(d1, d2, d3)
    for i, b in enumerate(d4):
        g.d4[i] = b
    return g


_AUM = (0x9F4C2855, 0x9F79, 0x4B39, (0xA8, 0xD0, 0xE1, 0xD4, 0x2D, 0xE1, 0xD5, 0xF3))
_IID_PS = _guid(0x886D8EEB, 0x8CF2, 0x4446, (0x8D, 0x02, 0xCD, 0xBA, 0x1D, 0xBD, 0xCF, 0x99))
_branded = set()


def _relaunch_cmd():
    import sys
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    here = os.path.dirname(os.path.abspath(__file__))
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    return f'"{exe}" "{os.path.join(here, "discord_overlay.py")}"'


def brand_window(hwnd, force=False):
    """AppUserModelID / назва / значок / перезапуск для вікна hwnd (будь-якого процесу)."""
    if not hwnd or (hwnd in _branded and not force):
        return False
    try:
        store = ctypes.c_void_p()
        hr = ctypes.windll.shell32.SHGetPropertyStoreForWindow(ctypes.c_void_p(hwnd), ctypes.byref(_IID_PS),
                                                               ctypes.byref(store))
        if hr != 0 or not store.value:
            return False
        vtbl = ctypes.cast(ctypes.cast(store, ctypes.POINTER(ctypes.c_void_p))[0],
                           ctypes.POINTER(ctypes.c_void_p))
        HR = ctypes.c_long
        set_value = ctypes.WINFUNCTYPE(HR, ctypes.c_void_p, ctypes.POINTER(_PKEY),
                                       ctypes.POINTER(_PROPVARIANT))(vtbl[6])
        commit = ctypes.WINFUNCTYPE(HR, ctypes.c_void_p)(vtbl[7])
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
        keep = []
        # спершу команда / назва / значок, ідентифікатор — останнім (так радить документація)
        for pid, val in ((2, _relaunch_cmd()), (4, APP_NAME), (3, ico_path() + ",0"), (5, APP_ID)):
            buf = ctypes.create_unicode_buffer(val)
            keep.append(buf)
            pv = _PROPVARIANT(31, 0, 0, 0, ctypes.cast(buf, ctypes.c_void_p), None)   # VT_LPWSTR
            key = _PKEY(_guid(*_AUM), pid)
            set_value(store, ctypes.byref(key), ctypes.byref(pv))
        commit(store)
        release(store)
        _branded.add(hwnd)
        return True
    except Exception:
        return False



def register_process_app_id():
    """Ідентифікатор програми для ВСЬОГО процесу (вікна Tk, сповіщення з трею) + його назва
    й значок у реєстрі (HKCU, офіційний спосіб для звичайних програм) — тоді Windows пише
    «Discord Auto-Compress», а не назву exe / «Python»."""
    try:
        import winreg
        png = os.path.join(tempfile.gettempdir(), "discord_autocompress_256.png")
        if not os.path.exists(png):
            with open(png, "wb") as f:
                f.write(_png_bytes(256))
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Software\\Classes\\AppUserModelId\\" + APP_ID)
        winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, png)
        winreg.CloseKey(k)
    except Exception:
        pass
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        return True
    except Exception:
        return False

if __name__ == "__main__":
    print("icon written to:", ico_path())
