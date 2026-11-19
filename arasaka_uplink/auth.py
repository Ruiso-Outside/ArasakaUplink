"""
ARASAKA UPLINK // confirma a senha do Linux antes de mexer no celular.

Usa o polkit (a janela de senha do proprio sistema). Com a acao do Uplink instalada, pede a senha do seu usuario
com a mensagem certa; sem ela, cai na confirmacao padrao de administrador (pkexec /bin/true).
A senha nunca passa pelo Uplink: quem pergunta e confere e o sistema.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

HELPER = Path("/usr/libexec/arasaka-uplink-auth")
POLICY = Path("/usr/share/polkit-1/actions/studio.arasaka.uplink.policy")
UNLOCK_MINUTES = 15


def available() -> bool:
    return bool(shutil.which("pkexec"))


def verify() -> tuple[bool, str]:
    """(ok, motivo). Abre a janela de senha do sistema e espera."""
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
