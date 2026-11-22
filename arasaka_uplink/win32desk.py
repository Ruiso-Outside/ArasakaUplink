"""
ARASAKA UPLINK // controle remoto no Windows: janelas, mouse e teclado pela API do Windows (user32, sem bibliotecas).

Mesma interface do X11 em remote.py (screen_size, windows, geometry, find, activate, move, button, click, scroll,
pointer, key, type_ascii). As coordenadas sao as da tela virtual em pixels fisicos, as mesmas do mss.
O texto vai como Unicode (KEYEVENTF_UNICODE): acentos e emojis tambem sao digitados.
"""
from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes

from .remote import Win

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    dwmapi = ctypes.WinDLL("dwmapi")
except OSError:
    dwmapi = None

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004
MOUSE = {1: (0x0002, 0x0004), 2: (0x0020, 0x0040), 3: (0x0008, 0x0010)}   # botao do X11 -> (desce, sobe)
MOUSEEVENTF_WHEEL, MOUSEEVENTF_HWHEEL = 0x0800, 0x1000
WHEEL_DELTA = 120
GWL_EXSTYLE, WS_EX_TOOLWINDOW, GW_OWNER = -20, 0x00000080, 4
DWMWA_EXTENDED_FRAME_BOUNDS, DWMWA_CLOAKED = 9, 14
SW_RESTORE = 9
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetWindow.restype = wintypes.HWND
user32.IsWindowVisible.argtypes = user32.IsIconic.argtypes = (wintypes.HWND,)
user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.SetForegroundWindow.argtypes = user32.BringWindowToTop.argtypes = (wintypes.HWND,)
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.VkKeyScanW.argtypes = (wintypes.WCHAR,)
user32.VkKeyScanW.restype = ctypes.c_short
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))

VK = {"ctrl": 0x11, "control": 0x11, "control_l": 0x11, "shift": 0x10, "shift_l": 0x10, "alt": 0x12, "alt_l": 0x12,
      "super": 0x5B, "super_l": 0x5B, "win": 0x5B, "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B,
      "backspace": 0x08, "del": 0x2E, "delete": 0x2E, "tab": 0x09, "space": 0x20, "left": 0x25, "up": 0x26, "right": 0x27,
      "down": 0x28, "pgup": 0x21, "prior": 0x21, "pgdn": 0x22, "next": 0x22, "home": 0x24, "end": 0x23, "insert": 0x2D,
      "menu": 0x5D, "print": 0x2C}
VK.update({f"f{i}": 0x6F + i for i in range(1, 25)})


def dpi_aware():
    """Coordenadas em pixels fisicos (as mesmas do mss), tambem com a escala do Windows em 125%/150%."""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))    # por monitor v2
    except Exception:  # noqa: BLE001
        try:
            ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
        except Exception:  # noqa: BLE001
            pass


def _send(*inputs: INPUT):
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def _mouse(flags: int, data: int = 0) -> INPUT:
    return INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, ctypes.c_ulong(data & 0xFFFFFFFF).value, flags, 0, 0))


def _key(vk: int = 0, up: bool = False, scan: int = 0, unicode: bool = False) -> INPUT:
    flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_UNICODE if unicode else 0)
    return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, scan, flags, 0, 0))


