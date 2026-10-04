"""Vista de páginas con desplazamiento continuo, zoom y herramientas de edición."""

from __future__ import annotations

from collections import OrderedDict
from enum import Enum, auto

import pymupdf
from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QCursor, QImage, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QFrame, QMenu, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from . import tema
from .documento import Documento

MARGEN = 24
MARGEN_INFERIOR = 84  # deja sitio a la barra flotante de navegación
ESPACIO = 18
MAX_PIXMAPS = 24


class Herramienta(Enum):
    SELECCIONAR = auto()
    MANO = auto()
    RESALTAR = auto()
    SUBRAYAR = auto()
    TACHAR = auto()
    TEXTO = auto()
    NOTA = auto()
    DIBUJO = auto()
    RECTANGULO = auto()
    ELIPSE = auto()
    FLECHA = auto()
    TAPAR = auto()
    EDITAR_TEXTO = auto()
    IMAGEN = auto()
    FIRMA = auto()
    FIRMA_DIGITAL = auto()
    BORRADOR = auto()


HERRAMIENTAS_TEXTO = {Herramienta.SELECCIONAR, Herramienta.RESALTAR,
                      Herramienta.SUBRAYAR, Herramienta.TACHAR}
HERRAMIENTAS_ARRASTRE = {Herramienta.RECTANGULO, Herramienta.ELIPSE, Herramienta.FLECHA,
                         Herramienta.TAPAR, Herramienta.IMAGEN, Herramienta.FIRMA,
                         Herramienta.FIRMA_DIGITAL}


def a_rgb(color: QColor) -> tuple[float, float, float]:
    return (color.redF(), color.greenF(), color.blueF())


class PaginaWidget(QWidget):
    """Una página renderizada. Delega los eventos de ratón en la vista."""

    def __init__(self, vista: "VistaPDF", indice: int):
        super().__init__()
        self.vista = vista
        self.indice = indice
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.actualizar_tamano()

    def actualizar_tamano(self) -> None:
        r = self.vista.documento.pagina(self.indice).rect
        z = self.vista.zoom
        self.setFixedSize(QSize(max(1, round(r.width * z)), max(1, round(r.height * z))))

    # --- Conversión de coordenadas ---------------------------------------
    def a_pdf(self, p: QPointF) -> pymupdf.Point:
        pagina = self.vista.documento.pagina(self.indice)
        z = self.vista.zoom
        return pymupdf.Point(p.x() / z, p.y() / z) * pagina.derotation_matrix

    def a_pantalla(self, r: pymupdf.Rect) -> QRectF:
        pagina = self.vista.documento.pagina(self.indice)
        z = self.vista.zoom
        rr = pymupdf.Rect(r) * pagina.rotation_matrix
        rr.normalize()
        return QRectF(rr.x0 * z, rr.y0 * z, rr.width * z, rr.height * z)

    def punto_pantalla(self, p: pymupdf.Point) -> QPointF:
        pagina = self.vista.documento.pagina(self.indice)
        z = self.vista.zoom
        q = pymupdf.Point(p) * pagina.rotation_matrix
        return QPointF(q.x * z, q.y * z)

    # --- Dibujo ----------------------------------------------------------
    def paintEvent(self, _ev) -> None:
        painter = QPainter(self)
        pix = self.vista.pixmap_de(self.indice)
        if pix is not None:
            painter.drawPixmap(self.rect(), pix)
        else:
            painter.fillRect(self.rect(), Qt.white)
        painter.setPen(QColor(0, 0, 0, 22))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.setRenderHint(QPainter.Antialiasing)
        self.vista.dibujar_superposicion(self, painter)
        painter.end()

    # --- Ratón -----------------------------------------------------------
    def mousePressEvent(self, ev) -> None:
        self.vista.raton_pulsado(self, ev)

    def mouseMoveEvent(self, ev) -> None:
        self.vista.raton_movido(self, ev)

    def mouseReleaseEvent(self, ev) -> None:
        self.vista.raton_soltado(self, ev)

    def mouseDoubleClickEvent(self, ev) -> None:
        self.vista.doble_click(self, ev)

    def contextMenuEvent(self, ev) -> None:
        self.vista.menu_contextual(self, ev)


