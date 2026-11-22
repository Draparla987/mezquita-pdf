"""Escribir y cambiar texto directamente sobre la página, viendo cómo queda mientras se escribe.

El cuadro se coloca justo donde irá el texto, con la misma letra, tamaño, color e interlineado con
que MuPDF dibuja después el cuadro de texto del PDF: lo que se ve al escribir es lo que queda.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

import pymupdf
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QActionGroup, QColor, QFont, QFontDatabase, QFontMetricsF, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QDoubleSpinBox, QFrame, QMenu, QPushButton, QTextEdit, QToolButton, QVBoxLayout,
)

from . import tema
from .componentes import MuestraColor, Pildora, separador_vertical
from .plataforma import teclas

# Cómo compone MuPDF el texto de un cuadro de texto (en tamaños de letra): el texto empieza en el
# borde izquierdo, la primera línea base queda a 0,8 de arriba y las siguientes van de 1,2 en 1,2
PRIMERA_BASE = 0.8
INTERLINEA = 1.2

# Letra → (código de PyMuPDF para medir y escribir, nombre en la anotación, familias en pantalla)
FUENTES = {
    "Helvetica": ("helv", "Helv", ("Helvetica", "Arial", "Liberation Sans")),
    "Times": ("tiro", "TiRo", ("Times", "Times New Roman", "Liberation Serif")),
    "Courier": ("cour", "Cour", ("Courier", "Courier New", "Liberation Mono")),
}
DE_ANOTACION = {nombre_annot: fuente for fuente, (_c, nombre_annot, _f) in FUENTES.items()}
COLORES = ("#000000", "#8E1B2C", "#E03131", "#1C7ED6", "#2F9E44")
MARGEN_CAJA = 5  # px entre el texto y el recuadro discontinuo


@dataclass(frozen=True)
class Estilo:
    fuente: str = "Helvetica"
    tamano: float = 12.0
    color: str = "#000000"
    negrita: bool = False
    cursiva: bool = False

    @property
    def codigo(self) -> str:
        """Nombre de la fuente estándar de PDF («helv», «hebo», «tiit»…)."""
        base = FUENTES[self.fuente][0]
        if not (self.negrita or self.cursiva):
            return base
        sufijo = "bi" if self.negrita and self.cursiva else "bo" if self.negrita else "it"
        return base[:2] + sufijo

    @property
    def rgb(self) -> tuple[float, float, float]:
        c = QColor(self.color)
        return (c.redF(), c.greenF(), c.blueF())


def estilo_guardado() -> Estilo:
    """El último estilo usado para escribir texto nuevo."""
    s = QSettings()
    fuente = s.value("texto/fuente", "Helvetica")
    try:
        tamano = float(s.value("texto/tamano", 12))
    except (TypeError, ValueError):
        tamano = 12.0
    return Estilo(fuente if fuente in FUENTES else "Helvetica", max(4.0, min(144.0, tamano)),
                  QColor(s.value("texto/color", "#000000")).name())


def guardar_estilo(e: Estilo) -> None:
    s = QSettings()
    s.setValue("texto/fuente", e.fuente)
    s.setValue("texto/tamano", e.tamano)
    s.setValue("texto/color", e.color)


def estilo_de_anotacion(doc: pymupdf.Document, annot) -> Estilo:
    """Letra, tamaño y color de un cuadro de texto, leídos de su /DA («0 0 0 rg /Helv 12 Tf»)."""
    da = doc.xref_get_key(annot.xref, "DA")[1] or ""
    letra = re.search(r"/([\w-]+)\s+([\d.]+)\s+Tf", da)
    fuente = DE_ANOTACION.get(letra.group(1), "Helvetica") if letra else "Helvetica"
    tamano = float(letra.group(2)) if letra and float(letra.group(2)) > 0 else 12.0
    if c := re.search(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+rg", da):
        color = QColor.fromRgbF(*(min(1.0, float(x)) for x in c.groups())).name()
    elif g := re.search(r"([\d.]+)\s+g\b", da):
        color = QColor.fromRgbF(*(min(1.0, float(g.group(1))),) * 3).name()
    else:
        color = "#000000"
    return Estilo(fuente, tamano, color)


_LETRAS: dict[str, pymupdf.Font] = {}


def tamano_texto(texto: str, e: Estilo) -> tuple[float, float]:
    """Ancho y alto (pt) del cuadro de texto que necesita `texto`. MuPDF parte en dos las líneas que
    no caben, así que se mide con su misma letra (get_text_length se queda corto con «á», «ñ» o «€»)."""
    letra = _LETRAS.setdefault(e.codigo, pymupdf.Font(e.codigo))
    lineas = texto.split("\n") or [""]
    ancho = max(letra.text_length(l, fontsize=e.tamano) for l in lineas)
    return ancho + e.tamano * 0.3 + 1, len(lineas) * INTERLINEA * e.tamano + 0.25 * e.tamano


def _familia(fuente: str) -> str:
    disponibles = set(QFontDatabase.families())
    return next((f for f in FUENTES[fuente][2] if f in disponibles), FUENTES[fuente][2][0])


# ----------------------------------------------------------------------------
# El cuadro donde se escribe
# ----------------------------------------------------------------------------
class CuadroTexto(QTextEdit):
    """Texto sin formato, transparente, que crece con lo que se escribe."""
    terminar = Signal()
    cancelar = Signal()
    foco_perdido = Signal()

    def __init__(self, parent, una_linea: bool):
        super().__init__(parent)
        self.una_linea = una_linea
        self.setObjectName("cuadroTexto")
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTabChangesFocus(True)  # un tabulador no se puede escribir en un cuadro de texto de PDF
        self.document().setDocumentMargin(0)
        self.viewport().setAutoFillBackground(False)

    def event(self, ev) -> bool:
        # Que Esc e Intro lleguen aquí y no a los atajos de la ventana
        if ev.type() == QEvent.ShortcutOverride and ev.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            ev.accept()
            return True
        return super().event(ev)

    def keyPressEvent(self, ev) -> None:
        k = ev.key()
        if k == Qt.Key_Escape:
            self.cancelar.emit()
            return
        if k in (Qt.Key_Return, Qt.Key_Enter):
            if self.una_linea or ev.modifiers() & (Qt.ControlModifier | Qt.MetaModifier):
                self.terminar.emit()
            else:  # salto de línea normal (también con ⇧), con el mismo interlineado
                self.textCursor().insertBlock()
            return
        super().keyPressEvent(ev)

    def focusOutEvent(self, ev) -> None:
        super().focusOutEvent(ev)
        self.foco_perdido.emit()


class BarraTexto(Pildora):
    """Letra, tamaño y color del texto que se está escribiendo, pegada al cuadro."""
    cambiada = Signal(object)  # Estilo
    listo = Signal()

    def __init__(self, parent, estilo: Estilo):
        super().__init__(parent)
        self.setObjectName("pildora")
        self.estilo = estilo
        # La letra: un botón con su lista (cada una escrita con su propia letra)
        self.boton_letra = QToolButton()
        self.boton_letra.setObjectName("botonLetra")
        self.boton_letra.setPopupMode(QToolButton.InstantPopup)
        self.boton_letra.setToolTip("Letra")
        self.boton_letra.setCursor(Qt.PointingHandCursor)
        menu = QMenu(self.boton_letra)
        grupo = QActionGroup(menu)
        for nombre in FUENTES:
            a = menu.addAction(nombre)
            a.setFont(QFont(_familia(nombre), 14))
            a.setCheckable(True)
            a.setChecked(nombre == estilo.fuente)
            grupo.addAction(a)
            a.triggered.connect(lambda _=False, n=nombre: self._cambiar(fuente=n))
        self.boton_letra.setMenu(menu)
        self.capa.addWidget(self.boton_letra)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(4, 144)
        self.spin.setDecimals(0 if float(estilo.tamano).is_integer() else 1)  # 10,5 pt de un PDF se respeta
        self.spin.setSingleStep(1)
        self.spin.setSuffix(" pt")
        self.spin.setValue(estilo.tamano)
        self.spin.setToolTip("Tamaño")
        self.spin.setKeyboardTracking(False)
        self.spin.valueChanged.connect(lambda v: self._cambiar(tamano=float(v)))
        self.capa.addWidget(self.spin)
        self.capa.addSpacing(4)
        self.capa.addWidget(separador_vertical(20))
        self.capa.addSpacing(4)
        self.muestras: list[MuestraColor] = []
        colores = list(COLORES) if estilo.color.upper() in COLORES else [estilo.color, *COLORES]
        for c in colores:
            m = MuestraColor(QColor(c))
            m.setChecked(c.upper() == estilo.color.upper())
            m.clicked.connect(lambda _=False, col=c: self._cambiar(color=QColor(col).name()))
            self.capa.addWidget(m)
            self.muestras.append(m)
        self.capa.addSpacing(4)
        self.capa.addWidget(separador_vertical(20))
        self.capa.addSpacing(4)
        boton = QPushButton("Listo")
        boton.setObjectName("primario")
        boton.setCursor(Qt.PointingHandCursor)
        boton.setToolTip(teclas("Terminar (⌘↩) · Esc para cancelar"))
        boton.setFocusPolicy(Qt.NoFocus)
        boton.clicked.connect(self.listo)
        self.capa.addWidget(boton)
        self.boton_letra.setText(f"{estilo.fuente}  ▾")

    def _cambiar(self, **cambios) -> None:
        self.estilo = replace(self.estilo, **cambios)
        self.boton_letra.setText(f"{self.estilo.fuente}  ▾")
        for m in self.muestras:
            m.setChecked(m.color.name().upper() == self.estilo.color.upper())
        self.cambiada.emit(self.estilo)


# ----------------------------------------------------------------------------
# Una edición en curso
# ----------------------------------------------------------------------------
class EdicionTexto(QObject):
    """El cuadro de texto y su barra sobre una página. `ancla` es la esquina superior izquierda del
    texto en puntos de la página tal como se ve (girada); la vista llama a `terminar` o `cancelar`.

    `al_terminar(texto, estilo, rect)` recibe el rectángulo (en coordenadas del PDF) del cuadro de
    texto que hace falta, como mínimo de `minimo` (ancho, alto en puntos)."""

    def __init__(self, vista, pagina_widget, *, texto: str, estilo: Estilo, ancla: QPointF,
                 al_terminar, al_cancelar, una_linea: bool = False,
                 minimo: tuple[float, float] = (0.0, 0.0)):
        super().__init__(vista)
        self.vista = vista
        self.w = pagina_widget
        self.indice = pagina_widget.indice
        self.estilo = estilo
        self.ancla = QPointF(ancla)
        self.minimo = minimo
        self.al_terminar = al_terminar
        self.al_cancelar = al_cancelar
        self.cerrada = False
        lienzo = vista.contenedor

        self.caja = QFrame(lienzo)
        self.caja.setObjectName("cajaTexto")
        capa = QVBoxLayout(self.caja)
        capa.setContentsMargins(MARGEN_CAJA, MARGEN_CAJA, MARGEN_CAJA, MARGEN_CAJA)
        self.cuadro = CuadroTexto(self.caja, una_linea)
        self.cuadro.setPlaceholderText("Escribe aquí")
        capa.addWidget(self.cuadro)
        self.barra = BarraTexto(lienzo, estilo)
        # Un clic en la barra o en el recuadro deja el foco en el cuadro. Si no, Qt se lo daría a la
        # vista de debajo y la edición terminaría antes de cambiar el color o el tamaño
        for wid in (self.barra, self.caja):
            wid.setFocusPolicy(Qt.ClickFocus)
            wid.setFocusProxy(self.cuadro)

        self._aplicar_estilo()
        self.cuadro.setPlainText(texto)
        self._interlineado()
        self.cuadro.moveCursor(QTextCursor.End)
        self.cuadro.textChanged.connect(self._texto_cambiado)
        self.cuadro.terminar.connect(self.terminar)
        self.cuadro.cancelar.connect(self.cancelar)
        self.cuadro.foco_perdido.connect(lambda: QTimer.singleShot(0, self._comprobar_foco))
        self.barra.cambiada.connect(self._estilo_cambiado)
        self.barra.listo.connect(self.terminar)
        self.barra.boton_letra.menu().aboutToHide.connect(lambda: QTimer.singleShot(0, self._volver_al_cuadro))
        self.barra.spin.editingFinished.connect(self._volver_al_cuadro)
        self.w.installEventFilter(self)  # la página se mueve o cambia de tamaño (zoom, ventana)
        self.caja.show()
        self.barra.show()
        self.recolocar()
        self.cuadro.setFocus(Qt.OtherFocusReason)

    # --- Aspecto -----------------------------------------------------------------
    def _px(self, pt: float) -> float:
        return pt * self.vista.zoom

    def _aplicar_estilo(self) -> None:
        e, p = self.estilo, tema.paleta()
        dpi = self.cuadro.logicalDpiY() or 72
        tam_pt = self._px(e.tamano) * 72 / dpi  # tamaño en pantalla, en puntos de Qt
        acento = QColor(p.acento)
        self.cuadro.setStyleSheet(
            f"QTextEdit#cuadroTexto {{ background: transparent; border: none; padding: 0; margin: 0;"
            f" font-family: \"{_familia(e.fuente)}\"; font-size: {tam_pt:.3f}pt;"
            f" font-weight: {700 if e.negrita else 400}; font-style: {'italic' if e.cursiva else 'normal'};"
            f" color: {e.color}; selection-color: {e.color};"
            f" selection-background-color: rgba({acento.red()}, {acento.green()}, {acento.blue()}, 0.25); }}")
        self.caja.setStyleSheet(
            f"QFrame#cajaTexto {{ border: 1px dashed {p.acento}; border-radius: 3px;"
            f" background: rgba({acento.red()}, {acento.green()}, {acento.blue()}, 0.04); }}")
        self.cuadro.setCursorWidth(max(1, round(self.vista.zoom)))
        self._interlineado()

    def _interlineado(self) -> None:
        """Todas las líneas a 1,2 veces el tamaño de letra, como las dibuja MuPDF."""
        formato = QTextBlockFormat()
        formato.setLineHeight(self._px(INTERLINEA * self.estilo.tamano), QTextBlockFormat.LineHeightTypes.FixedHeight.value)
        cursor = QTextCursor(self.cuadro.document())
        cursor.select(QTextCursor.Document)
        self.cuadro.blockSignals(True)
        cursor.mergeBlockFormat(formato)
        self.cuadro.blockSignals(False)

    def _texto_cambiado(self) -> None:
        self._interlineado()  # p. ej. al pegar varias líneas
        self.recolocar()

    def _estilo_cambiado(self, estilo: Estilo) -> None:
        self.estilo = estilo
        self._aplicar_estilo()
        self.recolocar()
        self._volver_al_cuadro()

    def _volver_al_cuadro(self) -> None:
        if not self.cerrada:
            self.cuadro.setFocus(Qt.OtherFocusReason)

    def recolocar(self) -> None:
        """Pone el cuadro de modo que su primera línea base caiga donde la pondrá MuPDF."""
        if self.cerrada:
            return
        self.cuadro.ensurePolished()
        doc = self.cuadro.document()
        doc.adjustSize()
        bloque = doc.firstBlock().layout()
        fm = QFontMetricsF(self.cuadro.font())
        if bloque is not None and bloque.lineCount():
            linea = bloque.lineAt(0)
            base_cuadro = bloque.position().y() + linea.y() + linea.ascent()
        else:
            base_cuadro = fm.ascent()
        ancho = max(doc.idealWidth(), fm.horizontalAdvance(self.cuadro.placeholderText())) \
            + self.cuadro.cursorWidth() + 2
        alto = max(doc.size().height(), self._px(INTERLINEA * self.estilo.tamano))
        self.cuadro.setFixedSize(QSize(int(ancho + 1), int(alto + 1)))
        borde = MARGEN_CAJA + 1
        self.caja.setFixedSize(self.cuadro.width() + 2 * borde, self.cuadro.height() + 2 * borde)
        x = self._px(self.ancla.x())
        base = self._px(self.ancla.y() + PRIMERA_BASE * self.estilo.tamano)
        origen = QPointF(self.w.pos()) + QPointF(x - borde, base - base_cuadro - borde)
        self.caja.move(QPoint(round(origen.x()), round(origen.y())))
        self.caja.raise_()
        self.cuadro.horizontalScrollBar().setValue(0)
        self.cuadro.verticalScrollBar().setValue(0)
        # La barra, encima del cuadro (o debajo si no cabe), sin salirse del lienzo
        self.barra.adjustSize()
        lienzo = self.vista.contenedor
        bx = min(max(8, self.caja.x()), max(8, lienzo.width() - self.barra.width() - 8))
        by = self.caja.y() - self.barra.height() - 8
        if by < self.w.y() - 4:
            by = self.caja.y() + self.caja.height() + 8
        self.barra.move(bx, by)
        self.barra.raise_()

    def eventFilter(self, obj, ev) -> bool:
        if obj is self.w and ev.type() in (QEvent.Move, QEvent.Resize):
            QTimer.singleShot(0, self._reajustar)
        return False

    def _reajustar(self) -> None:
        if not self.cerrada:
            self._aplicar_estilo()  # el zoom cambia el tamaño de la letra en pantalla
            self.recolocar()

    # --- Terminar ----------------------------------------------------------------
    def _comprobar_foco(self) -> None:
        """El foco ha salido del cuadro: se termina si ha ido a otra parte de la ventana (no a la
        barra, a una lista desplegable ni a otra app)."""
        if self.cerrada:
            return
        fw = QApplication.focusWidget()
        if fw is None or QApplication.activePopupWidget() is not None:
            return
        if fw is self.cuadro or self.barra.isAncestorOf(fw) or fw.window() is not self.cuadro.window():
            return
        self.terminar()

    def texto(self) -> str:
        return self.cuadro.toPlainText().replace(" ", "\n").replace(" ", "\n").rstrip("\n")

    def rect_pdf(self, texto: str) -> pymupdf.Rect:
        ancho, alto = tamano_texto(texto, self.estilo)
        ancho, alto = max(ancho, self.minimo[0]), max(alto, self.minimo[1])
        m = self.vista.documento.pagina(self.indice).derotation_matrix
        a = pymupdf.Point(self.ancla.x(), self.ancla.y())
        r = pymupdf.Rect(a * m, (a + (ancho, alto)) * m)
        r.normalize()
        return r

    def _cerrar(self) -> None:
        self.cerrada = True
        if self.vista._edicion is self:
            self.vista._edicion = None
        self.w.removeEventFilter(self)
        for wid in (self.caja, self.barra):
            wid.hide()
            wid.deleteLater()
        self.vista.setFocus(Qt.OtherFocusReason)

    def terminar(self) -> None:
        if self.cerrada:
            return
        texto = self.texto()
        rect = self.rect_pdf(texto)
        estilo = self.estilo
        self._cerrar()
        self.al_terminar(texto, estilo, rect)

    def cancelar(self) -> None:
        if self.cerrada:
            return
        self._cerrar()
        self.al_cancelar()
