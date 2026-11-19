"""
ARASAKA // kit de interface compartilhado (estilo, widgets HUD).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import (QObject, QPointF, QProcess, QProcessEnvironment, QRectF, QSize, Qt, QThread, QTimer,
                            Signal)
from PySide6.QtGui import (QAction, QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPen, QPixmap,
                           QPolygonF, QTextCursor)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
                               QPushButton, QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QToolButton,
                               QVBoxLayout, QWidget)

from pathlib import Path as _P

ASSETS = _P(__file__).resolve().parent / "assets"
APP_NAME = "ARASAKA"

RED = QColor(227, 18, 31)
RED_HI = QColor(255, 36, 54)
BG0 = QColor(3, 3, 4)
BG1 = QColor(8, 8, 10)
BG2 = QColor(14, 14, 17)
LINE = QColor(42, 42, 49)
FG = QColor(236, 236, 240)
MUTED = QColor(140, 140, 150)

FONTS = {"ui": "Sans Serif", "mono": "Monospace", "brand": "Sans Serif", "code": "Monospace"}


# ================================================================ fontes e estilo
def load_fonts():
    fid = QFontDatabase.addApplicationFont(str(ASSETS / "cedge1.ttf"))
    fams = set(QFontDatabase.families())
    if fid >= 0:
        FONTS["brand"] = QFontDatabase.applicationFontFamilies(fid)[0]
    for cand in ["Rajdhani", "Bahnschrift", "Inter", "Cantarell", "DejaVu Sans"]:
        if cand in fams:
            FONTS["ui"] = cand
            break
    for cand in ["Share Tech Mono", "JetBrains Mono", "Consolas", "DejaVu Sans Mono", "Monospace"]:
        if cand in fams:
            FONTS["mono"] = cand
            break
    for cand in ["JetBrains Mono", "Fira Code", "Cascadia Code", "Cascadia Mono", "Source Code Pro",
                 "Ubuntu Mono", "Consolas", "DejaVu Sans Mono", "Liberation Mono", "Monospace"]:
        if cand in fams:
            FONTS["code"] = cand
            break


def stylesheet() -> str:
    ui, mono = FONTS["ui"], FONTS["mono"]
    size = 15 if ui == "Rajdhani" else 13
    return f"""
* {{ font-family: "{ui}"; font-size: {size}px; color: #ececf0; outline: none; }}
QMainWindow, QWidget#root, QDialog, QMessageBox {{ background: #070708; }}
QWidget#page {{ background: transparent; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}

QFrame#sidebar {{ background: #030304; border-right: 1px solid #2a0a0d; }}
QPushButton#nav {{
  text-align: left; padding: 13px 20px; border: none; border-left: 3px solid transparent;
  color: #8c8c96; font-weight: 700; background: transparent;
}}
QPushButton#nav:hover {{ color: #ffffff; background: rgba(227,18,31,0.08); }}
QPushButton#nav:checked {{ color: #ffffff; border-left: 3px solid #e3121f; background: rgba(227,18,31,0.16); }}

