"""
ARASAKA // efeitos visuais "Cyberpunk" para os apps Qt (o mesmo visual da Arasaka Central).

    from . import fx
    fx.install(win, name="ARASAKA HOLO", icon=ASSETS / "arasaka-holo.svg")

O que entra na janela:
  - monitor CRT por cima de tudo (linhas de varredura, vinheta e uma faixa de varredura que passa de vez em quando);
  - glitch nos títulos de HUD (HudHeader, SidebarBrand, HeroBanner) de tempos em tempos e ao passar o mouse;
  - tela de inicialização Arasaka (clique ou tecla pula);
  - barra de status no rodapé com relógio, letreiro e o botão FX, que liga e desliga os efeitos.

Só visual: não mexe em nada do app. A escolha do FX fica salva (QSettings "Arasaka/fx"); ARASAKA_FX=0 desliga tudo.
O overlay é desenhado uma vez por tamanho de janela (cache), para não gastar processador.
"""
from __future__ import annotations

import os
import random
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSettings, Qt, QTime, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPen, QPixmap, QPolygonF, QRadialGradient
from PySide6.QtWidgets import QVBoxLayout, QWidget

RED = QColor(255, 26, 26)
RED_DIM = QColor(227, 18, 31)
CYAN = QColor(0, 240, 255)
FG = QColor(236, 236, 240)
MUTED = QColor(140, 140, 150)
GLITCH_CLASSES = ("HudHeader", "SidebarBrand", "HeroBanner")
TICKER = ["CORPO-SEC: NENHUMA INTRUSÃO DETECTADA", "NIGHT CITY // FAIXA 7 ESTÁVEL", "SAKURA TOWER // UPLINK ATIVO",
          "BLACKWALL: ÍNTEGRA", "DIVISÃO DE CONTRAINTELIGÊNCIA // MONITORANDO", "LEALDADE É LUCRO", "SAÚDE DO SISTEMA: NOMINAL"]


def _settings() -> QSettings:
    return QSettings("Arasaka", "fx")


def enabled() -> bool:
    if os.environ.get("ARASAKA_FX", "1") == "0":
        return False
    return _settings().value("on", True, bool)


def _mono(px: int, bold=False) -> QFont:
    f = QFont("Monospace")
    f.setStyleHint(QFont.TypeWriter)
    f.setPixelSize(px)
    f.setBold(bold)
    return f


# ---------------------------------------------------------------- monitor CRT
class CRTOverlay(QWidget):
    """Linhas de varredura + vinheta (em cache) e uma faixa de varredura que desce a cada ~9 s."""

    def __init__(self, win: QWidget):
        super().__init__(win)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.NoFocus)
        self._cache: QPixmap | None = None
        self._band = None  # y da faixa (None = parada)
        self._tick = QTimer(self, interval=40, timeout=self._step)
        self._next = QTimer(self, singleShot=True, timeout=self._start_sweep)
        win.installEventFilter(self)
        self.setGeometry(win.rect())
        self._next.start(2500)

    def eventFilter(self, obj, ev):
        if obj is self.parent() and ev.type() == QEvent.Resize:
            self.setGeometry(self.parent().rect())
            self._cache = None
            self.raise_()
        elif obj is self.parent() and ev.type() == QEvent.ChildAdded:
            QTimer.singleShot(0, self.raise_)
        return False

    def _build(self):
        w, h = max(1, self.width()), max(1, self.height())
        pm = QPixmap(w, h)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        line = QColor(0, 0, 0, 46)
        for y in range(0, h, 3):
            p.fillRect(0, y, w, 1, line)
        g = QRadialGradient(QPointF(w / 2, h / 2), max(w, h) * .72)
        g.setColorAt(0.0, QColor(0, 0, 0, 0))
        g.setColorAt(0.62, QColor(0, 0, 0, 0))
        g.setColorAt(1.0, QColor(0, 0, 0, 120))
        p.fillRect(0, 0, w, h, g)
        top = QLinearGradient(0, 0, 0, h * .35)
        top.setColorAt(0, QColor(255, 0, 0, 16))
        top.setColorAt(1, QColor(255, 0, 0, 0))
        p.fillRect(0, 0, w, int(h * .35), top)
        p.end()
        self._cache = pm

    def _start_sweep(self):
        self._band = -self.height() * .25
        self._tick.start()

    def _step(self):
        h = self.height()
        old = self._band
        self._band += max(6, h / 34)
        bh = int(h * .22)
        self.update(0, int(min(old, self._band)) - 2, self.width(), bh + int(abs(self._band - old)) + 4)
        if self._band > h:
            self._band = None
            self._tick.stop()
            self._next.start(random.randint(7000, 12000))

    def paintEvent(self, ev):
        if self._cache is None or self._cache.size() != self.size():
            self._build()
        p = QPainter(self)
        r = ev.rect()
        p.drawPixmap(r, self._cache, r)
        if self._band is not None:
            bh = self.height() * .22
            g = QLinearGradient(0, self._band, 0, self._band + bh)
            g.setColorAt(0, QColor(255, 40, 40, 0))
            g.setColorAt(.5, QColor(255, 40, 40, 20))
            g.setColorAt(1, QColor(255, 40, 40, 0))
            p.fillRect(QRectF(0, self._band, self.width(), bh), g)


