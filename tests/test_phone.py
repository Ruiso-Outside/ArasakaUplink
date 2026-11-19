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
