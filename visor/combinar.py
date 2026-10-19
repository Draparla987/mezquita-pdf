"""Combinar varios PDF (o imágenes) en un documento nuevo."""

from __future__ import annotations

import io
import itertools
import os
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps
from PySide6.QtCore import QModelIndex, QRectF, QSettings, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
    QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton, QStackedWidget, QStyle,
    QStyledItemDelegate, QStyleOptionViewItem, QVBoxLayout, QWidget,
)

from . import tema
from .documento import Documento, parsear_rango

EXT_IMAGEN = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")
FILTRO = ("PDF e imágenes (*.pdf *.jpg *.jpeg *.png *.tif *.tiff *.bmp);;"
          "Documentos PDF (*.pdf);;Todos los archivos (*)")
A4 = (595.28, 841.89)
MARGEN_IMAGEN = 24


# ----------------------------------------------------------------------------
# Lógica (sin interfaz)
# ----------------------------------------------------------------------------
@dataclass
class Parte:
    """Un documento de la lista: el PDF abierto y las páginas que se van a usar."""
    nombre: str
    doc: pymupdf.Document
    ruta: str | None = None
    tam: int = 0
    origen: str = "pdf"                 # «pdf», «imagen» o «abierto» (el documento de la ventana)
    paginas: list[int] | None = None    # None = todas
    rango: str = ""                     # tal como lo escribió el usuario
    firmado: bool = False
    miniatura: QPixmap | None = field(default=None, repr=False)

    @property
    def num_usadas(self) -> int:
        return self.doc.page_count if self.paginas is None else len(self.paginas)


def imagen_a_pdf(ruta: str) -> pymupdf.Document:
    """Coloca una foto o escaneo en una página A4 (vertical u horizontal según la imagen)."""
    with Image.open(ruta) as original:
        img = ImageOps.exif_transpose(original)  # fotos del móvil: respeta la orientación
        ancho_px, alto_px = img.size
        buf = io.BytesIO()
        if img.mode in ("RGBA", "LA", "P"):
            img.convert("RGBA").save(buf, "PNG")
        else:
            img.convert("RGB").save(buf, "JPEG", quality=92)
    ancho, alto = A4 if alto_px >= ancho_px else A4[::-1]
    doc = pymupdf.open()
    pagina = doc.new_page(width=ancho, height=alto)
    caja = pagina.rect + (MARGEN_IMAGEN, MARGEN_IMAGEN, -MARGEN_IMAGEN, -MARGEN_IMAGEN)
    pagina.insert_image(caja, stream=buf.getvalue(), keep_proportion=True)
    return doc


def _tramos(paginas: list[int]) -> list[tuple[int, int]]:
    """[0, 1, 2, 5, 4] → [(0, 2), (5, 5), (4, 4)]: bloques seguidos para insert_pdf."""
    tramos: list[list[int]] = []
    for p in paginas:
        if tramos and p == tramos[-1][1] + 1:
            tramos[-1][1] = p
        else:
            tramos.append([p, p])
    return [(a, b) for a, b in tramos]


def combinar(partes: list[Parte], marcador_por_documento: bool = True) -> pymupdf.Document:
    """Devuelve un PDF nuevo con las páginas elegidas de cada parte, en orden."""
    salida = pymupdf.open()
    indice: list[list] = []
    for parte in partes:
        inicio = salida.page_count
        todas = parte.paginas is None
        for a, b in _tramos(list(range(parte.doc.page_count)) if todas else parte.paginas):
            salida.insert_pdf(parte.doc, from_page=a, to_page=b)
        # El índice (marcadores) original solo se conserva si se copia el documento entero
        propio = parte.doc.get_toc(simple=True) if todas else []
        destino = lambda p: inicio + p if p >= 1 else inicio + 1  # noqa: E731
        if marcador_por_documento:
            indice.append([1, Path(parte.nombre).stem, inicio + 1])
            indice += [[nivel + 1, titulo, destino(p)] for nivel, titulo, p in propio]
        else:
            indice += [[nivel, titulo, destino(p)] for nivel, titulo, p in propio]
    if indice:
        salida.set_toc(indice)
    salida.set_metadata({**(salida.metadata or {}), "creator": tema.NOMBRE_APP, "producer": tema.NOMBRE_APP})
    return salida


