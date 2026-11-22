"""
ARASAKA UPLINK // controle remoto (X11; no Windows, win32desk.py): janelas, captura da tela e mouse/teclado.

Usa a propria sessao grafica (X11): mss para capturar, Pillow para virar JPEG e a extensao XTest (python-xlib)
para mover o mouse, clicar e digitar. No Wayland isso nao funciona (o Wayland exige um portal com permissao),
e o Uplink avisa na tela.
"""
from __future__ import annotations

import io
import os
import sys
import threading
import time
from dataclasses import dataclass


WIN = sys.platform == "win32"


def supported() -> tuple[bool, str]:
    if WIN:   # Windows: mss + Pillow para a imagem, a API do Windows (win32desk) para mouse e teclado
        try:
            import mss  # noqa: F401
            from PIL import Image  # noqa: F401
        except ImportError as e:
            return False, f"falta um pacote do controle remoto ({e.name}): reinstale o Uplink"
        return True, ""
    if os.environ.get("XDG_SESSION_TYPE") == "wayland" and not os.environ.get("DISPLAY"):
        return False, "a sessão é Wayland: entre na sessão Xorg (na tela de login) para usar o controle remoto"
    if not os.environ.get("DISPLAY"):
        return False, "sem sessão gráfica (DISPLAY)"
    try:
        import mss  # noqa: F401
        from PIL import Image  # noqa: F401
        from Xlib import display  # noqa: F401
    except ImportError as e:
        return False, f"falta um pacote do controle remoto ({e.name}): reinstale o Uplink"
    return True, ""


@dataclass
class Win:
    id: int
    title: str
    wm_class: str
    x: int
    y: int
    w: int
    h: int
    desktop: int = 0

    def as_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "cls": self.wm_class, "w": self.w, "h": self.h}


class X11:
    """Uma conexao com o X por thread (o python-xlib nao e thread-safe)."""

    def __init__(self):
        self._local = threading.local()
        self.lock = threading.Lock()

    @property
    def d(self):
        if not getattr(self._local, "d", None):
            from Xlib import display
            self._local.d = display.Display()
        return self._local.d

    def _atom(self, name):
        return self.d.intern_atom(name)

    def _prop(self, win, name, kind=None):
        from Xlib import X
        try:
            p = win.get_full_property(self._atom(name), kind if kind is not None else X.AnyPropertyType)
            return p.value if p else None
        except Exception:
            return None

    def screen_size(self) -> tuple[int, int]:
        s = self.d.screen()
        return s.width_in_pixels, s.height_in_pixels

    def windows(self) -> list[Win]:
        """Janelas de aplicativos abertas (as que aparecem na barra de tarefas)."""
        root = self.d.screen().root
        ids = self._prop(root, "_NET_CLIENT_LIST") or []
        skip = {self._atom("_NET_WM_WINDOW_TYPE_DOCK"), self._atom("_NET_WM_WINDOW_TYPE_DESKTOP"),
                self._atom("_NET_WM_WINDOW_TYPE_NOTIFICATION"), self._atom("_NET_WM_WINDOW_TYPE_SPLASH")}
        out = []
        for wid in ids:
            try:
                w = self.d.create_resource_object("window", wid)
                types = set(self._prop(w, "_NET_WM_WINDOW_TYPE") or [])
                if types & skip:
                    continue
                state = set(self._prop(w, "_NET_WM_STATE") or [])
                if self._atom("_NET_WM_STATE_SKIP_TASKBAR") in state:
                    continue
                name = self._prop(w, "_NET_WM_NAME", self._atom("UTF8_STRING"))
                title = name.decode("utf-8", "replace") if isinstance(name, bytes) else (w.get_wm_name() or "")
                cls = (w.get_wm_class() or ("", ""))[1] or ""
                x, y, ww, hh = self.geometry(wid)
                if ww < 40 or hh < 40:
                    continue
                desk = (self._prop(w, "_NET_WM_DESKTOP") or [0])[0]
                out.append(Win(wid, title or cls or "janela", cls, x, y, ww, hh, desk))
            except Exception:
                continue
        return out

    def geometry(self, wid: int) -> tuple[int, int, int, int]:
        """Posicao e tamanho na tela (sem a borda do gerenciador de janelas)."""
        w = self.d.create_resource_object("window", wid)
        g = w.get_geometry()
        t = w.translate_coords(self.d.screen().root, 0, 0)
        return -t.x, -t.y, g.width, g.height

    def find(self, wm_class: str = "", title: str = "") -> Win | None:
        wc, tl = wm_class.lower(), title.lower()
        for w in self.windows():
            if (wc and wc in w.wm_class.lower()) or (tl and tl in w.title.lower()):
                return w
        return None

    def activate(self, wid: int):
        """Traz a janela para a frente (tirando de minimizada) pelo protocolo do gerenciador de janelas."""
        from Xlib import X
        from Xlib.protocol import event
        root = self.d.screen().root
        w = self.d.create_resource_object("window", wid)
        desk = self._prop(w, "_NET_WM_DESKTOP")
        if desk:
            ev = event.ClientMessage(window=root, client_type=self._atom("_NET_CURRENT_DESKTOP"), data=(32, [desk[0], X.CurrentTime, 0, 0, 0]))
            root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        ev = event.ClientMessage(window=w, client_type=self._atom("_NET_ACTIVE_WINDOW"), data=(32, [2, X.CurrentTime, 0, 0, 0]))
        root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        self.d.flush()

    # ------------------------------------------------ mouse e teclado (XTest)
    def _fake(self, kind, detail, x=None, y=None):
        from Xlib.ext import xtest
        if x is not None:
            xtest.fake_input(self.d, kind, detail, root=self.d.screen().root, x=int(x), y=int(y))
        else:
            xtest.fake_input(self.d, kind, detail)

    def move(self, x: int, y: int):
        from Xlib import X
        self._fake(X.MotionNotify, 0, x, y)
        self.d.sync()

    def button(self, b: int, down: bool):
        from Xlib import X
        self._fake(X.ButtonPress if down else X.ButtonRelease, b)
        self.d.sync()

    def click(self, x: int, y: int, b: int = 1, double: bool = False):
        self.move(x, y)
        for _ in range(2 if double else 1):
            self.button(b, True)
            self.button(b, False)

    def scroll(self, x: int, y: int, dy: int, dx: int = 0):
        """dy > 0 desce; usa os botoes 4/5 (e 6/7 para os lados), como uma roda de mouse."""
        self.move(x, y)
        for _ in range(min(abs(dy), 15)):
            self.button(5 if dy > 0 else 4, True)
            self.button(5 if dy > 0 else 4, False)
        for _ in range(min(abs(dx), 15)):
            self.button(7 if dx > 0 else 6, True)
            self.button(7 if dx > 0 else 6, False)

    def pointer(self) -> tuple[int, int]:
        p = self.d.screen().root.query_pointer()
        return p.root_x, p.root_y

    def key(self, combo: str):
        """Combinacao como 'ctrl+shift+t', 'Return', 'alt+F4'."""
        from Xlib import X, XK
        names = {"ctrl": "Control_L", "control": "Control_L", "shift": "Shift_L", "alt": "Alt_L", "super": "Super_L", "win": "Super_L",
                 "enter": "Return", "esc": "Escape", "backspace": "BackSpace", "del": "Delete", "tab": "Tab", "space": "space",
                 "up": "Up", "down": "Down", "left": "Left", "right": "Right", "pgup": "Prior", "pgdn": "Next", "home": "Home", "end": "End"}
        codes = []
        for part in combo.split("+"):
            name = names.get(part.lower(), part)
            ks = XK.string_to_keysym(name)
            if not ks and len(name) == 1:
                ks = ord(name)
            kc = self.d.keysym_to_keycode(ks)
            if not kc:
                raise ValueError(f"tecla desconhecida: {part}")
            codes.append(kc)
        for kc in codes:
            self._fake(X.KeyPress, kc)
        for kc in reversed(codes):
            self._fake(X.KeyRelease, kc)
        self.d.sync()

    def type_ascii(self, text: str) -> str:
        """Digita o que for ASCII imprimivel; devolve o que sobrou (acentos etc., que vao pela area de transferencia)."""
        from Xlib import X, XK
        shift = self.d.keysym_to_keycode(XK.string_to_keysym("Shift_L"))
        rest = ""
        for ch in text:
            if ch == "\n":
                self.key("Return")
                continue
            if not (32 <= ord(ch) < 127):
                rest += ch
                continue
            ks = XK.string_to_keysym(ch) or ord(ch)
            if ch == " ":
                ks = XK.string_to_keysym("space")
            kc = self.d.keysym_to_keycode(ks)
            if not kc:
                rest += ch
                continue
            need_shift = self.d.keycode_to_keysym(kc, 0) != ks
            if need_shift:
                self._fake(X.KeyPress, shift)
            self._fake(X.KeyPress, kc)
            self._fake(X.KeyRelease, kc)
            if need_shift:
                self._fake(X.KeyRelease, shift)
        self.d.sync()
        return rest


