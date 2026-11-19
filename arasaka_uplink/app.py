"""
ARASAKA UPLINK // interface (PySide6 / Qt 6).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QByteArray, QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QIcon
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from . import core, fx
from .core import APP_NAME, VERSION
from .kit import CutFrame, Page, SidebarBrand, button, label, load_fonts, spaced, stylesheet

EXTRA_QSS = """
QPlainTextEdit { background: #050506; border: 1px solid #2a2a31; color: #ececf0; padding: 6px; }
QListWidget#files::item { padding: 10px; border-bottom: 1px solid #16161a; }
QListWidget#files::item:selected { background: rgba(227,18,31,0.18); border-left: 3px solid #e3121f; }
"""


class Bridge(QObject):
    device = Signal(object)
    file = Signal(object, object)
    text = Signal(object, str)
    progress = Signal(object, str, int, int)
    remote_req = Signal(object)
    stream = Signal()
    paste = Signal(str)


class WatchBar(QWidget):
    """Aviso no topo da tela enquanto um aparelho ve/controla o PC."""

    def __init__(self, on_stop):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.X11BypassWindowManagerHint)
        self.setStyleSheet("background:#e3121f; color:#ffffff;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 6, 8, 6)
        self.lbl = label("", px=2, bold=True)
        self.lbl.setStyleSheet("color:#ffffff;")
        lay.addWidget(self.lbl)
        b = QPushButton("ENCERRAR")
        b.setStyleSheet("background:#000; color:#fff; border:none; padding:6px 14px; font-weight:bold; letter-spacing:2px;")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(on_stop)
        lay.addWidget(b)

    def show_for(self, names: list[str]):
        self.lbl.setText(f"■  UPLINK · {', '.join(names)} está vendo e controlando esta tela")
        self.adjustSize()
        g = QGuiApplication.primaryScreen().geometry()
        self.move(g.x() + (g.width() - self.width()) // 2, g.y())
        self.show()
        self.raise_()


class ConnectPage(Page):
    def __init__(self, win):
        super().__init__(win, "CONECTAR", "Leia o QR code com a câmera do celular, na mesma rede Wi-Fi", "UPLINK://LINK")
        row = QHBoxLayout()
        qrbox = CutFrame(cut=14)
        ql = QVBoxLayout(qrbox)
        ql.setContentsMargins(18, 18, 18, 18)
        self.qr = QSvgWidget()
        self.qr.setFixedSize(280, 280)
        self.qr.setStyleSheet("background:#ffffff;")
        ql.addWidget(self.qr, 0, Qt.AlignCenter)
        self.noqr = label("", "muted", wrap=True)
        ql.addWidget(self.noqr)
        row.addWidget(qrbox)
        info = QVBoxLayout()
        info.addWidget(label("ENDERECO", "muted", 2, 11, True))
        self.url = QLabel()
        self.url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.url.setWordWrap(True)
        spaced(self.url, 0.5, 14)
        info.addWidget(self.url)
        r = QHBoxLayout()
        self.ip = QComboBox()
        self.ip.currentTextChanged.connect(self.refresh)
        r.addWidget(self.ip, 1)
        r.addWidget(button("COPIAR LINK", None, lambda: (QGuiApplication.clipboard().setText(self.win.up.url(self.ip.currentText())), self.win.toast("Link copiado"))))
        info.addLayout(r)
        info.addWidget(label("O link tem um código secreto desta sessão. Cada aparelho novo precisa ser aceito aqui; os aceitos ficam lembrados.",
                             "muted", wrap=True))
        info.addSpacing(10)
        info.addWidget(label("APARELHOS", "muted", 2, 11, True))
        self.devs = QListWidget()
        self.devs.setObjectName("files")
        self.devs.setMinimumHeight(160)
        info.addWidget(self.devs, 1)
        info.addWidget(button("ESQUECER APARELHO", None, self.forget))
        info.addSpacing(10)
        info.addWidget(label("CONTROLE REMOTO", "muted", 2, 11, True))
        rr = QHBoxLayout()
        self.remote_btn = button("", None, self.toggle_remote)
        rr.addWidget(self.remote_btn)
        rr.addStretch()
        info.addLayout(rr)
        self.remote_lbl = label("", "muted", wrap=True)
        info.addWidget(self.remote_lbl)
        row.addLayout(info, 1)
        self.lay.addLayout(row)
        self.fw = CutFrame(cut=10)
        self.fw.set_border(QColor(150, 110, 20))
        fl = QHBoxLayout(self.fw)
        fl.setContentsMargins(16, 10, 16, 10)
        self.fw_lbl = label("", "red", wrap=True)
        fl.addWidget(self.fw_lbl, 1)
        self.fw_btn = button("LIBERAR NO FIREWALL", "primary", self.open_firewall)
        fl.addWidget(self.fw_btn)
        fl.addWidget(button("JÁ LIBEREI", None, self.firewall_done))
        self.lay.insertWidget(1, self.fw)      # logo abaixo do titulo: e o motivo mais comum de o celular nao conectar
        self.lay.addWidget(label("Funciona só na sua rede (HTTP local): use em casa, não em Wi-Fi público.", "dim", wrap=True))
        self.lay.addStretch()

    def refresh_firewall(self):
        on = core.firewall_active() and not self.win.fw_opened
        self.fw.setVisible(on)
        if on:
            nets = ", ".join(core.local_networks())
            self.fw_lbl.setText(f"O firewall do sistema (ufw) está ligado e bloqueia o celular. Libere a porta {self.win.up.port} só para a "
                                f"sua rede ({nets}). Pede a senha de administrador.")

    def firewall_done(self):
        self.win.fw_opened = True
        try:
            core.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            (core.CONFIG_DIR / "firewall-liberado").write_text("ok\n")
        except OSError:
            pass
        self.refresh_firewall()

    def open_firewall(self):
        import shutil
        import subprocess
        if not shutil.which("pkexec"):
            return self.win.alert("Firewall", "Rode no terminal:\n\n" + "\n".join("sudo " + " ".join(c) for c in core.firewall_command(self.win.up.port)))
        self.fw_btn.setEnabled(False)
        ok = True
        for cmd in core.firewall_command(self.win.up.port):
            r = subprocess.run(["pkexec", *cmd], capture_output=True, text=True)
            ok = ok and r.returncode == 0
        self.fw_btn.setEnabled(True)
        if ok:
            self.firewall_done()
            self.win.toast("Porta liberada no firewall para a rede de casa")
        else:
            self.win.alert("Firewall", "Não foi liberado (senha cancelada?). Dá para rodar no terminal:\n\n"
                           + "\n".join("sudo " + " ".join(c) for c in core.firewall_command(self.win.up.port)))

    def refresh(self, *_):
        self.refresh_firewall()
        ips = core.lan_ips()
        if self.ip.count() != len(ips):
            self.ip.blockSignals(True)
            self.ip.clear()
            self.ip.addItems(ips)
            self.ip.blockSignals(False)
        url = self.win.up.url(self.ip.currentText() or None)
        self.url.setText(url.split("#")[0] + "#••••••")
        try:
            self.qr.load(QByteArray(core.qr_svg(url).encode()))
            self.qr.show()
            self.noqr.setText("")
        except ImportError:
            self.qr.hide()
            self.noqr.setText("Falta o pacote qrcode: use COPIAR LINK e mande o link para o celular.")
        self.refresh_remote()
        self.devs.clear()
        for d in sorted(self.win.up.devices.values(), key=lambda d: -d.seen):
            it = QListWidgetItem(f"{d.name}   ·   {d.state.upper()}   ·   {d.ip}")
            it.setData(Qt.UserRole, d.id)
            self.devs.addItem(it)
        for did, name in self.win.up.trusted.items():
            if did not in self.win.up.devices:
                it = QListWidgetItem(f"{name}   ·   LEMBRADO (desconectado)")
                it.setData(Qt.UserRole, did)
                self.devs.addItem(it)

    def refresh_remote(self):
        from . import remote as R
        ok, why = R.supported()
        hub = self.win.up.remote
        self.remote_btn.setText("DESLIGAR O CONTROLE REMOTO" if hub.enabled else "LIGAR O CONTROLE REMOTO")
        self.remote_btn.setEnabled(ok)
        names = hub.watching()
        self.remote_lbl.setText(why if not ok else ("Desligado: os aparelhos só trocam arquivos e textos." if not hub.enabled else
                                (f"Vendo agora: {', '.join(names)}" if names else "Ligado: aparelhos com permissão podem abrir os apps e usar a tela pelo celular.")))

    def toggle_remote(self):
        hub = self.win.up.remote
        hub.enabled = not hub.enabled
        if not hub.enabled:
            self.win.stop_remote()
        self.refresh_remote()

    def forget(self):
        it = self.devs.currentItem()
        if it:
            self.win.up.forget(it.data(Qt.UserRole))
            self.refresh()


class ReceivedPage(Page):
    def __init__(self, win):
        super().__init__(win, "RECEBIDOS", "O que chegou do celular", "UPLINK://INBOX")
        self.where = label("", "muted", wrap=True)
        self.lay.addWidget(self.where)
        self.list = QListWidget()
        self.list.setObjectName("files")
        self.list.setMinimumHeight(260)
        self.list.itemDoubleClicked.connect(lambda it: QDesktopServices.openUrl(QUrl.fromLocalFile(it.data(Qt.UserRole))))
        self.lay.addWidget(self.list, 1)
        r = QHBoxLayout()
        r.addWidget(button("ABRIR PASTA", None, lambda: (self.win.up.recv_dir.mkdir(parents=True, exist_ok=True),
                                                        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.win.up.recv_dir))))))
        r.addWidget(button("TROCAR PASTA...", None, self.pick))
        r.addStretch()
        self.lay.addLayout(r)
        self.lay.addWidget(label("TEXTOS RECEBIDOS", "muted", 2, 11, True))
        self.texts = QPlainTextEdit()
        self.texts.setReadOnly(True)
        self.texts.setMaximumHeight(170)
        self.lay.addWidget(self.texts)
        r2 = QHBoxLayout()
        r2.addWidget(button("COPIAR O ÚLTIMO TEXTO", None, self.copy_last))
        r2.addStretch()
        self.lay.addLayout(r2)
        self.last_text = ""

    def refresh(self):
        self.where.setText(f"Salvando em {self.win.up.recv_dir}")

    def add_file(self, dev, path: Path):
        it = QListWidgetItem(f"{path.name}   ·   {core_size(path)}   ·   de {dev.name}   ·   {time.strftime('%H:%M')}")
        it.setData(Qt.UserRole, str(path))
        self.list.insertItem(0, it)

    def add_text(self, dev, text: str):
        self.last_text = text
        self.texts.setPlainText(f"[{time.strftime('%H:%M')} · {dev.name}]\n{text}\n\n" + self.texts.toPlainText())

    def copy_last(self):
        if self.last_text:
            QGuiApplication.clipboard().setText(self.last_text)
            self.win.toast("Texto copiado")

    def pick(self):
        d = QFileDialog.getExistingDirectory(self, "Pasta dos arquivos recebidos", str(self.win.up.recv_dir))
        if d:
            self.win.up.recv_dir = Path(d)
            self.refresh()


class SendPage(Page):
    def __init__(self, win):
        super().__init__(win, "ENVIAR", "Arquivos e textos que o celular pode baixar", "UPLINK://OUTBOX")
        self.list = QListWidget()
        self.list.setObjectName("files")
        self.list.setMinimumHeight(240)
        self.lay.addWidget(self.list, 1)
        r = QHBoxLayout()
        r.addWidget(button("COMPARTILHAR ARQUIVOS...", "primary", self.add))
        r.addWidget(button("PARAR DE COMPARTILHAR", None, self.remove))
        r.addStretch()
        self.lay.addLayout(r)
        self.lay.addWidget(label("TEXTO PARA O CELULAR", "muted", 2, 11, True))
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("Um link, um endereço, uma senha temporária... aparece na página do celular com o botão COPIAR")
        self.text.setMaximumHeight(110)
        self.lay.addWidget(self.text)
        r2 = QHBoxLayout()
        r2.addWidget(button("ENVIAR TEXTO", None, self.send_text))
        r2.addStretch()
        self.lay.addLayout(r2)
        self.lay.addWidget(label("Os arquivos não são copiados: o celular baixa direto do lugar onde estão, enquanto o Uplink estiver aberto.", "dim", wrap=True))

    def refresh(self):
        self.list.clear()
        for s in self.win.up.shared:
            it = QListWidgetItem(f"{s.name}   ·   {core_size(s.path)}   ·   {s.path.parent}")
            it.setData(Qt.UserRole, s.id)
            self.list.addItem(it)

    def add(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Compartilhar com o celular", str(core.HOME))
        for f in files:
            self.win.up.share(Path(f))
        self.refresh()

    def remove(self):
        it = self.list.currentItem()
        if it:
            self.win.up.unshare(it.data(Qt.UserRole))
            self.refresh()

    def send_text(self):
        t = self.text.toPlainText().strip()
        if t:
            self.win.up.send_text(t)
            self.text.clear()
            self.win.toast("Texto disponível na página do celular")


def core_size(p: Path) -> str:
    try:
        n = p.stat().st_size
    except OSError:
        return "?"
    return f"{n / 1048576:.1f} MB" if n > 1048576 else f"{max(1, n // 1024)} KB"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 760)
        self.fw_opened = (core.CONFIG_DIR / "firewall-liberado").exists()
        self.bridge = Bridge()
        self.up = core.Uplink(on_device=self.bridge.device.emit, on_file=self.bridge.file.emit, on_text=self.bridge.text.emit)
        self.up.on_remote_request = self.bridge.remote_req.emit
        self.up.on_stream = self.bridge.stream.emit
        self.up.on_paste = self.bridge.paste.emit
        self.up.start()
        self.watchbar = WatchBar(self.stop_remote)
        self.bridge.remote_req.connect(self.ask_remote)
        self.bridge.stream.connect(self.update_watch)
        self.bridge.paste.connect(self.paste_text)
        self.bridge.device.connect(self.ask_device)
        self.bridge.file.connect(self.got_file)
        self.bridge.text.connect(self.got_text)
        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(232)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 14)
        sl.setSpacing(2)
        sl.addWidget(SidebarBrand("UPLINK"))
        sl.addSpacing(10)
        self.nav = QButtonGroup(self)
        self.stack = QStackedWidget()
        from .phone_ui import PhonePage
        self.pages = {"connect": ConnectPage(self), "recv": ReceivedPage(self), "send": SendPage(self), "phone": PhonePage(self)}
        for i, (key, text) in enumerate([("connect", "CONECTAR"), ("recv", "RECEBIDOS"), ("send", "ENVIAR"), ("phone", "CELULAR")]):
            b = QPushButton(f"{i + 1:02d}   {text}")
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            spaced(b, 2.5)
            b.clicked.connect(lambda _=False, k=key: self.go(k))
            self.nav.addButton(b, i)
            sl.addWidget(b)
            self.stack.addWidget(self.pages[key])
        sl.addStretch()
        st = label(f"■  ONLINE · PORTA {self.up.port}", "muted", 1.5, 11, True)
        st.setContentsMargins(20, 0, 0, 0)
        sl.addWidget(st)
        ver = label(f"UPLINK v{VERSION}", "dim", 2, 11)
        ver.setContentsMargins(20, 0, 0, 0)
        sl.addWidget(ver)
        h.addWidget(side)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.toast_lbl = QLabel(self)
        self.toast_lbl.setStyleSheet("background:#000; border:1px solid #e3121f; padding:10px 18px; color:#ececf0;")
        self.toast_lbl.hide()
        self.go("connect")

    def go(self, key: str):
        self.nav.button(list(self.pages).index(key)).setChecked(True)
        self.stack.setCurrentWidget(self.pages[key])
        self.pages[key].refresh()

    def ask_device(self, dev):
        self.raise_()
        self.activateWindow()
        mb = QMessageBox(self)
        mb.setWindowTitle("Novo aparelho")
        mb.setText(f"\"{dev.name}\" ({dev.ip}) quer se conectar.")
        mb.setInformativeText("Aceite só se for um aparelho seu. Aceito, ele pode enviar arquivos e textos e baixar o que você compartilhar.")
        yes = mb.addButton("ACEITAR", QMessageBox.AcceptRole)
        yes.setProperty("kind", "primary")
        mb.addButton("RECUSAR", QMessageBox.RejectRole)
        mb.exec()
        self.up.decide(dev.id, mb.clickedButton() is yes)
        self.pages["connect"].refresh()

    def ask_remote(self, dev):
        self.raise_()
        self.activateWindow()
        mb = QMessageBox(self)
        mb.setWindowTitle("Controle remoto")
        mb.setText(f"\"{dev.name}\" quer VER e CONTROLAR a tela deste PC.")
        mb.setInformativeText("Ele vai poder abrir os apps Arasaka, clicar e digitar como se estivesse aqui. Enquanto isso, aparece um aviso "
                              "vermelho no topo da tela, com o botão ENCERRAR. Aceite só se for um aparelho seu.")
        yes = mb.addButton("PERMITIR", QMessageBox.AcceptRole)
        yes.setProperty("kind", "danger")
        once = mb.addButton("SÓ DESTA VEZ", QMessageBox.ActionRole)
        mb.addButton("RECUSAR", QMessageBox.RejectRole)
        mb.exec()
        c = mb.clickedButton()
        self.up.remote.set_perm(dev.id, c in (yes, once), remember=c is not once)   # "so desta vez" nao fica salvo

    def update_watch(self):
        names = self.up.remote.watching()
        if names:
            self.watchbar.show_for(names)
        else:
            self.watchbar.hide()
        self.pages["connect"].refresh_remote()

    def stop_remote(self):
        self.up.remote.end_device(None)
        self.watchbar.hide()
        self.toast("Controle remoto encerrado")

    def paste_text(self, text: str):
        QGuiApplication.clipboard().setText(text)
        QTimer.singleShot(150, lambda: self.up.remote.x.key("ctrl+v"))

    def got_file(self, dev, path):
        self.pages["recv"].add_file(dev, path)
        self.toast(f"Recebido de {dev.name}: {path.name}")

    def got_text(self, dev, text):
        self.pages["recv"].add_text(dev, text)
        self.toast(f"Texto de {dev.name}")

    def toast(self, text: str):
        self.toast_lbl.setText(text)
        spaced(self.toast_lbl, 1)
        self.toast_lbl.adjustSize()
        self.toast_lbl.move(self.width() - self.toast_lbl.width() - 24, 20)
        self.toast_lbl.raise_()
        self.toast_lbl.show()
        QTimer.singleShot(3500, self.toast_lbl.hide)

    def closeEvent(self, e):
        self.watchbar.hide()
        if self.up._remote:
            self.up.remote.end_device(None)
        self.up.stop()
        e.accept()


def main(argv: list[str] | None = None):
    argv = list(sys.argv if argv is None else argv)
    QApplication.setApplicationName(core.APP_ID)
    QApplication.setApplicationDisplayName(APP_NAME)
    QApplication.setDesktopFileName(core.APP_ID)
    app = QApplication(argv)
    load_fonts()
    app.setStyleSheet(stylesheet() + EXTRA_QSS)
    app.setWindowIcon(QIcon(str(core.ASSETS / "arasaka-uplink.svg")))
    win = MainWindow()
    fx.install(win, name=APP_NAME, icon=core.ASSETS / "arasaka-uplink.svg", boot=not any(a.startswith("--screenshot=") for a in argv))
    win.show()
    shot = next((a.split("=", 1)[1] for a in argv if a.startswith("--screenshot=")), None)
    if shot:
        path, _, page = shot.partition(",")
        if page:
            QTimer.singleShot(200, lambda: win.go(page))
        QTimer.singleShot(2600, lambda: (win.grab().save(path), win.up.stop(), app.quit()))
    return app.exec()
