"""Servidor do Uplink: codigo, aprovacao do aparelho, envio de arquivo e texto, download e nomes perigosos.

    python tests/test_server.py
"""
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

T = Path(tempfile.mkdtemp())
os.environ.update(HOME=str(T), XDG_CONFIG_HOME=str(T / ".config"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from arasaka_uplink import core as C  # noqa: E402

events = {"dev": [], "file": [], "text": []}
up = C.Uplink(recv_dir=T / "recebidos", on_device=lambda d: events["dev"].append(d.id),
              on_file=lambda d, p: events["file"].append(p), on_text=lambda d, t: events["text"].append(t))
port = up.start(7199)
base = f"http://127.0.0.1:{port}"
DEV = "a1b2c3d4e5f60718293a4b5c6d7e8f90"


def req(path, data=None, key=up.key, dev=DEV, method=None, ctype="application/json"):
    h = {"X-Uplink-Key": key, "X-Uplink-Device": dev}
    if data is not None:
        h["Content-Type"] = ctype
    r = urllib.request.Request(base + path, data=data, headers=h, method=method or ("POST" if data is not None else "GET"))
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


code, body = req("/")
assert code == 200 and b"ARASAKA UPLINK" in body, "pagina"
assert req("/api/hello", b'{"device":"%s","name":"Teste"}' % DEV.encode(), key="errado")[0] == 403, "codigo errado"
code, body = req("/api/hello", json.dumps({"device": DEV, "name": "Celular de teste"}).encode())
assert code == 200 and json.loads(body)["state"] == "pendente" and events["dev"] == [DEV], "aparelho novo fica pendente"
assert req("/api/state")[0] == 403, "pendente nao acessa"
up.decide(DEV, True)
assert json.loads(req("/api/state")[1])["files"] == []

code, body = req("/api/upload?name=" + "..%2F..%2Fetc%2Fpasswd", b"conteudo", ctype="application/octet-stream")
saved = Path(events["file"][-1])
assert code == 200 and saved.parent == T / "recebidos" and saved.name == "passwd", "nome perigoso fica dentro da pasta"
req("/api/upload?name=foto.jpg", b"x" * 300000, ctype="application/octet-stream")
req("/api/upload?name=foto.jpg", b"y", ctype="application/octet-stream")
assert sorted(p.name for p in (T / "recebidos").iterdir()) == ["foto (1).jpg", "foto.jpg", "passwd"], "nao sobrescreve"
assert (T / "recebidos" / "foto.jpg").stat().st_size == 300000

assert req("/api/text", json.dumps({"text": "https://exemplo.com"}).encode())[0] == 200 and events["text"] == ["https://exemplo.com"]

f = T / "do-pc.txt"
f.write_text("ola do PC")
s = up.share(f)
st = json.loads(req("/api/state")[1])
assert st["files"][0]["name"] == "do-pc.txt"
code, body = req(f"/api/file/{s.id}")
assert code == 200 and body == b"ola do PC"
up.unshare(s.id)
assert req(f"/api/file/{s.id}")[0] == 404

# aparelho aprovado fica lembrado na proxima sessao (com codigo novo)
up.stop()
up2 = C.Uplink(recv_dir=T / "recebidos")
assert DEV in up2.trusted and up2.key != up.key
assert C.is_local("192.168.0.10") and C.is_local("10.1.2.3") and C.is_local("fe80::1") and not C.is_local("8.8.8.8")
assert C.safe_name("../../x") == "x" and C.safe_name("") == "arquivo"
try:
    import qrcode  # noqa: F401
    assert "<svg" in C.qr_svg("http://192.168.0.2:7099/#abc")
except ImportError:
    print("(qrcode nao instalado: QR nao testado)")
print("OK: codigo, aprovacao, envio, texto, download, nomes perigosos e aparelhos lembrados")
