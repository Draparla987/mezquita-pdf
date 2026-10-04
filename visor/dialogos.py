"""Diálogos de la aplicación: texto, firmas manuscritas, firma digital y verificación."""

from __future__ import annotations

import io
import os
import sys
import time
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRect, QSettings, QSize, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTabWidget,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import firma_digital as fd
from . import llavero, tema


# ----------------------------------------------------------------------------
# Almacén de firmas manuscritas
# ----------------------------------------------------------------------------
def _carpeta_base(nombre: str) -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / nombre
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / nombre
    return Path.home() / ".local" / "share" / nombre


def carpeta_datos() -> Path:
    if os.environ.get("MEZQUITA_DATOS"):  # carpeta alternativa (pruebas)
        base = Path(os.environ["MEZQUITA_DATOS"])
        (base / "firmas").mkdir(parents=True, exist_ok=True)
        return base
    base = _carpeta_base("MezquitaPDF")
    if not (base / "firmas").exists():
        (base / "firmas").mkdir(parents=True, exist_ok=True)
        # Recupera las firmas creadas con la versión anterior («Visor PDF»)
        antiguas = _carpeta_base("VisorPDF") / "firmas"
        if antiguas.is_dir():
            import shutil
            for f in antiguas.glob("*.png"):
                shutil.copy2(f, base / "firmas" / f.name)
    return base


def firmas_guardadas() -> list[Path]:
    return sorted((carpeta_datos() / "firmas").glob("*.png"), key=lambda p: p.stat().st_mtime)


def guardar_firma(img: QImage) -> Path:
    ruta = carpeta_datos() / "firmas" / f"firma_{int(time.time() * 1000)}.png"
    img.save(str(ruta), "PNG")
    return ruta


def _a_pil(img: QImage) -> Image.Image:
    return Image.open(io.BytesIO(imagen_a_png(img))).convert("RGBA")


def _a_qimage(img: Image.Image) -> QImage:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return QImage.fromData(buf.getvalue(), "PNG")


def recortar_transparente(img: QImage, margen: int = 8) -> QImage:
    """Recorta los bordes vacíos de una imagen con transparencia."""
    pil = _a_pil(img)
    caja = pil.getchannel("A").point(lambda a: 255 if a > 10 else 0).getbbox()
    if not caja:
        return img
    x0, y0, x1, y1 = caja
    caja = (max(0, x0 - margen), max(0, y0 - margen),
            min(pil.width, x1 + margen), min(pil.height, y1 + margen))
    return _a_qimage(pil.crop(caja))


def quitar_fondo_blanco(img: QImage, umbral: int = 225) -> QImage:
    """Convierte el fondo claro de una foto/escaneo de firma en transparente."""
    pil = _a_pil(img)
    luz = pil.convert("L")
    alfa = luz.point(lambda v: 0 if v >= umbral else min(255, int((umbral - v) * 255 / (umbral - 80))))
    pil.putalpha(alfa)
    return _a_qimage(pil)


def imagen_a_png(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba.data())


# ----------------------------------------------------------------------------
# Botón de color
# ----------------------------------------------------------------------------
class BotonColor(QPushButton):
    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self.setFixedSize(QSize(34, 24))
        self.set_color(color)
        self.clicked.connect(self._elegir)

    def set_color(self, color: QColor) -> None:
        self.color = QColor(color)
        self.setStyleSheet(
            f"background-color: {self.color.name()}; border: 1px solid #888; border-radius: 4px;"
        )

    def _elegir(self) -> None:
        c = QColorDialog.getColor(self.color, self, "Elegir color")
        if c.isValid():
            self.set_color(c)


# ----------------------------------------------------------------------------
# Texto
# ----------------------------------------------------------------------------
FUENTES_PDF = {
    "Helvetica": ("helv", "Helv"),
    "Times": ("tiro", "TiRo"),
    "Courier": ("cour", "Cour"),
}