def Desktop():  # noqa: N802 - fabrica: o controle de janelas, mouse e teclado do sistema
    if WIN:
        from .win32desk import Win32
        return Win32()
    return X11()


class Capturer:
    """Captura uma regiao (ou a tela toda) e devolve JPEG, reduzindo para a largura pedida."""

    def __init__(self):
        self._local = threading.local()

    def grab_jpeg(self, region: tuple[int, int, int, int] | None, max_w: int = 1280, quality: int = 60) -> tuple[bytes, tuple[int, int, int, int]]:
        import mss
        from PIL import Image
        if not getattr(self._local, "sct", None):
            self._local.sct = mss.mss()
        sct = self._local.sct
        mon = sct.monitors[0]                      # todas as telas juntas (coordenadas da tela do X)
        if region:
            x, y, w, h = region
            x0, y0 = max(x, mon["left"]), max(y, mon["top"])
            x1, y1 = min(x + w, mon["left"] + mon["width"]), min(y + h, mon["top"] + mon["height"])
            if x1 - x0 < 8 or y1 - y0 < 8:
                raise ValueError("a janela está fora da tela (minimizada?)")
            box = {"left": x0, "top": y0, "width": x1 - x0, "height": y1 - y0}
        else:
            box = mon
        shot = sct.grab(box)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        if img.width > max_w:
            img = img.resize((max_w, int(img.height * max_w / img.width)), Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=False)
        return buf.getvalue(), (box["left"], box["top"], box["width"], box["height"])


class Session:
    """Uma transmissao para um aparelho: o que esta sendo visto e onde (para converter o toque em coordenadas)."""

    def __init__(self, device_id: str, target: int | None):
        self.device_id = device_id
        self.target = target          # id da janela, ou None = tela inteira
        self.region = (0, 0, 1, 1)    # ultima regiao capturada (x, y, w, h)
        self.last = time.time()
        self.viewers = 0

    def to_screen(self, nx: float, ny: float) -> tuple[int, int]:
        x, y, w, h = self.region
        nx, ny = min(max(nx, 0.0), 1.0), min(max(ny, 0.0), 1.0)
        return int(x + nx * (w - 1)), int(y + ny * (h - 1))
