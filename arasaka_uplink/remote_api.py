"""
ARASAKA UPLINK // rotas do controle remoto (/api/r/...): apps, abrir, janelas, video da tela e comandos.

Permissao propria, separada da de arquivos: na primeira vez que um aparelho pede para ver/controlar, o PC pergunta.
Enquanto houver alguem vendo, o app mostra um aviso no PC com o botao de encerrar.
"""
from __future__ import annotations

import configparser
import hashlib
import json
import os
import re
import secrets
import shlex
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote

from . import remote as R

HOME = Path.home()
WIN_OPEN = "@startfile"   # cmd = [WIN_OPEN, atalho.lnk, argumentos...] (Windows)
FPS = 10
SESSION_IDLE = 30 * 60


class RemoteHub:
    def __init__(self, up):
        self.up = up
        self.x = R.Desktop()
        self.cap = R.Capturer()
        self.sessions: dict[str, R.Session] = {}
        self.pending: set[str] = set()
        self.enabled = True
        self.icons: dict[str, Path] = {}
        self.perms_path = up_config_dir() / "remoto.json"
        try:
            self.perms: dict[str, bool] = json.loads(self.perms_path.read_text(encoding="utf-8"))
        except Exception:
            self.perms = {}
        self.temp: set[str] = set()      # "so desta vez": vale ate fechar o Uplink, nunca vai para o disco
        self.lock = threading.Lock()

    # ------------------------------------------------ permissoes
    def perm(self, dev_id: str):
        """True (pode), False (recusado) ou None (ainda nao perguntado)."""
        return True if dev_id in self.temp else self.perms.get(dev_id)
    def set_perm(self, dev_id: str, ok: bool, remember: bool = True):
        self.pending.discard(dev_id)
        if ok and not remember:
            self.temp.add(dev_id)
            return
        self.temp.discard(dev_id)
        self.perms[dev_id] = ok
        if remember:
            self.perms_path.parent.mkdir(parents=True, exist_ok=True)
            self.perms_path.write_text(json.dumps(self.perms, indent=1), encoding="utf-8")
        if not ok:
            self.end_device(dev_id)

    def forget(self, dev_id: str):
        self.end_device(dev_id)
        self.pending.discard(dev_id)
        self.temp.discard(dev_id)
        if self.perms.pop(dev_id, None) is not None:
            self.perms_path.parent.mkdir(parents=True, exist_ok=True)
            self.perms_path.write_text(json.dumps(self.perms, indent=1), encoding="utf-8")

    def end_device(self, dev_id: str | None = None):
        """Encerra as transmissoes de um aparelho (ou de todos)."""
        with self.lock:
            for t, s in list(self.sessions.items()):
                if dev_id is None or s.device_id == dev_id:
                    del self.sessions[t]

    def watching(self) -> list[str]:
        """Nomes dos aparelhos que estao vendo a tela agora."""
        ids = {s.device_id for s in self.sessions.values() if s.viewers > 0}
        return [self.up.devices[i].name for i in ids if i in self.up.devices]

    # ------------------------------------------------ apps e modulos
    def apps_windows(self) -> list[dict]:
        """Windows: os atalhos dos apps Arasaka no Menu Iniciar (e os modulos, pelo atalho da Central)."""
        menus = [Path(os.environ.get("APPDATA") or HOME) / "Microsoft/Windows/Start Menu/Programs",
                 Path(os.environ.get("PROGRAMDATA") or "C:/ProgramData") / "Microsoft/Windows/Start Menu/Programs"]
        local = Path(os.environ.get("LOCALAPPDATA") or HOME)
        out, seen, central = [], set(), None
        for d in menus:
            for f in sorted(d.glob("*.lnk")) if d.is_dir() else []:
                name = f.stem
                if name in seen or not (name.startswith("Arasaka ") or name.startswith("Demonic")) or name == "Arasaka Uplink":
                    continue
                seen.add(name)
                app_id = name.lower().replace(" ", "-")
                key = "app:" + app_id
                svg = local / app_id / "app" / app_id.replace("-", "_") / "assets" / f"{app_id}.svg"
                if svg.is_file():
                    self.icons[key] = svg
                app = {"key": key, "name": name, "kind": "app", "cmd": [WIN_OPEN, str(f)], "cls": name, "desc": ""}
                if name == "Arasaka Central":
                    central = app
                out.append(app)
        mods = Path(os.environ.get("APPDATA") or HOME) / "Arasaka Central" / "modules"
        if central and mods.is_dir():
            for mf in sorted(mods.glob("*/module.json")):
                try:
                    m = json.loads(mf.read_text(encoding="utf-8-sig"))
                except Exception:
                    continue
                mid = m.get("id", mf.parent.name)
                png = next(iter(sorted((mf.parent / "icons").glob("*.png"))), None) if (mf.parent / "icons").is_dir() else None
                if png:
                    self.icons["mod:" + mid] = png
                out.append({"key": "mod:" + mid, "name": m.get("name", mid), "kind": "modulo", "cmd": central["cmd"] + [f"--module={mid}"],
                            "cls": "Arasaka Central", "desc": "Módulo da Arasaka Central"})
        return out

    def apps(self) -> list[dict]:
        if R.WIN:
            return self.apps_windows()
        out = []
        share = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share"))
        for f in sorted((share / "applications").glob("*.desktop")):
            if not (f.name.startswith("arasaka-") or f.name in ("piphin-hub.desktop", "demonic-engine.desktop")) or f.name == "arasaka-uplink.desktop":
                continue
            cp = configparser.RawConfigParser(interpolation=None, strict=False)
            cp.optionxform = str
            try:
                cp.read(f, encoding="utf-8")
                e = cp["Desktop Entry"]
                cmd = shlex.split(re.sub(r"%[fFuU]", "", e.get("Exec", "")))
            except Exception:
                continue
            if not cmd:
                continue
            key = "app:" + f.stem
            self._icon(key, e.get("Icon", ""))
            out.append({"key": key, "name": e.get("Name", f.stem), "kind": "app", "cmd": cmd,
                        "cls": e.get("StartupWMClass", f.stem), "desc": e.get("Comment", "")})
        mods = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "Arasaka Central" / "modules"
        central = next((a for a in out if a["key"] == "app:piphin-hub"), None)
        if central and mods.is_dir():
            for mf in sorted(mods.glob("*/module.json")):
                try:
                    m = json.loads(mf.read_text(encoding="utf-8-sig"))
                except Exception:
                    continue
                mid = m.get("id", mf.parent.name)
                key = "mod:" + mid
                png = next(iter(sorted((mf.parent / "icons").glob("*.png"))), None) if (mf.parent / "icons").is_dir() else None
                if png:
                    self.icons[key] = png
                out.append({"key": key, "name": m.get("name", mid), "kind": "modulo", "cmd": central["cmd"] + [f"--module={mid}"],
                            "cls": "arasaka-central", "desc": "Módulo da Arasaka Central"})
        return out

    def _icon(self, key: str, icon: str):
        share = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share"))
        cands = [Path(icon)] if icon.startswith("/") else [
            share / "icons/Arasaka/scalable/apps" / f"{icon}.svg", share / "icons/hicolor/scalable/apps" / f"{icon}.svg",
            Path("/usr/share/icons/hicolor/scalable/apps") / f"{icon}.svg", Path("/usr/share/pixmaps") / f"{icon}.png"]
        p = next((c for c in cands if c.is_file()), None)
        if p:
            self.icons[key] = p

    def _find(self, cls: str):
        # Windows: os apps Arasaka rodam no pythonw (o nome do programa nao diferencia): acha pelo titulo da janela
        return self.x.find(title=cls) if R.WIN else self.x.find(wm_class=cls)

    def launch(self, app: dict) -> R.Win | None:
        if app["kind"] == "app":                 # ja aberto: so traz para a frente (nao abre outra copia)
            w = self._find(app["cls"])
            if w:
                self.x.activate(w.id)
                return w
        if app["cmd"] and app["cmd"][0] == WIN_OPEN:   # atalho do Windows, com argumentos (modulo da Central)
            os.startfile(app["cmd"][1], "open", subprocess.list2cmdline(app["cmd"][2:]), str(HOME))  # noqa: S606
        else:
            subprocess.Popen(app["cmd"], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(HOME))
        end = time.time() + 15
        while time.time() < end:
            time.sleep(0.5)
            w = self._find(app["cls"])
            if w:
                time.sleep(0.6)            # deixa a janela terminar de abrir
                self.x.activate(w.id)
                return w
        return None

    # ------------------------------------------------ rotas
    def handle(self, h, method: str, path: str, query: str) -> bool:
        """Trata /api/r/...; devolve False se a rota nao for daqui."""
        if not path.startswith("/api/r/"):
            return False
        route = path[len("/api/r/"):]
        ok, why = R.supported()
        if route == "status" and method == "GET":
            dev = h._guard()
            if dev:
                h._json(200, {"ok": ok and self.enabled, "why": why if not ok else ("o controle remoto está desligado no PC" if not self.enabled else ""),
                              "perm": self.perm(dev.id)})
            return True
        if route.startswith("icon/") and method == "GET":
            if not h._guard():
                return True
            if not self.icons:
                self.apps()                       # o indice de icones e montado junto com a lista
            p = self.icons.get(unquote(route[5:]))
            if not p:
                h._json(404, {"erro": "sem ícone"})
                return True
            body = p.read_bytes()
            h.send_response(200)
            h.send_header("Content-Type", "image/svg+xml" if p.suffix == ".svg" else "image/png")
            h.send_header("Content-Length", str(len(body)))
            h.send_header("Cache-Control", "max-age=3600")
            h.end_headers()
            h.wfile.write(body)
            return True
        if route == "stream" and method == "GET":
            # a tag <img> nao manda cabecalhos: o video e liberado pela chave da sessao (secreta, curta e presa ao aparelho)
            from .core import is_local
            q = parse_qs(query)
            s = self.sessions.get(q.get("t", [""])[0])
            dev = self.up.devices.get(s.device_id) if s else None
            if not is_local(h.client_address[0]) or not dev or dev.state != "aprovado" or self.perm(dev.id) is not True or not self.enabled:
                h._json(403, {"erro": "transmissão encerrada"})
            else:
                self._stream(h, dev, q)
            return True
        dev = h._guard()
        if not dev:
            return True
        if not ok or not self.enabled:
            h._json(503, {"erro": why or "o controle remoto está desligado no PC"})
            return True
        if route == "apps" and method == "GET":
            h._json(200, {"apps": [{k: a[k] for k in ("key", "name", "kind", "desc")} for a in self.apps()]})
        elif route == "windows" and method == "GET":
            if not self._perm_ok(h, dev):
                return True
            h._json(200, {"windows": [w.as_dict() for w in self.x.windows()]})
        elif route == "start" and method == "POST":
            self._start(h, dev)
        elif route == "launch" and method == "POST":
            if not self._perm_ok(h, dev):
                return True
            d = self._body(h)
            app = next((a for a in self.apps() if a["key"] == d.get("key")), None)
            if not app:
                h._json(404, {"erro": "app não encontrado"})
                return True
            w = self.launch(app)
            h._json(200, {"window": w.as_dict() if w else None, "erro": None if w else f"{app['name']} não abriu a tempo"})
        elif route == "input" and method == "POST":
            self._input(h, dev)
        elif route == "stop" and method == "POST":
            d = self._body(h)
            with self.lock:
                self.sessions.pop(str(d.get("t", "")), None)
            h._json(200, {"ok": True})
        else:
            h._json(404, {"erro": "não encontrado"})
        return True

    def _body(self, h) -> dict:
        try:
            return json.loads(h.rfile.read(min(int(h.headers.get("Content-Length", 0)), 200_000)) or b"{}")
        except ValueError:
            return {}

    def _perm_ok(self, h, dev) -> bool:
        if self.perm(dev.id) is True:
            return True
        h._json(403, {"erro": "este aparelho não tem permissão de controle remoto", "perm": self.perm(dev.id)})
        return False

    def _start(self, h, dev):
        d = self._body(h)
        p = self.perm(dev.id)
        if p is False:
            h._json(403, {"erro": "o PC recusou o controle remoto para este aparelho", "state": "recusado"})
            return
        if p is None:
            if dev.id not in self.pending:
                self.pending.add(dev.id)
                cb = getattr(self.up, "on_remote_request", None)
                if cb:
                    cb(dev)
            h._json(200, {"state": "pendente"})
            return
        target = d.get("window")
        target = int(target) if target not in (None, "", "tela") else None
        if target:
            try:
                self.x.activate(target)
            except Exception:
                pass
        token = secrets.token_urlsafe(18)
        with self.lock:
            for t, s in list(self.sessions.items()):     # limpa as paradas
                if time.time() - s.last > SESSION_IDLE:
                    del self.sessions[t]
            self.sessions[token] = R.Session(dev.id, target)
        h._json(200, {"state": "ok", "t": token, "screen": self.x.screen_size()})

    def _session(self, token, dev) -> R.Session | None:
        s = self.sessions.get(token)
        return s if s and s.device_id == dev.id else None

    def _stream(self, h, dev, q):
        s = self._session(q.get("t", [""])[0], dev)
        if not s:
            h._json(403, {"erro": "transmissão encerrada"})
            return
        w = max(320, min(int(q.get("w", ["1280"])[0] or 1280), 1920))
        quality = max(30, min(int(q.get("q", ["60"])[0] or 60), 85))
        h.send_response(200)
        h.send_header("Content-Type", "multipart/x-mixed-replace; boundary=uplinkframe")
        h.send_header("Cache-Control", "no-store")
        h.end_headers()
        s.viewers += 1
        cb = getattr(self.up, "on_stream", None)
        if cb:
            cb()
        last_hash, last_sent = b"", 0.0
        try:
            while self.enabled and self.sessions.get(q.get("t", [""])[0]) is s:
                t0 = time.time()
                try:
                    region = self.x.geometry(s.target) if s.target else None
                    jpg, s.region = self.cap.grab_jpeg(region, w, quality)
                except Exception as e:  # noqa: BLE001  (janela fechada/minimizada: mostra a tela inteira)
                    if s.target:
                        s.target = None
                        continue
                    raise e
                hsh = hashlib.blake2b(jpg, digest_size=8).digest()
                if hsh != last_hash or t0 - last_sent > 2:
                    h.wfile.write(b"--uplinkframe\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                    h.wfile.flush()
                    last_hash, last_sent = hsh, t0
                s.last = time.time()
                time.sleep(max(0.0, 1 / FPS - (time.time() - t0)))
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            s.viewers = max(0, s.viewers - 1)
            if cb:
                cb()

    def _input(self, h, dev):
        d = self._body(h)
        s = self._session(str(d.get("t", "")), dev)
        if not s:
            h._json(403, {"erro": "transmissão encerrada"})
            return
        if self.perm(dev.id) is not True:
            h._json(403, {"erro": "sem permissão"})
            return
        s.last = time.time()
        x = self.x
        try:
            for ev in d.get("ev", [])[:60]:
                t = ev.get("t")
                if "x" in ev:
                    px, py = s.to_screen(float(ev["x"]), float(ev["y"]))
                if t == "move":
                    x.move(px, py)
                elif t == "click":
                    if s.target:
                        x.activate(s.target)
                    x.click(px, py, int(ev.get("b", 1)), bool(ev.get("dbl")))
                elif t in ("down", "up"):
                    if "x" in ev:
                        x.move(px, py)
                    x.button(int(ev.get("b", 1)), t == "down")
                elif t == "scroll":
                    x.scroll(px, py, int(ev.get("dy", 0)), int(ev.get("dx", 0)))
                elif t == "key":
                    x.key(str(ev.get("k", "")))
                elif t == "text":
                    rest = x.type_ascii(str(ev.get("s", ""))[:2000])
                    if rest:
                        paste = getattr(self.up, "on_paste", None)
                        if paste:
                            paste(rest)            # acentos e emojis: area de transferencia + Ctrl+V
            h._json(200, {"ok": True})
        except Exception as e:  # noqa: BLE001
            h._json(400, {"erro": str(e)})


def up_config_dir() -> Path:
    from .core import CONFIG_DIR
    return CONFIG_DIR
