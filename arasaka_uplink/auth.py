"""
ARASAKA UPLINK // confirma a senha do sistema antes de mexer no celular (polkit no Linux, Windows Hello ou UAC no Windows).

Usa o polkit (a janela de senha do proprio sistema). Com a acao do Uplink instalada, pede a senha do seu usuario
com a mensagem certa; sem ela, cai na confirmacao padrao de administrador (pkexec /bin/true).
A senha nunca passa pelo Uplink: quem pergunta e confere e o sistema.
"""
from __future__ import annotations

import shutil
import sys
import subprocess
import time
from pathlib import Path

HELPER = Path("/usr/libexec/arasaka-uplink-auth")
POLICY = Path("/usr/share/polkit-1/actions/studio.arasaka.uplink.policy")
UNLOCK_MINUTES = 15


WIN = sys.platform == "win32"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Windows Hello (PIN, digital ou rosto) pela API do proprio Windows; quem pergunta e confere e o sistema.
HELLO = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $t) { $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait(-1) | Out-Null; $task.Result }
$V = [Windows.Security.Credentials.UI.UserConsentVerifier, Windows.Security.Credentials.UI, ContentType = WindowsRuntime]
$a = Await ($V::CheckAvailabilityAsync()) ([Windows.Security.Credentials.UI.UserConsentVerifierAvailability])
if ("$a" -ne 'Available') { exit 3 }
$r = Await ($V::RequestVerificationAsync('Arasaka Uplink: confirme que é você para mexer no celular')) ([Windows.Security.Credentials.UI.UserConsentVerificationResult])
if ("$r" -eq 'Verified') { exit 0 } elseif ("$r" -eq 'Canceled') { exit 126 } else { exit 127 }
"""


def available() -> bool:
    return True if WIN else bool(shutil.which("pkexec"))


def _verify_windows() -> tuple[bool, str]:
    """Windows Hello; sem ele configurado, a confirmacao de administrador do Windows (UAC)."""
    import base64
    def run(script: str) -> int:
        enc = base64.b64encode(script.encode("utf-16-le")).decode()
        return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc], capture_output=True,
                              timeout=300, creationflags=NO_WINDOW).returncode
    try:
        code = run(HELLO)
        if code == 3:   # sem Windows Hello: o UAC (num usuario padrao pede a senha de um administrador)
            code = run("try { Start-Process cmd.exe -ArgumentList '/c','exit' -Verb RunAs -WindowStyle Hidden -Wait; exit 0 } "
                       "catch { exit 126 }")
    except subprocess.TimeoutExpired:
        return False, "tempo esgotado"
    if code == 0:
        return True, ""
    return False, "confirmação cancelada" if code == 126 else "não confirmado pelo Windows"


def verify() -> tuple[bool, str]:
    """(ok, motivo). Abre a janela de senha do sistema e espera."""
    if WIN:
        return _verify_windows()
    if not available():
        return False, "o pkexec (polkit) não está instalado"
    target = str(HELPER) if HELPER.exists() and POLICY.exists() else "/bin/true"
    try:
        r = subprocess.run(["pkexec", target], capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return False, "tempo esgotado"
    if r.returncode == 0:
        return True, ""
    if r.returncode == 126:
        return False, "senha cancelada"
    if r.returncode == 127:
        return False, "senha errada ou sem permissão"
    return False, (r.stderr.strip() or f"pkexec terminou com {r.returncode}")[:160]


class Gate:
    """Destrava por alguns minutos depois da senha; cada uso renova o prazo."""

    def __init__(self, minutes: int = UNLOCK_MINUTES):
        self.minutes = minutes
        self.until = 0.0

    @property
    def open(self) -> bool:
        return time.time() < self.until

    def unlock(self) -> tuple[bool, str]:
        ok, why = verify()
        if ok:
            self.until = time.time() + self.minutes * 60
        return ok, why

    def touch(self):
        if self.open:
            self.until = time.time() + self.minutes * 60

    def lock(self):
        self.until = 0.0

    def left(self) -> int:
        return max(0, int(self.until - time.time()))