# ----------------------------------------------------------------------------
# Interfaz
# ----------------------------------------------------------------------------
def _tam_legible(n: int) -> str:
    if n < 1024 * 1024:
        return f"{max(1, round(n / 1024))} KB"
    return f"{n / 1024 / 1024:.1f} MB".replace(".", ",")


def _plural(n: int, singular: str, plural: str | None = None) -> str:
    return f"{n} {singular if n == 1 else (plural or singular + 's')}"


class _Delegado(QStyledItemDelegate):
    """Dibuja cada documento: nº de orden, miniatura, nombre, páginas y avisos."""
    ALTO = 78

    def __init__(self, dialogo: "DialogoCombinar"):
        super().__init__(dialogo)
        self.dialogo = dialogo

    def sizeHint(self, opt, _idx) -> QSize:
        return QSize(opt.rect.width(), self.ALTO)

    def paint(self, painter: QPainter, opt: QStyleOptionViewItem, idx: QModelIndex) -> None:
        parte = self.dialogo.parte_de_indice(idx)
        if parte is None:
            return
        p = tema.paleta()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        r = QRectF(opt.rect).adjusted(5, 3, -5, -3)
        if opt.state & QStyle.State_Selected:
            painter.setPen(QPen(QColor(p.acento), 1.2))
            painter.setBrush(QColor(p.acento_suave))
        elif opt.state & QStyle.State_MouseOver:
            c = QColor(p.texto)
            c.setAlphaF(0.05)
            painter.setPen(Qt.NoPen)
            painter.setBrush(c)
        else:
            painter.setPen(Qt.NoPen)
            painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(r, 10, 10)

        # Número de orden
        circulo = QRectF(r.left() + 10, r.center().y() - 11, 22, 22)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(p.acento))
        painter.drawEllipse(circulo)
        fuente = QFont(opt.font)
        fuente.setPixelSize(11)
        fuente.setBold(True)
        painter.setFont(fuente)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(circulo, Qt.AlignCenter, str(idx.row() + 1))

        # Miniatura de la primera página que se usará
        caja = QRectF(circulo.right() + 12, r.top() + 6, 50, r.height() - 12)
        if parte.miniatura is not None:
            tam = parte.miniatura.deviceIndependentSize()
            destino = QRectF(caja.center().x() - tam.width() / 2, caja.center().y() - tam.height() / 2,
                             tam.width(), tam.height())
            painter.setPen(QPen(QColor(p.borde_fuerte), 1))
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawRect(destino.adjusted(-0.5, -0.5, 0.5, 0.5))
            painter.drawPixmap(destino.toRect(), parte.miniatura)

        # Textos
        x = caja.right() + 14
        ancho = r.right() - x - 12
        fuente = QFont(opt.font)
        fuente.setPixelSize(13)
        fuente.setBold(True)
        painter.setFont(fuente)
        painter.setPen(QColor(p.texto))
        nombre = painter.fontMetrics().elidedText(parte.nombre, Qt.ElideMiddle, int(ancho))
        painter.drawText(QRectF(x, r.top() + 10, ancho, 20), Qt.AlignLeft | Qt.AlignVCenter, nombre)

        fuente.setPixelSize(12)
        fuente.setBold(False)
        painter.setFont(fuente)
        painter.setPen(QColor(p.texto_suave))
        detalles = {"abierto": "Documento abierto ahora", "imagen": "Imagen (se coloca en una página A4)"}
        linea = [detalles.get(parte.origen, "PDF"), _plural(parte.doc.page_count, "página")]
        if parte.tam:
            linea.append(_tam_legible(parte.tam))
        painter.drawText(QRectF(x, r.top() + 30, ancho, 18), Qt.AlignLeft | Qt.AlignVCenter, " · ".join(linea))

        fila3 = QRectF(x, r.top() + 48, ancho, 18)
        if parte.paginas is None:
            texto = "Todas las páginas"
        else:
            painter.setPen(QColor(p.acento))
            texto = f"Páginas {parte.rango} ({parte.num_usadas} de {parte.doc.page_count})"
        painter.drawText(fila3, Qt.AlignLeft | Qt.AlignVCenter, texto)
        if parte.firmado:
            usado = painter.fontMetrics().horizontalAdvance(texto + "   ")
            painter.setPen(QColor(p.error))
            aviso = painter.fontMetrics().elidedText(
                "· Firmado: la firma digital no se conserva al combinar", Qt.ElideRight, int(ancho - usado))
            painter.drawText(fila3.adjusted(usado, 0, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, aviso)
        painter.restore()


class _ListaPartes(QListWidget):
    """Lista reordenable que además acepta archivos arrastrados desde Finder."""
    archivos_soltados = Signal(list, int)  # rutas, fila donde insertarlas (-1 = al final)

    def __init__(self):
        super().__init__()
        self.setObjectName("listaCombinar")
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setMouseTracking(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setUniformItemSizes(True)

    def _es_externo(self, ev) -> bool:
        return ev.source() is not self and ev.mimeData().hasUrls()

    def dragEnterEvent(self, ev) -> None:
        if self._es_externo(ev):
            ev.acceptProposedAction()
        else:
            super().dragEnterEvent(ev)

    def dragMoveEvent(self, ev) -> None:
        if self._es_externo(ev):
            ev.acceptProposedAction()
        else:
            super().dragMoveEvent(ev)

    def dropEvent(self, ev) -> None:
        if not self._es_externo(ev):
            super().dropEvent(ev)
            return
        rutas = [u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile()]
        ev.acceptProposedAction()
        self.archivos_soltados.emit(rutas, self.indexAt(ev.position().toPoint()).row())


class DialogoCombinar(QDialog):
    """Elegir documentos, ordenarlos y (opcionalmente) qué páginas de cada uno se usan.

    Si se acepta, `resultado` contiene el nuevo `Documento` (sin guardar todavía).
    """

    def __init__(self, parent=None, actual: Documento | None = None):
        super().__init__(parent)
        self.setWindowTitle("Combinar documentos")
        self.setMinimumSize(660, 580)
        self.setAcceptDrops(True)
        self.ajustes = QSettings()
        self.resultado: Documento | None = None
        self._partes: dict[int, Parte] = {}
        self._claves = itertools.count(1)
        p = tema.paleta()

        capa = QVBoxLayout(self)
        capa.setContentsMargins(20, 18, 20, 16)
        capa.setSpacing(12)

        cab = QHBoxLayout()
        cab.setSpacing(12)
        ico = QLabel()
        ico.setPixmap(tema.icono("file-document-multiple-outline", p.acento).pixmap(34, 34))
        cab.addWidget(ico, 0, Qt.AlignTop)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        titulo = QLabel("Combinar documentos")
        titulo.setStyleSheet("font-size: 17px; font-weight: 700;")
        sub = QLabel("Une varios PDF (o fotos y escaneos) en un documento nuevo. Arrastra para cambiar "
                     "el orden y haz doble clic en uno para elegir qué páginas se incluyen.")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {p.texto_suave}; font-size: 12px;")
        textos.addWidget(titulo)
        textos.addWidget(sub)
        cab.addLayout(textos, 1)
        capa.addLayout(cab)

        # Lista (o, si está vacía, una invitación a añadir archivos)
        self.pila = QStackedWidget()
        vacio = QWidget()
        vacio.setObjectName("vacioCombinar")
        vacio.setAttribute(Qt.WA_StyledBackground, True)
        vacio.setStyleSheet(f"QWidget#vacioCombinar {{ background: {p.superficie}; "
                            f"border: 2px dashed {p.borde_fuerte}; border-radius: 12px; }}")
        cv = QVBoxLayout(vacio)
        cv.setAlignment(Qt.AlignCenter)
        cv.setSpacing(8)
        ico_v = QLabel()
        ico_v.setPixmap(tema.icono("file-multiple-outline", p.texto_suave).pixmap(52, 52))
        ico_v.setAlignment(Qt.AlignCenter)
        txt_v = QLabel("<b>Añade los documentos que quieres unir</b><br>"
                       f"<span style='color:{p.texto_suave}'>PDF o imágenes (JPG, PNG…). "
                       "También puedes arrastrarlos aquí.</span>")
        txt_v.setAlignment(Qt.AlignCenter)
        btn_v = QPushButton("  Añadir archivos…")
        btn_v.setObjectName("primario")
        tema.poner_icono(btn_v, "plus", "#FFFFFF")
        btn_v.setCursor(Qt.PointingHandCursor)
        btn_v.clicked.connect(self.elegir_archivos)
        cv.addWidget(ico_v)
        cv.addWidget(txt_v)
        cv.addSpacing(6)
        cv.addWidget(btn_v, 0, Qt.AlignCenter)
        self.pila.addWidget(vacio)

        self.lista = _ListaPartes()
        self.lista.setItemDelegate(_Delegado(self))
        self.lista.archivos_soltados.connect(self.añadir_rutas)
        self.lista.itemSelectionChanged.connect(self._actualizar)
        self.lista.itemDoubleClicked.connect(lambda _: self.elegir_paginas())
        self.lista.model().rowsMoved.connect(lambda *_: self._actualizar())
        self.lista.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lista.customContextMenuRequested.connect(self._menu)
        for tecla in (QKeySequence.Delete, QKeySequence(Qt.Key_Backspace)):
            QShortcut(tecla, self.lista, activated=self.quitar, context=Qt.WidgetShortcut)
        self.pila.addWidget(self.lista)
        capa.addWidget(self.pila, 1)

        # Botones de la lista
        fila = QHBoxLayout()
        fila.setSpacing(6)
        self.b_anadir = QPushButton("  Añadir archivos…")
        tema.poner_icono(self.b_anadir, "plus")
        self.b_anadir.clicked.connect(self.elegir_archivos)
        self.b_paginas = QPushButton("  Páginas…")
        tema.poner_icono(self.b_paginas, "file-document-edit-outline")
        self.b_paginas.setToolTip("Elegir qué páginas de este documento se incluyen")
        self.b_paginas.clicked.connect(self.elegir_paginas)
        self.b_subir = QPushButton()
        tema.poner_icono(self.b_subir, "arrow-up")
        self.b_subir.setToolTip("Subir")
        self.b_subir.clicked.connect(lambda: self.mover(-1))
        self.b_bajar = QPushButton()
        tema.poner_icono(self.b_bajar, "arrow-down")
        self.b_bajar.setToolTip("Bajar")
        self.b_bajar.clicked.connect(lambda: self.mover(1))
        self.b_quitar = QPushButton("  Quitar")
        tema.poner_icono(self.b_quitar, "close")
        self.b_quitar.clicked.connect(self.quitar)
        fila.addWidget(self.b_anadir)
        fila.addWidget(self.b_paginas)
        fila.addStretch(1)
        for b in (self.b_subir, self.b_bajar, self.b_quitar):
            fila.addWidget(b)
        capa.addLayout(fila)

        self.c_marcadores = QCheckBox("Añadir un marcador con el nombre de cada documento")
        self.c_marcadores.setChecked(self.ajustes.value("combinar/marcadores", True, type=bool))
        capa.addWidget(self.c_marcadores)

        # Pie
        pie = QHBoxLayout()
        self.resumen = QLabel()
        self.resumen.setStyleSheet(f"color: {p.texto_suave};")
        pie.addWidget(self.resumen, 1)
        cancelar = QPushButton("Cancelar")
        cancelar.clicked.connect(self.reject)
        self.b_combinar = QPushButton("  Combinar")
        self.b_combinar.setObjectName("primario")
        tema.poner_icono(self.b_combinar, "file-document-multiple-outline", "#FFFFFF")
        self.b_combinar.setDefault(True)
        self.b_combinar.clicked.connect(self._combinar)
        pie.addWidget(cancelar)
        pie.addWidget(self.b_combinar)
        capa.addLayout(pie)

        if actual is not None:
            doc = pymupdf.open(stream=actual.bytes_actuales(), filetype="pdf")
            self._añadir_parte(Parte(actual.nombre, doc, ruta=actual.ruta, origen="abierto",
                                     firmado=doc.get_sigflags() > 0))
        self._actualizar()

    # --- Partes -------------------------------------------------------------
    def parte_de_indice(self, idx: QModelIndex) -> Parte | None:
        return self._partes.get(idx.data(Qt.UserRole))

    def _parte(self, it: QListWidgetItem) -> Parte:
        return self._partes[it.data(Qt.UserRole)]

    def partes(self) -> list[Parte]:
        return [self._parte(self.lista.item(i)) for i in range(self.lista.count())]

    def _miniatura(self, parte: Parte) -> None:
        pagina = parte.doc[parte.paginas[0] if parte.paginas else 0]
        dpr = self.devicePixelRatioF()
        r = pagina.rect
        escala = min(46 / r.width, 60 / r.height) * dpr
        pm = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala), alpha=False)
        img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy()
        pix = QPixmap.fromImage(img)
        pix.setDevicePixelRatio(dpr)
        parte.miniatura = pix

    def _añadir_parte(self, parte: Parte, fila: int = -1) -> None:
        self._miniatura(parte)
        clave = next(self._claves)
        self._partes[clave] = parte
        it = QListWidgetItem(parte.nombre)
        it.setData(Qt.UserRole, clave)
        it.setToolTip(parte.ruta or parte.nombre)
        if 0 <= fila < self.lista.count():
            self.lista.insertItem(fila, it)
        else:
            self.lista.addItem(it)

    def _abrir(self, ruta: str) -> Parte | None:
        nombre = os.path.basename(ruta)
        tam = os.path.getsize(ruta)
        if ruta.lower().endswith(EXT_IMAGEN):
            return Parte(nombre, imagen_a_pdf(ruta), ruta=ruta, tam=tam, origen="imagen")
        doc = pymupdf.open(ruta)
        if not doc.is_pdf:
            doc.close()
            raise ValueError("no es un PDF ni una imagen compatible")
        if doc.needs_pass:
            from .dialogos import DialogoContrasena
            while True:
                dlg = DialogoContrasena(nombre, self)
                if dlg.exec() != QDialog.Accepted:
                    doc.close()
                    return None
                if doc.authenticate(dlg.campo.text()):
                    break
                QMessageBox.warning(self, "Contraseña", "Contraseña incorrecta.")
        return Parte(nombre, doc, ruta=ruta, tam=tam, firmado=doc.get_sigflags() > 0)

    def añadir_rutas(self, rutas: list[str], fila: int = -1) -> None:
        errores = []
        for ruta in rutas:
            if os.path.isdir(ruta):
                continue
            try:
                parte = self._abrir(ruta)
            except Exception as exc:
                errores.append(f"• {os.path.basename(ruta)}: {exc}")
                continue
            if parte is None:
                continue
            self._añadir_parte(parte, fila)
            if fila >= 0:
                fila += 1
            self.ajustes.setValue("ultima_carpeta", os.path.dirname(ruta))
        if errores:
            QMessageBox.warning(self, "Combinar documentos",
                                "No se han podido añadir estos archivos:\n\n" + "\n".join(errores))
        self._actualizar()

    def elegir_archivos(self) -> None:
        inicio = self.ajustes.value("ultima_carpeta", str(Path.home()))
        rutas, _ = QFileDialog.getOpenFileNames(self, "Añadir documentos", inicio, FILTRO)
        if rutas:
            self.añadir_rutas(rutas)

    def elegir_paginas(self) -> None:
        items = self.lista.selectedItems()
        if len(items) != 1:
            return
        parte = self._parte(items[0])
        n = parte.doc.page_count
        if n == 1:
            QMessageBox.information(self, "Elegir páginas", f"«{parte.nombre}» solo tiene una página.")
            return
        texto, ok = QInputDialog.getText(
            self, "Elegir páginas",
            f"Páginas de «{parte.nombre}» que quieres incluir (p. ej. 1-3, 5, 8-10).\n"
            f"Déjalo vacío para incluirlas todas. Tiene {n} páginas.",
            text=parte.rango)
        if not ok:
            return
        texto = texto.strip()
        if not texto:
            parte.paginas, parte.rango = None, ""
        else:
            try:
                parte.paginas = parsear_rango(texto, n)
            except ValueError:
                QMessageBox.warning(self, "Elegir páginas",
                                    f"El rango «{texto}» no es válido: usa números del 1 al {n}, "
                                    "separados por comas o guiones.")
                return
            parte.rango = texto.replace(" ", "").replace(",", ", ")
            if parte.paginas == list(range(n)):
                parte.paginas, parte.rango = None, ""
        self._miniatura(parte)
        self.lista.viewport().update()
        self._actualizar()

    def mover(self, paso: int) -> None:
        items = self.lista.selectedItems()
        if len(items) != 1:
            return
        fila = self.lista.row(items[0])
        nueva = fila + paso
        if not 0 <= nueva < self.lista.count():
            return
        it = self.lista.takeItem(fila)
        self.lista.insertItem(nueva, it)
        self.lista.setCurrentItem(it)
        self._actualizar()

    def quitar(self) -> None:
        for it in self.lista.selectedItems():
            parte = self._partes.pop(it.data(Qt.UserRole))
            self.lista.takeItem(self.lista.row(it))
            parte.doc.close()
        self._actualizar()

    def _menu(self, pos) -> None:
        if self.lista.itemAt(pos) is None:
            return
        menu = QMenu(self)
        menu.addAction("Elegir páginas…", self.elegir_paginas).setEnabled(len(self.lista.selectedItems()) == 1)
        menu.addSeparator()
        menu.addAction("Quitar de la lista", self.quitar)
        menu.exec(self.lista.mapToGlobal(pos))

    # --- Estado -------------------------------------------------------------
    def _actualizar(self) -> None:
        n = self.lista.count()
        self.pila.setCurrentIndex(1 if n else 0)
        sel = self.lista.selectedItems()
        fila = self.lista.row(sel[0]) if len(sel) == 1 else -1
        self.b_paginas.setEnabled(fila >= 0)
        self.b_subir.setEnabled(fila > 0)
        self.b_bajar.setEnabled(0 <= fila < n - 1)
        self.b_quitar.setEnabled(bool(sel))
        self.b_combinar.setEnabled(n >= 2)
        total = sum(p.num_usadas for p in self.partes())
        if n == 0:
            self.resumen.setText("")
        elif n == 1:
            self.resumen.setText("Añade al menos otro documento para combinarlos")
        else:
            self.resumen.setText(f"{_plural(n, 'documento')} · el resultado tendrá {_plural(total, 'página')}")
        self.lista.viewport().update()  # renumerar tras mover

    # --- Arrastrar archivos sobre cualquier parte del diálogo ----------------
    def dragEnterEvent(self, ev) -> None:
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:
        self.añadir_rutas([u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile()])

    # --- Resultado ------------------------------------------------------------
    def _combinar(self) -> None:
        partes = self.partes()
        if len(partes) < 2:
            return
        self.ajustes.setValue("combinar/marcadores", self.c_marcadores.isChecked())
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            salida = combinar(partes, self.c_marcadores.isChecked())
            datos = salida.tobytes(garbage=3, deflate=True)
            salida.close()
            self.resultado = Documento(datos=datos, nombre="Combinado.pdf")
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Combinar documentos", f"No se han podido combinar:\n{exc}")
            return
        QApplication.restoreOverrideCursor()
        self.resultado.modificado = True
        self.accept()

    def done(self, codigo: int) -> None:
        for parte in self._partes.values():
            parte.doc.close()
        self._partes.clear()
        super().done(codigo)
