"""Panel de miniaturas al estilo de Vista Previa: seleccionar, arrastrar para ordenar,
soltar PDF o imágenes para insertarlos y borrar páginas con la tecla ⌫."""

from __future__ import annotations

import json

from PySide6.QtCore import QByteArray, QMimeData, QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QListView, QListWidget, QListWidgetItem, QStyle, QStyledItemDelegate,
)

from . import tema
from .combinar import EXT_IMAGEN

MIME_PAGINAS = "application/x-mezquita-paginas"
ROL_PIXMAP = Qt.UserRole + 1
ROL_TAMANO = Qt.UserRole + 2     # QSize de la miniatura (según la proporción de la página)
CAJA = QSize(140, 176)           # tamaño máximo de una miniatura
MARGEN_SUP = 8
ALTO_NUMERO = 26
ZONA_AUTODESPLAZAR = 36


def tam_miniatura(ancho: float, alto: float) -> QSize:
    escala = min(CAJA.width() / max(ancho, 1), CAJA.height() / max(alto, 1))
    return QSize(max(1, round(ancho * escala)), max(1, round(alto * escala)))


def es_archivo_admitido(ruta: str) -> bool:
    return ruta.lower().endswith((".pdf",) + EXT_IMAGEN)


class _Delegado(QStyledItemDelegate):
    def __init__(self, lista: "ListaMiniaturas"):
        super().__init__(lista)
        self.lista = lista

    def sizeHint(self, _opt, idx) -> QSize:
        tam = idx.data(ROL_TAMANO) or CAJA
        # Todo el ancho del panel: así la miniatura queda centrada y toda la fila responde al clic
        return QSize(max(CAJA.width(), self.lista.viewport().width()), MARGEN_SUP + tam.height() + ALTO_NUMERO + 4)

    def paint(self, painter: QPainter, opt, idx) -> None:
        p = tema.paleta()
        tam = idx.data(ROL_TAMANO) or CAJA
        r = opt.rect
        pagina = QRectF(r.center().x() - tam.width() / 2 + 0.5, r.top() + MARGEN_SUP, tam.width(), tam.height())
        seleccionada = bool(opt.state & QStyle.State_Selected)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        if seleccionada:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(p.acento_suave))
            painter.drawRoundedRect(pagina.adjusted(-6, -6, 6, 6), 8, 8)
        elif opt.state & QStyle.State_MouseOver:
            c = QColor(p.texto)
            c.setAlphaF(0.05)
            painter.setPen(Qt.NoPen)
            painter.setBrush(c)
            painter.drawRoundedRect(pagina.adjusted(-6, -6, 6, 6), 8, 8)

        # Sombra suave y página
        sombra = QColor(0, 0, 0, 28)
        painter.setPen(Qt.NoPen)
        painter.setBrush(sombra)
        painter.drawRoundedRect(pagina.adjusted(-1, 0, 1, 2), 2, 2)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRect(pagina)
        pix: QPixmap | None = idx.data(ROL_PIXMAP)
        if pix is not None and not pix.isNull():
            painter.drawPixmap(pagina, pix, QRectF(pix.rect()))
        if seleccionada:
            painter.setPen(QPen(QColor(p.acento), 2.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(pagina.adjusted(-2, -2, 2, 2), 3, 3)
        else:
            painter.setPen(QPen(QColor(p.borde_fuerte), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(pagina)

        # Número de página (en una píldora granate si está seleccionada)
        fuente = QFont(opt.font)
        fuente.setPixelSize(12)
        fuente.setBold(seleccionada)
        painter.setFont(fuente)
        texto = str(idx.row() + 1)
        ancho = max(26, painter.fontMetrics().horizontalAdvance(texto) + 14)
        pildora = QRectF(r.center().x() - ancho / 2, pagina.bottom() + 6, ancho, 18)
        if seleccionada:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(p.acento))
            painter.drawRoundedRect(pildora, 9, 9)
            painter.setPen(QColor("#FFFFFF"))
        else:
            painter.setPen(QColor(p.texto_suave))
        painter.drawText(pildora, Qt.AlignCenter, texto)
        painter.restore()


class ListaMiniaturas(QListWidget):
    """Lista vertical de páginas. No cambia el documento: emite señales para que lo haga la ventana."""
    paginas_movidas = Signal(list, int)     # índices de las páginas, posición de destino (0…n)
    archivos_soltados = Signal(list, int)   # rutas de archivos, posición donde insertarlos
    borrar_pedido = Signal(list)            # índices de las páginas seleccionadas

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("miniaturas")
        self.setItemDelegate(_Delegado(self))
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)  # se dibuja una línea propia, también al soltar archivos
        self.setDefaultDropAction(Qt.MoveAction)
        self.setMouseTracking(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(24)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setResizeMode(QListView.Adjust)
        self._destino: int | None = None    # dónde se insertaría lo arrastrado
        self._velocidad = 0
        self._autodesplazar = QTimer(self)
        self._autodesplazar.setInterval(30)
        self._autodesplazar.timeout.connect(
            lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().value() + self._velocidad))

    # --- Contenido -------------------------------------------------------------
    def cargar(self, tamanos: list[QSize]) -> None:
        """Rellena la lista con páginas en blanco (las miniaturas se pintan después)."""
        self.blockSignals(True)
        self.clear()
        for i, tam in enumerate(tamanos):
            it = QListWidgetItem(str(i + 1))
            it.setData(ROL_TAMANO, tam)
            self.addItem(it)
        self.blockSignals(False)

    def poner_miniatura(self, i: int, pix: QPixmap, tam: QSize) -> None:
        it = self.item(i)
        if it is not None:
            it.setData(ROL_TAMANO, tam)
            it.setData(ROL_PIXMAP, pix)

    def seleccionadas(self) -> list[int]:
        return sorted(self.row(it) for it in self.selectedItems())

    def seleccionar(self, filas: list[int], actual: int | None = None) -> None:
        """Selecciona `filas` sin emitir señales (la vista ya está en su sitio)."""
        self.blockSignals(True)
        self.clearSelection()
        for f in filas:
            if 0 <= f < self.count():
                self.item(f).setSelected(True)
        if actual is not None and 0 <= actual < self.count():
            self.setCurrentRow(actual, self.selectionModel().SelectionFlag.NoUpdate)
            self.scrollToItem(self.item(actual))
        self.blockSignals(False)
        self.viewport().update()

    def keyPressEvent(self, ev) -> None:
        # ⌫ (o Supr) borra las páginas seleccionadas, como en Vista Previa
        if ev.key() in (Qt.Key_Backspace, Qt.Key_Delete) and not (ev.modifiers() & ~Qt.KeypadModifier):
            filas = self.seleccionadas()
            if filas:
                self.borrar_pedido.emit(filas)
            ev.accept()
            return
        super().keyPressEvent(ev)

    # --- Arrastrar páginas -------------------------------------------------------
    def startDrag(self, _acciones) -> None:
        filas = self.seleccionadas()
        if not filas:
            return
        datos = QMimeData()
        datos.setData(MIME_PAGINAS, QByteArray(json.dumps(filas).encode()))
        arrastre = QDrag(self)
        arrastre.setMimeData(datos)
        actual = self.currentItem() if self.currentItem() in self.selectedItems() else self.item(filas[0])
        arrastre.setPixmap(self._imagen_arrastre(actual, len(filas)))
        arrastre.setHotSpot(QPoint(40, 30))
        arrastre.exec(Qt.MoveAction)
        self._fin_arrastre()

    def _imagen_arrastre(self, it: QListWidgetItem, n: int) -> QPixmap:
        p = tema.paleta()
        dpr = self.devicePixelRatioF()
        tam = (it.data(ROL_TAMANO) or CAJA).scaled(QSize(80, 100), Qt.KeepAspectRatio)
        lienzo = QPixmap(QSize(tam.width() + 24, tam.height() + 24) * dpr)
        lienzo.setDevicePixelRatio(dpr)
        lienzo.fill(Qt.transparent)
        painter = QPainter(lienzo)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        pagina = QRectF(6, 12, tam.width(), tam.height())
        if n > 1:  # pila de hojas
            painter.setPen(QPen(QColor(p.borde_fuerte), 1))
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawRect(pagina.translated(5, -5))
        painter.setOpacity(0.92)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRect(pagina)
        pix = it.data(ROL_PIXMAP)
        if pix is not None:
            painter.drawPixmap(pagina, pix, QRectF(pix.rect()))
        painter.setOpacity(1)
        painter.setPen(QPen(QColor(p.acento), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(pagina)
        if n > 1:
            insignia = QRectF(pagina.right() - 4, 2, 22, 22)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(p.acento))
            painter.drawEllipse(insignia)
            fuente = painter.font()
            fuente.setPixelSize(11)
            fuente.setBold(True)
            painter.setFont(fuente)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(insignia, Qt.AlignCenter, str(n))
        painter.end()
        return lienzo

    # --- Soltar (páginas de esta lista o archivos de Finder) --------------------
    def _rutas(self, ev) -> list[str]:
        if not ev.mimeData().hasUrls():
            return []
        return [u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile() and es_archivo_admitido(u.toLocalFile())]

    def _es_interno(self, ev) -> bool:
        return ev.source() is self and ev.mimeData().hasFormat(MIME_PAGINAS)

    def _posicion_destino(self, pos: QPoint) -> int:
        idx = self.indexAt(pos)
        if not idx.isValid():
            if self.count() and pos.y() < self.visualItemRect(self.item(0)).top():
                return 0
            return self.count()
        r = self.visualRect(idx)
        return idx.row() if pos.y() < r.center().y() else idx.row() + 1

    def dragEnterEvent(self, ev) -> None:
        if self._es_interno(ev) or self._rutas(ev):
            ev.setDropAction(Qt.MoveAction if self._es_interno(ev) else Qt.CopyAction)
            ev.accept()
        else:
            ev.ignore()

    def dragMoveEvent(self, ev) -> None:
        if not (self._es_interno(ev) or self._rutas(ev)):
            ev.ignore()
            return
        pos = ev.position().toPoint()
        destino = self._posicion_destino(pos)
        if destino != self._destino:
            self._destino = destino
            self.viewport().update()
        y, alto = pos.y(), self.viewport().height()
        if y < ZONA_AUTODESPLAZAR:
            self._velocidad = -max(4, (ZONA_AUTODESPLAZAR - y) // 2)
        elif y > alto - ZONA_AUTODESPLAZAR:
            self._velocidad = max(4, (y - alto + ZONA_AUTODESPLAZAR) // 2)
        else:
            self._velocidad = 0
        if self._velocidad and not self._autodesplazar.isActive():
            self._autodesplazar.start()
        elif not self._velocidad:
            self._autodesplazar.stop()
        ev.setDropAction(Qt.MoveAction if self._es_interno(ev) else Qt.CopyAction)
        ev.accept()

    def dragLeaveEvent(self, ev) -> None:
        self._fin_arrastre()
        ev.accept()

    def dropEvent(self, ev) -> None:
        destino = self._posicion_destino(ev.position().toPoint())
        interno = self._es_interno(ev)
        rutas = [] if interno else self._rutas(ev)
        self._fin_arrastre()
        if interno:
            filas = json.loads(bytes(ev.mimeData().data(MIME_PAGINAS)).decode())
            ev.setDropAction(Qt.MoveAction)
            ev.accept()
            # Soltarlas justo donde estaban no cambia nada
            if not all(f in filas for f in range(min(filas), max(filas) + 1)) or not (min(filas) <= destino <= max(filas) + 1):
                QTimer.singleShot(0, lambda: self.paginas_movidas.emit(filas, destino))
        elif rutas:
            ev.setDropAction(Qt.CopyAction)
            ev.accept()
            # Fuera del arrastre: así Finder no se queda esperando mientras se piden contraseñas
            QTimer.singleShot(0, lambda: self.archivos_soltados.emit(rutas, destino))
        else:
            ev.ignore()

    def _fin_arrastre(self) -> None:
        self._autodesplazar.stop()
        self._velocidad = 0
        if self._destino is not None:
            self._destino = None
            self.viewport().update()

    def paintEvent(self, ev) -> None:
        super().paintEvent(ev)
        if self._destino is None:
            return
        if self.count() == 0:
            y = 4
        elif self._destino < self.count():
            y = self.visualItemRect(self.item(self._destino)).top() + 1
        else:
            y = self.visualItemRect(self.item(self.count() - 1)).bottom() - 1
        p = tema.paleta()
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(p.acento), 3, Qt.SolidLine, Qt.RoundCap))
        izq, der = 14, self.viewport().width() - 14
        painter.drawLine(izq, y, der, y)
        painter.setBrush(QColor(p.acento))
        painter.drawEllipse(QRectF(izq - 4, y - 4, 8, 8))
        painter.drawEllipse(QRectF(der - 4, y - 4, 8, 8))
        painter.end()