class Lienzo(QWidget):
    """Fondo de la vista: color cálido y sombra suave bajo cada página."""

    def __init__(self, vista: "VistaPDF"):
        super().__init__()
        self.vista = vista
        self.setObjectName("contenedor")

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.fillRect(ev.rect(), QColor(tema.paleta().lienzo))
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        zona = ev.rect().adjusted(-30, -30, 30, 30)
        for w in self.vista.paginas:
            g = w.geometry()
            if not g.intersects(zona):
                continue
            for i, alfa in enumerate((26, 18, 12, 8, 5, 3)):
                r = QRectF(g).adjusted(-i, -i + 2, i, i + 3)
                p.setBrush(QColor(0, 0, 0, alfa))
                p.drawRoundedRect(r, 2 + i, 2 + i)
        p.end()


class VistaPDF(QScrollArea):
    pagina_cambiada = Signal(int)
    zoom_cambiado = Signal(float)
    documento_modificado = Signal()
    mensaje = Signal(str)
    # Peticiones a la ventana principal (necesitan diálogos)
    pedir_texto = Signal(int, object)          # página, punto PDF
    pedir_nota = Signal(int, object)
    pedir_imagen = Signal(int, object)         # página, rect PDF
    pedir_firma_manuscrita = Signal(int, object)
    pedir_firma_digital = Signal(int, object)
    pedir_editar_texto = Signal(int, object)   # página, info de la línea
    pedir_campo_formulario = Signal(int, object)
    pedir_editar_anotacion = Signal(int, int)  # página, xref

    def __init__(self, parent=None):
        super().__init__(parent)
        self.documento: Documento | None = None
        self.zoom = 1.0
        self.herramienta = Herramienta.SELECCIONAR
        self.color = QColor(255, 220, 0)
        self.color_trazo = QColor(220, 30, 30)
        self.grosor = 2.0
        self.paginas: list[PaginaWidget] = []
        self._pixmaps: OrderedDict[tuple[int, float], QPixmap] = OrderedDict()
        self._palabras: dict[int, list] = {}
        self._lineas: dict[int, list] = {}

        # Estado de interacción
        self._pagina_activa: PaginaWidget | None = None
        self._inicio: QPointF | None = None
        self._actual: QPointF | None = None
        self._trazo: list[QPointF] = []
        self._seleccion: tuple[int, list[pymupdf.Rect], str] | None = None
        self._hover_linea: tuple[int, pymupdf.Rect] | None = None
        self._hover_anot: tuple[int, pymupdf.Rect] | None = None
        self._arrastre_mano: QPoint | None = None

        # Búsqueda
        self.resultados: list[tuple[int, pymupdf.Rect]] = []
        self.resultado_actual = -1

        self.contenedor = Lienzo(self)
        self.capa = QVBoxLayout(self.contenedor)
        self.capa.setContentsMargins(MARGEN, MARGEN, MARGEN, MARGEN_INFERIOR)
        self.capa.setSpacing(ESPACIO)
        self.capa.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.setWidget(self.contenedor)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setAlignment(Qt.AlignHCenter)
        self.contenedor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.verticalScrollBar().valueChanged.connect(self._al_desplazar)
        self._ultima_pagina = -1

    # ------------------------------------------------------------------
    # Documento
    # ------------------------------------------------------------------
    def set_documento(self, documento: Documento | None) -> None:
        self.documento = documento
        self.limpiar_busqueda()
        self.recargar(conservar_posicion=False)

    def recargar(self, conservar_posicion: bool = True) -> None:
        """Reconstruye las páginas tras un cambio en el documento."""
        pagina = self.pagina_actual() if conservar_posicion else 0
        self._pixmaps.clear()
        self._palabras.clear()
        self._lineas.clear()
        self._seleccion = None
        self._hover_linea = None
        self._hover_anot = None
        for w in self.paginas:
            self.capa.removeWidget(w)
            w.deleteLater()
        self.paginas = []
        if self.documento is None:
            return
        for i in range(self.documento.num_paginas):
            w = PaginaWidget(self, i)
            self.capa.addWidget(w, 0, Qt.AlignHCenter)
            self.paginas.append(w)
        if conservar_posicion:
            QTimer.singleShot(0, lambda: self.ir_a_pagina(min(pagina, len(self.paginas) - 1), suave=False))

    def refrescar_pagina(self, indice: int) -> None:
        """Vuelve a renderizar una página modificada."""
        for clave in [k for k in self._pixmaps if k[0] == indice]:
            del self._pixmaps[clave]
        self._palabras.pop(indice, None)
        self._lineas.pop(indice, None)
        if 0 <= indice < len(self.paginas):
            self.paginas[indice].actualizar_tamano()
            self.paginas[indice].update()

    def _modificado(self, indice: int) -> None:
        self.refrescar_pagina(indice)
        self.documento_modificado.emit()

    def pixmap_de(self, indice: int) -> QPixmap | None:
        if self.documento is None:
            return None
        dpr = self.devicePixelRatioF()
        clave = (indice, round(self.zoom * dpr, 3))
        pix = self._pixmaps.get(clave)
        if pix is not None:
            self._pixmaps.move_to_end(clave)
            return pix
        pagina = self.documento.pagina(indice)
        m = pymupdf.Matrix(self.zoom * dpr, self.zoom * dpr)
        try:
            pm = pagina.get_pixmap(matrix=m, alpha=False, annots=True)
        except Exception:
            return None
        img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy()
        pix = QPixmap.fromImage(img)
        pix.setDevicePixelRatio(dpr)
        self._pixmaps[clave] = pix
        while len(self._pixmaps) > MAX_PIXMAPS:
            self._pixmaps.popitem(last=False)
        return pix

    # ------------------------------------------------------------------
    # Navegación y zoom
    # ------------------------------------------------------------------
    def pagina_actual(self) -> int:
        if not self.paginas:
            return 0
        centro = self.verticalScrollBar().value() + self.viewport().height() // 3
        for w in self.paginas:
            if w.y() + w.height() + ESPACIO / 2 >= centro:
                return w.indice
        return len(self.paginas) - 1

    def _al_desplazar(self, _v) -> None:
        p = self.pagina_actual()
        if p != self._ultima_pagina:
            self._ultima_pagina = p
            self.pagina_cambiada.emit(p)

    def ir_a_pagina(self, indice: int, y_pdf: float | None = None, suave: bool = True) -> None:
        if not self.paginas or not (0 <= indice < len(self.paginas)):
            return
        w = self.paginas[indice]
        y = w.y() - MARGEN // 2
        if y_pdf is not None:
            y = w.y() + int(y_pdf * self.zoom) - self.viewport().height() // 3
        self.verticalScrollBar().setValue(max(0, y))
        self._ultima_pagina = -1
        self._al_desplazar(0)

    def set_zoom(self, zoom: float, ancla: QPoint | None = None) -> None:
        zoom = max(0.1, min(8.0, zoom))
        if abs(zoom - self.zoom) < 1e-4 or not self.paginas:
            self.zoom = zoom
            self.zoom_cambiado.emit(zoom)
            return
        barra_v, barra_h = self.verticalScrollBar(), self.horizontalScrollBar()
        if ancla is None:
            ancla = QPoint(self.viewport().width() // 2, self.viewport().height() // 2)
        fy = (barra_v.value() + ancla.y() - MARGEN) / max(1, self.contenedor.height() - 2 * MARGEN)
        fx = (barra_h.value() + ancla.x()) / max(1, self.contenedor.width())
        self.zoom = zoom
        for w in self.paginas:
            w.actualizar_tamano()
        self.contenedor.adjustSize()
        QApplication.processEvents()
        barra_v.setValue(int(fy * (self.contenedor.height() - 2 * MARGEN) + MARGEN - ancla.y()))
        barra_h.setValue(int(fx * self.contenedor.width() - ancla.x()))
        self.zoom_cambiado.emit(zoom)

    def ajustar_ancho(self) -> None:
        if not self.documento:
            return
        ancho = self.documento.pagina(self.pagina_actual()).rect.width
        disponible = self.viewport().width() - 2 * MARGEN - self.verticalScrollBar().width()
        self.set_zoom(disponible / ancho)

    def ajustar_pagina(self) -> None:
        if not self.documento:
            return
        p = self.pagina_actual()
        r = self.documento.pagina(p).rect
        disp_w = self.viewport().width() - 2 * MARGEN
        disp_h = self.viewport().height() - MARGEN - MARGEN_INFERIOR
        self.set_zoom(min(disp_w / r.width, disp_h / r.height))
        self.ir_a_pagina(p)

    def wheelEvent(self, ev) -> None:
        if ev.modifiers() & (Qt.ControlModifier | Qt.MetaModifier):
            factor = 1.0015 ** ev.angleDelta().y()
            self.set_zoom(self.zoom * factor, ev.position().toPoint())
            ev.accept()
            return
        super().wheelEvent(ev)

    def event(self, ev):
        # Gesto de pellizco en el trackpad del Mac
        if ev.type() == ev.Type.NativeGesture:
            if ev.gestureType() == Qt.ZoomNativeGesture:
                self.set_zoom(self.zoom * (1 + ev.value()), self.viewport().mapFromGlobal(QCursor.pos()))
                return True
        return super().event(ev)

    # ------------------------------------------------------------------
    # Herramientas
    # ------------------------------------------------------------------
    def set_herramienta(self, h: Herramienta) -> None:
        self.herramienta = h
        self._seleccion = None
        self._hover_linea = None
        self._hover_anot = None
        cursores = {
            Herramienta.MANO: Qt.OpenHandCursor,
            Herramienta.SELECCIONAR: Qt.IBeamCursor,
            Herramienta.RESALTAR: Qt.IBeamCursor,
            Herramienta.SUBRAYAR: Qt.IBeamCursor,
            Herramienta.TACHAR: Qt.IBeamCursor,
            Herramienta.TEXTO: Qt.IBeamCursor,
            Herramienta.EDITAR_TEXTO: Qt.IBeamCursor,
            Herramienta.BORRADOR: Qt.PointingHandCursor,
        }
        cursor = cursores.get(h, Qt.CrossCursor)
        for w in self.paginas:
            w.setCursor(cursor)
        self.viewport().update()
        for w in self.paginas:
            w.update()

    def _palabras_de(self, indice: int) -> list:
        if indice not in self._palabras:
            self._palabras[indice] = self.documento.pagina(indice).get_text("words", sort=True)
        return self._palabras[indice]

    def _lineas_de(self, indice: int) -> list[dict]:
        """Líneas de texto con su información de fuente (para editar texto)."""
        if indice not in self._lineas:
            lineas = []
            datos = self.documento.pagina(indice).get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
            for bloque in datos["blocks"]:
                if bloque.get("type") != 0:
                    continue
                for linea in bloque["lines"]:
                    spans = [s for s in linea["spans"] if s["text"].strip()]
                    if not spans:
                        continue
                    texto = "".join(s["text"] for s in linea["spans"]).strip()
                    rect = pymupdf.Rect(linea["bbox"])
                    lineas.append({
                        "rect": rect,
                        "texto": texto,
                        "origen": pymupdf.Point(spans[0]["origin"]),
                        "tamano": spans[0]["size"],
                        "color": spans[0]["color"],
                        "fuente": spans[0]["font"],
                        "flags": spans[0]["flags"],
                        "dir": linea.get("dir", (1, 0)),
                    })
            self._lineas[indice] = lineas
        return self._lineas[indice]

    def _seleccion_flujo(self, indice: int, p0: pymupdf.Point, p1: pymupdf.Point):
        """Selección de texto en orden de lectura entre dos puntos (como Acrobat)."""
        palabras = self._palabras_de(indice)
        if not palabras:
            return [], ""

        def mas_cercana(p):
            mejor, dist = 0, float("inf")
            for i, w in enumerate(palabras):
                r = pymupdf.Rect(w[:4])
                dx = max(r.x0 - p.x, 0, p.x - r.x1)
                dy = max(r.y0 - p.y, 0, p.y - r.y1)
                d = dx * dx + dy * dy * 4
                if d < dist:
                    mejor, dist = i, d
            return mejor

        a, b = mas_cercana(p0), mas_cercana(p1)
        if a > b:
            a, b = b, a
        elegidas = palabras[a:b + 1]
        rects: list[pymupdf.Rect] = []
        texto_lineas: list[str] = []
        clave_ant = None
        for w in elegidas:
            clave = (w[5], w[6])
            r = pymupdf.Rect(w[:4])
            if clave == clave_ant:
                rects[-1] |= r
                texto_lineas[-1] += " " + w[4]
            else:
                rects.append(r)
                texto_lineas.append(w[4])
            clave_ant = clave
        return rects, "\n".join(texto_lineas)

    def _anotacion_en(self, indice: int, p: pymupdf.Point):
        pagina = self.documento.pagina(indice)
        encontrada = None
        for annot in pagina.annots():
            r = pymupdf.Rect(annot.rect)
            r.x0 -= 2; r.y0 -= 2; r.x1 += 2; r.y1 += 2
            if r.contains(p):
                encontrada = annot  # la última es la que está encima
        return encontrada

    def _widget_en(self, indice: int, p: pymupdf.Point):
        for w in self.documento.pagina(indice).widgets():
            if w.rect.contains(p) and w.field_type != pymupdf.PDF_WIDGET_TYPE_SIGNATURE:
                return w
        return None

    def _enlace_en(self, indice: int, p: pymupdf.Point):
        for enlace in self.documento.pagina(indice).get_links():
            if pymupdf.Rect(enlace["from"]).contains(p):
                return enlace
        return None

    # --- Eventos de ratón ------------------------------------------------
    def raton_pulsado(self, w: PaginaWidget, ev) -> None:
        if ev.button() != Qt.LeftButton or self.documento is None:
            return
        pos = ev.position()
        p = w.a_pdf(pos)
        h = self.herramienta
        self._pagina_activa = w
        self._inicio = pos
        self._actual = pos
        if h == Herramienta.MANO:
            self._arrastre_mano = ev.globalPosition().toPoint()
            w.setCursor(Qt.ClosedHandCursor)
        elif h == Herramienta.SELECCIONAR:
            campo = self._widget_en(w.indice, p)
            if campo is not None:
                self._inicio = None
                self.pedir_campo_formulario.emit(w.indice, campo.xref)
                return
            enlace = self._enlace_en(w.indice, p)
            if enlace is not None:
                self._inicio = None
                self._seguir_enlace(enlace)
                return
            self._seleccion = None
        elif h == Herramienta.DIBUJO:
            self._trazo = [pos]
        w.update()

    def raton_movido(self, w: PaginaWidget, ev) -> None:
        if self.documento is None:
            return
        pos = ev.position()
        h = self.herramienta
        if self._inicio is not None and self._pagina_activa is w:
            self._actual = pos
            if h == Herramienta.MANO and self._arrastre_mano is not None:
                g = ev.globalPosition().toPoint()
                d = g - self._arrastre_mano
                self._arrastre_mano = g
                self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
                return
            if h in HERRAMIENTAS_TEXTO:
                rects, texto = self._seleccion_flujo(w.indice, w.a_pdf(self._inicio), w.a_pdf(pos))
                self._seleccion = (w.indice, rects, texto)
            elif h == Herramienta.DIBUJO:
                self._trazo.append(pos)
            w.update()
            return

        # Sin botón pulsado: efectos al pasar el ratón
        p = w.a_pdf(pos)
        if h == Herramienta.EDITAR_TEXTO:
            nueva = None
            for linea in self._lineas_de(w.indice):
                if linea["rect"].contains(p):
                    nueva = (w.indice, linea["rect"])
                    break
            if nueva != self._hover_linea:
                self._hover_linea = nueva
                w.update()
        elif h == Herramienta.BORRADOR:
            annot = self._anotacion_en(w.indice, p)
            nueva = (w.indice, pymupdf.Rect(annot.rect)) if annot else None
            if nueva != self._hover_anot:
                self._hover_anot = nueva
                w.update()
        elif h == Herramienta.SELECCIONAR:
            if self._widget_en(w.indice, p) is not None or self._enlace_en(w.indice, p) is not None:
                w.setCursor(Qt.PointingHandCursor)
            else:
                w.setCursor(Qt.IBeamCursor)

    def raton_soltado(self, w: PaginaWidget, ev) -> None:
        if ev.button() != Qt.LeftButton or self._inicio is None or self._pagina_activa is None:
            return
        w = self._pagina_activa
        inicio, fin = self._inicio, ev.position()
        self._inicio = None
        h = self.herramienta
        pagina = self.documento.pagina(w.indice)
        p0, p1 = w.a_pdf(inicio), w.a_pdf(fin)
        rect = pymupdf.Rect(p0, p1)
        rect.normalize()
        es_click = (fin - inicio).manhattanLength() < 4

        if h == Herramienta.MANO:
            self._arrastre_mano = None
            w.setCursor(Qt.OpenHandCursor)

        elif h == Herramienta.SELECCIONAR:
            if self._seleccion and self._seleccion[2]:
                QApplication.clipboard().setText(self._seleccion[2])
                self.mensaje.emit("Texto copiado al portapapeles")

        elif h in (Herramienta.RESALTAR, Herramienta.SUBRAYAR, Herramienta.TACHAR):
            if self._seleccion and self._seleccion[1]:
                rects = self._seleccion[1]
                self.documento.instantanea()
                if h == Herramienta.RESALTAR:
                    annot = pagina.add_highlight_annot(rects)
                    annot.set_colors(stroke=a_rgb(self.color))
                elif h == Herramienta.SUBRAYAR:
                    annot = pagina.add_underline_annot(rects)
                    annot.set_colors(stroke=a_rgb(self.color_trazo))
                else:
                    annot = pagina.add_strikeout_annot(rects)
                    annot.set_colors(stroke=a_rgb(self.color_trazo))
                annot.update()
                self._seleccion = None
                self._modificado(w.indice)

        elif h == Herramienta.TEXTO:
            self.pedir_texto.emit(w.indice, p0)

        elif h == Herramienta.NOTA:
            self.pedir_nota.emit(w.indice, p0)

        elif h == Herramienta.DIBUJO:
            if len(self._trazo) > 1:
                puntos = [tuple(w.a_pdf(q)) for q in self._trazo]
                self.documento.instantanea()
                annot = pagina.add_ink_annot([puntos])
                annot.set_colors(stroke=a_rgb(self.color_trazo))
                annot.set_border(width=self.grosor)
                annot.update()
                self._modificado(w.indice)
            self._trazo = []

        elif h in (Herramienta.RECTANGULO, Herramienta.ELIPSE, Herramienta.FLECHA):
            if not es_click:
                self.documento.instantanea()
                if h == Herramienta.RECTANGULO:
                    annot = pagina.add_rect_annot(rect)
                elif h == Herramienta.ELIPSE:
                    annot = pagina.add_circle_annot(rect)
                else:
                    annot = pagina.add_line_annot(p0, p1)
                    annot.set_line_ends(pymupdf.PDF_ANNOT_LE_NONE, pymupdf.PDF_ANNOT_LE_CLOSED_ARROW)
                    annot.set_colors(stroke=a_rgb(self.color_trazo), fill=a_rgb(self.color_trazo))
                if h != Herramienta.FLECHA:
                    annot.set_colors(stroke=a_rgb(self.color_trazo))
                annot.set_border(width=self.grosor)
                annot.update()
                self._modificado(w.indice)

        elif h == Herramienta.TAPAR:
            if not es_click:
                self.documento.instantanea()
                pagina.add_redact_annot(rect, fill=(1, 1, 1))
                pagina.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS)
                self._modificado(w.indice)
                self.mensaje.emit("Contenido eliminado de la zona seleccionada")

        elif h == Herramienta.EDITAR_TEXTO:
            for linea in self._lineas_de(w.indice):
                if linea["rect"].contains(p0):
                    self.pedir_editar_texto.emit(w.indice, linea)
                    break

        elif h == Herramienta.IMAGEN:
            self.pedir_imagen.emit(w.indice, p0 if es_click else rect)

        elif h == Herramienta.FIRMA:
            self.pedir_firma_manuscrita.emit(w.indice, p0 if es_click else rect)

        elif h == Herramienta.FIRMA_DIGITAL:
            if es_click:
                self.mensaje.emit("Arrastra para dibujar el recuadro donde irá la firma")
            else:
                self.pedir_firma_digital.emit(w.indice, rect)

        elif h == Herramienta.BORRADOR:
            annot = self._anotacion_en(w.indice, p0)
            if annot is not None:
                self.documento.instantanea()
                pagina.delete_annot(annot)
                self._hover_anot = None
                self._modificado(w.indice)

        w.update()

    def doble_click(self, w: PaginaWidget, ev) -> None:
        if self.documento is None:
            return
        p = w.a_pdf(ev.position())
        annot = self._anotacion_en(w.indice, p)
        if annot is not None and annot.type[0] in (pymupdf.PDF_ANNOT_FREE_TEXT, pymupdf.PDF_ANNOT_TEXT):
            self.pedir_editar_anotacion.emit(w.indice, annot.xref)

    def menu_contextual(self, w: PaginaWidget, ev) -> None:
        if self.documento is None:
            return
        p = w.a_pdf(QPointF(ev.pos()))
        menu = QMenu(self)
        annot = self._anotacion_en(w.indice, p)
        if self._seleccion and self._seleccion[2]:
            texto = self._seleccion[2]
            menu.addAction("Copiar", lambda: QApplication.clipboard().setText(texto))
            menu.addSeparator()
        if annot is not None:
            xref = annot.xref
            tipo = annot.type[0]
            if tipo in (pymupdf.PDF_ANNOT_FREE_TEXT, pymupdf.PDF_ANNOT_TEXT):
                menu.addAction("Editar texto de la anotación…",
                               lambda: self.pedir_editar_anotacion.emit(w.indice, xref))
            menu.addAction("Eliminar anotación", lambda: self.eliminar_anotacion(w.indice, xref))
            menu.addSeparator()
        menu.addAction("Girar página a la derecha", lambda: self.window().girar_pagina(90, w.indice))
        menu.addAction("Eliminar esta página", lambda: self.window().eliminar_pagina(w.indice))
        menu.exec(ev.globalPos())

    def eliminar_anotacion(self, indice: int, xref: int) -> None:
        pagina = self.documento.pagina(indice)
        annot = pagina.load_annot(xref)
        if annot:
            self.documento.instantanea()
            pagina.delete_annot(annot)
            self._modificado(indice)

    def _seguir_enlace(self, enlace: dict) -> None:
        tipo = enlace.get("kind")
        if tipo in (pymupdf.LINK_GOTO, pymupdf.LINK_NAMED) and enlace.get("page", -1) >= 0:
            destino = enlace.get("to")
            self.ir_a_pagina(enlace["page"], destino.y if destino else None)
        elif tipo == pymupdf.LINK_URI and enlace.get("uri"):
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(enlace["uri"]))

    # ------------------------------------------------------------------
    # Superposiciones (selección, búsqueda, previsualización)
    # ------------------------------------------------------------------
    @staticmethod
    def _color_acento(alfa: int = 255) -> QColor:
        c = QColor(tema.paleta().acento)
        c.setAlpha(alfa)
        return c

    def dibujar_superposicion(self, w: PaginaWidget, painter: QPainter) -> None:
        # Resultados de búsqueda
        for i, (pag, r) in enumerate(self.resultados):
            if pag != w.indice:
                continue
            actual = i == self.resultado_actual
            color = QColor(255, 140, 0, 130) if actual else QColor(255, 230, 0, 90)
            painter.fillRect(w.a_pantalla(r), color)

        # Selección de texto
        if self._seleccion and self._seleccion[0] == w.indice:
            for r in self._seleccion[1]:
                painter.fillRect(w.a_pantalla(r), self._color_acento(60))

        # Línea editable bajo el ratón
        if self._hover_linea and self._hover_linea[0] == w.indice:
            painter.setPen(QPen(self._color_acento(), 1.5, Qt.DashLine))
            painter.setBrush(self._color_acento(22))
            painter.drawRect(w.a_pantalla(self._hover_linea[1]).adjusted(-2, -2, 2, 2))

        # Anotación que se borraría
        if self._hover_anot and self._hover_anot[0] == w.indice:
            painter.setPen(QPen(QColor(220, 40, 40), 2, Qt.DashLine))
            painter.setBrush(QColor(220, 40, 40, 30))
            painter.drawRect(w.a_pantalla(self._hover_anot[1]).adjusted(-2, -2, 2, 2))

        if self._pagina_activa is not w or self._inicio is None:
            return
        h = self.herramienta
        if h == Herramienta.DIBUJO and len(self._trazo) > 1:
            camino = QPainterPath(self._trazo[0])
            for q in self._trazo[1:]:
                camino.lineTo(q)
            painter.setPen(QPen(self.color_trazo, self.grosor * self.zoom, Qt.SolidLine,
                                Qt.RoundCap, Qt.RoundJoin))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(camino)
        elif h in HERRAMIENTAS_ARRASTRE and self._actual is not None:
            r = QRectF(self._inicio, self._actual).normalized()
            if h == Herramienta.FLECHA:
                painter.setPen(QPen(self.color_trazo, self.grosor * self.zoom))
                painter.drawLine(self._inicio, self._actual)
            elif h == Herramienta.ELIPSE:
                painter.setPen(QPen(self.color_trazo, self.grosor * self.zoom))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(r)
            elif h == Herramienta.TAPAR:
                painter.setPen(QPen(QColor(220, 40, 40), 1, Qt.DashLine))
                painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
                painter.drawRect(r)
            elif h in (Herramienta.FIRMA_DIGITAL, Herramienta.FIRMA, Herramienta.IMAGEN):
                painter.setPen(QPen(self._color_acento(), 1.5, Qt.DashLine))
                painter.setBrush(self._color_acento(28))
                painter.drawRect(r)
            else:
                painter.setPen(QPen(self.color_trazo, self.grosor * self.zoom))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(r)

    # ------------------------------------------------------------------
    # Búsqueda
    # ------------------------------------------------------------------
    def buscar(self, texto: str) -> int:
        self.resultados = []
        self.resultado_actual = -1
        if self.documento and texto:
            for i in range(self.documento.num_paginas):
                for r in self.documento.pagina(i).search_for(texto):
                    self.resultados.append((i, r))
        if self.resultados:
            # Empezar por el primer resultado a partir de la página actual
            actual = self.pagina_actual()
            self.resultado_actual = next(
                (k for k, (p, _) in enumerate(self.resultados) if p >= actual), 0
            )
            self._mostrar_resultado()
        for w in self.paginas:
            w.update()
        return len(self.resultados)

    def siguiente_resultado(self, paso: int = 1) -> None:
        if not self.resultados:
            return
        self.resultado_actual = (self.resultado_actual + paso) % len(self.resultados)
        self._mostrar_resultado()
        for w in self.paginas:
            w.update()

    def _mostrar_resultado(self) -> None:
        pag, r = self.resultados[self.resultado_actual]
        w = self.paginas[pag]
        rp = w.a_pantalla(r)
        self.ensureVisible(int(w.x() + rp.center().x()), int(w.y() + rp.center().y()),
                           50, self.viewport().height() // 3)
        self.mensaje.emit(f"Resultado {self.resultado_actual + 1} de {len(self.resultados)}")

    def limpiar_busqueda(self) -> None:
        self.resultados = []
        self.resultado_actual = -1
        for w in self.paginas:
            w.update()
