"""Controle remoto: permissao por aparelho, apps, chave do video, primeiro quadro, janelas e (numa tela virtual) o mouse.

    python tests/test_remote.py                         # sem mexer no mouse (pode rodar na sua sessao)
    UPLINK_TEST_INPUT=1 xvfb-run python tests/test_remote.py   # tambem testa o mouse (so numa tela virtual!)
"""
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

T = Path(tempfile.mkdtemp())
(T / "share/applications").mkdir(parents=True)
(T / "share/applications/arasaka-teste.desktop").write_text("[Desktop Entry]\nType=Application\nName=Arasaka Teste\nExec=true\nIcon=x\nStartupWMClass=arasaka-teste\n")
(T / "share/applications/piphin-hub.desktop").write_text("[Desktop Entry]\nType=Application\nName=Arasaka Central\nExec=true\n")
(T / "share/applications/arasaka-uplink.desktop").write_text("[Desktop Entry]\nType=Application\nName=Uplink\nExec=true\n")
mod = T / "cfg/Arasaka Central/modules/foto"
mod.mkdir(parents=True)
(mod / "module.json").write_text(json.dumps({"id": "foto", "name": "Arasaka Optics"}))
os.environ.update(HOME=str(T), XDG_CONFIG_HOME=str(T / "cfg"), XDG_DATA_HOME=str(T / "share"))
if sys.platform == "win32":   # Windows: os apps vem dos atalhos do Menu Iniciar; configuracoes em %APPDATA%
    menu = T / "cfg/Microsoft/Windows/Start Menu/Programs"
    menu.mkdir(parents=True)
    for n in ("Arasaka Teste", "Arasaka Central", "Arasaka Uplink", "Bloco de Notas"):
        (menu / f"{n}.lnk").write_bytes(b"")
    os.environ.update(APPDATA=str(T / "cfg"), LOCALAPPDATA=str(T / "share"), PROGRAMDATA=str(T / "none"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from arasaka_uplink import core as C, remote as R  # noqa: E402

asked = []
up = C.Uplink(recv_dir=T / "rec")
up.on_remote_request = lambda d: asked.append(d.id)
port = up.start(7299)
DEV = "f" * 32


def req(path, body=None, headers=True):
    h = {"X-Uplink-Key": up.key, "X-Uplink-Device": DEV} if headers else {}
    data = None if body is None else json.dumps(body).encode()
    if data is not None:
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=h)
    try:
        resp = urllib.request.urlopen(r, timeout=15)
        return resp.status, resp
    except urllib.error.HTTPError as e:
        return e.code, e


req("/api/hello", {"device": DEV, "name": "Teste"})
up.decide(DEV, True)
ok, why = R.supported()
code, resp = req("/api/r/status")
st = json.loads(resp.read())
assert st["ok"] == ok, (st, why)
if not ok:
    assert req("/api/r/apps")[0] == 503
    print(f"(sem sessão gráfica: {why}; só a recusa foi testada)")
    sys.exit(0)

apps = json.loads(req("/api/r/apps")[1].read())["apps"]
keys = {a["key"] for a in apps}
assert "app:arasaka-teste" in keys and "mod:foto" in keys and "app:arasaka-uplink" not in keys, keys
if sys.platform == "win32":
    assert "app:bloco-de-notas" not in keys, "no Windows so os apps Arasaka"
    foto = next(a for a in up.remote.apps() if a["key"] == "mod:foto")   # o comando nao vai para o celular: le direto
    assert foto["cmd"][-1] == "--module=foto" and foto["cmd"][1].endswith("Arasaka Central.lnk"), foto
    from arasaka_uplink.win32desk import Win32  # noqa: E402
    w32 = Win32()
    assert w32._vk("ctrl") == 0x11 and w32._vk("F4") == 0x73 and w32._vk("a") == 0x41
    assert all(w.w > 0 and w.title for w in w32.windows())

assert req("/api/r/windows")[0] == 403, "sem permissão não lista janelas"
code, resp = req("/api/r/start", {})
assert json.loads(resp.read())["state"] == "pendente" and asked == [DEV], "primeira vez: o PC pergunta"
req("/api/r/start", {})
assert asked == [DEV], "não pergunta de novo enquanto espera"
up.remote.set_perm(DEV, True)
code, resp = req("/api/r/start", {})
d = json.loads(resp.read())
assert d["state"] == "ok" and d["t"]
tok = d["t"]

assert req("/api/r/stream?t=errado", headers=False)[0] == 403, "chave errada não vê a tela"
code, resp = req(f"/api/r/stream?t={tok}&w=640&q=40", headers=False)
assert code == 200 and "multipart/x-mixed-replace" in resp.headers["Content-Type"]
buf = b""
while b"\xff\xd9" not in buf and len(buf) < 4_000_000:
    buf += resp.read1(65536) if hasattr(resp, "read1") else resp.read(65536)
assert b"Content-Type: image/jpeg" in buf and b"\xff\xd8" in buf, "primeiro quadro em JPEG"
resp.close()
assert isinstance(json.loads(req("/api/r/windows")[1].read())["windows"], list)

if os.environ.get("UPLINK_TEST_INPUT") == "1":
    sw, sh = up.remote.x.screen_size()
    assert req("/api/r/input", {"t": tok, "ev": [{"t": "move", "x": 0.25, "y": 0.75}]})[0] == 200
    px, py = up.remote.x.pointer()
    assert abs(px - int(0.25 * (sw - 1))) <= 2 and abs(py - int(0.75 * (sh - 1))) <= 2, (px, py)
    assert req("/api/r/input", {"t": tok, "ev": [{"t": "click", "x": 0.5, "y": 0.5}, {"t": "key", "k": "ctrl+a"}, {"t": "text", "s": "abc"}]})[0] == 200
    print("(mouse e teclado testados na tela virtual)")

req("/api/r/stop", {"t": tok})
assert req(f"/api/r/stream?t={tok}", headers=False)[0] == 403, "parada encerra a chave"
up.forget(DEV)
up.devices[DEV].state = "aprovado"
code, resp = req("/api/r/start", {})
assert json.loads(resp.read())["state"] == "pendente", "esquecer apaga a permissão"
up.remote.set_perm(DEV, True, remember=False)
assert json.loads((T / "cfg/arasaka-uplink/remoto.json").read_text()) == {}, "'só desta vez' não vai para o disco"
up.stop()
print("OK: permissão, apps, chave do vídeo, primeiro quadro, janelas, parar e esquecer")