class DialogoTexto(QDialog):
    def __init__(self, parent=None, titulo="Añadir texto", texto="", tamano=12.0,
                 color=QColor(0, 0, 0), fuente="Helvetica", mostrar_formato=True):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.resize(460, 260)
        capa = QVBoxLayout(self)
        self.editor = QPlainTextEdit(texto)
        capa.addWidget(self.editor)
        fila = QHBoxLayout()
        self.combo_fuente = QComboBox()
        self.combo_fuente.addItems(list(FUENTES_PDF))
        self.combo_fuente.setCurrentText(fuente)
        self.spin_tam = QDoubleSpinBox()
        self.spin_tam.setRange(4, 144)
        self.spin_tam.setValue(tamano)
        self.spin_tam.setSuffix(" pt")
        self.boton_color = BotonColor(color)
        for etiqueta, wid in (("Fuente:", self.combo_fuente), ("Tamaño:", self.spin_tam),
                              ("Color:", self.boton_color)):
            fila.addWidget(QLabel(etiqueta))
            fila.addWidget(wid)
        fila.addStretch()
        if mostrar_formato:
            capa.addLayout(fila)
        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        capa.addWidget(botones)
        self.editor.setFocus()

    @property
    def texto(self) -> str:
        return self.editor.toPlainText()

    @property
    def tamano(self) -> float:
        return self.spin_tam.value()

    @property
    def color(self) -> QColor:
        return self.boton_color.color

    @property
    def fuente(self) -> str:
        return self.combo_fuente.currentText()


