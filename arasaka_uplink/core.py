"""
ARASAKA UPLINK // nucleo: servidor na rede de casa para trocar arquivos e textos com o celular (ou outro PC).

O celular le um QR code e abre uma pagina no navegador; nao precisa instalar nada. Protecoes:
  - so aceita enderecos da rede local (192.168.x, 10.x, 172.16-31.x, fe80::, loopback);
  - cada sessao tem um codigo secreto aleatorio, que vai no QR (depois do #, nao aparece em logs);
  - cada aparelho novo precisa ser aprovado no PC (os aprovados ficam lembrados);
  - o servidor so existe enquanto o app esta aberto.
Limite honesto: a pagina e HTTP (o navegador so libera criptografia em paginas HTTPS), entao use na sua rede.
"""
from __future__ import annotations

import ipaddress
import json
import mimetypes
import os
import re
import secrets
import socket
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

APP_ID = "arasaka-uplink"
APP_NAME = "ARASAKA UPLINK"
VERSION = "1.2.0"

HOME = Path.home()
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / APP_ID
ASSETS = Path(__file__).resolve().parent / "assets"
PAGE = Path(__file__).resolve().parent / "web" / "index.html"
MAX_TEXT = 100_000
CHUNK = 1024 * 256


def downloads_dir() -> Path:
    try:
        txt = (Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "user-dirs.dirs").read_text(encoding="utf-8")
        m = re.search(r'^XDG_DOWNLOAD_DIR="?([^"\n]+)"?', txt, re.M)
        if m:
            return Path(m.group(1).replace("$HOME", str(HOME))) / "Uplink"
    except OSError:
        pass
    return HOME / "Downloads" / "Uplink"


def lan_ips() -> list[str]:
    """IPs desta maquina na rede local (o primeiro e o da rota padrao)."""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))        # endereco de documentacao: nenhum pacote sai, so escolhe a interface
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    return ips or ["127.0.0.1"]


def local_networks() -> list[str]:
    """Redes locais das placas deste PC (ex.: 192.168.1.0/24), para liberar no firewall so a rede de casa."""
    nets = []
    try:
        out = subprocess.run(["ip", "-4", "-o", "addr", "show", "scope", "global"], capture_output=True, text=True, timeout=5).stdout
        for m in re.finditer(r"inet (\d+\.\d+\.\d+\.\d+/\d+)", out):
            net = ipaddress.ip_interface(m.group(1)).network
            if net.is_private and str(net) not in nets:
                nets.append(str(net))
    except Exception:
        pass
    return nets or ["192.168.0.0/16"]


def firewall_active() -> bool:
    """ufw ligado? (da para saber sem senha: o servico e o arquivo de configuracao sao legiveis)"""
    try:
        enabled = "ENABLED=yes" in Path("/etc/ufw/ufw.conf").read_text()
    except OSError:
        return False
    r = subprocess.run(["systemctl", "is-active", "ufw"], capture_output=True, text=True)
    return enabled and r.stdout.strip() == "active"


def firewall_command(port: int = 7099) -> list[list[str]]:
    """Comandos do ufw que liberam as portas do Uplink so para as redes locais."""
    return [["ufw", "allow", "from", net, "to", "any", "port", f"{port}:{port + 19}", "proto", "tcp", "comment", "Arasaka Uplink"]
            for net in local_networks()]


def is_local(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    return a.is_private or a.is_loopback or a.is_link_local


def safe_name(name: str) -> str:
    name = os.path.basename(unquote(name or "")).replace("\x00", "").strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)[:180]
    return name if name not in ("", ".", "..") else "arquivo"


def unique_path(folder: Path, name: str) -> Path:
    p = folder / name
    stem, suf, i = p.stem, p.suffix, 1
    while p.exists():
        p = folder / f"{stem} ({i}){suf}"
        i += 1
    return p


@dataclass
class Device:
    id: str
    name: str
    ip: str
    state: str = "pendente"       # pendente | aprovado | recusado
    seen: float = field(default_factory=time.time)


@dataclass
class Shared:
    id: str
    path: Path

    @property
    def name(self) -> str:
        return self.path.name