class Win32:
    def __init__(self):
        dpi_aware()
        self.lock = threading.Lock()

    def screen_size(self) -> tuple[int, int]:
        return user32.GetSystemMetrics(SM_CXVIRTUALSCREEN), user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

    # ------------------------------------------------ janelas
    def _title(self, h) -> str:
        n = user32.GetWindowTextLengthW(h)
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, buf, n + 1)
        return buf.value

    def _exe(self, h) -> str:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        hp = kernel32.OpenProcess(0x1000, False, pid.value)    # PROCESS_QUERY_LIMITED_INFORMATION
        if not hp:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if kernel32.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(size)):
                return os.path.splitext(os.path.basename(buf.value))[0]
        finally:
            kernel32.CloseHandle(hp)
        return ""

    def _cloaked(self, h) -> bool:
        if not dwmapi:
            return False
        v = wintypes.DWORD()
        return dwmapi.DwmGetWindowAttribute(wintypes.HWND(h), DWMWA_CLOAKED, ctypes.byref(v), ctypes.sizeof(v)) == 0 and v.value != 0

    def geometry(self, wid: int) -> tuple[int, int, int, int]:
        r = wintypes.RECT()
        if not (dwmapi and dwmapi.DwmGetWindowAttribute(wintypes.HWND(wid), DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) == 0):
            user32.GetWindowRect(wid, ctypes.byref(r))    # sem a sombra/borda invisivel do Windows 10/11 quando o DWM responde
        return r.left, r.top, r.right - r.left, r.bottom - r.top

    def windows(self) -> list[Win]:
        """Janelas de aplicativos abertas (as que aparecem na barra de tarefas)."""
        out: list[Win] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(h, _l):
            try:
                if not user32.IsWindowVisible(h) or user32.GetWindow(h, GW_OWNER) or self._cloaked(h):
                    return True
                if user32.GetWindowLongW(h, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
                    return True
                title = self._title(h)
                if not title or title in ("Program Manager",):
                    return True
                x, y, w, hh = self.geometry(h)
                if not user32.IsIconic(h) and (w < 40 or hh < 40):
                    return True
                out.append(Win(int(h), title, self._exe(h), x, y, w, hh))
            except Exception:  # noqa: BLE001
                pass
            return True
        user32.EnumWindows(cb, 0)
        return out

    def find(self, wm_class: str = "", title: str = "") -> Win | None:
        wc, tl = wm_class.lower(), title.lower()
        for w in self.windows():
            if (wc and wc in w.wm_class.lower()) or (tl and tl in w.title.lower()):
                return w
        return None

    def activate(self, wid: int):
        """Traz para a frente (tirando de minimizada). O Windows so deixa trocar o foco depois de uma tecla: um Alt solto."""
        if user32.IsIconic(wid):
            user32.ShowWindow(wid, SW_RESTORE)
        _send(_key(0x12), _key(0x12, up=True))
        user32.BringWindowToTop(wid)
        user32.SetForegroundWindow(wid)

    # ------------------------------------------------ mouse e teclado
    def move(self, x: int, y: int):
        user32.SetCursorPos(int(x), int(y))

    def button(self, b: int, down: bool):
        if b in MOUSE:
            _send(_mouse(MOUSE[b][0 if down else 1]))

    def click(self, x: int, y: int, b: int = 1, double: bool = False):
        self.move(x, y)
        for _ in range(2 if double else 1):
            self.button(b, True)
            self.button(b, False)

    def scroll(self, x: int, y: int, dy: int, dx: int = 0):
        """dy > 0 desce (como no X11)."""
        self.move(x, y)
        if dy:
            _send(_mouse(MOUSEEVENTF_WHEEL, -WHEEL_DELTA * max(-15, min(15, dy))))
        if dx:
            _send(_mouse(MOUSEEVENTF_HWHEEL, WHEEL_DELTA * max(-15, min(15, dx))))

    def pointer(self) -> tuple[int, int]:
        p = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(p))
        return p.x, p.y

    def _vk(self, part: str) -> int:
        name = part.lower()
        if name in VK:
            return VK[name]
        if len(part) == 1:
            r = user32.VkKeyScanW(part)
            if r != -1:
                return r & 0xFF
        raise ValueError(f"tecla desconhecida: {part}")

    def key(self, combo: str):
        """Combinacao como 'ctrl+shift+t', 'Return', 'alt+F4'."""
        codes = [self._vk(p) for p in combo.split("+")]
        _send(*[_key(c) for c in codes], *[_key(c, up=True) for c in reversed(codes)])

    def type_ascii(self, text: str) -> str:
        """Digita tudo (Unicode, inclusive acentos); nao sobra nada para a area de transferencia."""
        for ch in text:
            if ch == "\n":
                self.key("Return")
                continue
            data = ch.encode("utf-16-le")
            units = [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]
            _send(*[_key(scan=u, unicode=True) for u in units], *[_key(scan=u, unicode=True, up=True) for u in units])
        return ""