# ---------------------------------------------------------------- glitch
class _GlitchLayer(QWidget):
    """Por cima do título: fatias da imagem dele deslocadas, com cópias ciano e vermelha (3 quadros)."""

    def __init__(self, target: QWidget):
        super().__init__(target)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setGeometry(target.rect())
        self.snap = target.grab()
        self.frame = 0
        self.raise_()
        self.show()
        self._t = QTimer(self, interval=90, timeout=self._next)
        self._t.start()

    def _next(self):
        self.frame += 1
        if self.frame >= 4:
            self._t.stop()
            self.deleteLater()
        else:
            self.update()

    def paintEvent(self, _e):
        if self.frame >= 4:
            return
        p = QPainter(self)
        w, h = self.width(), self.height()
        dpr = self.snap.devicePixelRatio() or 1
        rnd = random.Random(self.frame * 7 + w)
        for _ in range(3):
            y = rnd.randint(0, max(1, h - 6))
            sh = rnd.randint(4, max(5, h // 3))
            dx = rnd.choice((-6, -4, 4, 7))
            src = QRectF(0, y * dpr, w * dpr, sh * dpr)
            p.setOpacity(.85)
            p.drawPixmap(QRectF(dx, y, w, sh), self.snap, src)
            p.setCompositionMode(QPainter.CompositionMode_Screen)
            p.setOpacity(.35)
            p.fillRect(QRectF(dx - 2, y, w, sh), CYAN if dx < 0 else RED)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)


class Glitcher(QObject):
    def __init__(self, win: QWidget):
        super().__init__(win)
        self.win = win
        self.on = True
        self._t = QTimer(self, singleShot=True, timeout=self._fire)
        self._arm()
        win.installEventFilter(self)

    def _arm(self):
        self._t.start(random.randint(3500, 9000))

    def targets(self):
        return [w for w in self.win.findChildren(QWidget) if type(w).__name__ in GLITCH_CLASSES and w.isVisible() and w.width() > 20]

    def glitch(self, w: QWidget):
        if self.on and w.isVisible() and not w.findChild(_GlitchLayer):
            _GlitchLayer(w)

    def _fire(self):
        t = self.targets()
        if t and self.on and self.win.isActiveWindow():
            self.glitch(random.choice(t))
        self._arm()

    def watch_hover(self):
        for w in self.targets():
            if not w.property("_cyHover"):
                w.setProperty("_cyHover", True)
                w.setAttribute(Qt.WA_Hover)
                w.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Enter and type(obj).__name__ in GLITCH_CLASSES:
            self.glitch(obj)
        elif obj is self.win and ev.type() in (QEvent.Show, QEvent.WindowActivate):
            QTimer.singleShot(300, self.watch_hover)
        return False


# ---------------------------------------------------------------- inicialização
class BootSplash(QWidget):
    def __init__(self, win: QWidget, name: str, icon: Path | None, kanji: str):
        super().__init__(win)
        self.name, self.kanji = name, kanji
        self.logo = QIcon(str(icon)).pixmap(168, 168) if icon and Path(icon).exists() else None
        hexa = lambda: f"{random.randint(0, 0xFFFFFF):06X}"
        self.lines = [f"> ARASAKA CORP // SUBNET {hexa()}", "> AUTENTICANDO OPERADOR...........  OK",
                      "> CARREGANDO SUBSISTEMAS..........  OK", f"> CRIPTOGRAFIA ICE v7.{random.randint(0, 9)}...........  ATIVA",
                      "> LINK NEURAL ESTABELECIDO"]
        self.shown = 0
        self.out = 0  # quadros da saída
        self.setGeometry(win.rect())
        win.installEventFilter(self)
        self.raise_()
        self.show()
        self.setFocus()
        self._t = QTimer(self, timeout=self._step)
        self._t.start(210)

    def eventFilter(self, obj, ev):
        if obj is self.parent() and ev.type() == QEvent.Resize:
            self.setGeometry(self.parent().rect())
        return False

    def _step(self):
        if self.out:
            self.out += 1
            if self.out > 6:
                self._t.stop()
                self.parent().removeEventFilter(self)
                self.deleteLater()
            self.update()
            return
        self.shown += 1
        if self.shown > len(self.lines) + 1:
            self.finish()
        self.update()

    def finish(self):
        if not self.out:
            self.out = 1
            self._t.start(70)

    def mousePressEvent(self, _e):
        self.finish()

    def keyPressEvent(self, _e):
        self.finish()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if self.out:  # sai fechando ao meio, deslocado
            k = self.out / 6
            cut = int(h / 2 * k)
            p.setClipRect(0, cut, w, max(0, h - 2 * cut))
            p.translate((-1) ** self.out * 10 * k, 0)
        p.fillRect(self.rect(), QColor(3, 0, 0))
        cy = h / 2 - 150
        if self.logo:
            p.drawPixmap(int(w / 2 - 84), int(cy), self.logo)
        f = QFont()
        f.setPixelSize(26)
        f.setBold(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 10)
        p.setFont(f)
        p.setPen(FG)
        p.drawText(QRectF(0, cy + 180, w, 36), Qt.AlignCenter, self.name)
        f2 = QFont()
        f2.setPixelSize(14)
        f2.setLetterSpacing(QFont.AbsoluteSpacing, 8)
        p.setFont(f2)
        p.setPen(RED)
        p.drawText(QRectF(0, cy + 216, w, 22), Qt.AlignCenter, self.kanji)
        p.setFont(_mono(13))
        x0, lw = w / 2 - 260, 520
        for i, line in enumerate(self.lines[:self.shown]):
            ok = line.endswith(("OK", "ATIVA"))
            head = line.rsplit(" ", 1)[0] + " " if ok else line
            p.setPen(QColor(255, 70, 70))
            p.drawText(QPointF(x0, cy + 268 + i * 21), head)
            if ok:
                p.setPen(QColor(25, 230, 164))
                p.drawText(QPointF(x0 + p.fontMetrics().horizontalAdvance(head), cy + 268 + i * 21), line.rsplit(" ", 1)[1])
        by = cy + 268 + len(self.lines) * 21 + 6
        p.fillRect(QRectF(x0, by, lw, 3), QColor(255, 26, 26, 40))
        p.fillRect(QRectF(x0, by, lw * min(1, self.shown / len(self.lines)), 3), RED)
        p.setPen(QColor(0, 0, 0, 90))
        for y in range(0, h, 3):
            p.drawLine(0, y, w, y)


# ---------------------------------------------------------------- barra de status
class StatusStrip(QWidget):
    H = 24

    def __init__(self, ctl: "_FX", kanji: str, extra=None):
        super().__init__()
        self.ctl, self.kanji, self.extra = ctl, kanji, extra
        self.setFixedHeight(self.H)
        self.setCursor(Qt.ArrowCursor)
        hexa = lambda: " ".join(f"{random.randint(0, 0xFFFF):04X}" for _ in range(4))
        msgs = TICKER[:]
        random.shuffle(msgs)
        self.text = "    ///    ".join(f"{m}  ▲  0x{hexa()}" for m in msgs) + "    ///    "
        self.off = 0.0
        self.fx_rect = QRectF()
        self.tick_rect = QRectF()
        self._t = QTimer(self, interval=40, timeout=self._scroll)
        self._t.start()
        self._clock = QTimer(self, interval=1000, timeout=self.update)
        self._clock.start()

    def _scroll(self):
        self.off += 1.6
        if not self.tick_rect.isEmpty():
            self.update(self.tick_rect.toAlignedRect())

    def mousePressEvent(self, e):
        if self.fx_rect.contains(e.position()):
            self.ctl.set_on(not self.ctl.on)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor(10, 0, 0))
        g.setColorAt(1, QColor(5, 5, 5))
        p.fillRect(self.rect(), g)
        p.setPen(QPen(QColor(255, 60, 60, 82), 1))
        p.drawLine(0, 0, w, 0)
        # etiqueta vermelha com o canto cortado
        p.setFont(_mono(11, bold=True))
        tag = "ARASAKA // ONLINE"
        tw = p.fontMetrics().horizontalAdvance(tag) + 34
        p.setPen(Qt.NoPen)
        p.setBrush(RED)
        p.drawPolygon(QPolygonF([QPointF(0, 1), QPointF(tw, 1), QPointF(tw - 10, h), QPointF(0, h)]))
        blink = QTime.currentTime().msec() < 600 or True
        p.setBrush(QColor(0, 0, 0))
        if blink and QTime.currentTime().second() % 2 == 0:
            p.drawRect(QRectF(9, h / 2 - 3, 6, 6))
        p.setPen(QColor(0, 0, 0))
        p.drawText(QRectF(20, 0, tw - 20, h), Qt.AlignVCenter | Qt.AlignLeft, tag)
        x = tw + 6
        p.setFont(_mono(11))

        def item(label, value):
            nonlocal x
            fm = p.fontMetrics()
            p.setPen(MUTED)
            p.drawText(QRectF(x + 10, 0, 400, h), Qt.AlignVCenter | Qt.AlignLeft, label)
            vx = x + 10 + fm.horizontalAdvance(label + " ")
            p.setPen(RED)
            p.drawText(QRectF(vx, 0, 400, h), Qt.AlignVCenter | Qt.AlignLeft, value)
            x = vx + fm.horizontalAdvance(value) + 10
            p.setPen(QPen(QColor(255, 60, 60, 40), 1))
            p.drawLine(int(x), 5, int(x), h - 5)

        item("T", QTime.currentTime().toString("HH:mm:ss"))
        if self.extra:
            try:
                for k, v in self.extra():
                    item(k, v)
            except Exception:  # noqa: BLE001
                pass
        # à direita: FX e kanji
        p.setFont(_mono(11, bold=True))
        fm = p.fontMetrics()
        kw = fm.horizontalAdvance(self.kanji) + 26
        fxw = fm.horizontalAdvance("FX OFF") + 22
        self.fx_rect = QRectF(w - kw - fxw, 0, fxw, h)
        p.setPen(QPen(QColor(255, 60, 60, 40), 1))
        p.drawLine(int(self.fx_rect.left()), 5, int(self.fx_rect.left()), h - 5)
        p.setPen(MUTED)
        p.drawText(self.fx_rect.adjusted(10, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, "FX")
        p.setPen(RED if self.ctl.on else MUTED)
        p.drawText(self.fx_rect.adjusted(10 + fm.horizontalAdvance("FX "), 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, "ON" if self.ctl.on else "OFF")
        p.setPen(RED)
        p.drawText(QRectF(w - kw, 0, kw, h), Qt.AlignCenter, self.kanji)
        # letreiro no meio
        self.tick_rect = QRectF(x + 8, 0, max(0, self.fx_rect.left() - x - 16), h)
        if self.tick_rect.width() > 40:
            p.save()
            p.setClipRect(self.tick_rect)
            p.setFont(_mono(11))
            p.setPen(QColor(255, 90, 90, 140))
            tw = p.fontMetrics().horizontalAdvance(self.text)
            start = self.tick_rect.left() - (self.off % tw)
            while start < self.tick_rect.right():
                p.drawText(QPointF(start, h / 2 + 4), self.text)
                start += tw
            fade = QLinearGradient(self.tick_rect.left(), 0, self.tick_rect.right(), 0)
            fade.setColorAt(0, QColor(8, 2, 2, 255))
            fade.setColorAt(.06, QColor(8, 2, 2, 0))
            fade.setColorAt(.94, QColor(8, 2, 2, 0))
            fade.setColorAt(1, QColor(8, 2, 2, 255))
            p.fillRect(self.tick_rect, fade)
            p.restore()


# ---------------------------------------------------------------- instalação
class _FX(QObject):
    def __init__(self, win, name, icon, kanji, extra, boot):
        super().__init__(win)
        self.win = win
        self.on = enabled()
        # barra de status: embaixo do conteúdo (não usa o statusBar do app, que mostra mensagens)
        old = win.centralWidget()
        if old is not None:
            box = QWidget()
            lay = QVBoxLayout(box)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
            win.takeCentralWidget()
            lay.addWidget(old, 1)
            self.strip = StatusStrip(self, kanji, extra)
            lay.addWidget(self.strip)
            win.setCentralWidget(box)
        else:
            self.strip = None
        self.crt = CRTOverlay(win)
        self.glitcher = Glitcher(win)
        self.apply()
        if boot and self.on and os.environ.get("ARASAKA_FX_BOOT", "1") != "0":
            BootSplash(win, name, icon, kanji)

    def set_on(self, on: bool):
        self.on = on
        _settings().setValue("on", on)
        self.apply()

    def apply(self):
        self.crt.setVisible(self.on)
        self.glitcher.on = self.on
        if self.on:
            self.crt.raise_()
        if self.strip:
            self.strip.update()


def install(win, *, name: str, icon: Path | str | None = None, kanji: str = "荒坂", extra=None, boot: bool = True):
    """Liga os efeitos numa QMainWindow já montada. extra: função que devolve [(rótulo, valor)] para a barra de status."""
    if os.environ.get("ARASAKA_FX", "1") == "0":
        return None
    fx = _FX(win, name, Path(icon) if icon else None, kanji, extra, boot)
    win._arasaka_fx = fx
    return fx
