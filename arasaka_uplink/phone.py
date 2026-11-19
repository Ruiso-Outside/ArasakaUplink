"""
ARASAKA UPLINK // celular Android pelo PC (ADB + scrcpy).

Consentimento no celular, uma vez: parear pela "Depuracao sem fio" lendo o QR code do Uplink, ou autorizar pelo cabo
USB ("Sempre permitir neste computador"). Depois disso o PC espelha e controla a tela, mexe nos arquivos e resgata as
fotos e documentos, mesmo com a tela quebrada. O proprio Android mostra uma notificacao enquanto a depuracao estiver
conectada, e tudo pode ser revogado no celular (Opcoes do desenvolvedor > Revogar autorizacoes de depuracao).

No PC, cada uso exige a senha do Linux (ver auth.py).
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import string
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .core import CONFIG_DIR, HOME

PHONES = CONFIG_DIR / "celulares.json"

# pastas que valem resgatar de um celular (relativas a /sdcard); as que nao existirem sao puladas
RESCUE = ["DCIM", "Pictures", "Movies", "Music", "Documents", "Download", "Recordings", "Podcasts", "Audiobooks",
          "Android/media/com.whatsapp/WhatsApp/Media", "WhatsApp/Media", "Android/media/org.telegram.messenger",
          "Telegram"]


def tools() -> dict[str, str | None]:
    return {"adb": shutil.which("adb"), "scrcpy": shutil.which("scrcpy")}


def adb(*args: str, serial: str | None = None, timeout: float = 30, check: bool = False) -> str:
    if not shutil.which("adb"):
        raise RuntimeError("o adb não está instalado (sudo apt install adb)")
    cmd = ["adb"] + (["-s", serial] if serial else []) + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip() else f"adb terminou com {r.returncode}")
    return r.stdout + (r.stderr if not r.stdout else "")


# ================================================================ aparelhos
@dataclass
class Phone:
    serial: str
    state: str                       # device | unauthorized | offline | ...
    model: str = ""
    transport: str = "usb"           # usb | wifi
    props: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return (self.model or self.serial).replace("_", " ")

    @property
    def ready(self) -> bool:
        return self.state == "device"


def parse_devices(text: str) -> list[Phone]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        props = dict(p.split(":", 1) for p in parts[2:] if ":" in p)
        serial = parts[0]
        wifi = ":" in serial or "_adb-tls-connect" in serial
        out.append(Phone(serial, parts[1], props.get("model", ""), "wifi" if wifi else "usb", props))
    return out


def devices() -> list[Phone]:
    return parse_devices(adb("devices", "-l", timeout=10))


def parse_mdns(text: str) -> list[tuple[str, str, str]]:
    """(nome, tipo, ip:porta) do `adb mdns services`."""
    out = []
    for line in text.splitlines():
        m = re.match(r"^(\S+)\s+(_adb[-\w]*\._tcp)\.?\s+([\d.]+:\d+)\s*$", line.strip())
        if m:
            out.append((m.group(1), m.group(2), m.group(3)))
    return out


def mdns() -> list[tuple[str, str, str]]:
    return parse_mdns(adb("mdns", "services", timeout=10))


# ================================================================ parear (QR da depuracao sem fio)
def new_pairing() -> tuple[str, str, str]:
    """(nome, senha, texto do QR). O celular le o QR em Depuracao sem fio > Parear dispositivo com QR code."""
    name = "ARASAKA-" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    pw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
    return name, pw, f"WIFI:T:ADB;S:{name};P:{pw};;"


def wait_pairing(name: str, pw: str, timeout: float = 180, should_stop=lambda: False) -> str:
    """Espera o celular anunciar o pareamento (mDNS) e conclui o `adb pair`. Devolve o ip:porta do pareamento."""
    end = time.time() + timeout
    while time.time() < end and not should_stop():
        for svc, kind, addr in mdns():
            if kind.startswith("_adb-tls-pairing") and svc == name:
                out = adb("pair", addr, pw, timeout=30)
                if "Successfully paired" not in out:
                    raise RuntimeError(out.strip().splitlines()[-1] if out.strip() else "falha no pareamento")
                return addr
        time.sleep(1.5)
    raise TimeoutError("o celular não leu o QR code a tempo")


def connect_known() -> list[str]:
    """Conecta nos celulares pareados que estiverem anunciando a depuracao sem fio na rede."""
    connected = {p.serial for p in devices() if p.ready}
    done = []
    for svc, kind, addr in mdns():
        if kind.startswith("_adb-tls-connect") and addr not in connected and not any(svc in s for s in connected):
            out = adb("connect", addr, timeout=15)
            if "connected" in out and "failed" not in out:
                done.append(addr)
    return done


def remember(p: Phone):
    known = load_known()
    known[p.props.get("device") or p.model or p.serial] = {"model": p.model, "serial": p.serial, "seen": time.time(), "transport": p.transport}
    PHONES.parent.mkdir(parents=True, exist_ok=True)
    PHONES.write_text(json.dumps(known, indent=1, ensure_ascii=False), encoding="utf-8")


def load_known() -> dict:
    try:
        return json.loads(PHONES.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ================================================================ informacoes e teclas
def info(serial: str) -> dict:
    bat = adb("shell", "dumpsys", "battery", serial=serial, timeout=10)
    lvl = re.search(r"level:\s*(\d+)", bat)
    charging = re.search(r"(AC|USB|Wireless) powered:\s*true", bat)
    ver = adb("shell", "getprop", "ro.build.version.release", serial=serial, timeout=10).strip()
    brand = adb("shell", "getprop", "ro.product.brand", serial=serial, timeout=10).strip()
    model = adb("shell", "getprop", "ro.product.model", serial=serial, timeout=10).strip()
    screen = adb("shell", "dumpsys", "power", serial=serial, timeout=10)
    awake = re.search(r"mWakefulness=(\w+)", screen)
    return {"battery": int(lvl.group(1)) if lvl else None, "charging": bool(charging), "android": ver,
            "name": f"{brand.capitalize()} {model}".strip(), "awake": (awake.group(1) == "Awake") if awake else None}


KEYS = {"acordar": "KEYCODE_WAKEUP", "apagar": "KEYCODE_SLEEP", "inicio": "KEYCODE_HOME", "voltar": "KEYCODE_BACK",
        "recentes": "KEYCODE_APP_SWITCH", "energia": "KEYCODE_POWER", "volume+": "KEYCODE_VOLUME_UP", "volume-": "KEYCODE_VOLUME_DOWN",
        "menu": "KEYCODE_MENU"}


def key(serial: str, name: str):
    adb("shell", "input", "keyevent", KEYS[name], serial=serial, timeout=10, check=True)


def swipe_up(serial: str):
    """Arrasta de baixo para cima (tira a tela de bloqueio do caminho para digitar o PIN)."""
    size = re.search(r"(\d+)x(\d+)", adb("shell", "wm", "size", serial=serial, timeout=10))
    w, h = (int(size.group(1)), int(size.group(2))) if size else (1080, 2340)
    adb("shell", "input", "swipe", str(w // 2), str(int(h * 0.85)), str(w // 2), str(int(h * 0.3)), "250", serial=serial, timeout=10, check=True)


def type_text(serial: str, text: str):
    """Digita no celular (o `input text` nao aceita espaco literal nem alguns simbolos)."""
    safe = re.sub(r"([\\\"'`$&|;<>(){}\[\]*?~!#])", r"\\\1", text).replace(" ", "%s")
    adb("shell", "input", "text", safe, serial=serial, timeout=15, check=True)


# ================================================================ espelhar e controlar
def mirror(serial: str, title: str, screen_off: bool = False, audio: bool = False) -> subprocess.Popen:
    if not shutil.which("scrcpy"):
        raise RuntimeError("o scrcpy não está instalado (sudo apt install scrcpy)")
    cmd = ["scrcpy", "-s", serial, "--window-title", title, "--stay-awake"]
    if screen_off:
        cmd.append("--turn-screen-off")
    help_text = subprocess.run(["scrcpy", "--help"], capture_output=True, text=True).stdout
    if not audio and "--no-audio" in help_text:
        cmd.append("--no-audio")
    return subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)


# ================================================================ arquivos
@dataclass
class Entry:
    name: str
    is_dir: bool
    size: int
    when: str


def parse_ls(text: str) -> list[Entry]:
    """Saida do `ls -la` do Android (toybox)."""
    out = []
    for line in text.splitlines():
        m = re.match(r"^([dl-])[rwxsStT-]{9}\S*\s+\d+\s+\S+\s+\S+\s+(\d+)\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s+(.+)$", line)
        if not m:
            continue
        name = m.group(4)
        if m.group(1) == "l":
            name = name.split(" -> ")[0]
        if name in (".", ".."):
            continue
        out.append(Entry(name, m.group(1) in "dl", int(m.group(2)), m.group(3)))
    return sorted(out, key=lambda e: (not e.is_dir, e.name.lower()))


def ls(serial: str, path: str) -> list[Entry]:
    q = "'" + path.replace("'", "'\\''") + "'"
    return parse_ls(adb("shell", f"ls -la {q}/", serial=serial, timeout=20))


def pull(serial: str, remote: str, local: Path, on_line=None) -> int:
    """Copia do celular para o PC (pasta ou arquivo). Devolve o codigo do adb."""
    local.mkdir(parents=True, exist_ok=True)
    p = subprocess.Popen(["adb", "-s", serial, "pull", "-a", remote, str(local)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in p.stdout:
        if on_line and line.strip():
            on_line(line.strip())
    return p.wait()


def push(serial: str, local: Path, remote_dir: str) -> str:
    return adb("push", str(local), remote_dir.rstrip("/") + "/", serial=serial, timeout=3600, check=True)


def rescue(serial: str, dest_root: Path, on_line=None, should_stop=lambda: False) -> Path:
    """Copia as pastas importantes (fotos, videos, documentos, WhatsApp...) para uma pasta nova no PC."""
    i = info(serial)
    dest = dest_root / f"Celular {i['name'] or serial} {time.strftime('%Y-%m-%d %H%M')}".replace("/", "-")
    dest.mkdir(parents=True, exist_ok=True)
    for rel in RESCUE:
        if should_stop():
            break
        remote = f"/sdcard/{rel}"
        exists = adb("shell", f"[ -d '{remote}' ] && echo sim", serial=serial, timeout=10).strip() == "sim"
        if not exists:
            continue
        if on_line:
            on_line(f"> {rel}")
        code = pull(serial, remote, dest / Path(rel).parent if "/" in rel else dest, on_line)
        if code != 0 and on_line:
            on_line(f"!! {rel}: o adb terminou com código {code} (alguns arquivos podem ter ficado de fora)")
    if on_line:
        on_line(f"■ resgate em {dest}")
    return dest


def default_dest() -> Path:
    return HOME / "Celular"
