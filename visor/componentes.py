"""Componentes visuales reutilizables de la interfaz."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve, QMimeData, QPoint, QPropertyAnimation, QRectF, QSettings, QSize, Qt, QTimer,
    QUrl, Signal,
)
from PySide6.QtGui import QColor, QDrag, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from . import compartir, tema


def sombra(widget: QWidget, radio: int = 24, desplazamiento: int = 4, alfa: int = 40) -> None:
    efecto = QGraphicsDropShadowEffect(widget)
    efecto.setBlurRadius(radio)
    efecto.setOffset(0, desplazamiento)
    efecto.setColor(QColor(0, 0, 0, alfa))
    widget.setGraphicsEffect(efecto)


def separador_vertical(alto: int = 22) -> QFrame:
    f = QFrame()
    f.setObjectName("separador")
    f.setFixedSize(1, alto)
    return f


# ----------------------------------------------------------------------------
# Aviso flotante (toast)
# ----------------------------------------------------------------------------
class Toast(QLabel):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(False)
        self._opacidad = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacidad)
        self._anim = QPropertyAnimation(self._opacidad, b"opacity", self)
        self._anim.setDuration(220)
        self._temporizador = QTimer(self)
        self._temporizador.setSingleShot(True)
        self._temporizador.timeout.connect(self._ocultar)
        self.hide()

    def mostrar(self, texto: str, segundos: float = 3.0) -> None:
        self.setText(texto)
        self.adjustSize()
        self.recolocar()
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(self._opacidad.opacity() if self.isVisible() else 0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._temporizador.start(int(segundos * 1000))

    def recolocar(self) -> None:
        padre = self.parentWidget()
        self.move((padre.width() - self.width()) // 2, padre.height() - self.height() - 78)

    def _ocultar(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._tras_ocultar)
        self._anim.start()

    def _tras_ocultar(self) -> None:
        self._anim.finished.disconnect(self._tras_ocultar)
        if self._opacidad.opacity() < 0.05:
            self.hide()


# ----------------------------------------------------------------------------
# Píldora flotante (barra de navegación y propiedades de herramienta)
# ----------------------------------------------------------------------------
class Pildora(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("pildora")
        self.capa = QHBoxLayout(self)
        self.capa.setContentsMargins(10, 4, 10, 4)
        self.capa.setSpacing(4)
        sombra(self, 26, 5, 45)

    def boton(self, accion=None, nombre_icono: str | None = None, consejo: str = "") -> QToolButton:
        b = QToolButton()
        b.setAutoRaise(True)
        b.setIconSize(QSize(18, 18))
        if accion is not None:
            b.setDefaultAction(accion)
            b.setToolButtonStyle(Qt.ToolButtonIconOnly)
        if nombre_icono:
            tema.poner_icono(b, nombre_icono)
        if consejo:
            b.setToolTip(consejo)
        self.capa.addWidget(b)
        return b


class MuestraColor(QToolButton):
    """Botón redondo con un color; resaltado cuando está seleccionado."""

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.setCheckable(True)
        self.setFixedSize(26, 26)
        self.setToolTip(self.color.name())
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        if self.isChecked():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(tema.paleta().acento))
            p.drawEllipse(QRectF(self.rect()).adjusted(1, 1, -1, -1))
            p.setBrush(QColor(tema.paleta().superficie))
            p.drawEllipse(QRectF(self.rect()).adjusted(3, 3, -3, -3))
        p.setBrush(self.color)
        borde = QColor(tema.paleta().texto)
        borde.setAlpha(70)
        p.setPen(borde)
        p.drawEllipse(r)
        p.end()


# ----------------------------------------------------------------------------
# Barra lateral de herramientas
# ----------------------------------------------------------------------------
class BotonRail(QToolButton):
    def __init__(self, texto: str, nombre_icono: str, consejo: str = ""):
        super().__init__()
        self.setObjectName("botonRail")
        self.setText(texto)
        self.setCheckable(True)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(20, 20))
        self.setFixedWidth(74)
        self.setFixedHeight(46)
        self.setToolTip(consejo or texto)
        self.setCursor(Qt.PointingHandCursor)
        tema.poner_icono(self, nombre_icono, tema.paleta().texto_suave)


class LineaRail(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("lineaRail")
        self.setFixedSize(40, 1)


# ----------------------------------------------------------------------------
# Ficha de archivo arrastrable
# ----------------------------------------------------------------------------
class FichaArchivo(QFrame):
    """Muestra un archivo y permite arrastrarlo a otra aplicación (WhatsApp, Mail, Finder…)."""

    def __init__(self, ruta: str, parent=None):
        super().__init__(parent)
        self.ruta = str(Path(ruta).resolve())
        self.setCursor(Qt.OpenHandCursor)
        p = tema.paleta()
        self.setStyleSheet(
            f"FichaArchivo {{ background: {p.panel}; border: 1px dashed {p.borde_fuerte}; border-radius: 12px; }}"
        )
        capa = QHBoxLayout(self)
        capa.setContentsMargins(12, 10, 12, 10)
        ico = QLabel()
        ico.setPixmap(tema.icono("file-pdf-box", p.acento).pixmap(36, 36))
        capa.addWidget(ico)
        textos = QVBoxLayout()
        nombre = QLabel(f"<b>{Path(ruta).name}</b>")
        tam = os.path.getsize(ruta) if os.path.exists(ruta) else 0
        info = QLabel(f"{_tam_legible(tam)} · arrástralo a un chat o a otra aplicación")
        info.setStyleSheet(f"color: {p.texto_suave}; font-size: 12px;")
        textos.addWidget(nombre)
        textos.addWidget(info)
        capa.addLayout(textos, 1)

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            datos = QMimeData()
            datos.setUrls([QUrl.fromLocalFile(self.ruta)])
            drag = QDrag(self)
            drag.setMimeData(datos)
            drag.setPixmap(self.grab().scaledToWidth(min(320, self.width()), Qt.SmoothTransformation))
            drag.setHotSpot(QPoint(20, 20))
            drag.exec(Qt.CopyAction)


def _tam_legible(n: int) -> str:
    for unidad in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unidad == "GB":
            return f"{n:.0f} {unidad}" if unidad == "bytes" else f"{n:.1f} {unidad}"
        n /= 1024
    return ""


# ----------------------------------------------------------------------------
# Diálogo de WhatsApp
# ----------------------------------------------------------------------------
class DialogoWhatsApp(QDialog):
    def __init__(self, ruta: str, parent=None):
        super().__init__(parent)
        self.ruta = ruta
        self.ajustes = QSettings()
        self.setWindowTitle("Enviar por WhatsApp")
        self.setMinimumWidth(500)
        instalado = compartir.whatsapp_instalado()
        p = tema.paleta()

        capa = QVBoxLayout(self)
        capa.setContentsMargins(22, 20, 22, 18)
        capa.setSpacing(14)
        cabecera = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(tema.icono("whatsapp", tema.COLOR_WHATSAPP).pixmap(40, 40))
        cabecera.addWidget(logo)
        titulos = QVBoxLayout()
        t = QLabel("Enviar por WhatsApp")
        t.setStyleSheet("font-size: 18px; font-weight: 700;")
        st = QLabel("El PDF quedará listo para pegarlo en el chat." if instalado
                    else "No se ha encontrado WhatsApp para Mac: se usará WhatsApp Web.")
        st.setStyleSheet(f"color: {p.texto_suave};")
        titulos.addWidget(t)
        titulos.addWidget(st)
        cabecera.addLayout(titulos, 1)
        capa.addLayout(cabecera)

        capa.addWidget(FichaArchivo(ruta))

        etiqueta = QLabel("Teléfono del destinatario (opcional)")
        etiqueta.setStyleSheet("font-weight: 600;")
        capa.addWidget(etiqueta)
        self.telefono = QComboBox()
        self.telefono.setEditable(True)
        self.telefono.lineEdit().setPlaceholderText("p. ej. 600 123 456 · déjalo vacío para elegir el chat")
        for n in self.ajustes.value("whatsapp/recientes", [], type=list):
            self.telefono.addItem(n)
        self.telefono.setCurrentText("")
        capa.addWidget(self.telefono)

        pasos = QLabel(
            "<ol style='margin-left:-18px'>"
            "<li>Pulsa <b>Abrir WhatsApp</b>: el PDF se copia automáticamente.</li>"
            + ("<li>En el chat, pulsa <b>⌘V</b> y luego <b>Enviar</b>.</li>" if instalado else
               "<li>En el chat de WhatsApp Web, pulsa <b>⌘V</b> o arrastra la ficha de arriba.</li>")
            + "</ol>"
        )
        pasos.setStyleSheet(f"color: {p.texto_suave};")
        capa.addWidget(pasos)

        botones = QHBoxLayout()
        botones.addStretch()
        cancelar = QPushButton("Cancelar")
        cancelar.clicked.connect(self.reject)
        abrir = QPushButton("  Abrir WhatsApp" if instalado else "  Abrir WhatsApp Web")
        abrir.setObjectName("botonWhatsApp")
        abrir.setIcon(tema.icono("whatsapp", "#FFFFFF"))
        abrir.setDefault(False)
        abrir.setAutoDefault(True)
        abrir.clicked.connect(self._abrir)
        botones.addWidget(cancelar)
        botones.addWidget(abrir)
        capa.addLayout(botones)
        abrir.setFocus()
        self.modo = ""

    def _abrir(self) -> None:
        numero = self.telefono.currentText().strip()
        if numero:
            recientes = [n for n in self.ajustes.value("whatsapp/recientes", [], type=list) if n != numero]
            self.ajustes.setValue("whatsapp/recientes", [numero] + recientes[:4])
        compartir.copiar_archivo(self.ruta)
        self.modo = compartir.abrir_whatsapp(numero)
        if self.modo == "web":
            compartir.mostrar_en_carpeta(self.ruta)
        self.accept()


# ----------------------------------------------------------------------------
# Pantalla de bienvenida
# ----------------------------------------------------------------------------
class FilaReciente(QFrame):
    pulsada = Signal(str)

    def __init__(self, ruta: str):
        super().__init__()
        self.ruta = ruta
        self.setObjectName("filaReciente")
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(ruta)
        p = tema.paleta()
        capa = QHBoxLayout(self)
        capa.setContentsMargins(12, 8, 14, 8)
        capa.setSpacing(12)
        ico = QLabel()
        ico.setPixmap(tema.icono("file-pdf-box", p.acento).pixmap(30, 30))
        capa.addWidget(ico)
        textos = QVBoxLayout()
        textos.setSpacing(1)
        nombre = QLabel(Path(ruta).name)
        nombre.setStyleSheet(f"font-weight: 600; color: {p.texto};")
        carpeta = QLabel()
        carpeta.setStyleSheet(f"color: {p.texto_suave}; font-size: 12px;")
        texto_carpeta = str(Path(ruta).parent).replace(str(Path.home()), "~")
        carpeta.setText(carpeta.fontMetrics().elidedText(texto_carpeta, Qt.ElideMiddle, 380))
        textos.addWidget(nombre)
        textos.addWidget(carpeta)
        capa.addLayout(textos, 1)
        fecha = QLabel(_fecha_relativa(os.path.getmtime(ruta)))
        fecha.setStyleSheet(f"color: {p.texto_suave}; font-size: 12px;")
        capa.addWidget(fecha)

    def mouseReleaseEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton and self.rect().contains(ev.position().toPoint()):
            self.pulsada.emit(self.ruta)


class PantallaBienvenida(QWidget):
    abrir_solicitado = Signal()
    reciente_solicitado = Signal(str)
    firmas_solicitado = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bienvenida")
        self.setAutoFillBackground(False)
        externa = QVBoxLayout(self)
        externa.setContentsMargins(40, 150, 40, 16)
        externa.addStretch(1)

        centro = QVBoxLayout()
        centro.setSpacing(6)
        centro.setAlignment(Qt.AlignHCenter)
        self.logo = QLabel()
        self.logo.setAlignment(Qt.AlignCenter)
        self.logo.setPixmap(tema.pixmap_logo(96))
        centro.addWidget(self.logo)
        titulo = QLabel(tema.NOMBRE_APP)
        titulo.setObjectName("tituloBienvenida")
        titulo.setAlignment(Qt.AlignCenter)
        centro.addWidget(titulo)
        sub = QLabel("Abre, edita, firma y comparte tus documentos PDF")
        sub.setObjectName("subtituloBienvenida")
        sub.setAlignment(Qt.AlignCenter)
        centro.addWidget(sub)
        centro.addSpacing(18)

        fila = QHBoxLayout()
        fila.setSpacing(10)
        fila.addStretch()
        abrir = QPushButton("  Abrir un PDF")
        abrir.setObjectName("primario")
        tema.poner_icono(abrir, "folder-open-outline", "#FFFFFF")
        abrir.setIconSize(QSize(18, 18))
        abrir.setMinimumHeight(40)
        abrir.setMinimumWidth(170)
        abrir.setCursor(Qt.PointingHandCursor)
        abrir.clicked.connect(self.abrir_solicitado)
        firmas = QPushButton("  Mis firmas")
        tema.poner_icono(firmas, "signature-freehand")
        firmas.setIconSize(QSize(18, 18))
        firmas.setMinimumHeight(40)
        firmas.setCursor(Qt.PointingHandCursor)
        firmas.clicked.connect(self.firmas_solicitado)
        fila.addWidget(abrir)
        fila.addWidget(firmas)
        fila.addStretch()
        centro.addLayout(fila)
        pista = QLabel("o arrastra un archivo PDF a esta ventana")
        pista.setObjectName("subtituloBienvenida")
        pista.setStyleSheet("font-size: 12px;")
        pista.setAlignment(Qt.AlignCenter)
        centro.addSpacing(4)
        centro.addWidget(pista)
        externa.addLayout(centro)
        externa.addSpacing(18)

        # Aviso: hacerla app predeterminada para PDF (solo si procede)
        self.aviso = QFrame()
        self.aviso.setObjectName("avisoBienvenida")
        self.aviso.setMaximumWidth(620)
        ca = QHBoxLayout(self.aviso)
        ca.setContentsMargins(14, 10, 10, 10)
        ca.setSpacing(12)
        self.aviso_icono = QLabel()
        ca.addWidget(self.aviso_icono)
        self.aviso_texto = QLabel()
        self.aviso_texto.setWordWrap(True)
        ca.addWidget(self.aviso_texto, 1)
        self.aviso_boton = QPushButton()
        self.aviso_boton.setObjectName("primario")
        self.aviso_boton.setCursor(Qt.PointingHandCursor)
        ca.addWidget(self.aviso_boton)
        self.aviso_cerrar = QToolButton()
        self.aviso_cerrar.setToolTip("No volver a preguntar")
        self.aviso_cerrar.setCursor(Qt.PointingHandCursor)
        ca.addWidget(self.aviso_cerrar)
        self.aviso.hide()
        fila_aviso = QHBoxLayout()
        fila_aviso.addStretch()
        fila_aviso.addWidget(self.aviso)
        fila_aviso.addStretch()
        externa.addLayout(fila_aviso)
        externa.addSpacing(14)

        self.caja_recientes = QWidget()
        self.caja_recientes.setMaximumWidth(620)
        self.caja_recientes.setMinimumWidth(460)
        self.capa_recientes = QVBoxLayout(self.caja_recientes)
        self.capa_recientes.setContentsMargins(0, 0, 0, 0)
        self.capa_recientes.setSpacing(2)
        contenedor = QHBoxLayout()
        contenedor.addStretch()
        contenedor.addWidget(self.caja_recientes)
        contenedor.addStretch()
        externa.addLayout(contenedor)
        externa.addStretch(2)
        pie = QLabel(f"Versión {tema.VERSION} · inspirado en la Mezquita de Córdoba")
        pie.setObjectName("subtituloBienvenida")
        pie.setStyleSheet("font-size: 11px;")
        pie.setAlignment(Qt.AlignCenter)
        externa.addWidget(pie)

    def mostrar_aviso(self, texto: str, texto_boton: str, al_aceptar, al_cerrar) -> None:
        p = tema.paleta()
        self.aviso.setStyleSheet(
            f"QFrame#avisoBienvenida {{ background: {p.acento_suave}; border: 1px solid {p.borde}; border-radius: 12px; }}"
            f"QFrame#avisoBienvenida QLabel {{ background: transparent; color: {p.texto}; }}"
        )
        self.aviso_icono.setPixmap(tema.icono("file-pdf-box", p.acento).pixmap(26, 26))
        self.aviso_texto.setText(texto)
        self.aviso_boton.setText(texto_boton)
        tema.poner_icono(self.aviso_cerrar, "close", p.texto_suave)
        for senal in (self.aviso_boton.clicked, self.aviso_cerrar.clicked):
            try:
                senal.disconnect()
            except (RuntimeError, TypeError):
                pass
        self.aviso_boton.clicked.connect(al_aceptar)
        self.aviso_cerrar.clicked.connect(al_cerrar)
        self.aviso.show()

    def ocultar_aviso(self) -> None:
        self.aviso.hide()

    def actualizar_recientes(self, rutas: list[str]) -> None:
        while self.capa_recientes.count():
            item = self.capa_recientes.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        rutas = [r for r in rutas if os.path.exists(r)][:6]
        if not rutas:
            self.caja_recientes.hide()
            return
        self.caja_recientes.show()
        cab = QLabel("RECIENTES")
        cab.setObjectName("seccion")
        self.capa_recientes.addWidget(cab)
        for ruta in rutas:
            fila = FilaReciente(ruta)
            fila.pulsada.connect(self.reciente_solicitado.emit)
            self.capa_recientes.addWidget(fila)

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        pal = tema.paleta()
        p.fillRect(self.rect(), QColor(pal.fondo))
        # Friso de arquería en la parte superior
        n = max(5, self.width() // 150)
        alto = 120
        tema.dibujar_arqueria(p, QRectF(-20, 14, self.width() + 40, alto), n, pal,
                              0.20 if not pal.oscuro else 0.28)
        p.end()


def _fecha_relativa(marca: float) -> str:
    fecha = datetime.fromtimestamp(marca)
    dias = (datetime.now().date() - fecha.date()).days
    if dias == 0:
        return f"hoy, {fecha:%H:%M}"
    if dias == 1:
        return "ayer"
    if dias < 7:
        return f"hace {dias} días"
    return f"{fecha:%d/%m/%Y}"
