#!/usr/bin/env python3
"""
mpvplayer.py — вбудований програвач редактора на libmpv (через ctypes, без сторонніх пакетів).
Файл відкривається ОДИН раз і тримається в пам'яті, тому «грати / пауза / перемотати» —
миттєві (як у CapCut), а не ~0.3 с на запуск окремого ffplay щоразу.
Малює прямо у вікно редактора (опція wid). Якщо libmpv-2.dll нема — available() == False,
і редактор працює по-старому через ffplay.
"""
import ctypes
import os
import tempfile
import threading
import time
import urllib.request
import zlib

DLL_NAME = "libmpv-2.dll"
# Одноразове фонове завантаження (45 МБ). Стиснуто звичайним zlib (є в будь-якому exe
# програми) — жодних архіваторів у друзів не треба. ТРИ незалежні джерела: якщо одне не
# відповідає (збій мережі, блокування GitHub у провайдера) — пробуємо наступне.
_REPO = "ramka1q/discord-autocompress"
_PARTS = 4                                  # дзеркала з шматками ≤ 20 МБ (ліміт jsDelivr)
MIRRORS = [                                 # від найшвидшого (заміряно) до найповільнішого
    ("GitHub raw", [f"https://raw.githubusercontent.com/{_REPO}/mpv-bin/libmpv-2.dll.z.{i}"
                    for i in range(_PARTS)]),
    ("jsDelivr", [f"https://cdn.jsdelivr.net/gh/{_REPO}@mpv-bin/libmpv-2.dll.z.{i}"
                  for i in range(_PARTS)]),
    ("GitHub", [f"https://github.com/{_REPO}/releases/download/mpv-v1/libmpv-2.dll.z"]),
]
DLL_SIZE = 121789952
Z_SIZE = 47250489             # скільки реально качається (стиснуто)
DLL_CRC32 = 3745875392
_dl = {"state": "idle", "pct": 0}      # idle / running / done / failed
_FMT_DOUBLE, _FMT_FLAG, _FMT_STRING = 5, 3, 1
_dll = None


def _dl_dir():
    return os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "DiscordAutoCompress", "mpv")


def dll_path():
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (here, _dl_dir()):
        p = os.path.join(d, DLL_NAME)
        if os.path.exists(p):
            return p
    return None


def _load():
    global _dll
    if _dll is not None:
        return _dll or None
    p = dll_path()
    if not p:
        _dll = False
        return None
    try:
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(os.path.dirname(p))
        d = ctypes.CDLL(p)
        d.mpv_create.restype = ctypes.c_void_p
        d.mpv_initialize.argtypes = [ctypes.c_void_p]
        d.mpv_set_option_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        d.mpv_set_property_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        d.mpv_command.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p)]
        d.mpv_command_async.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.POINTER(ctypes.c_char_p)]
        d.mpv_get_property.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p]
        d.mpv_terminate_destroy.argtypes = [ctypes.c_void_p]
        d.mpv_error_string.restype = ctypes.c_char_p
        _dll = d
    except Exception:
        _dll = False
    return _dll or None


def available():
    return _load() is not None


def download_state():
    return dict(_dl)