QPushButton, QToolButton {{
  background: #141418; border: 1px solid #2a2a31; padding: 9px 16px; font-weight: 700; color: #ececf0;
}}
QPushButton:hover, QToolButton:hover {{ border-color: #e3121f; background: #1f0a0d; color: #ffffff; }}
QPushButton:pressed, QToolButton:pressed {{ background: #e3121f; }}
QPushButton:disabled {{ color: #4a4a52; border-color: #1b1b20; background: #0c0c0e; }}
QPushButton[kind="primary"] {{ background: #e3121f; border: 1px solid #ff2436; color: #ffffff; }}
QPushButton[kind="primary"]:hover {{ background: #ff2436; }}
QPushButton[kind="primary"]:disabled {{ background: #3a0a0e; border-color: #5a080e; color: #8c5a5e; }}
QPushButton[kind="danger"] {{ background: #16050a; border-color: #5a080e; color: #ff3b47; }}
QPushButton[kind="danger"]:hover {{ background: #e3121f; color: #ffffff; }}
QPushButton[kind="ghost"] {{ background: transparent; border-color: transparent; color: #8c8c96; padding: 4px 10px; }}
QPushButton[kind="ghost"]:hover {{ color: #ffffff; border-color: #e3121f; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

QLineEdit, QComboBox {{
  background: #050506; border: 1px solid #2a2a31; padding: 8px 10px; selection-background-color: #e3121f;
}}
QLineEdit:focus, QComboBox:focus, QComboBox:on {{ border-color: #e3121f; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: none; border-left: 5px solid transparent; border-right: 5px solid transparent;
  border-top: 6px solid #e3121f; width: 0; height: 0; margin-right: 10px; }}
QComboBox QAbstractItemView {{ background: #0a0a0c; border: 1px solid #e3121f; selection-background-color: #e3121f; }}

QListWidget {{ background: #050506; border: 1px solid #1d1d22; }}
QListWidget::item {{ padding: 10px 8px; border-left: 3px solid transparent; }}
QListWidget::item:hover {{ background: rgba(227,18,31,0.10); }}
QListWidget::item:selected {{ background: rgba(227,18,31,0.28); border-left: 3px solid #e3121f; color: #ffffff; }}
QListWidget#grid::item {{ padding: 12px 4px; margin: 4px; border: 1px solid #1d1d22; background: #0b0b0e; }}
QListWidget#grid::item:hover {{ border-color: #e3121f; background: #160709; }}
QListWidget#grid::item:selected {{ border: 1px solid #ff2436; background: rgba(227,18,31,0.22); }}

QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #2e2e35; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #e3121f; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; }}
QScrollBar::handle:horizontal {{ background: #2e2e35; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid #4a4a52; background: #050506; }}
QCheckBox::indicator:hover {{ border-color: #e3121f; }}
QCheckBox::indicator:checked {{ background: #e3121f; border-color: #ff2436; }}

QMenu {{ background: #0a0a0c; border: 1px solid #e3121f; padding: 4px; }}
QMenu::item {{ padding: 8px 22px; }}
QMenu::item:selected {{ background: rgba(227,18,31,0.32); }}
QMenu::separator {{ height: 1px; background: #2a2a31; margin: 4px 8px; }}
QToolTip {{ background: #000000; border: 1px solid #e3121f; color: #ececf0; padding: 6px; }}

QLabel#muted {{ color: #8c8c96; }}
QLabel#dim {{ color: #55555e; }}
QLabel#red {{ color: #e3121f; font-weight: 700; }}
QLabel#section {{ color: #e3121f; font-weight: 700; }}

QPlainTextEdit#console {{
  font-family: "{mono}"; font-size: 12px; background: #030304; border: none; color: #c9c9cf;
  selection-background-color: #e3121f;
}}
QFrame#consoleBar {{ background: #050506; border-top: 1px solid #3a0a0f; border-bottom: 1px solid #16161a; }}
QSplitter::handle {{ background: #120507; }}
QDialogButtonBox QPushButton {{ min-width: 110px; }}
"""


def spaced(w: QWidget, px: float = 2.0, size: int | None = None, bold: bool = False, family: str | None = None):
    f = w.font()
    if family:
        f.setFamily(family)
    if size:
        f.setPixelSize(size)
    if bold:
        f.setBold(True)
    f.setLetterSpacing(QFont.AbsoluteSpacing, px)
    w.setFont(f)
    return w


def label(text: str, obj: str | None = None, px: float = 1.0, size: int | None = None, bold=False, wrap=False):
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    spaced(lb, px, size, bold)
    lb.setWordWrap(wrap)
    return lb


def button(text: str, kind: str | None = None, slot=None, tip: str | None = None) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    b.setCursor(Qt.PointingHandCursor)
    spaced(b, 1.5)
    if slot:
        b.clicked.connect(lambda _checked=False, s=slot: s())
    if tip:
        b.setToolTip(tip)
    return b


def logo_pixmap(size: int, path: Path | None = None) -> QPixmap:
    r = QSvgRenderer(str(path or ASSETS / "arasaka.svg"))
    dpr = QApplication.instance().devicePixelRatio() if QApplication.instance() else 1
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r.render(p)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


# ================================================================ widgets visuais
class CutFrame(QFrame):
    """Painel com cantos cortados e borda fina (estilo HUD)."""

    def __init__(self, cut=14, border=LINE, fill=BG2, accent=True, parent=None):
        super().__init__(parent)
        self.cut, self.border, self.fill, self.accent = cut, border, fill, accent
        self.setAttribute(Qt.WA_StyledBackground, False)

    def set_border(self, c: QColor):
        self.border = c
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h, c = self.width() - 1, self.height() - 1, self.cut
        poly = QPolygonF([QPointF(c, 0.5), QPointF(w, 0.5), QPointF(w, h - c), QPointF(w - c, h),
                          QPointF(0.5, h), QPointF(0.5, c)])
        p.setBrush(self.fill)
        p.setPen(QPen(self.border, 1))
        p.drawPolygon(poly)
        if self.accent:
            p.setPen(QPen(RED, 2))
            p.drawLine(QPointF(c, 1), QPointF(c + 34, 1))
            p.drawLine(QPointF(w - c, h - 1), QPointF(w - c - 34, h - 1))


class HudHeader(QWidget):
    """Cabecalho de pagina: titulo na fonte da marca + subtitulo + linha vermelha."""

    def __init__(self, title: str, subtitle: str = "", code: str = ""):
        super().__init__()
        self.title, self.subtitle, self.code = title, subtitle, code
        self.setMinimumHeight(92)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont(FONTS["brand"])
        f.setPixelSize(34)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 6)
        p.setFont(f)
        p.setPen(FG)
        p.drawText(QRectF(0, 6, self.width(), 44), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        f2 = QFont(FONTS["ui"])
        f2.setPixelSize(14)
        f2.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        p.setFont(f2)
        p.setPen(MUTED)
        p.drawText(QRectF(2, 52, self.width(), 22), Qt.AlignLeft | Qt.AlignVCenter, self.subtitle)
        if self.code:
            f3 = QFont(FONTS["mono"])
            f3.setPixelSize(11)
            p.setFont(f3)
            p.setPen(QColor(85, 85, 94))
            p.drawText(QRectF(0, 10, self.width(), 18), Qt.AlignRight | Qt.AlignVCenter, self.code)
        y = self.height() - 6
        p.setPen(QPen(QColor(42, 10, 13), 1))
        p.drawLine(0, y, self.width(), y)
        p.setPen(QPen(RED, 3))
        p.drawLine(0, y, 90, y)
        p.setPen(QPen(RED, 1))
        for i in range(6):
            x = self.width() - 8 - i * 9
            p.drawLine(x, y - 4, x - 4, y + 2)


class Indicator(QWidget):
    """Quadrado de status que pisca quando offline."""

    def __init__(self, ok=True):
        super().__init__()
        self.ok = ok
        self.phase = 0
        self.setFixedSize(14, 14)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(500)

    def set_ok(self, ok):
        self.ok = ok
        self.update()

    def _tick(self):
        self.phase ^= 1
        if not self.ok:
            self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        if self.ok:
            p.fillRect(2, 2, 10, 10, FG)
            p.setPen(QPen(RED, 1))
            p.drawRect(0, 0, 13, 13)
        else:
            p.fillRect(2, 2, 10, 10, RED if self.phase else QColor(90, 8, 14))


class StatusCard(CutFrame):
    def __init__(self, check, on_fix):
        super().__init__(cut=12)
        self.setMinimumHeight(104)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        top = QHBoxLayout()
        self.ind = Indicator(check.ok)
        top.addWidget(self.ind)
        t = label(check.title, px=2, bold=True)
        top.addWidget(t)
        top.addStretch()
        state = label("ONLINE" if check.ok else ("OPCIONAL" if check.optional else "OFFLINE"),
                      "muted" if check.ok else "red", px=2, size=12)
        top.addWidget(state)
        lay.addLayout(top)
        d = label(check.detail, "muted", px=0.5, wrap=True)
        lay.addWidget(d)
        if not check.ok and check.action:
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(button("INSTALAR" if check.key != "i386" else "ATIVAR", "primary",
                                 lambda: on_fix(check.action)))
            lay.addLayout(row)
        else:
            lay.addStretch()
        self.set_border(LINE if check.ok else QColor(90, 8, 14))


class HeroBanner(QWidget):
    """Banner grande com logo, grade e titulo (pagina Roblox Studio)."""

    def __init__(self, title: str, kicker: str):
        super().__init__()
        self.title, self.kicker = title, kicker
        self.status = ""
        self.ok = True
        self.logo = logo_pixmap(150)
        self.setMinimumHeight(210)

    def set_status(self, text: str, ok: bool):
        self.status, self.ok = text, ok
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        path = QPainterPath()
        c = 22
        path.moveTo(c, 0)
        path.lineTo(w, 0)
        path.lineTo(w, h - c)
        path.lineTo(w - c, h)
        path.lineTo(0, h)
        path.lineTo(0, c)
        path.closeSubpath()
        p.fillPath(path, QColor(10, 3, 5))
        p.save()
        p.setClipPath(path)
        p.setPen(QPen(QColor(227, 18, 31, 26), 1))
        for x in range(0, w, 32):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, 32):
            p.drawLine(0, y, w, y)
        p.setOpacity(0.10)
        big = logo_pixmap(420)
        p.drawPixmap(w - 330, int(h / 2 - 210), big)
        p.setOpacity(1)
        p.restore()
        p.setPen(QPen(QColor(227, 18, 31, 160), 1))
        p.drawPath(path)
        p.drawPixmap(36, int(h / 2 - 75), self.logo)
        x0 = 220
        f = QFont(FONTS["ui"])
        f.setPixelSize(14)
        f.setBold(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 4)
        p.setFont(f)
        p.setPen(RED)
        p.drawText(QRectF(x0, h / 2 - 70, w - x0, 24), Qt.AlignLeft | Qt.AlignVCenter, self.kicker)
        fb = QFont(FONTS["brand"])
        fb.setPixelSize(46)
        fb.setLetterSpacing(QFont.AbsoluteSpacing, 8)
        p.setFont(fb)
        p.setPen(FG)
        p.drawText(QRectF(x0, h / 2 - 44, w - x0, 64), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        fs = QFont(FONTS["mono"])
        fs.setPixelSize(13)
        p.setFont(fs)
        p.fillRect(QRectF(x0, h / 2 + 36, 10, 10), FG if self.ok else RED)
        p.setPen(FG if self.ok else RED_HI)
        p.drawText(QRectF(x0 + 20, h / 2 + 30, w - x0, 22), Qt.AlignLeft | Qt.AlignVCenter, self.status)


class SidebarBrand(QWidget):
    def __init__(self, subtitle: str = "BRIDGE"):
        super().__init__()
        self.subtitle = subtitle
        self.setFixedHeight(150)
        self.logo = logo_pixmap(64)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        p.drawPixmap(int(w / 2 - 32), 18, self.logo)
        f = QFont(FONTS["brand"])
        f.setPixelSize(22)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 5)
        p.setFont(f)
        p.setPen(FG)
        p.drawText(QRectF(0, 88, w, 28), Qt.AlignCenter, "ARASAKA")
        f2 = QFont(FONTS["ui"])
        f2.setPixelSize(12)
        f2.setBold(True)
        f2.setLetterSpacing(QFont.AbsoluteSpacing, 6)
        p.setFont(f2)
        p.setPen(RED)
        p.drawText(QRectF(0, 116, w, 18), Qt.AlignCenter, self.subtitle)
        p.setPen(QPen(QColor(42, 10, 13), 1))
        p.drawLine(20, 146, w - 20, 146)



class BaseDialog(QDialog):
    def __init__(self, parent, title: str, subtitle: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(26, 18, 26, 20)
        self.lay.setSpacing(12)
        self.lay.addWidget(HudHeader(title, subtitle))

    def add_buttons(self, ok_text="CONFIRMAR"):
        box = QDialogButtonBox()
        ok = button(ok_text, "primary")
        cancel = button("CANCELAR")
        box.addButton(cancel, QDialogButtonBox.RejectRole)
        box.addButton(ok, QDialogButtonBox.AcceptRole)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        self.lay.addSpacing(6)
        self.lay.addWidget(box)
        return ok



class Page(QWidget):
    def __init__(self, win, title: str, subtitle: str, code: str = ""):
        super().__init__()
        self.setObjectName("page")
        self.win = win
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("page")
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(36, 26, 36, 26)
        self.lay.setSpacing(16)
        self.lay.addWidget(HudHeader(title, subtitle, code))
        scroll.setWidget(inner)
        outer.addWidget(scroll)

    def refresh(self):
        pass


