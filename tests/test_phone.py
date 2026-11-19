"""Celular (ADB): leitura das saidas do adb, QR de pareamento, digitar com seguranca e o cadeado da senha.

    python tests/test_phone.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

T = Path(tempfile.mkdtemp())
os.environ.update(HOME=str(T), XDG_CONFIG_HOME=str(T / "cfg"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from arasaka_uplink import auth, phone as P  # noqa: E402

ds = P.parse_devices("""List of devices attached
RZ8N90ABCDE            device usb:1-4 product:a52qnsxx model:SM_A525M device:a52q transport_id:2
192.168.1.20:37099     device product:a52qnsxx model:SM_A525M device:a52q transport_id:3
adb-RZ8N90ABCDE-XyZ._adb-tls-connect._tcp device product:x model:SM_A525M device:a52q
emulator-5554          unauthorized transport_id:1
""")
assert [(d.transport, d.state) for d in ds] == [("usb", "device"), ("wifi", "device"), ("wifi", "device"), ("usb", "unauthorized")]
assert ds[0].name == "SM A525M" and ds[0].ready and not ds[3].ready

ms = P.parse_mdns("""List of discovered mdns services
adb-RZ8N90ABCDE-XyZ\t_adb-tls-connect._tcp\t192.168.1.20:37099
ARASAKA-AB12CD34\t_adb-tls-pairing._tcp\t192.168.1.20:41231
""")
assert ms == [("adb-RZ8N90ABCDE-XyZ", "_adb-tls-connect._tcp", "192.168.1.20:37099"),
              ("ARASAKA-AB12CD34", "_adb-tls-pairing._tcp", "192.168.1.20:41231")]

name, pw, qr = P.new_pairing()
assert name.startswith("ARASAKA-") and len(pw) == 12 and qr == f"WIFI:T:ADB;S:{name};P:{pw};;"

ls = P.parse_ls("""total 40
drwxrws--- 4 u0_a123 media_rw 3452 2026-11-01 10:22 DCIM
-rw-rw---- 1 u0_a123 media_rw 1048576 2026-11-18 21:05 foto 1.jpg
lrwxrwxrwx 1 root root 21 2026-01-01 00:00 sdcard -> /storage/self/primary
drwxrwx--x 2 root root 3452 2026-01-01 00:00 .
""")
assert [(e.name, e.is_dir, e.size) for e in ls] == [("DCIM", True, 3452), ("sdcard", True, 21), ("foto 1.jpg", False, 1048576)]

calls = []
with mock.patch.object(P, "adb", lambda *a, **k: calls.append(a) or ""):
    P.type_text("X", "a b;c$1")
assert calls[-1] == ("shell", "input", "text", r"a%sb\;c\$1"), calls[-1]

# Xiaomi/POCO: toques bloqueados sem "Depuracao USB (Configuracoes de seguranca)"
props = {"ro.miui.ui.version.name": "V816", "persist.security.adbinput": ""}
with mock.patch.object(P, "adb", lambda *a, **k: props.get(a[-1], "")):
    assert P.input_blocked("X")
    props["persist.security.adbinput"] = "1"
    assert not P.input_blocked("X")
    props["ro.miui.ui.version.name"] = ""; props["persist.security.adbinput"] = ""
    assert not P.input_blocked("X")          # outras marcas: nao bloqueia
blocked = "java.lang.SecurityException: Injecting input events requires the caller (or the source of the instrumentation, if any) to have the INJECT_EVENTS permission."
with mock.patch.object(P, "adb", lambda *a, **k: blocked):
    try:
        P.key("X", "inicio"); raise AssertionError("devia falhar")
    except RuntimeError as e:
        assert "Configurações de segurança" in str(e)
assert "Configurações de segurança" in P.mirror_problem("INFO: ...\n" + blocked)
assert P.mirror_problem("INFO: Renderer: opengl\nINFO: Texture: 1080x2400") is None

# scrcpy antigo (1.25 do Ubuntu) no Android 14: a tela aparece mas o toque quebra
old_log = """scrcpy 1.25 <https://github.com/Genymobile/scrcpy>
java.lang.AssertionError: java.lang.reflect.InvocationTargetException
	at com.genymobile.scrcpy.wrappers.ServiceManager.getInputManager(ServiceManager.java:75)