class Uplink:
    """Estado do servidor. Os callbacks (on_device, on_file, on_text) rodam na thread do servidor."""

    def __init__(self, recv_dir: Path | None = None, on_device=None, on_file=None, on_text=None, on_progress=None):
        self.recv_dir = recv_dir or downloads_dir()
        self.key = secrets.token_urlsafe(18)
        self.devices: dict[str, Device] = {}
        self.shared: list[Shared] = []
        self.texts_out: list[dict] = []     # textos do PC para o celular
        self.on_device, self.on_file, self.on_text, self.on_progress = on_device, on_file, on_text, on_progress
        self.httpd: ThreadingHTTPServer | None = None
        self.port = 0
        self.lock = threading.Lock()
        self.trusted = self._load_trusted()
        self.on_remote_request = None     # (aparelho) pede para ver/controlar a tela: o app pergunta
        self.on_stream = None             # alguem comecou/parou de ver a tela: o app mostra/esconde o aviso
        self.on_paste = None              # texto com acentos: o app poe na area de transferencia e cola
        self._remote = None

    @property
    def remote(self):
        if self._remote is None:
            from .remote_api import RemoteHub
            self._remote = RemoteHub(self)
        return self._remote

    # ------------------------------------------------ aparelhos lembrados
    def _load_trusted(self) -> dict[str, str]:
        try:
            return json.loads((CONFIG_DIR / "aparelhos.json").read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_trusted(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        (CONFIG_DIR / "aparelhos.json").write_text(json.dumps(self.trusted, ensure_ascii=False, indent=1), encoding="utf-8")

    def decide(self, dev_id: str, ok: bool, remember: bool = True):
        with self.lock:
            d = self.devices.get(dev_id)
            if not d:
                return
            d.state = "aprovado" if ok else "recusado"
            if ok and remember:
                self.trusted[dev_id] = d.name
                self._save_trusted()

    def forget(self, dev_id: str):
        self.trusted.pop(dev_id, None)
        if self._remote:
            self._remote.forget(dev_id)
        self._save_trusted()
        if dev_id in self.devices:
            self.devices[dev_id].state = "recusado"

    # ------------------------------------------------ compartilhar do PC
    def share(self, path: Path) -> Shared:
        s = Shared(uuid.uuid4().hex[:12], Path(path))
        self.shared.append(s)
        return s

    def unshare(self, sid: str):
        self.shared = [s for s in self.shared if s.id != sid]

    def send_text(self, text: str):
        self.texts_out = ([{"id": uuid.uuid4().hex[:8], "text": text[:MAX_TEXT], "at": time.time()}] + self.texts_out)[:20]

    # ------------------------------------------------ servidor
    def url(self, ip: str | None = None) -> str:
        return f"http://{ip or lan_ips()[0]}:{self.port}/#{self.key}"

    def start(self, port: int = 7099) -> int:
        handler = make_handler(self)
        for p in [port] + list(range(port + 1, port + 20)) + [0]:
            try:
                self.httpd = ThreadingHTTPServer(("0.0.0.0", p), handler)
                break
            except OSError:
                continue
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="uplink-http").start()
        return self.port

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None


def make_handler(up: Uplink):
    class H(BaseHTTPRequestHandler):
        server_version = "Uplink"
        sys_version = ""

        def log_message(self, *a):         # nao registra IPs nem acessos
            pass

        def _json(self, code: int, obj):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _guard(self, need_device=True) -> Device | None:
            if not is_local(self.client_address[0]):
                self._json(403, {"erro": "só na rede local"})
                return None
            if not secrets.compare_digest(self.headers.get("X-Uplink-Key", ""), up.key):
                self._json(403, {"erro": "código inválido: leia o QR code de novo"})
                return None
            if not need_device:
                return Device("", "", "")
            dev = up.devices.get(self.headers.get("X-Uplink-Device", ""))
            if not dev or dev.state != "aprovado":
                self._json(403, {"erro": "aparelho não aprovado", "state": dev.state if dev else "desconhecido"})
                return None
            dev.seen = time.time()
            return dev

        # ---------------------------------------- GET
        def do_GET(self):  # noqa: N802
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                if not is_local(self.client_address[0]):
                    return self._json(403, {"erro": "só na rede local"})
                body = PAGE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            if u.path == "/api/state":
                if not self._guard():
                    return
                return self._json(200, {"pc": socket.gethostname(),
                                        "files": [{"id": s.id, "name": s.name, "size": s.path.stat().st_size if s.path.exists() else 0} for s in up.shared],
                                        "texts": up.texts_out})
            if u.path.startswith("/api/r/") and up.remote.handle(self, "GET", u.path, u.query):
                return
            m = re.match(r"^/api/file/([0-9a-f]{12})$", u.path)
            if m:
                if not self._guard():
                    return
                s = next((x for x in up.shared if x.id == m.group(1)), None)
                if not s or not s.path.is_file():
                    return self._json(404, {"erro": "arquivo não está mais compartilhado"})
                size = s.path.stat().st_size
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(s.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(size))
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(s.name)}")
                self.end_headers()
                with open(s.path, "rb") as f:
                    while chunk := f.read(CHUNK):
                        self.wfile.write(chunk)
                return
            self._json(404, {"erro": "não encontrado"})

        # ---------------------------------------- POST
        def do_POST(self):  # noqa: N802
            u = urlparse(self.path)
            if u.path == "/api/hello":
                if not self._guard(need_device=False):
                    return
                try:
                    d = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 4096)) or b"{}")
                except ValueError:
                    d = {}
                dev_id = re.sub(r"[^0-9a-f]", "", str(d.get("device", "")))[:32]
                if len(dev_id) < 16:
                    return self._json(400, {"erro": "aparelho inválido"})
                name = re.sub(r"[\x00-\x1f]", "", str(d.get("name", "Aparelho")))[:60] or "Aparelho"
                new = False
                with up.lock:
                    dev = up.devices.get(dev_id)
                    if not dev:
                        dev = Device(dev_id, name, self.client_address[0], "aprovado" if dev_id in up.trusted else "pendente")
                        up.devices[dev_id] = dev
                        new = dev.state == "pendente"
                    dev.seen, dev.ip = time.time(), self.client_address[0]
                if new and up.on_device:
                    up.on_device(dev)
                return self._json(200, {"state": dev.state, "pc": socket.gethostname()})
            if u.path.startswith("/api/r/") and up.remote.handle(self, "POST", u.path, u.query):
                return
            if u.path == "/api/upload":
                dev = self._guard()
                if not dev:
                    return
                name = safe_name(parse_qs(u.query).get("name", ["arquivo"])[0])
                size = int(self.headers.get("Content-Length", 0))
                up.recv_dir.mkdir(parents=True, exist_ok=True)
                dest = unique_path(up.recv_dir, name)
                tmp = dest.with_name(dest.name + ".uplink-part")
                got = 0
                try:
                    with open(tmp, "wb") as f:
                        while got < size:
                            chunk = self.rfile.read(min(CHUNK, size - got))
                            if not chunk:
                                break
                            f.write(chunk)
                            got += len(chunk)
                            if up.on_progress:
                                up.on_progress(dev, name, got, size)
                    if got != size:
                        tmp.unlink(missing_ok=True)
                        return self._json(400, {"erro": "envio interrompido"})
                    tmp.rename(dest)
                except OSError as e:
                    tmp.unlink(missing_ok=True)
                    return self._json(500, {"erro": f"não consegui salvar: {e}"})
                if up.on_file:
                    up.on_file(dev, dest)
                return self._json(200, {"ok": True, "name": dest.name})
            if u.path == "/api/text":
                dev = self._guard()
                if not dev:
                    return
                try:
                    d = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), MAX_TEXT * 4)) or b"{}")
                except ValueError:
                    return self._json(400, {"erro": "texto inválido"})
                text = str(d.get("text", ""))[:MAX_TEXT]
                if text and up.on_text:
                    up.on_text(dev, text)
                return self._json(200, {"ok": True})
            self._json(404, {"erro": "não encontrado"})

    return H


def qr_svg(text: str) -> str:
    """QR code em SVG (precisa do pacote qrcode)."""
    import qrcode
    import qrcode.image.svg
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathFillImage, box_size=10, border=2)
    from io import BytesIO
    buf = BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")