def _fetch_mirror(urls, tmpdll, progress):
    """Один спосіб: качає частини підряд, розпаковує на льоту, перевіряє розмір і CRC32."""
    dec = zlib.decompressobj()
    crc, size = 0, 0
    with open(tmpdll, "wb") as f:
        for k, url in enumerate(urls):
            req = urllib.request.Request(url, headers={"User-Agent": "DAC-mpv/1.0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                total = int(r.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    got += len(chunk)
                    data = dec.decompress(chunk)
                    crc = zlib.crc32(data, crc)
                    size += len(data)
                    f.write(data)
                    if total:
                        progress(int((k + got / total) * 100 / len(urls)))
        tail = dec.flush()
        crc = zlib.crc32(tail, crc)
        size += len(tail)
        f.write(tail)
    if size != DLL_SIZE or (crc & 0xffffffff) != DLL_CRC32:
        raise ValueError(f"damaged file ({size} B)")


_listeners = []
WAITS = (5, 15, 30, 60, 120)          # пауза між колами спроб (сек), далі — кожні 2 хв


def ensure_downloaded(on_done=None, on_status=None):
    """Фоном докачує libmpv-2.dll і НЕ ЗДАЄТЬСЯ: по колу пробує всі дзеркала (по 2 спроби),
    між колами — пауза, поки не скачає (немає інтернету — дочекається, коли з'явиться).
    on_status(state, pct, source) — для рядка стану (state: running / retry / wait / done);
    on_done(True) — коли готово. Викликаються з ФОНОВОГО потоку. Можна викликати скільки
    завгодно разів (кожен редактор додає свої колбеки до вже запущеного завантаження)."""
    if dll_path():
        if on_done:
            on_done(True)
        return
    if on_done or on_status:
        _listeners.append((on_done, on_status))
    if _dl["state"] in ("running", "retry", "wait"):
        return
    _dl["state"] = "running"

    def status(state, pct=0, src=""):
        _dl.update(state=state, pct=pct, source=src)
        for _d, st in list(_listeners):
            if st:
                try:
                    st(state, pct, src)
                except Exception:
                    pass

    def work():
        global _dll
        d = _dl_dir()
        errors = []
        rnd = 0
        while True:
            try:
                os.makedirs(d, exist_ok=True)
            except OSError as e:
                errors.append(repr(e))
            tmpdll = os.path.join(d, DLL_NAME + ".part")
            for name, urls in MIRRORS:
                for attempt in range(2):
                    status("running", 0, name)
                    try:
                        _fetch_mirror(urls, tmpdll, lambda pct, n=name: status("running", pct, n))
                        os.replace(tmpdll, os.path.join(d, DLL_NAME))
                        _dl["errors"] = errors
                        _dll = None                 # перечитати бібліотеку при наступному available()
                        status("done", 100, "")
                        for dn, _s in list(_listeners):
                            if dn:
                                try:
                                    dn(True)
                                except Exception:
                                    pass
                        _listeners.clear()
                        return
                    except Exception as e:
                        errors.append(f"{name} #{attempt + 1}: {e!r}")
                        del errors[:-30]
                        _dl["errors"] = errors
                        try:
                            os.remove(tmpdll)
                        except OSError:
                            pass
                        status("retry", 0, name)
                        time.sleep(1.5)
            wait = WAITS[min(rnd, len(WAITS) - 1)]
            rnd += 1
            _dl["rounds"] = rnd
            for left in range(wait, 0, -1):     # зворотний відлік у рядку стану
                status("wait", left, "")
                time.sleep(1)
    threading.Thread(target=work, daemon=True).start()


def _b(s):
    return s.encode("utf-8") if isinstance(s, str) else s


class Player:
    """Один екземпляр mpv, вбудований у вікно з HWND = wid."""

    def __init__(self, wid):
        d = _load()
        if d is None:
            raise RuntimeError("libmpv not available")
        self.d = d
        self.h = d.mpv_create()
        if not self.h:
            raise RuntimeError("mpv_create failed")
        for k, v in (("wid", str(int(wid))), ("vo", "gpu"), ("hwdec", "auto-safe"),
                     ("keep-open", "yes"), ("idle", "yes"), ("osc", "no"), ("osd-level", "0"),
                     ("input-default-bindings", "no"), ("input-vo-keyboard", "no"),
                     ("input-cursor", "no"), ("cursor-autohide", "no"), ("terminal", "no"),
                     ("audio-display", "no"), ("pause", "yes"), ("hr-seek", "yes"),
                     ("video-sync", "audio"), ("cache", "no")):
            d.mpv_set_option_string(self.h, _b(k), _b(v))
        rc = d.mpv_initialize(self.h)
        if rc < 0:
            raise RuntimeError("mpv_initialize: " + d.mpv_error_string(rc).decode())

    # ---------------------------------------------------------- базове -- #
    def command(self, *args):
        arr = (ctypes.c_char_p * (len(args) + 1))(*[_b(a) for a in args], None)
        return self.d.mpv_command(self.h, arr)

    def set(self, name, value):
        if isinstance(value, bool):
            value = "yes" if value else "no"
        return self.d.mpv_set_property_string(self.h, _b(name), _b(str(value)))

    def get_double(self, name):
        v = ctypes.c_double(0.0)
        rc = self.d.mpv_get_property(self.h, _b(name), _FMT_DOUBLE, ctypes.byref(v))
        return v.value if rc >= 0 else None

    def get_flag(self, name):
        v = ctypes.c_int(0)
        rc = self.d.mpv_get_property(self.h, _b(name), _FMT_FLAG, ctypes.byref(v))
        return bool(v.value) if rc >= 0 else None

    # ------------------------------------------------------- для редактора -- #
    def load(self, path, start=0.0, end=None, lavfi=None, paused=True, mute=False):
        """Відкрити файл з позиції start (сек) — паузою або одразу граючи.
        lavfi — граф фільтрів у синтаксисі ffmpeg з [vid1]/[aid1] -> [vo]/[ao]."""
        self.set("pause", paused)
        self.set("lavfi-complex", lavfi or "")
        self.set("mute", mute)
        opts = [f"start={start:.3f}"]
        if end is not None:
            opts.append(f"end={end:.3f}")
        return self.command("loadfile", path, "replace", "-1", ",".join(opts))

    def play(self):
        self.set("pause", False)

    def pause(self):
        self.set("pause", True)

    def position(self):
        return self.get_double("time-pos")

    def stop(self):
        self.command("stop")

    def close(self):
        if self.h:
            try:
                self.d.mpv_terminate_destroy(self.h)
            except Exception:
                pass
            self.h = None