# ----------------------------------------------------------------------------
# Firmas manuscritas
# ----------------------------------------------------------------------------
class LienzoFirma(QWidget):
    """Área para dibujar la firma con el ratón o el trackpad."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(520, 200)
        self.trazos: list[list[QPointF]] = []
        self.color = QColor(15, 30, 110)
        self.grosor = 3.0
        self.setCursor(Qt.CrossCursor)

    def limpiar(self) -> None:
        self.trazos = []
        self.update()

    def vacio(self) -> bool:
        return not any(len(t) > 1 for t in self.trazos)

    def mousePressEvent(self, ev) -> None:
        self.trazos.append([ev.position()])
        self.update()

    def mouseMoveEvent(self, ev) -> None:
        if self.trazos and ev.buttons() & Qt.LeftButton:
            self.trazos[-1].append(ev.position())
            self.update()

    def _camino(self, escala: float = 1.0) -> QPainterPath:
        camino = QPainterPath()
        for t in self.trazos:
            if len(t) < 2:
                continue
            pts = [QPointF(p.x() * escala, p.y() * escala) for p in t]
            camino.moveTo(pts[0])
            # Curvas suaves entre puntos medios
            for i in range(1, len(pts) - 1):
                medio = (pts[i] + pts[i + 1]) / 2
                camino.quadTo(pts[i], medio)
            camino.lineTo(pts[-1])
        return camino

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(255, 255, 255))
        p.setPen(QPen(QColor(200, 200, 200), 1, Qt.DashLine))
        y = int(self.height() * 0.72)
        p.drawLine(30, y, self.width() - 30, y)
        p.setPen(QColor(170, 170, 170))
        p.drawText(30, y + 20, "Firma aquí")
        p.setPen(QPen(self.color, self.grosor, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(self._camino())
        p.end()

    def imagen(self) -> QImage:
        escala = 3.0
        img = QImage(int(self.width() * escala), int(self.height() * escala), QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(self.color, self.grosor * escala, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(self._camino(escala))
        p.end()
        return recortar_transparente(img)


FUENTES_MANUSCRITAS = ["Snell Roundhand", "Bradley Hand", "Apple Chancery", "Zapfino",
                       "Segoe Script", "Lucida Handwriting", "Brush Script MT"]


class DialogoNuevaFirma(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crear firma")
        self.imagen_resultado: QImage | None = None
        capa = QVBoxLayout(self)
        self.pestanas = QTabWidget()
        capa.addWidget(self.pestanas)

        # Dibujar
        pag_dibujar = QWidget()
        cd = QVBoxLayout(pag_dibujar)
        self.lienzo = LienzoFirma()
        cd.addWidget(self.lienzo)
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Color:"))
        for nombre, color in (("Azul", QColor(15, 30, 110)), ("Negro", QColor(10, 10, 10))):
            b = QPushButton(nombre)
            b.clicked.connect(lambda _=False, c=color: self._color_lienzo(c))
            fila.addWidget(b)
        fila.addWidget(QLabel("Grosor:"))
        spin = QDoubleSpinBox()
        spin.setRange(1, 8)
        spin.setValue(3)
        spin.valueChanged.connect(lambda v: (setattr(self.lienzo, "grosor", v), self.lienzo.update()))
        fila.addWidget(spin)
        fila.addStretch()
        borrar = QPushButton("Borrar")
        borrar.clicked.connect(self.lienzo.limpiar)
        fila.addWidget(borrar)
        cd.addLayout(fila)
        self.pestanas.addTab(pag_dibujar, "Dibujar")

        # Escribir
        pag_escribir = QWidget()
        ce = QVBoxLayout(pag_escribir)
        self.campo_nombre = QLineEdit()
        self.campo_nombre.setPlaceholderText("Escribe tu nombre")
        ce.addWidget(self.campo_nombre)
        self.combo_letra = QComboBox()
        disponibles = set(QFontDatabase.families())
        for f in FUENTES_MANUSCRITAS:
            if f in disponibles:
                self.combo_letra.addItem(f)
        if self.combo_letra.count() == 0:
            self.combo_letra.addItem(QFont().family())
        ce.addWidget(self.combo_letra)
        self.vista_previa = QLabel()
        self.vista_previa.setMinimumHeight(140)
        self.vista_previa.setAlignment(Qt.AlignCenter)
        self.vista_previa.setStyleSheet("background: white; border: 1px solid #ccc;")
        ce.addWidget(self.vista_previa)
        self.campo_nombre.textChanged.connect(self._previa)
        self.combo_letra.currentTextChanged.connect(self._previa)
        self.pestanas.addTab(pag_escribir, "Escribir")

        # Imagen
        pag_imagen = QWidget()
        ci = QVBoxLayout(pag_imagen)
        ci.addWidget(QLabel("Carga una foto o escaneo de tu firma (fondo blanco)."))
        b = QPushButton("Elegir imagen…")
        b.clicked.connect(self._cargar_imagen)
        ci.addWidget(b)
        self.chk_fondo = QCheckBox("Quitar fondo blanco")
        self.chk_fondo.setChecked(True)
        ci.addWidget(self.chk_fondo)
        self.previa_imagen = QLabel()
        self.previa_imagen.setMinimumHeight(140)
        self.previa_imagen.setAlignment(Qt.AlignCenter)
        self.previa_imagen.setStyleSheet("background: white; border: 1px solid #ccc;")
        ci.addWidget(self.previa_imagen)
        self._imagen_cargada: QImage | None = None
        self.pestanas.addTab(pag_imagen, "Imagen")

        botones = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        botones.button(QDialogButtonBox.Save).setText("Guardar firma")
        botones.accepted.connect(self._aceptar)
        botones.rejected.connect(self.reject)
        capa.addWidget(botones)

    def _color_lienzo(self, c: QColor) -> None:
        self.lienzo.color = c
        self.lienzo.update()

    def _imagen_escrita(self) -> QImage | None:
        texto = self.campo_nombre.text().strip()
        if not texto:
            return None
        fuente = QFont(self.combo_letra.currentText(), 96)
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(fuente)
        r = fm.boundingRect(texto)
        img = QImage(r.width() + 80, fm.height() + 60, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(fuente)
        p.setPen(QColor(15, 30, 110))
        p.drawText(40, 30 + fm.ascent(), texto)
        p.end()
        return recortar_transparente(img)

    def _previa(self) -> None:
        img = self._imagen_escrita()
        if img is None:
            self.vista_previa.clear()
            return
        self.vista_previa.setPixmap(
            QPixmap.fromImage(img).scaled(480, 130, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def _cargar_imagen(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Imagen de la firma", str(Path.home()),
                                              "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif *.heic)")
        if not ruta:
            return
        img = QImage(ruta)
        if img.isNull():
            QMessageBox.warning(self, "Imagen", "No se pudo abrir la imagen.")
            return
        if img.width() > 1600:
            img = img.scaledToWidth(1600, Qt.SmoothTransformation)
        self._imagen_cargada = img
        prev = quitar_fondo_blanco(img) if self.chk_fondo.isChecked() else img
        self.previa_imagen.setPixmap(
            QPixmap.fromImage(prev).scaled(480, 130, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def _aceptar(self) -> None:
        pestana = self.pestanas.currentIndex()
        img = None
        if pestana == 0 and not self.lienzo.vacio():
            img = self.lienzo.imagen()
        elif pestana == 1:
            img = self._imagen_escrita()
        elif pestana == 2 and self._imagen_cargada is not None:
            img = self._imagen_cargada
            if self.chk_fondo.isChecked():
                img = recortar_transparente(quitar_fondo_blanco(img))
        if img is None or img.isNull():
            QMessageBox.information(self, "Firma", "Primero crea la firma.")
            return
        self.imagen_resultado = img
        self.accept()


class DialogoFirmas(QDialog):
    """Gestor de firmas guardadas. Devuelve la ruta de la firma elegida."""

    def __init__(self, parent=None, seleccionar=True):
        super().__init__(parent)
        self.setWindowTitle("Mis firmas")
        self.resize(520, 420)
        self.ruta_elegida: Path | None = None
        capa = QVBoxLayout(self)
        capa.addWidget(QLabel("Elige una firma para colocarla en el documento, o crea una nueva."))
        self.lista = QListWidget()
        self.lista.setIconSize(QSize(220, 80))
        self.lista.setViewMode(QListWidget.IconMode)
        self.lista.setResizeMode(QListWidget.Adjust)
        self.lista.setSpacing(10)
        self.lista.setStyleSheet("QListWidget { background: white; }")
        self.lista.itemDoubleClicked.connect(lambda _: self._usar())
        capa.addWidget(self.lista)
        fila = QHBoxLayout()
        nueva = QPushButton("Nueva firma…")
        nueva.clicked.connect(self._nueva)
        eliminar = QPushButton("Eliminar")
        eliminar.clicked.connect(self._eliminar)
        fila.addWidget(nueva)
        fila.addWidget(eliminar)
        fila.addStretch()
        if seleccionar:
            usar = QPushButton("Usar firma")
            usar.setDefault(True)
            usar.clicked.connect(self._usar)
            fila.addWidget(usar)
        cerrar = QPushButton("Cerrar")
        cerrar.clicked.connect(self.reject)
        fila.addWidget(cerrar)
        capa.addLayout(fila)
        self._cargar()
        if self.lista.count() == 0:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._nueva)

    def _cargar(self) -> None:
        self.lista.clear()
        for ruta in reversed(firmas_guardadas()):
            item = QListWidgetItem(QIcon(str(ruta)), "")
            item.setData(Qt.UserRole, str(ruta))
            item.setSizeHint(QSize(240, 100))
            self.lista.addItem(item)
        if self.lista.count():
            self.lista.setCurrentRow(0)

    def _nueva(self) -> None:
        dlg = DialogoNuevaFirma(self)
        if dlg.exec() == QDialog.Accepted and dlg.imagen_resultado is not None:
            guardar_firma(dlg.imagen_resultado)
            self._cargar()

    def _eliminar(self) -> None:
        item = self.lista.currentItem()
        if item is None:
            return
        if QMessageBox.question(self, "Eliminar firma", "¿Eliminar la firma seleccionada?") \
                == QMessageBox.Yes:
            Path(item.data(Qt.UserRole)).unlink(missing_ok=True)
            self._cargar()

    def _usar(self) -> None:
        item = self.lista.currentItem()
        if item is None:
            QMessageBox.information(self, "Firma", "Crea o selecciona una firma.")
            return
        self.ruta_elegida = Path(item.data(Qt.UserRole))
        self.accept()


# ----------------------------------------------------------------------------
# Firma digital con certificado
# ----------------------------------------------------------------------------
TSA_PREDETERMINADA = "http://timestamp.digicert.com"


class FilaCertificado(QWidget):
    """Fila de la lista de certificados: titular, emisor, caducidad y estado."""

    def __init__(self, cert: "llavero.CertificadoSistema"):
        super().__init__()
        p = tema.paleta()
        capa = QHBoxLayout(self)
        capa.setContentsMargins(10, 8, 10, 8)
        capa.setSpacing(12)
        ico = QLabel()
        nombre_icono = "card-account-details-outline" if cert.en_tarjeta else "certificate-outline"
        ico.setPixmap(tema.icono(nombre_icono, p.acento if cert.utilizable else p.texto_suave).pixmap(30, 30))
        capa.addWidget(ico)
        textos = QVBoxLayout()
        textos.setSpacing(1)
        titular = QLabel(cert.titular)
        titular.setStyleSheet(f"font-weight: 600; color: {p.texto if cert.utilizable else p.texto_suave};")
        detalle = QLabel(f"{cert.emisor} · válido hasta {cert.valido_hasta:%d/%m/%Y}"
                         + (" · tarjeta" if cert.en_tarjeta else ""))
        detalle.setStyleSheet(f"color: {p.texto_suave}; font-size: 12px;")
        textos.addWidget(titular)
        textos.addWidget(detalle)
        capa.addLayout(textos, 1)
        if cert.caducado:
            texto, color, fondo = "Caducado", p.error, p.error_suave
        elif cert.aun_no_valido:
            texto, color, fondo = "Aún no válido", p.error, p.error_suave
        else:
            texto, color, fondo = "Vigente", p.exito, p.exito_suave
        chip = QLabel(texto)
        chip.setStyleSheet(f"color: {color}; background: {fondo}; border-radius: 9px; padding: 2px 9px;"
                           " font-size: 11px; font-weight: 600;")
        capa.addWidget(chip)
        for w in (ico, titular, detalle, chip):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)


class DialogoFirmaDigital(QDialog):
    """Elegir el certificado (del Llavero o de un archivo) y los datos de la firma."""

    def __init__(self, parent=None, visible=True, rutas_llaveros: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Firmar con certificado digital")
        self.setMinimumWidth(600)
        self.ajustes = QSettings()
        self.firmante = None
        self._rutas_llaveros = rutas_llaveros
        self._certificados: list = []
        self._firmante_archivo = None
        p = tema.paleta()
        capa = QVBoxLayout(self)
        capa.setContentsMargins(20, 18, 20, 16)
        capa.setSpacing(12)

        cab = QHBoxLayout()
        titulo = QLabel("Elige el certificado con el que quieres firmar")
        titulo.setStyleSheet("font-size: 16px; font-weight: 700;")
        cab.addWidget(titulo, 1)
        recargar = QPushButton()
        tema.poner_icono(recargar, "refresh")
        recargar.setToolTip("Volver a buscar certificados (p. ej. tras insertar el DNIe)")
        recargar.clicked.connect(self._cargar_lista)
        cab.addWidget(recargar)
        capa.addLayout(cab)

        self.lista = QListWidget()
        self.lista.setMinimumHeight(170)
        self.lista.setSpacing(2)
        self.lista.itemSelectionChanged.connect(self._seleccion_cambiada)
        self.lista.itemDoubleClicked.connect(lambda _: self._aceptar())
        capa.addWidget(self.lista)
        self.aviso_lista = QLabel()
        self.aviso_lista.setWordWrap(True)
        self.aviso_lista.setStyleSheet(f"color: {p.texto_suave}; font-size: 12px;")
        capa.addWidget(self.aviso_lista)

        # Alternativa: archivo .p12 / .pfx
        self.boton_archivo = QPushButton("  Usar un archivo de certificado (.p12 / .pfx)…")
        tema.poner_icono(self.boton_archivo, "file-key-outline")
        self.boton_archivo.setCheckable(True)
        self.boton_archivo.setStyleSheet("text-align: left;")
        self.boton_archivo.toggled.connect(self._modo_archivo)
        capa.addWidget(self.boton_archivo)
        self.grupo_archivo = QGroupBox("Certificado en archivo")
        fc = QFormLayout(self.grupo_archivo)
        fila = QHBoxLayout()
        self.campo_ruta = QLineEdit(self.ajustes.value("firma/ruta_cert", ""))
        self.campo_ruta.setPlaceholderText("Fichero .p12 o .pfx")
        examinar = QPushButton("Examinar…")
        examinar.clicked.connect(self._examinar)
        fila.addWidget(self.campo_ruta)
        fila.addWidget(examinar)
        fc.addRow("Archivo:", fila)
        self.campo_pass = QLineEdit()
        self.campo_pass.setEchoMode(QLineEdit.Password)
        self.campo_pass.returnPressed.connect(self._cargar_cert)
        fila2 = QHBoxLayout()
        fila2.addWidget(self.campo_pass)
        abrir = QPushButton("Abrir")
        abrir.clicked.connect(self._cargar_cert)
        fila2.addWidget(abrir)
        fc.addRow("Contraseña:", fila2)
        self.info = QLabel("—")
        self.info.setWordWrap(True)
        fc.addRow("Titular:", self.info)
        self.grupo_archivo.setVisible(False)
        capa.addWidget(self.grupo_archivo)

        grupo_datos = QGroupBox("Datos de la firma (opcionales)")
        fd_ = QFormLayout(grupo_datos)
        self.campo_motivo = QLineEdit(self.ajustes.value("firma/motivo", ""))
        self.campo_motivo.setPlaceholderText("p. ej. Conformidad, Aprobación…")
        self.campo_lugar = QLineEdit(self.ajustes.value("firma/lugar", ""))
        self.campo_contacto = QLineEdit(self.ajustes.value("firma/contacto", ""))
        fd_.addRow("Motivo:", self.campo_motivo)
        fd_.addRow("Lugar:", self.campo_lugar)
        fd_.addRow("Contacto:", self.campo_contacto)
        capa.addWidget(grupo_datos)

        grupo_aspecto = QGroupBox("Opciones")
        fa = QVBoxLayout(grupo_aspecto)
        self.combo_rubrica = QComboBox()
        self.combo_rubrica.addItem("Sin rúbrica (solo texto)", None)
        for ruta in reversed(firmas_guardadas()):
            self.combo_rubrica.addItem(QIcon(str(ruta)), ruta.stem, str(ruta))
        self.combo_rubrica.setIconSize(QSize(90, 30))
        if self.combo_rubrica.count() > 1:
            self.combo_rubrica.setCurrentIndex(1)
        fila3 = QHBoxLayout()
        fila3.addWidget(QLabel("Rúbrica en el sello:"))
        fila3.addWidget(self.combo_rubrica, 1)
        if visible:
            fa.addLayout(fila3)
        self.chk_tsa = QCheckBox("Añadir sello de tiempo de una TSA (requiere Internet)")
        self.chk_tsa.setChecked(self.ajustes.value("firma/tsa", False, type=bool))
        self.campo_tsa = QLineEdit(self.ajustes.value("firma/url_tsa", TSA_PREDETERMINADA))
        self.campo_tsa.setEnabled(self.chk_tsa.isChecked())
        self.chk_tsa.toggled.connect(self.campo_tsa.setEnabled)
        fa.addWidget(self.chk_tsa)
        fa.addWidget(self.campo_tsa)
        self.chk_certificar = QCheckBox("Certificar documento (bloquea cambios salvo rellenar formularios)")
        fa.addWidget(self.chk_certificar)
        capa.addWidget(grupo_aspecto)

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.boton_firmar = botones.button(QDialogButtonBox.Ok)
        self.boton_firmar.setText("Firmar y guardar…")
        self.boton_firmar.setEnabled(False)
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self._aceptar)
        botones.rejected.connect(self.reject)
        capa.addWidget(botones)

        self._cargar_lista()
        if self.ajustes.value("firma/modo", "llavero") == "archivo" or not self._certificados:
            self.boton_archivo.setChecked(True)

    # --- Lista de certificados del sistema --------------------------------
    def _cargar_lista(self) -> None:
        self.lista.clear()
        self._certificados = llavero.listar_certificados(self._rutas_llaveros) if llavero.DISPONIBLE else []
        ultima = self.ajustes.value("firma/huella", "")
        seleccionar = None
        for cert in self._certificados:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, cert.huella)
            item.setSizeHint(QSize(100, 58))
            if not cert.utilizable:
                item.setFlags(item.flags() & ~Qt.ItemIsSelectable & ~Qt.ItemIsEnabled)
            self.lista.addItem(item)
            self.lista.setItemWidget(item, FilaCertificado(cert))
            if cert.utilizable and (seleccionar is None or cert.huella == ultima):
                if seleccionar is None or cert.huella == ultima:
                    seleccionar = item
        if not llavero.DISPONIBLE:
            self.aviso_lista.setText("Los certificados del sistema solo se pueden usar en macOS. "
                                     "Usa un archivo .p12 / .pfx.")
        elif not self._certificados:
            self.aviso_lista.setText("No se ha encontrado ningún certificado de firma en el Llavero. "
                                     "Si usas DNIe, conecta el lector y pulsa el botón de recargar; "
                                     "también puedes usar un archivo .p12 / .pfx.")
        else:
            self.aviso_lista.setText("La primera vez, macOS te pedirá permiso para usar el certificado: "
                                     "pulsa «Permitir siempre» para que no vuelva a preguntar. "
                                     "La clave privada nunca sale del Llavero.")
        if seleccionar is not None and not self.boton_archivo.isChecked():
            self.lista.setCurrentItem(seleccionar)
        self._actualizar_boton()

    def _cert_seleccionado(self):
        item = self.lista.currentItem()
        if item is None or not item.isSelected():
            return None
        huella = item.data(Qt.UserRole)
        return next((c for c in self._certificados if c.huella == huella), None)

    def _seleccion_cambiada(self) -> None:
        if self._cert_seleccionado() is not None and self.boton_archivo.isChecked():
            self.boton_archivo.setChecked(False)
        self._actualizar_boton()

    def _modo_archivo(self, activo: bool) -> None:
        self.grupo_archivo.setVisible(activo)
        if activo:
            self.lista.clearSelection()
            self.campo_pass.setFocus()
        self._actualizar_boton()
        self.adjustSize()

    def _actualizar_boton(self) -> None:
        if self.boton_archivo.isChecked():
            self.boton_firmar.setEnabled(self._firmante_archivo is not None)
        else:
            self.boton_firmar.setEnabled(self._cert_seleccionado() is not None)

    # --- Archivo .p12 -----------------------------------------------------
    def _examinar(self) -> None:
        inicio = os.path.dirname(self.campo_ruta.text()) or str(Path.home())
        ruta, _ = QFileDialog.getOpenFileName(self, "Certificado digital", inicio,
                                              "Certificados (*.p12 *.pfx);;Todos (*)")
        if ruta:
            self.campo_ruta.setText(ruta)
            self.campo_pass.setFocus()

    def _cargar_cert(self) -> None:
        ruta = self.campo_ruta.text().strip()
        if not ruta or not os.path.exists(ruta):
            QMessageBox.warning(self, "Certificado", "Selecciona un fichero de certificado válido.")
            return
        try:
            self._firmante_archivo = fd.cargar_certificado(ruta, self.campo_pass.text())
        except fd.ErrorFirma as exc:
            self._firmante_archivo = None
            self.info.setText(f"<span style='color:{tema.paleta().error}'>{exc}</span>")
            self._actualizar_boton()
            return
        info = fd.info_certificado(self._firmante_archivo)
        from datetime import datetime, timezone
        caducado = info.valido_hasta < datetime.now(timezone.utc)
        estado = (f"<span style='color:{tema.paleta().error}'><b>CADUCADO</b></span>" if caducado
                  else f"<span style='color:{tema.paleta().exito}'>vigente</span>")
        self.info.setText(f"<b>{info.titular}</b><br>Emisor: {info.emisor}<br>"
                          f"Válido hasta {info.valido_hasta:%d/%m/%Y} ({estado})")
        self.ajustes.setValue("firma/ruta_cert", ruta)
        self._actualizar_boton()

    # --- Aceptar ------------------------------------------------------------
    def _aceptar(self) -> None:
        if self.boton_archivo.isChecked():
            if self._firmante_archivo is None:
                return
            self.firmante = self._firmante_archivo
            self.ajustes.setValue("firma/modo", "archivo")
        else:
            cert = self._cert_seleccionado()
            if cert is None:
                return
            try:
                self.firmante = llavero.FirmanteLlavero(cert)
            except llavero.ErrorLlavero as exc:
                QMessageBox.warning(self, "Certificado", str(exc))
                return
            self.ajustes.setValue("firma/huella", cert.huella)
            self.ajustes.setValue("firma/modo", "llavero")
        self.ajustes.setValue("firma/motivo", self.campo_motivo.text())
        self.ajustes.setValue("firma/lugar", self.campo_lugar.text())
        self.ajustes.setValue("firma/contacto", self.campo_contacto.text())
        self.ajustes.setValue("firma/tsa", self.chk_tsa.isChecked())
        self.ajustes.setValue("firma/url_tsa", self.campo_tsa.text())
        self.accept()

    @property
    def rubrica_png(self) -> bytes | None:
        ruta = self.combo_rubrica.currentData()
        return Path(ruta).read_bytes() if ruta else None

    @property
    def url_tsa(self) -> str | None:
        return self.campo_tsa.text().strip() if self.chk_tsa.isChecked() else None


class DialogoVerificacion(QDialog):
    def __init__(self, resultados: list[fd.ResultadoVerificacion], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Firmas del documento")
        self.resize(640, 380)
        capa = QVBoxLayout(self)
        if not resultados:
            capa.addWidget(QLabel("Este documento no contiene firmas digitales."))
        arbol = QTreeWidget()
        arbol.setHeaderHidden(True)
        arbol.setWordWrap(True)
        for r in resultados:
            simbolo = "✅" if r.integra else "❌"
            raiz = QTreeWidgetItem([f"{simbolo}  {r.firmante}  —  {r.fecha}"])
            fuente = raiz.font(0)
            fuente.setBold(True)
            raiz.setFont(0, fuente)
            for linea in (
                r.resumen,
                f"Emisor del certificado: {r.emisor}",
                "Certificado de confianza (cadena verificada con las raíces del sistema)"
                if r.confiable else
                "Identidad no verificada: el certificado no procede de una autoridad de confianza "
                "del sistema (o falta la cadena intermedia).",
                f"Campo de firma: {r.campo}",
            ):
                hijo = QTreeWidgetItem([linea])
                hijo.setToolTip(0, linea)
                raiz.addChild(hijo)
            arbol.addTopLevelItem(raiz)
            raiz.setExpanded(True)
        if resultados:
            capa.addWidget(arbol)
        botones = QDialogButtonBox(QDialogButtonBox.Close)
        botones.rejected.connect(self.reject)
        capa.addWidget(botones)


class DialogoContrasena(QDialog):
    def __init__(self, nombre: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Documento protegido")
        capa = QVBoxLayout(self)
        capa.addWidget(QLabel(f"«{nombre}» está protegido con contraseña."))
        self.campo = QLineEdit()
        self.campo.setEchoMode(QLineEdit.Password)
        capa.addWidget(self.campo)
        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        capa.addWidget(botones)