Caused by: java.lang.NullPointerException
	at android.hardware.input.InputManager.getInstance(InputManager.java:271)"""
assert "1.25" in P.mirror_problem(old_log) and "Central" in P.mirror_problem(old_log)

# espelhar usa o scrcpy oficial baixado, com o mesmo adb do Uplink
import tempfile, os
with tempfile.TemporaryDirectory() as td:
    exe = Path(td) / "scrcpy"; exe.write_text("#!/bin/sh\necho 'scrcpy 5.0.1 <x>'\n"); exe.chmod(0o755)
    (Path(td) / "scrcpy-server").write_text("x")
    seen = {}
    class FakePopen:
        def __init__(self, cmd, **k): seen["cmd"], seen["env"] = cmd, k["env"]
    with mock.patch.object(P, "BUNDLED_SCRCPY", exe), mock.patch.object(P, "CONFIG_DIR", Path(td)):
        assert P.scrcpy_bin() == str(exe) and P.scrcpy_version() == (5, 0)
        with mock.patch.object(P.subprocess, "Popen", FakePopen), mock.patch.object(P, "scrcpy_version", lambda *a: (5, 0)):
            P.mirror("SER", "T")
    assert seen["cmd"][:3] == [str(exe), "-s", "SER"] and "--no-audio" in seen["cmd"], seen["cmd"]
    assert seen["env"]["SCRCPY_SERVER_PATH"].endswith("scrcpy-server")

# pareamento pelo codigo de 6 digitos
for bad in [("192.168.1.20", "123456"), ("192.168.1.20:41231", "12345"), ("x:1", "123456")]:
    try:
        P.pair_code(*bad)
        raise AssertionError(f"aceitou {bad}")
    except ValueError:
        pass
with mock.patch.object(P, "adb", lambda *a, **k: "Successfully paired to 192.168.1.20:41231 [guid=adb-XYZ]"), \
        mock.patch.object(P, "after_pair", lambda addr: f"pareado {addr}"):
    assert P.pair_code("192.168.1.20:41231", "482913") == "pareado 192.168.1.20:41231"
with mock.patch.object(P, "adb", lambda *a, **k: "Failed: Wrong password or connection was dropped."):
    try:
        P.pair_code("192.168.1.20:41231", "000000")
        raise AssertionError("aceitou código errado")
    except RuntimeError as e:
        assert "Wrong password" in str(e)

# depois de parear, conecta pela porta anunciada (outra que a do pareamento)
log = []
fake_adb = lambda *a, **k: (log.append(a), "connected to 192.168.1.80:39171" if a[0] == "connect" else "")[1]
with mock.patch.object(P, "adb", fake_adb), mock.patch.object(P, "mdns", lambda: [("adb-x", "_adb-tls-connect._tcp", "192.168.1.80:39171"),
                                                                            ("adb-y", "_adb-tls-connect._tcp", "192.168.1.55:41000")]):
    assert P.after_pair("192.168.1.80:42177") == "pareado e conectado (192.168.1.80:39171)"
    assert ("connect", "192.168.1.80:39171") in log and not any(x[0] == "connect" and "192.168.1.55" in x[1] for x in log), "só o celular pareado"
with mock.patch.object(P, "adb", lambda *a, **k: ""), mock.patch.object(P, "mdns", lambda: []), mock.patch.object(P.time, "sleep", lambda s: None):
    assert "CONECTAR POR IP" in P.after_pair("192.168.1.80:42177")
for bad in ("192.168.1.80", "abc:12"):
    try:
        P.connect_addr(bad)
        raise AssertionError(bad)
    except ValueError:
        pass
with mock.patch.object(P, "adb", lambda *a, **k: "failed to connect to '192.168.1.80:39999': Connection refused"):
    try:
        P.connect_addr("192.168.1.80:39999")
        raise AssertionError("conectou")
    except RuntimeError:
        pass

# senha: sem confirmar nao abre; confirmada vale o prazo; trancar fecha
g = auth.Gate(minutes=15)
with mock.patch.object(auth, "verify", return_value=(False, "senha cancelada")):
    assert g.unlock() == (False, "senha cancelada") and not g.open
with mock.patch.object(auth, "verify", return_value=(True, "")):
    assert g.unlock()[0] and g.open and 14 * 60 < g.left() <= 15 * 60
g.until = time.time() - 1
assert not g.open, "expira"
g.until = time.time() + 60
g.lock()
assert not g.open
print("OK: aparelhos, mDNS, QR de pareamento, pastas, digitar com segurança e senha")
