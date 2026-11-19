"""
ARASAKA UPLINK // aba Celular: controlar o celular Android pelo PC (com a senha do Linux).
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import QByteArray, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QVBoxLayout, QWidget)

from . import auth, core, phone
from .kit import CutFrame, Page, button, label


class Runner(QObject):
    """Roda trabalho do adb fora da interface e devolve o resultado na thread da interface."""
    done = Signal(object, object)       # (rotulo, resultado ou excecao)
    line = Signal(str)

    def run(self, tag, fn, *args, **kw):
        def go():
            try:
                r = fn(*args, **kw)
            except Exception as e:  # noqa: BLE001
                r = e
            try:
                self.done.emit(tag, r)
            except RuntimeError:
                pass
        threading.Thread(target=go, daemon=True).start()


class FilesDialog(QDialog):
    def __init__(self, page, serial: str, title: str):
        super().__init__(page)
        self.page, self.serial = page, serial
        self.setWindowTitle(f"Arquivos · {title}")
        self.resize(760, 560)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(button("↑ PASTA DE CIMA", None, self.up))
        self.path = QLineEdit("/sdcard")
        self.path.returnPressed.connect(self.load)
        top.addWidget(self.path, 1)
        top.addWidget(button("ATUALIZAR", None, self.load))
        lay.addLayout(top)
        self.list = QListWidget()
        self.list.setObjectName("files")
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.itemDoubleClicked.connect(self.open)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addWidget(button("COPIAR PARA O PC", "primary", self.pull))
        row.addWidget(button("ENVIAR ARQUIVOS PARA CÁ", None, self.push))
        row.addStretch()
        self.status = label("", "muted")
        row.addWidget(self.status)
        lay.addLayout(row)
        self.runner = Runner()
        self.runner.done.connect(self._done)
        self.load()

    def load(self):
        self.status.setText("lendo...")
        self.runner.run("ls", phone.ls, self.serial, self.path.text().rstrip("/") or "/")

    def _done(self, tag, r):
        if isinstance(r, Exception):
            self.status.setText(f"erro: {r}")
            return
        if tag == "ls":
            self.list.clear()
            for e in r:
                it = QListWidgetItem(("▸ " if e.is_dir else "   ") + e.name + ("" if e.is_dir else f"   ·   {e.size / 1048576:.1f} MB") + f"   ·   {e.when}")
                it.setData(Qt.UserRole, (e.name, e.is_dir))
                self.list.addItem(it)
            self.status.setText(f"{len(r)} item(ns)")
        else:
            self.status.setText(str(r))
            if tag == "push":
                self.load()

    def open(self, it):
        name, is_dir = it.data(Qt.UserRole)
        if is_dir:
            self.path.setText(self.path.text().rstrip("/") + "/" + name)
            self.load()

    def up(self):
        p = self.path.text().rstrip("/")
        self.path.setText(p.rsplit("/", 1)[0] or "/")
        self.load()

    def pull(self):
        items = self.list.selectedItems()
        if not items or not self.page.gate_ok():
            return
        dest = QFileDialog.getExistingDirectory(self, "Copiar para", str(phone.default_dest()))
        if not dest:
            return
        base = self.path.text().rstrip("/")
        names = [it.data(Qt.UserRole)[0] for it in items]
        self.status.setText("copiando...")

        def work():
            for n in names:
                phone.pull(self.serial, f"{base}/{n}", Path(dest))
            return f"copiado: {len(names)} item(ns) para {dest}"
        self.runner.run("pull", work)

    def push(self):
        if not self.page.gate_ok():
            return
        files, _ = QFileDialog.getOpenFileNames(self, "Enviar para o celular", str(core.HOME))
        if files:
            self.status.setText("enviando...")
            base = self.path.text()
            self.runner.run("push", lambda: ([phone.push(self.serial, Path(f), base) for f in files], f"enviado: {len(files)} arquivo(s)")[1])


class PhonePage(Page):
    def __init__(self, win):
        super().__init__(win, "CELULAR", "Use o seu celular Android pelo PC, até com a tela quebrada", "UPLINK://LINK-ANDROID")
        self.gate = auth.Gate()
        self.runner = Runner()
        self.runner.done.connect(self._done)
        self.runner.line.connect(self._line)
        self.phones: list[phone.Phone] = []
        self.pairing_stop = False
        self.mirrors = {}

        self.tools_box = CutFrame(cut=10)
        tl = QVBoxLayout(self.tools_box)
        tl.setContentsMargins(16, 10, 16, 10)
        self.tools_lbl = label("", "red", wrap=True)
        tl.addWidget(self.tools_lbl)
        self.lay.addWidget(self.tools_box)

        self.lock_box = CutFrame(cut=12)
        ll = QHBoxLayout(self.lock_box)
        ll.setContentsMargins(18, 12, 18, 12)
        self.lock_lbl = label("", px=1.5, bold=True, wrap=True)
        ll.addWidget(self.lock_lbl, 1)
        self.lock_btn = button("", "primary", self.toggle_lock)
        ll.addWidget(self.lock_btn)
        self.lay.addWidget(self.lock_box)

        body = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(label("CELULARES", "muted", 2, 11, True))
        self.list = QListWidget()
        self.list.setObjectName("files")
        self.list.setMinimumHeight(170)
        self.list.currentRowChanged.connect(lambda *_: self.show_phone())
        left.addWidget(self.list)
        g = QGridLayout()
        g.setSpacing(6)
        g.addWidget(button("PAREAR PELO QR CODE", "primary", self.pair,
                           "No celular: Depuração sem fio > Parear dispositivo com QR code"), 0, 0, 1, 2)
        g.addWidget(button("COM CÓDIGO", None, self.pair_code, "Depuração sem fio > Parear dispositivo com código de pareamento"), 1, 0)
        g.addWidget(button("POR IP", None, self.connect_ip, "Conectar com o \"Endereço IP e porta\" da tela Depuração sem fio"), 1, 1)
        g.addWidget(button("PROCURAR NA REDE", None, lambda: self.scan(True), "Procura celulares já pareados na rede"), 2, 0)
        g.addWidget(button("COMO PAREAR", None, self.how_to, "Passo a passo da primeira vez"), 2, 1)
        left.addLayout(g)
        self.pair_box = CutFrame(cut=10)
        pl = QVBoxLayout(self.pair_box)
        pl.setContentsMargins(14, 12, 14, 12)
        self.qr = QSvgWidget()
        self.qr.setFixedSize(300, 300)
        self.qr.setStyleSheet("background:#fff;")
        pl.addWidget(self.qr, 0, Qt.AlignCenter)
        self.pair_lbl = label("", "muted", wrap=True)
        pl.addWidget(self.pair_lbl)
        pl.addWidget(button("CANCELAR", None, self.cancel_pair))
        self.pair_box.hide()
        left.addWidget(self.pair_box)
        left.addWidget(label("Primeira vez? Faça com a tela do celular funcionando: veja COMO PAREAR.", "dim", wrap=True))
        left.addStretch()
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(340)
        body.addWidget(lw)

        right = QVBoxLayout()
        self.detail = CutFrame(cut=14)
        dl = QVBoxLayout(self.detail)
        dl.setContentsMargins(18, 14, 18, 14)
        self.p_title = label("", px=3, size=18, bold=True)
        self.p_info = label("", "muted", wrap=True)
        dl.addWidget(self.p_title)
        dl.addWidget(self.p_info)
        self.block_box = CutFrame(cut=10)
        self.block_box.set_border(QColor(160, 20, 28))
        bl = QVBoxLayout(self.block_box)
        bl.setContentsMargins(14, 10, 14, 10)
        bl.addWidget(label("■  O CELULAR BLOQUEIA OS TOQUES DO PC", "red", 1.5, bold=True, wrap=True))
        bl.addWidget(label(phone.XIAOMI_HELP, "muted", wrap=True))
        self.block_box.hide()
        dl.addWidget(self.block_box)
        dl.addWidget(button("ESPELHAR E CONTROLAR", "primary", self.mirror))
        self.screen_off = QCheckBox("apagar a tela do celular ao espelhar")
        self.screen_off.setToolTip("Economiza bateria; o PC continua vendo e mexendo")
        dl.addWidget(self.screen_off)
        grid = QGridLayout()
        grid.setSpacing(6)
        acts = [("ACORDAR", lambda: self.key("acordar")), ("INÍCIO", lambda: self.key("inicio")), ("VOLTAR", lambda: self.key("voltar")),
                ("RECENTES", lambda: self.key("recentes")), ("DESLIZAR", self.swipe), ("APAGAR TELA", lambda: self.key("apagar")),
                ("DIGITAR / PIN", self.type), ("ARQUIVOS", self.files), ("RESGATAR TUDO", self.rescue)]
        for i, (txt, fn) in enumerate(acts):
            grid.addWidget(button(txt, "danger" if txt == "RESGATAR TUDO" else None, fn), i // 3, i % 3)
        dl.addLayout(grid)
        dl.addWidget(label("RESGATAR TUDO copia para o PC: fotos e vídeos (DCIM), imagens, filmes, músicas, documentos, downloads, gravações "
                           "e a mídia do WhatsApp e do Telegram.", "dim", wrap=True))
        right.addWidget(self.detail)
        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(110)
        self.log.setMaximumHeight(180)
        right.addWidget(self.log)
        body.addLayout(right, 1)
        self.lay.addLayout(body)
        self.lay.addWidget(label("O próprio Android mostra uma notificação enquanto a depuração estiver conectada. Para tirar o acesso do PC: no celular, "
                                 "Opções do desenvolvedor > Revogar autorizações de depuração USB.", "dim", wrap=True))

        self.keep = QTimer(self)
        self.keep.timeout.connect(lambda: self.scan(False))
        self.keep.start(20000)
        self.tick = QTimer(self)
        self.tick.timeout.connect(self.refresh_lock)
        self.tick.start(1000)
        self.watch = QTimer(self)
        self.watch.timeout.connect(self.watch_mirrors)
        self.watch.start(1500)
        self.names: dict[str, str] = {}

    # ------------------------------------------------ senha
    def gate_ok(self) -> bool:
        if self.gate.open:
            self.gate.touch()
            return True
        self.win.toast("Destrave com a sua senha do Linux primeiro")
        return False

    def toggle_lock(self):
        if self.gate.open:
            self.gate.lock()
            self.refresh_lock()
            return
        self.lock_btn.setEnabled(False)
        self.lock_lbl.setText("■  CONFIRME A SENHA NA JANELA DO SISTEMA...")
        self.runner.run("unlock", self.gate.unlock)

    def refresh_lock(self):
        if self.gate.open:
            left = self.gate.left()
            self.lock_box.set_border(QColor(40, 110, 50))
            self.lock_lbl.setText(f"■  DESTRAVADO · tranca sozinho em {left // 60}:{left % 60:02d} sem uso")
            self.lock_btn.setText("TRANCAR AGORA")
        else:
            self.lock_box.set_border(QColor(120, 10, 18))
            self.lock_lbl.setText("■  TRANCADO · para mexer no celular, confirme a sua senha do Linux")
            self.lock_btn.setText("DESTRAVAR COM A SENHA")
        self.lock_btn.setEnabled(True)
        self.detail.setEnabled(self.gate.open and bool(self.current()))

    # ------------------------------------------------ lista e conexao
    def refresh(self):
        t = phone.tools()
        missing = [k for k, v in t.items() if not v]
        old = t["scrcpy"] and phone.scrcpy_version(t["scrcpy"]) < (2, 0)
        self.tools_box.setVisible(bool(missing or old))
        if missing:
            self.tools_lbl.setText(f"Falta instalar: {', '.join(missing)}. Reinstale o Uplink pela Arasaka Central.")
        elif old:
            v = phone.scrcpy_version(t["scrcpy"])
            msg = phone.OLD_SCRCPY.format(v=f"{v[0]}.{v[1]}")
            self.tools_lbl.setText(msg[0].upper() + msg[1:])
        self.refresh_lock()
        self.show_phone()
        self.scan(True)

    def scan(self, verbose: bool):
        if not phone.tools()["adb"]:
            return
        self.runner.run("scan" if verbose else "keep", lambda: (phone.connect_known(), phone.devices())[1])

    def current(self) -> phone.Phone | None:
        i = self.list.currentRow()
        return self.phones[i] if 0 <= i < len(self.phones) else None

    def fill(self):
        cur = self.current().serial if self.current() else None
        self.list.blockSignals(True)
        self.list.clear()
        for p in self.phones:
            st = {"device": "CONECTADO", "unauthorized": "AUTORIZE NO CELULAR", "offline": "OFFLINE"}.get(p.state, p.state.upper())
            it = QListWidgetItem(f"{self.names.get(p.serial, p.name)}\n{'WI-FI' if p.transport == 'wifi' else 'CABO'}  ·  {st}")
            it.setToolTip(p.serial)
            self.list.addItem(it)
        known = phone.load_known()
        live = {p.model for p in self.phones}
        for k, v in known.items():
            if v.get("model") not in live:
                self.list.addItem(f"{v.get('model') or k}\npareado, fora de alcance")
        self.list.blockSignals(False)
        idx = next((i for i, p in enumerate(self.phones) if p.serial == cur), 0 if self.phones else -1)
        self.list.setCurrentRow(idx)
        self.show_phone()

    def show_phone(self):
        p = self.current()
        self.detail.setEnabled(self.gate.open and bool(p and p.ready))
        self.block_box.hide()
        if not p:
            self.p_title.setText("NENHUM CELULAR CONECTADO")
            self.p_info.setText("Pareie pelo QR code ou ligue o cabo USB. Se já pareou, ligue a Depuração sem fio no celular (mesma rede Wi-Fi).")
            return
        self.p_title.setText(self.names.get(p.serial, p.name).upper())
        self.p_info.setText(f"{'Wi-Fi' if p.transport == 'wifi' else 'Cabo USB'} · {p.serial}" +
                            ("\nNo celular, aceite \"Permitir depuração\" e marque \"Sempre permitir neste computador\"." if p.state == "unauthorized" else ""))
        if p.ready and self.gate.open:
            self.runner.run("info", phone.info, p.serial)

    def _done(self, tag, r):
        if tag == "unlock":
            ok, why = r if not isinstance(r, Exception) else (False, str(r))
            if not ok:
                self.win.toast(f"Não destravou: {why}")
            self.refresh_lock()
            self.show_phone()
            return
        if isinstance(r, Exception):
            if tag != "keep":
                self._line(f"!! {r}")
            if tag in ("pair", "connect"):
                self.pair_lbl.setText(f"Não pareou: {r}")
            return
        if tag in ("scan", "keep"):
            self.phones = r
            for p in r:
                if p.ready:
                    phone.remember(p)
            self.fill()
        elif tag == "info":
            p = self.current()
            if p:
                if r.get("name") and self.names.get(p.serial) != r["name"]:
                    self.names[p.serial] = r["name"]
                    self.list.item(self.list.currentRow()).setText(f"{r['name']}\n{'WI-FI' if p.transport == 'wifi' else 'CABO'}  ·  CONECTADO")
                self.block_box.setVisible(bool(r.get("input_blocked")))
                self.p_title.setText((r.get("name") or p.name).upper())
                bat = f"bateria {r['battery']}%{' (carregando)' if r['charging'] else ''}" if r.get("battery") is not None else ""
                tela = "tela acesa" if r.get("awake") else "tela apagada" if r.get("awake") is False else ""
                self.p_info.setText(" · ".join(x for x in (f"Android {r.get('android')}", bat, tela, "Wi-Fi" if p.transport == "wifi" else "cabo USB") if x))
        elif tag in ("pair", "connect"):
            self.pair_box.hide()
            self._line(f"■ {r}")
            self.win.toast(str(r))
            self.scan(True)
        elif tag in ("rescue", "msg"):
            self._line(str(r))

    def _line(self, text: str):
        self.log.appendPlainText(text)

    # ------------------------------------------------ parear
    def pair(self):
        if not self.gate_ok():
            return
        name, pw, qr = phone.new_pairing()
        try:
            self.qr.load(QByteArray(core.qr_svg(qr).encode()))
        except ImportError:
            self.win.alert("QR code", "Falta o pacote qrcode: reinstale o Uplink.")
            return
        self.pair_lbl.setText("Leia com o leitor de DENTRO da Depuração sem fio, não com a câmera: Opções do desenvolvedor > toque no nome "
                              "Depuração sem fio > Parear dispositivo com QR code. (A câmera comum mostra uma rede Wi-Fi com senha: ignore.) "
                              "Celular e PC na mesma rede. Esperando...")
        self.pair_box.show()
        self.pairing_stop = False
        self.runner.run("pair", phone.wait_pairing, name, pw, 180, lambda: self.pairing_stop)

    def pair_code(self):
        """Parear com o codigo de 6 digitos (Depuracao sem fio > Parear dispositivo com codigo de pareamento)."""
        if not self.gate_ok():
            return
        addr, ok = QInputDialog.getText(self, "Parear com código",
                                        "No celular: Depuração sem fio > Parear dispositivo com código de pareamento.\n"
                                        "Digite o endereço que aparece lá (IP e porta, ex.: 192.168.1.20:41231):")
        if not ok or not addr.strip():
            return
        code, ok = QInputDialog.getText(self, "Parear com código", "Código de pareamento (6 dígitos):")
        if not ok or not code.strip():
            return
        self._line(f"> pareando com {addr.strip()}...")
        self.runner.run("pair", phone.pair_code, addr.strip(), code.strip())

    def connect_ip(self):
        if not self.gate_ok():
            return
        addr, ok = QInputDialog.getText(self, "Conectar por IP",
                                        "No celular: Opções do desenvolvedor > toque no nome Depuração sem fio.\n"
                                        "Digite o \"Endereço IP e porta\" que aparece lá (ex.: 192.168.1.80:39171):")
        if ok and addr.strip():
            self._line(f"> conectando em {addr.strip()}...")
            self.runner.run("connect", phone.connect_addr, addr.strip())

    def cancel_pair(self):
        self.pairing_stop = True
        self.pair_box.hide()

    # ------------------------------------------------ acoes
    def _need(self) -> phone.Phone | None:
        p = self.current()
        if not p or not p.ready:
            self.win.toast("Nenhum celular conectado")
            return None
        return p if self.gate_ok() else None

    def mirror(self):
        p = self._need()
        if not p:
            return
        try:
            proc = phone.mirror(p.serial, f"ARASAKA UPLINK · {p.name}", self.screen_off.isChecked())
            self.mirrors[p.serial] = [proc, False]
            self._line(f"> espelhando {self.names.get(p.serial, p.name)} (feche a janela para parar)")
        except Exception as e:  # noqa: BLE001
            self.win.alert("Espelhar", str(e))

    def watch_mirrors(self):
        """Le o registro do scrcpy: avisa se o celular bloquear os toques ou se o espelhamento cair."""
        for serial, st in list(self.mirrors.items()):
            proc, told = st
            try:
                log = (core.CONFIG_DIR / "scrcpy.log").read_text(encoding="utf-8", errors="replace")
            except OSError:
                log = ""
            why = phone.mirror_problem(log)
            if why and not told:
                st[1] = True
                self._line(f"!! {why}")
                if "INJECT_EVENTS" in log or "injectInputEvent" in log:
                    self.block_box.show()
                    self.win.toast("O celular bloqueou os toques do PC: veja o aviso vermelho")
            if proc.poll() is not None:
                del self.mirrors[serial]
                if proc.returncode not in (0, None) and not st[1]:
                    tail = [x for x in log.strip().splitlines() if x.strip()][-1:] or ["sem detalhes"]
                    self._line(f"!! o espelhamento fechou com erro: {tail[0]}")
                else:
                    self._line("> espelhamento encerrado")

    def how_to(self):
        self.win.alert("Como parear (primeira vez)",
                       "Faça no celular, com a tela funcionando:\n\n"
                       "1. Configurações > Sobre o telefone > toque 7 vezes em Número da versão (liga as Opções do desenvolvedor).\n\n"
                       "2. Opções do desenvolvedor > ligue Depuração USB e Depuração sem fio. Xiaomi/Redmi/POCO: ligue também "
                       "\"Depuração USB (Configurações de segurança)\", senão o PC só vê a tela e não mexe.\n\n"
                       "3. Pelo Wi-Fi: toque no NOME Depuração sem fio > Parear dispositivo com QR code e leia o QR do Uplink com "
                       "ESSE leitor (a câmera comum não serve). Ou use Parear dispositivo com código de pareamento > COM CÓDIGO.\n\n"
                       "4. Pelo cabo (o mais garantido para tela quebrada): ligue no USB e marque \"Sempre permitir neste computador\".\n\n"
                       "Se o celular não aparecer: PROCURAR NA REDE, ou POR IP com o \"Endereço IP e porta\" da tela Depuração sem fio.")

    def key(self, name):
        p = self._need()
        if p:
            self.runner.run("msg", lambda: (phone.key(p.serial, name), f"tecla: {name}")[1])

    def swipe(self):
        p = self._need()
        if p:
            self.runner.run("msg", lambda: (phone.key(p.serial, "acordar"), time.sleep(0.4), phone.swipe_up(p.serial), "deslizado")[-1])

    def type(self):
        p = self._need()
        if not p:
            return
        text, ok = QInputDialog.getText(self, "Digitar no celular", "Texto ou PIN (o celular recebe como se fosse digitado):", QLineEdit.Password)
        if ok and text:
            enter = text.isdigit()
            self.runner.run("msg", lambda: (phone.type_text(p.serial, text), enter and phone.adb("shell", "input", "keyevent", "KEYCODE_ENTER", serial=p.serial),
                                           "digitado" + (" + Enter" if enter else ""))[-1])

    def files(self):
        p = self._need()
        if p:
            FilesDialog(self, p.serial, p.name).exec()

    def rescue(self):
        p = self._need()
        if not p:
            return
        dest = QFileDialog.getExistingDirectory(self, "Onde salvar o resgate", str(core.HOME))
        if not dest:
            return
        self._line(f"> resgatando {p.name} para {dest} (pode levar bastante tempo)")
        self.runner.run("rescue", phone.rescue, p.serial, Path(dest), on_line=self.runner.line.emit)
