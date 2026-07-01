#!/usr/bin/env python3
"""
tray.py — значок у системному треї (приховані значки біля годинника) на чистому WinAPI.
ПКМ по значку -> меню «Відкрити меню» / «Закрити програму». Подвійний клік -> відкрити меню.
Закриття з трею закриває всю програму. Жодних сторонніх бібліотек — лише ctypes.

Працює у власному потоці з власним циклом повідомлень. Дії (on_open/on_quit)
мають бути потокобезпечними (у нас вони роблять root.after(...)).
"""
import ctypes
import threading
from ctypes import wintypes

import appicon

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

WM_APP = 0x8000
CB_MSG = WM_APP + 1
OPEN_MENU = WM_APP + 2      # інша копія просить відкрити меню
WND_CLASS = "DACtrayWnd"
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203
WM_CONTEXTMENU = 0x007B

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x01, 0x02, 0x04
TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x0002, 0x0100
MF_STRING, MF_SEPARATOR = 0x0000, 0x0800

ID_OPEN, ID_QUIT = 1001, 1002

LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_void_p, ctypes.c_uint, WPARAM, LPARAM)


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", ctypes.c_void_p),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", ctypes.c_void_p),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", ctypes.c_wchar * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", ctypes.c_void_p),
    ]


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.c_void_p),
        ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_uint, WPARAM, LPARAM]
user32.CreateWindowExW.restype = ctypes.c_void_p
user32.CreateWindowExW.argtypes = [wintypes.DWORD, ctypes.c_wchar_p, ctypes.c_wchar_p,
                                   wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_void_p, ctypes.c_void_p]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.TrackPopupMenu.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
user32.CreatePopupMenu.restype = ctypes.c_void_p
user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATA)]
kernel32.GetModuleHandleW.restype = ctypes.c_void_p
user32.FindWindowW.restype = ctypes.c_void_p
user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]


def find_existing():
    """HWND трею вже запущеної копії програми (або None)."""
    try:
        h = user32.FindWindowW(WND_CLASS, None)
        return h or None
    except Exception:
        return None


def signal_open():
    """Просить уже запущену копію відкрити меню. True, якщо копію знайдено."""
    h = find_existing()
    if h:
        try:
            user32.PostMessageW(h, OPEN_MENU, 0, 0)
            return True
        except Exception:
            pass
    return False


class Tray:
    def __init__(self, on_open, on_quit, texts):
        """texts = (open_label, quit_label, tooltip)."""
        self.on_open, self.on_quit = on_open, on_quit
        self.open_text, self.quit_text, self.tip = texts
        self.hwnd = None
        self.hicon = None
        self._nid = None
        self._class_name = WND_CLASS
        self._thread = threading.Thread(target=self._run, daemon=True)

    # ---------- публічне ----------
    def start(self):
        self._thread.start()

    def stop(self):
        if self.hwnd:
            try:
                user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
            except Exception:
                pass

    def update_texts(self, texts):
        self.open_text, self.quit_text, self.tip = texts
        if self._nid:
            self._nid.szTip = self.tip[:127]
            try:
                shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))
            except Exception:
                pass

    # ---------- внутрішнє ----------
    def _run(self):
        self._proc = WNDPROC(self._wndproc)   # тримаємо посилання від GC
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASS()
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = self._class_name
        user32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(0, self._class_name, "DAC", 0,
                                           0, 0, 0, 0, None, None, hinst, None)
        if not self.hwnd:
            return

        self.hicon = appicon.get_hicon(32)
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = CB_MSG
        nid.hIcon = self.hicon
        nid.szTip = self.tip[:127]
        self._nid = nid
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == CB_MSG:
            ev = lparam & 0xFFFF
            if ev in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._show_menu()
            elif ev == WM_LBUTTONDBLCLK:
                self._safe(self.on_open)
            return 0
        if msg == OPEN_MENU:
            self._safe(self.on_open)
            return 0
        if msg == WM_CLOSE:
            try:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            except Exception:
                pass
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _show_menu(self):
        try:
            hmenu = user32.CreatePopupMenu()
            user32.AppendMenuW(hmenu, MF_STRING, ID_OPEN, self.open_text or "Open")
            user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(hmenu, MF_STRING, ID_QUIT, self.quit_text or "Quit")
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetForegroundWindow(self.hwnd)
            cmd = user32.TrackPopupMenu(hmenu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                                        pt.x, pt.y, 0, self.hwnd, None)
            user32.PostMessageW(self.hwnd, 0, 0, 0)   # рекомендовано після TrackPopupMenu
            user32.DestroyMenu(hmenu)
        except Exception:
            return
        if cmd == ID_OPEN:
            self._safe(self.on_open)
        elif cmd == ID_QUIT:
            self._safe(self.on_quit)

    def _safe(self, fn):
        try:
            fn()
        except Exception:
            pass
