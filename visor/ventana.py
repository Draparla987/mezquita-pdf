"""Ventana principal de Mezquita PDF."""

from __future__ import annotations

import math
import os
from pathlib import Path

import pymupdf
from PySide6.QtCore import QEvent, QObject, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QImage, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QSlider, QSpinBox,
    QStackedWidget, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import compartir, sistema, tema
from . import firma_digital as fd
from .componentes import (
    BotonRail, DialogoWhatsApp, LineaRail, MuestraColor, PantallaBienvenida, Pildora, Toast,
    separador_vertical,
)
from .dialogos import (
    DialogoContrasena, DialogoFirmaDigital, DialogoFirmas, DialogoTexto, DialogoVerificacion,
    FUENTES_PDF,
)
from .documento import Documento
from .vista import Herramienta, VistaPDF, a_rgb

FILTRO_PDF = "Documentos PDF (*.pdf);;Todos los archivos (*)"
MAX_RECIENTES = 10

COLORES_RESALTADO = ["#FFD60A", "#8CE99A", "#74C0FC", "#FFA8C5", "#FFC078"]
COLORES_TRAZO = ["#8E1B2C", "#E03131", "#1C7ED6", "#2F9E44", "#212529"]

# herramienta → (texto corto, icono, consejo, atajo)
DEF_HERRAMIENTAS = {
    Herramienta.SELECCIONAR: ("Seleccionar", "cursor-text", "Selecciona y copia texto; rellena formularios y sigue enlaces", "V"),
    Herramienta.MANO: ("Mano", "hand-back-right-outline", "Desplazar el documento arrastrando", "H"),
    Herramienta.RESALTAR: ("Resaltar", "marker", "Resaltar texto", "Ctrl+Shift+H"),
    Herramienta.SUBRAYAR: ("Subrayar", "format-underline", "Subrayar texto", "Ctrl+Shift+U"),
    Herramienta.TACHAR: ("Tachar", "format-strikethrough-variant", "Tachar texto", None),
    Herramienta.TEXTO: ("Texto", "format-text", "Añadir un cuadro de texto", "T"),
    Herramienta.NOTA: ("Nota", "note-text-outline", "Añadir una nota adhesiva", "N"),
    Herramienta.DIBUJO: ("Dibujar", "draw", "Dibujo a mano alzada", "D"),
    Herramienta.RECTANGULO: ("Rectángulo", "rectangle-outline", "Dibujar un rectángulo", "R"),
    Herramienta.ELIPSE: ("Elipse", "ellipse-outline", "Dibujar una elipse", "O"),
    Herramienta.FLECHA: ("Flecha", "arrow-top-right", "Dibujar una flecha", "A"),
    Herramienta.EDITAR_TEXTO: ("Editar texto", "text-box-edit-outline", "Cambiar el texto existente del PDF", "E"),
    Herramienta.TAPAR: ("Borrar zona", "selection-remove", "Eliminar de verdad el contenido de una zona", None),
    Herramienta.IMAGEN: ("Imagen", "image-outline", "Insertar una imagen", "I"),
    Herramienta.FIRMA: ("Firmar", "signature-freehand", "Colocar tu firma manuscrita", "F"),
    Herramienta.FIRMA_DIGITAL: ("Certificado", "file-certificate-outline", "Firmar con certificado digital", None),
    Herramienta.BORRADOR: ("Borrador", "eraser", "Eliminar anotaciones con un clic", "X"),
}

FORMAS = (Herramienta.RECTANGULO, Herramienta.ELIPSE, Herramienta.FLECHA)

RAIL = [
    Herramienta.SELECCIONAR, Herramienta.MANO, None,
    Herramienta.RESALTAR, Herramienta.SUBRAYAR, Herramienta.TACHAR, None,
    Herramienta.TEXTO, Herramienta.NOTA, Herramienta.DIBUJO, "formas", None,
    Herramienta.EDITAR_TEXTO, Herramienta.TAPAR, Herramienta.IMAGEN, None,
    Herramienta.FIRMA, Herramienta.FIRMA_DIGITAL, None,
    Herramienta.BORRADOR,
]

PISTAS = {
    Herramienta.RESALTAR: "Arrastra sobre el texto para resaltarlo",
    Herramienta.SUBRAYAR: "Arrastra sobre el texto para subrayarlo",
    Herramienta.TACHAR: "Arrastra sobre el texto para tacharlo",
    Herramienta.TEXTO: "Haz clic donde quieras escribir",
    Herramienta.NOTA: "Haz clic donde quieras dejar la nota",
    Herramienta.DIBUJO: "Dibuja con el ratón o el trackpad",
    Herramienta.RECTANGULO: "Arrastra para dibujar",
    Herramienta.ELIPSE: "Arrastra para dibujar",
    Herramienta.FLECHA: "Arrastra para dibujar",
    Herramienta.EDITAR_TEXTO: "Haz clic en la línea de texto que quieras cambiar",
    Herramienta.TAPAR: "Arrastra para borrar todo lo que haya en la zona",
    Herramienta.IMAGEN: "Haz clic o arrastra para colocar la imagen",
    Herramienta.FIRMA: "Haz clic donde quieras firmar (o arrastra para elegir el tamaño)",
    Herramienta.FIRMA_DIGITAL: "Arrastra un recuadro donde irá la firma digital",
    Herramienta.BORRADOR: "Haz clic sobre una anotación para eliminarla",
}

_ventanas: list["VentanaPrincipal"] = []


def nueva_ventana(ruta: str | None = None) -> "VentanaPrincipal":
    v = VentanaPrincipal()
    _ventanas.append(v)
    v.show()
    if ruta:
        v.abrir_ruta(ruta)
    return v


def abrir_en_ventana(ruta: str) -> None:
    """Abre en una ventana vacía si la hay; si no, en una nueva."""
    for v in _ventanas:
        if v.documento and v.documento.ruta and os.path.abspath(v.documento.ruta) == os.path.abspath(ruta):
            v.raise_()
            v.activateWindow()
            return
    for v in _ventanas:
        if v.documento is None:
            v.abrir_ruta(ruta)
            v.raise_()
            return
    nueva_ventana(ruta)


def al_cambiar_tema() -> None:
    for v in _ventanas:
        v.refrescar_tema()


class _Recolocador(QObject):
    """Recoloca los elementos flotantes cuando cambia el tamaño de su contenedor."""

    def __init__(self, funcion):
        super().__init__()
        self.funcion = funcion

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.Resize, QEvent.Show):
            self.funcion()
        return False


class _Puente(QObject):
    """Lleva a la interfaz las respuestas que macOS entrega en otro hilo."""
    resultado = Signal(object)


class VentanaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setUnifiedTitleAndToolBarOnMac(False)
        self.ajustes = QSettings()
        self.documento: Documento | None = None
        self.tenia_firmas = False
        self.firma_actual: Path | None = None
        self.resize(1320, 880)
        self.setMinimumSize(900, 600)
        self.setAcceptDrops(True)

        self.vista = VistaPDF()
        self.vista.color = QColor(COLORES_RESALTADO[0])
        self.vista.color_trazo = QColor(COLORES_TRAZO[1])
        self._crear_acciones()
        self._crear_menus()
        self._crear_interfaz()
        self._conectar_vista()
        self._actualizar_estado_ui()
        self.restoreGeometry(self.ajustes.value("ventana/geometria", b""))
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self._escape)

    # ------------------------------------------------------------------
    # Acciones y menús
    # ------------------------------------------------------------------
    def _accion(self, texto, slot=None, atajo=None, icono=None, consejo=None, checkable=False):
        a = QAction(texto, self)
        if icono:
            tema.poner_icono(a, icono)
        if atajo:
            a.setShortcut(QKeySequence(atajo))
        tip = consejo or texto.rstrip("…")
        if atajo:
            tip += f"   {QKeySequence(atajo).toString(QKeySequence.NativeText)}"
        a.setToolTip(tip)
        a.setCheckable(checkable)
        if slot:
            a.triggered.connect(slot)
        return a

    def _crear_acciones(self) -> None:
        A = self._accion
        self.a_abrir = A("Abrir…", self.abrir, QKeySequence.Open, "folder-open-outline", "Abrir un PDF")
        self.a_guardar = A("Guardar", self.guardar, QKeySequence.Save, "content-save-outline")
        self.a_guardar_como = A("Guardar como…", self.guardar_como, QKeySequence.SaveAs)
        self.a_imprimir = A("Imprimir…", self.imprimir, QKeySequence.Print, "printer-outline")
        self.a_combinar = A("Combinar con otros PDF…", self.combinar, None, "file-document-multiple-outline")
        self.a_propiedades = A("Propiedades del documento…", self.propiedades, "Ctrl+D", "information-outline")
        self.a_cerrar_doc = A("Cerrar documento", self.cerrar_documento, QKeySequence.Close)
        self.a_cerrar = A("Cerrar ventana", self.close, "Ctrl+Shift+W")
        self.a_deshacer = A("Deshacer", self.deshacer, QKeySequence.Undo, "undo")
        self.a_rehacer = A("Rehacer", self.rehacer, QKeySequence.Redo, "redo")
        self.a_buscar = A("Buscar…", self._enfocar_busqueda, QKeySequence.Find, "magnify")
        self.a_buscar_sig = A("Buscar siguiente", lambda: self._paso_busqueda(1), QKeySequence.FindNext, "chevron-down")
        self.a_buscar_ant = A("Buscar anterior", lambda: self._paso_busqueda(-1), QKeySequence.FindPrevious, "chevron-up")
        self.a_acercar = A("Acercar", lambda: self.vista.set_zoom(self.vista.zoom * 1.2), QKeySequence.ZoomIn, "plus")
        self.a_alejar = A("Alejar", lambda: self.vista.set_zoom(self.vista.zoom / 1.2), QKeySequence.ZoomOut, "minus")
        self.a_real = A("Tamaño real", lambda: self.vista.set_zoom(1.0), "Ctrl+0")
        self.a_ancho = A("Ajustar al ancho", self.vista.ajustar_ancho, "Ctrl+2", "arrow-expand-horizontal")
        self.a_pagina = A("Ajustar página", self.vista.ajustar_pagina, "Ctrl+1", "fit-to-page-outline")
        self.a_primera = A("Primera página", lambda: self.vista.ir_a_pagina(0), "Home")
        self.a_ultima = A("Última página", lambda: self.vista.ir_a_pagina(self.documento.num_paginas - 1) if self.documento else None, "End")
        self.a_anterior = A("Página anterior", lambda: self.vista.ir_a_pagina(self.vista.pagina_actual() - 1), "Left", "chevron-left")
        self.a_siguiente = A("Página siguiente", lambda: self.vista.ir_a_pagina(self.vista.pagina_actual() + 1), "Right", "chevron-right")
        self.a_panel = A("Mostrar u ocultar miniaturas", self._alternar_panel, "Ctrl+Shift+L", "dock-left")

        self.a_girar_der = A("Girar página a la derecha", lambda: self.girar_pagina(90), "Ctrl+R", "rotate-right")
        self.a_girar_izq = A("Girar página a la izquierda", lambda: self.girar_pagina(-90), "Ctrl+Shift+R", "rotate-left")
        self.a_eliminar_pag = A("Eliminar página", self.eliminar_pagina, None, "delete-outline")
        self.a_pag_blanco = A("Insertar página en blanco", self.insertar_blanco, None, "file-plus-outline")
        self.a_pag_archivo = A("Insertar páginas desde archivo…", self.insertar_desde_archivo)
        self.a_extraer = A("Extraer páginas…", self.extraer_paginas)
        self.a_subir_pag = A("Mover página arriba", lambda: self.mover_pagina(-1))
        self.a_bajar_pag = A("Mover página abajo", lambda: self.mover_pagina(1))

        self.a_mis_firmas = A("Firma manuscrita…", self.elegir_firma_manuscrita, "Ctrl+Shift+S", "signature-freehand")
        self.a_firma_digital = A("Firmar con certificado digital…", self.iniciar_firma_digital, "Ctrl+Shift+D", "file-certificate-outline")
        self.a_firma_invisible = A("Firma digital invisible…", self.firma_digital_invisible)
        self.a_verificar = A("Verificar firmas…", self.verificar_firmas, None, "shield-check-outline")
        self.a_gestionar_firmas = A("Gestionar mis firmas…", self.gestionar_firmas, None, "draw-pen")

        self.a_correo = A("Enviar por correo electrónico…", self.compartir_correo, "Ctrl+Shift+E", "email-outline")
        self.a_whatsapp = A("Enviar por WhatsApp…", self.compartir_whatsapp, None, "whatsapp")
        tema.poner_icono(self.a_whatsapp, "whatsapp", tema.COLOR_WHATSAPP)
        self.a_copiar_archivo = A("Copiar el archivo (para pegarlo en otra app)", self.copiar_archivo, None, "content-copy")
        self.a_finder = A("Mostrar en Finder", self.mostrar_en_finder, None, "folder-search-outline")

        # Herramientas
        self.grupo_herr = QActionGroup(self)
        self.grupo_herr.setExclusive(True)
        self.accion_de_herr: dict[Herramienta, QAction] = {}
        for herr, (texto, ico, consejo, atajo) in DEF_HERRAMIENTAS.items():
            a = A(texto, None, atajo, ico, consejo, checkable=True)
            a.triggered.connect(lambda _=False, h=herr: self.set_herramienta(h))
            self.grupo_herr.addAction(a)
            self.accion_de_herr[herr] = a
        self.accion_de_herr[Herramienta.SELECCIONAR].setChecked(True)

        # Acciones que necesitan un documento abierto
        self._acciones_doc = [
            a for a in self.findChildren(QAction)
            if a not in (self.a_abrir, self.a_cerrar, self.a_gestionar_firmas, self.a_cerrar_doc)
        ]

    def _crear_menus(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu("&Archivo")
        m.addAction(self.a_abrir)
        self.menu_recientes = m.addMenu("Abrir reciente")
        self.menu_recientes.aboutToShow.connect(self._rellenar_recientes)
        m.addSeparator()
        m.addAction(self.a_guardar)
        m.addAction(self.a_guardar_como)
        m.addSeparator()
        self.menu_compartir = QMenu("Compartir", self)
        tema.poner_icono(self.menu_compartir.menuAction(), "share-variant-outline")
        self.menu_compartir.aboutToShow.connect(self._rellenar_menu_compartir)
        m.addMenu(self.menu_compartir)
        m.addAction(self.a_imprimir)
        m.addSeparator()
        m.addAction(self.a_combinar)
        m.addAction(self.a_propiedades)
        m.addSeparator()
        m.addAction(self.a_cerrar_doc)
        m.addAction(self.a_cerrar)

        m = mb.addMenu("&Edición")
        for a in (self.a_deshacer, self.a_rehacer, None, self.a_buscar, self.a_buscar_sig, self.a_buscar_ant):
            m.addSeparator() if a is None else m.addAction(a)

        m = mb.addMenu("&Ver")
        for a in (self.a_acercar, self.a_alejar, self.a_real, self.a_ancho, self.a_pagina, None,
                  self.a_primera, self.a_anterior, self.a_siguiente, self.a_ultima, None, self.a_panel):
            m.addSeparator() if a is None else m.addAction(a)

        m = mb.addMenu("&Páginas")
        for a in (self.a_girar_der, self.a_girar_izq, None, self.a_pag_blanco, self.a_pag_archivo,
                  self.a_extraer, None, self.a_subir_pag, self.a_bajar_pag, None, self.a_eliminar_pag):
            m.addSeparator() if a is None else m.addAction(a)

        m = mb.addMenu("&Herramientas")
        for h in RAIL:
            if h is None:
                m.addSeparator()
            elif h == "formas":
                for f in FORMAS:
                    m.addAction(self.accion_de_herr[f])
            else:
                m.addAction(self.accion_de_herr[h])

        self.menu_firmar = mb.addMenu("&Firmar")
        for a in (self.a_mis_firmas, self.a_gestionar_firmas, None, self.a_firma_digital,
                  self.a_firma_invisible, None, self.a_verificar):
            self.menu_firmar.addSeparator() if a is None else self.menu_firmar.addAction(a)

        m = mb.addMenu("Ay&uda")
        self.a_predeterminada = m.addAction("Usar Mezquita PDF como app predeterminada para PDF",
                                            self.hacer_predeterminada)
        self.a_predeterminada.setEnabled(sistema.ruta_app() is not None)
        m.addSeparator()
        self.a_acerca = m.addAction(f"Acerca de {tema.NOMBRE_APP}", self._acerca_de)

    # ------------------------------------------------------------------
    # Interfaz
    # ------------------------------------------------------------------
    def _crear_interfaz(self) -> None:
        self.raiz = QWidget()
        capa_raiz = QVBoxLayout(self.raiz)
        capa_raiz.setContentsMargins(0, 0, 0, 0)
        self.pila = QStackedWidget()
        capa_raiz.addWidget(self.pila)
        self.setCentralWidget(self.raiz)

        self.bienvenida = PantallaBienvenida()
        self.bienvenida.abrir_solicitado.connect(self.abrir)
        self.bienvenida.reciente_solicitado.connect(abrir_en_ventana)
        self.bienvenida.firmas_solicitado.connect(self.gestionar_firmas)
        self.pila.addWidget(self.bienvenida)

        editor = QWidget()
        capa = QVBoxLayout(editor)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)
        capa.addWidget(self._crear_barra_superior())
        cuerpo = QHBoxLayout()
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)
        cuerpo.addWidget(self._crear_rail())
        cuerpo.addWidget(self._crear_panel_lateral())
        cuerpo.addWidget(self._crear_zona_vista(), 1)
        capa.addLayout(cuerpo, 1)
        self.pila.addWidget(editor)
        self.editor = editor

        self.toast = Toast(self.raiz)
        self._recolocador_raiz = _Recolocador(self.toast.recolocar)
        self.raiz.installEventFilter(self._recolocador_raiz)
        self._mostrar_bienvenida()

    def _boton_barra(self, accion: QAction) -> QToolButton:
        b = QToolButton()
        b.setDefaultAction(accion)
        b.setIconSize(QSize(20, 20))
        b.setToolButtonStyle(Qt.ToolButtonIconOnly)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _crear_barra_superior(self) -> QWidget:
        barra = QWidget()
        barra.setObjectName("barraSuperior")
        barra.setAttribute(Qt.WA_StyledBackground, True)
        barra.setFixedHeight(56)
        capa = QHBoxLayout(barra)
        capa.setContentsMargins(14, 6, 14, 6)
        capa.setSpacing(4)

        self.logo_barra = QLabel()
        self.logo_barra.setPixmap(tema.pixmap_logo(30))
        capa.addWidget(self.logo_barra)
        capa.addSpacing(6)
        textos = QVBoxLayout()
        textos.setSpacing(0)
        nombre = QLabel(tema.NOMBRE_APP)
        nombre.setObjectName("nombreApp")
        self.etiqueta_doc = QLabel("")
        self.etiqueta_doc.setObjectName("nombreDoc")
        self.etiqueta_doc.setMaximumWidth(320)
        textos.addWidget(nombre)
        textos.addWidget(self.etiqueta_doc)
        capa.addLayout(textos)
        capa.addSpacing(14)
        capa.addWidget(separador_vertical())
        capa.addSpacing(6)
        for a in (self.a_panel, self.a_abrir, self.a_guardar, self.a_imprimir):
            capa.addWidget(self._boton_barra(a))
        capa.addSpacing(6)
        capa.addWidget(separador_vertical())
        capa.addSpacing(6)
        for a in (self.a_deshacer, self.a_rehacer):
            capa.addWidget(self._boton_barra(a))
        capa.addStretch(1)

        # Búsqueda
        self.campo_buscar = QLineEdit()
        self.campo_buscar.setObjectName("busqueda")
        self.campo_buscar.setPlaceholderText("Buscar en el documento")
        self.campo_buscar.setClearButtonEnabled(True)
        self._accion_lupa = self.campo_buscar.addAction(tema.icono("magnify", tema.paleta().texto_suave),
                                                        QLineEdit.LeadingPosition)
        self._accion_lupa.setProperty("icono", "magnify")
        self.campo_buscar.setFixedWidth(240)
        self.campo_buscar.returnPressed.connect(self._buscar)
        self.campo_buscar.textChanged.connect(self._busqueda_editada)
        capa.addWidget(self.campo_buscar)
        self.contador_busqueda = QLabel("")
        self.contador_busqueda.setObjectName("contadorBusqueda")
        capa.addWidget(self.contador_busqueda)
        self.boton_buscar_ant = self._boton_barra(self.a_buscar_ant)
        self.boton_buscar_sig = self._boton_barra(self.a_buscar_sig)
        capa.addWidget(self.boton_buscar_ant)
        capa.addWidget(self.boton_buscar_sig)
        for w in (self.contador_busqueda, self.boton_buscar_ant, self.boton_buscar_sig):
            w.setVisible(False)
        capa.addSpacing(10)

        # Compartir y Firmar
        self.boton_compartir = QToolButton()
        self.boton_compartir.setObjectName("botonSecundario")
        self.boton_compartir.setText("Compartir")
        tema.poner_icono(self.boton_compartir, "share-variant-outline")
        self.boton_compartir.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.boton_compartir.setPopupMode(QToolButton.InstantPopup)
        self.boton_compartir.setMenu(self.menu_compartir)
        self.boton_compartir.setCursor(Qt.PointingHandCursor)
        capa.addWidget(self.boton_compartir)
        capa.addSpacing(4)
        self.boton_firmar = QToolButton()
        self.boton_firmar.setObjectName("botonPrimario")
        self.boton_firmar.setText("Firmar")
        tema.poner_icono(self.boton_firmar, "signature-freehand", "#FFFFFF", "#FFFFFF")
        self.boton_firmar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.boton_firmar.setPopupMode(QToolButton.InstantPopup)
        self.boton_firmar.setMenu(self.menu_firmar)
        self.boton_firmar.setCursor(Qt.PointingHandCursor)
        capa.addWidget(self.boton_firmar)
        return barra

    def _crear_rail(self) -> QWidget:
        rail = QWidget()
        rail.setObjectName("rail")
        capa = QVBoxLayout(rail)
        capa.setContentsMargins(5, 8, 5, 8)
        capa.setSpacing(2)
        self.botones_rail: dict[Herramienta, BotonRail] = {}
        for h in RAIL:
            if h is None:
                capa.addSpacing(3)
                capa.addWidget(LineaRail(), 0, Qt.AlignHCenter)
                capa.addSpacing(3)
                continue
            if h == "formas":
                b = BotonRail("Formas", "shape-outline", "Rectángulos, elipses y flechas")
                b.setPopupMode(QToolButton.InstantPopup)
                menu = QMenu(b)
                for f in FORMAS:
                    menu.addAction(self.accion_de_herr[f])
                menu.aboutToHide.connect(lambda: QTimer.singleShot(0, self._sincronizar_rail))
                b.setMenu(menu)
                self.boton_formas = b
            else:
                texto, ico, consejo, atajo = DEF_HERRAMIENTAS[h]
                if atajo:
                    consejo += f"   {QKeySequence(atajo).toString(QKeySequence.NativeText)}"
                b = BotonRail(texto, ico, consejo)
                b.clicked.connect(lambda _=False, hh=h: self.set_herramienta(hh))
                self.botones_rail[h] = b
            capa.addWidget(b, 0, Qt.AlignHCenter)
        capa.addStretch(1)
        scroll = QScrollArea()
        scroll.setObjectName("railScroll")
        scroll.setWidget(rail)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedWidth(86)
        scroll.setFrameShape(QFrame.NoFrame)
        return scroll

    def _crear_panel_lateral(self) -> QWidget:
        self.panel = QWidget()
        self.panel.setObjectName("panelLateral")
        self.panel.setAttribute(Qt.WA_StyledBackground, True)
        self.panel.setFixedWidth(200)
        capa = QVBoxLayout(self.panel)
        capa.setContentsMargins(10, 12, 10, 6)
        capa.setSpacing(10)
        segmentos = QWidget()
        segmentos.setObjectName("segmentos")
        segmentos.setAttribute(Qt.WA_StyledBackground, True)
        cs = QHBoxLayout(segmentos)
        cs.setContentsMargins(3, 3, 3, 3)
        cs.setSpacing(2)
        grupo = QButtonGroup(self)
        self.panel_pila = QStackedWidget()
        for i, texto in enumerate(("Páginas", "Marcadores")):
            b = QToolButton()
            b.setObjectName("segmento")
            b.setText(texto)
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.setToolButtonStyle(Qt.ToolButtonTextOnly)
            b.setSizePolicy(b.sizePolicy().horizontalPolicy().Expanding, b.sizePolicy().verticalPolicy())
            b.clicked.connect(lambda _=False, n=i: self.panel_pila.setCurrentIndex(n))
            grupo.addButton(b)
            cs.addWidget(b)
        capa.addWidget(segmentos)

        self.miniaturas = QListWidget()
        self.miniaturas.setObjectName("miniaturas")
        self.miniaturas.setViewMode(QListWidget.IconMode)
        self.miniaturas.setFlow(QListWidget.TopToBottom)
        self.miniaturas.setWrapping(False)
        self.miniaturas.setIconSize(QSize(140, 180))
        self.miniaturas.setSpacing(4)
        self.miniaturas.setMovement(QListWidget.Snap)
        self.miniaturas.setDragDropMode(QAbstractItemView.InternalMove)
        self.miniaturas.setDefaultDropAction(Qt.MoveAction)
        self.miniaturas.setContextMenuPolicy(Qt.CustomContextMenu)
        self.miniaturas.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.miniaturas.customContextMenuRequested.connect(self._menu_miniatura)
        self.miniaturas.itemClicked.connect(lambda it: self.vista.ir_a_pagina(self.miniaturas.row(it)))
        self.miniaturas.model().rowsMoved.connect(self._miniatura_movida)
        self.panel_pila.addWidget(self.miniaturas)

        pag_marc = QWidget()
        cm = QVBoxLayout(pag_marc)
        cm.setContentsMargins(0, 0, 0, 0)
        self.marcadores = QTreeWidget()
        self.marcadores.setObjectName("marcadores")
        self.marcadores.setHeaderHidden(True)
        self.marcadores.setIndentation(14)
        self.marcadores.itemClicked.connect(self._ir_a_marcador)
        self.sin_marcadores = QLabel("Este documento no tiene marcadores.")
        self.sin_marcadores.setObjectName("vacio")
        self.sin_marcadores.setWordWrap(True)
        self.sin_marcadores.setAlignment(Qt.AlignCenter)
        cm.addWidget(self.marcadores)
        cm.addWidget(self.sin_marcadores)
        self.panel_pila.addWidget(pag_marc)
        capa.addWidget(self.panel_pila, 1)

        self._cola_miniaturas: list[int] = []
        self._temporizador_mini = QTimer(self)
        self._temporizador_mini.timeout.connect(self._renderizar_miniaturas)
        self.panel.setVisible(self.ajustes.value("ventana/panel", True, type=bool))
        return self.panel

    def _crear_zona_vista(self) -> QWidget:
        zona = QWidget()
        self.zona_vista = zona
        capa = QVBoxLayout(zona)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)
        self.banner = self._crear_banner()
        capa.addWidget(self.banner)
        capa.addWidget(self.vista, 1)

        # Barra flotante de navegación (abajo)
        self.pildora_nav = Pildora(zona)
        self.pildora_nav.boton(self.a_anterior)
        self.spin_pagina = QSpinBox()
        self.spin_pagina.setMinimum(1)
        self.spin_pagina.setKeyboardTracking(False)
        self.spin_pagina.setButtonSymbols(QSpinBox.NoButtons)
        self.spin_pagina.setAlignment(Qt.AlignCenter)
        self.spin_pagina.setFixedWidth(46)
        self.spin_pagina.valueChanged.connect(lambda v: self.vista.ir_a_pagina(v - 1))
        self.pildora_nav.capa.addWidget(self.spin_pagina)
        self.etiqueta_total = QLabel("/ 0")
        self.pildora_nav.capa.addWidget(self.etiqueta_total)
        self.pildora_nav.boton(self.a_siguiente)
        self.pildora_nav.capa.addSpacing(4)
        self.pildora_nav.capa.addWidget(separador_vertical(20))
        self.pildora_nav.capa.addSpacing(4)
        self.pildora_nav.boton(self.a_alejar)
        self.combo_zoom = QComboBox()
        self.combo_zoom.setEditable(True)
        self.combo_zoom.setFixedWidth(78)
        for z in (50, 75, 100, 125, 150, 200, 300, 400):
            self.combo_zoom.addItem(f"{z} %", z / 100)
        self.combo_zoom.activated.connect(self._zoom_desde_combo)
        self.combo_zoom.lineEdit().returnPressed.connect(self._zoom_desde_combo)
        self.combo_zoom.lineEdit().setAlignment(Qt.AlignCenter)
        self.pildora_nav.capa.addWidget(self.combo_zoom)
        self.pildora_nav.boton(self.a_acercar)
        self.pildora_nav.capa.addSpacing(4)
        self.pildora_nav.capa.addWidget(separador_vertical(20))
        self.pildora_nav.capa.addSpacing(4)
        for a in (self.a_ancho, self.a_pagina, self.a_girar_izq, self.a_girar_der):
            self.pildora_nav.boton(a)

        # Barra flotante de propiedades de la herramienta (arriba)
        self.pildora_prop = Pildora(zona)
        self.pildora_prop.hide()

        self._recolocador_zona = _Recolocador(self._recolocar_flotantes)
        zona.installEventFilter(self._recolocador_zona)
        return zona

    def _crear_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("banner")
        banner.setVisible(False)
        capa = QHBoxLayout(banner)
        capa.setContentsMargins(14, 8, 10, 8)
        self.banner_icono = QLabel()
        capa.addWidget(self.banner_icono)
        self.banner_texto = QLabel()
        capa.addWidget(self.banner_texto, 1)
        boton = QPushButton("Ver firmas")
        boton.setCursor(Qt.PointingHandCursor)
        boton.clicked.connect(self.verificar_firmas)
        capa.addWidget(boton)
        envoltorio = QFrame()
        ce = QVBoxLayout(envoltorio)
        ce.setContentsMargins(14, 10, 14, 4)
        ce.addWidget(banner)
        envoltorio.setStyleSheet(f"background: {tema.paleta().lienzo};")
        envoltorio.setVisible(False)
        self._banner_interior = banner
        return envoltorio

    def _recolocar_flotantes(self) -> None:
        z = self.zona_vista
        barra_v = self.vista.verticalScrollBar().width() if self.vista.verticalScrollBar().isVisible() else 0
        ancho_util = z.width() - barra_v
        self.pildora_nav.adjustSize()
        self.pildora_nav.move((ancho_util - self.pildora_nav.width()) // 2,
                              z.height() - self.pildora_nav.height() - 18)
        self.pildora_nav.raise_()
        if self.pildora_prop.isVisible():
            self.pildora_prop.adjustSize()
            arriba = self.banner.height() if self.banner.isVisible() else 0
            self.pildora_prop.move((ancho_util - self.pildora_prop.width()) // 2, arriba + 14)
            self.pildora_prop.raise_()

    def _conectar_vista(self) -> None:
        v = self.vista
        v.pagina_cambiada.connect(self._pagina_cambiada)
        v.zoom_cambiado.connect(self._zoom_cambiado)
        v.documento_modificado.connect(self._doc_modificado)
        v.mensaje.connect(self.aviso)
        v.pedir_texto.connect(self._anadir_texto)
        v.pedir_nota.connect(self._anadir_nota)
        v.pedir_imagen.connect(self._anadir_imagen)
        v.pedir_firma_manuscrita.connect(self._colocar_firma)
        v.pedir_firma_digital.connect(self._firmar_digital)
        v.pedir_editar_texto.connect(self._editar_linea)
        v.pedir_campo_formulario.connect(self._editar_campo)
        v.pedir_editar_anotacion.connect(self._editar_anotacion)

    def aviso(self, texto: str, segundos: float = 3.0) -> None:
        self.toast.mostrar(texto, segundos)

    def refrescar_tema(self) -> None:
        tema.refrescar_iconos(self)
        self.logo_barra.setPixmap(tema.pixmap_logo(30))
        self._banner_wrapper_estilo()
        self._comprobar_firmas()
        self.bienvenida.actualizar_recientes(self._recientes())
        self.bienvenida.update()
        if self.vista.herramienta not in (Herramienta.SELECCIONAR, Herramienta.MANO):
            self._actualizar_pildora_propiedades(self.vista.herramienta)
        self.vista.contenedor.update()

    def _banner_wrapper_estilo(self) -> None:
        self.banner.setStyleSheet(f"background: {tema.paleta().lienzo};")

    def _mostrar_bienvenida(self) -> None:
        self.bienvenida.actualizar_recientes(self._recientes())
        self._ofrecer_predeterminada()
        self.pila.setCurrentWidget(self.bienvenida)

    # ------------------------------------------------------------------
    # App predeterminada para PDF (macOS)
    # ------------------------------------------------------------------
    def _ofrecer_predeterminada(self) -> None:
        if (sistema.ruta_app() is None or sistema.es_predeterminada()
                or self.ajustes.value("no_ofrecer_predeterminada", False, type=bool)):
            self.bienvenida.ocultar_aviso()
            return
        actual = sistema.app_predeterminada_pdf()
        texto = ("<b>Abre tus PDF directamente con Mezquita PDF.</b><br>"
                 + (f"Ahora se abren con {actual}." if actual else ""))
        if not sistema.en_aplicaciones():
            texto += "<br><small>Consejo: mueve antes la app a la carpeta Aplicaciones.</small>"
        self.bienvenida.mostrar_aviso(texto, "Usar por defecto", self.hacer_predeterminada,
                                      self._no_ofrecer_predeterminada)

    def _no_ofrecer_predeterminada(self) -> None:
        self.ajustes.setValue("no_ofrecer_predeterminada", True)
        self.bienvenida.ocultar_aviso()

    def hacer_predeterminada(self) -> None:
        if sistema.ruta_app() is None:
            self.aviso("Esta opción está disponible en la app instalada (Mezquita PDF.app)", 5)
            return
        self._puente = _Puente()
        self._puente.resultado.connect(self._tras_predeterminada)
        puente = self._puente
        sistema.hacer_predeterminada(lambda error: puente.resultado.emit(error))

    def _tras_predeterminada(self, error) -> None:
        if error:
            QMessageBox.warning(self, "App predeterminada",
                                f"macOS no ha permitido el cambio:\n{error}\n\n"
                                "También puedes hacerlo en Finder: selecciona un PDF → ⌘I → "
                                "«Abrir con» → Mezquita PDF → «Cambiar todo…».")
            return
        self.bienvenida.ocultar_aviso()
        self.aviso("Listo: los PDF se abrirán con Mezquita PDF al hacer doble clic", 5)

    def _escape(self) -> None:
        if self.campo_buscar.hasFocus():
            self.campo_buscar.clear()
            self.vista.setFocus()
        elif self.vista.herramienta != Herramienta.SELECCIONAR:
            self.set_herramienta(Herramienta.SELECCIONAR)

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------
    def _actualizar_estado_ui(self) -> None:
        hay = self.documento is not None
        for a in self._acciones_doc:
            a.setEnabled(hay)
        for b in self.botones_rail.values():
            b.setEnabled(hay)
        self.boton_formas.setEnabled(hay)
        self.boton_compartir.setEnabled(hay)
        self.a_cerrar_doc.setEnabled(hay)
        if hay:
            self.a_deshacer.setEnabled(self.documento.puede_deshacer())
            self.a_rehacer.setEnabled(self.documento.puede_rehacer())
            self.spin_pagina.setMaximum(self.documento.num_paginas)
            self.etiqueta_total.setText(f"/ {self.documento.num_paginas}")
        self._actualizar_titulo()
        QTimer.singleShot(0, self._recolocar_flotantes)

    def _actualizar_titulo(self) -> None:
        if self.documento is None:
            self.setWindowTitle(tema.NOMBRE_APP)
            self.setWindowFilePath("")
            self.etiqueta_doc.setText("")
            return
        self.setWindowTitle(f"{self.documento.nombre}[*] — {tema.NOMBRE_APP}")
        self.setWindowFilePath(self.documento.ruta or "")
        self.setWindowModified(self.documento.modificado)
        marca = " · sin guardar" if self.documento.modificado else ""
        texto = self.documento.nombre + marca
        fm = self.etiqueta_doc.fontMetrics()
        self.etiqueta_doc.setText(fm.elidedText(texto, Qt.ElideMiddle, 300))
        self.etiqueta_doc.setToolTip(self.documento.ruta or "")

    def _doc_modificado(self) -> None:
        self._actualizar_estado_ui()
        self._actualizar_miniatura(self.vista.pagina_actual())

    def _pagina_cambiada(self, p: int) -> None:
        self.spin_pagina.blockSignals(True)
        self.spin_pagina.setValue(p + 1)
        self.spin_pagina.blockSignals(False)
        if 0 <= p < self.miniaturas.count():
            self.miniaturas.blockSignals(True)
            self.miniaturas.setCurrentRow(p)
            self.miniaturas.scrollToItem(self.miniaturas.item(p))
            self.miniaturas.blockSignals(False)

    def _zoom_cambiado(self, z: float) -> None:
        self.combo_zoom.setEditText(f"{round(z * 100)} %")

    def _zoom_desde_combo(self, *_):
        texto = self.combo_zoom.currentText().replace("%", "").strip()
        try:
            self.vista.set_zoom(float(texto.replace(",", ".")) / 100)
        except ValueError:
            pass
        self.vista.setFocus()

    def set_herramienta(self, h: Herramienta) -> None:
        self.accion_de_herr[h].setChecked(True)
        self.vista.set_herramienta(h)
        self._sincronizar_rail()
        self._actualizar_pildora_propiedades(h)
        if h == Herramienta.FIRMA and self.firma_actual is None:
            self.elegir_firma_manuscrita()

    def _sincronizar_rail(self) -> None:
        h = self.vista.herramienta
        for herr, b in self.botones_rail.items():
            b.setChecked(herr == h)
        es_forma = h in FORMAS
        self.boton_formas.setChecked(es_forma)
        icono_forma = DEF_HERRAMIENTAS[h][1] if es_forma else "shape-outline"
        tema.poner_icono(self.boton_formas, icono_forma, tema.paleta().texto_suave)

    def _actualizar_pildora_propiedades(self, h: Herramienta) -> None:
        pild = self.pildora_prop
        capa = pild.capa
        while capa.count():
            item = capa.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if h in (Herramienta.SELECCIONAR, Herramienta.MANO):
            pild.hide()
            return
        texto, ico, _consejo, _atajo = DEF_HERRAMIENTAS[h]
        icono = QLabel()
        icono.setPixmap(tema.icono(ico, tema.paleta().acento).pixmap(18, 18))
        capa.addWidget(icono)
        titulo = QLabel(f"<b>{texto}</b>")
        titulo.setStyleSheet(f"color: {tema.paleta().texto};")
        capa.addWidget(titulo)
        pista = QLabel(PISTAS.get(h, ""))
        capa.addWidget(pista)

        if h in (Herramienta.RESALTAR, Herramienta.SUBRAYAR, Herramienta.TACHAR, Herramienta.DIBUJO, *FORMAS):
            capa.addSpacing(6)
            capa.addWidget(separador_vertical(20))
            capa.addSpacing(6)
            es_resaltado = h == Herramienta.RESALTAR
            colores = COLORES_RESALTADO if es_resaltado else COLORES_TRAZO
            actual = (self.vista.color if es_resaltado else self.vista.color_trazo).name().upper()
            grupo = QButtonGroup(pild)
            for c in colores:
                m = MuestraColor(QColor(c))
                m.setChecked(c.upper() == actual)
                grupo.addButton(m)
                m.clicked.connect(lambda _=False, col=c, r=es_resaltado: self._elegir_color(col, r))
                capa.addWidget(m)
        if h in (Herramienta.DIBUJO, *FORMAS):
            capa.addSpacing(6)
            capa.addWidget(separador_vertical(20))
            capa.addSpacing(6)
            capa.addWidget(QLabel("Grosor"))
            slider = QSlider(Qt.Horizontal)
            slider.setRange(1, 12)
            slider.setValue(int(round(self.vista.grosor)))
            slider.setFixedWidth(90)
            valor = QLabel(f"{int(self.vista.grosor)} pt")
            valor.setFixedWidth(34)

            def cambiar(v, etiqueta=valor):
                self.vista.grosor = float(v)
                etiqueta.setText(f"{v} pt")
            slider.valueChanged.connect(cambiar)
            capa.addWidget(slider)
            capa.addWidget(valor)
        if h == Herramienta.FIRMA and self.firma_actual and self.firma_actual.exists():
            capa.addSpacing(6)
            capa.addWidget(separador_vertical(20))
            capa.addSpacing(6)
            miniatura = QLabel()
            pix = QPixmap(str(self.firma_actual))
            miniatura.setPixmap(pix.scaledToHeight(26, Qt.SmoothTransformation))
            miniatura.setStyleSheet("background: white; border-radius: 6px; padding: 2px 6px;")
            capa.addWidget(miniatura)
            cambiar = QPushButton("Cambiar…")
            cambiar.clicked.connect(self.elegir_firma_manuscrita)
            capa.addWidget(cambiar)

        capa.addSpacing(4)
        cerrar = QToolButton()
        tema.poner_icono(cerrar, "close", tema.paleta().texto_suave)
        cerrar.setIconSize(QSize(16, 16))
        cerrar.setToolTip("Terminar (Esc)")
        cerrar.clicked.connect(lambda: self.set_herramienta(Herramienta.SELECCIONAR))
        capa.addWidget(cerrar)
        pild.show()
        QTimer.singleShot(0, self._recolocar_flotantes)

    def _elegir_color(self, color: str, resaltado: bool) -> None:
        if resaltado:
            self.vista.color = QColor(color)
        else:
            self.vista.color_trazo = QColor(color)

    # ------------------------------------------------------------------
    # Abrir / guardar
    # ------------------------------------------------------------------
    def abrir(self) -> None:
        inicio = self.ajustes.value("ultima_carpeta", str(Path.home()))
        rutas, _ = QFileDialog.getOpenFileNames(self, "Abrir PDF", inicio, FILTRO_PDF)
        for ruta in rutas:
            self.ajustes.setValue("ultima_carpeta", os.path.dirname(ruta))
            abrir_en_ventana(ruta)

    def abrir_ruta(self, ruta: str) -> bool:
        try:
            doc = Documento(ruta)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo abrir el archivo:\n{exc}")
            return False
        if doc.necesita_contrasena():
            while True:
                dlg = DialogoContrasena(doc.nombre, self)
                if dlg.exec() != QDialog.Accepted:
                    doc.cerrar()
                    return False
                if doc.autenticar(dlg.campo.text()):
                    break
                QMessageBox.warning(self, "Contraseña", "Contraseña incorrecta.")
        if self.documento is not None:
            self.documento.cerrar()
        self.documento = doc
        self.pila.setCurrentWidget(self.editor)
        self.vista.set_documento(doc)
        self.set_herramienta(Herramienta.SELECCIONAR)
        self._añadir_reciente(ruta)
        self._cargar_panel_lateral()
        self._comprobar_firmas()
        self._actualizar_estado_ui()
        QTimer.singleShot(50, self._zoom_inicial)
        return True

    def _zoom_inicial(self) -> None:
        """Ajusta al ancho sin pasar del 140 % y empieza en la primera página."""
        if self.documento is None:
            return
        r = self.documento.pagina(0).rect
        disponible = self.vista.viewport().width() - 60
        self.vista.set_zoom(max(0.5, min(1.4, disponible / r.width)))
        self.vista.ir_a_pagina(0)

    def _comprobar_firmas(self) -> None:
        self.tenia_firmas = False
        self.banner.setVisible(False)
        QTimer.singleShot(0, self._recolocar_flotantes)
        if not self.documento or not self.documento.ruta:
            return
        try:
            datos = Path(self.documento.ruta).read_bytes()
        except OSError:
            return
        if not fd.tiene_firmas(datos):
            return
        self.tenia_firmas = True
        resultados = fd.verificar_firmas(datos)
        validas = all(r.integra for r in resultados)
        n = len(resultados)
        p = tema.paleta()
        if validas:
            firmantes = ", ".join(dict.fromkeys(r.firmante for r in resultados))
            texto = (f"<b>Documento firmado</b> · {n} firma{'s' if n > 1 else ''} "
                     f"válida{'s' if n > 1 else ''} · {firmantes}")
            color, fondo, ico = p.exito, p.exito_suave, "check-decagram"
        else:
            texto = ("<b>Firma no válida</b> · el documento se ha modificado después de firmarse "
                     "o la firma está dañada")
            color, fondo, ico = p.error, p.error_suave, "alert-decagram"
        self._banner_interior.setStyleSheet(
            f"QFrame#banner {{ background: {fondo}; border: 1px solid {color}; border-radius: 10px; }}"
            f"QFrame#banner QLabel {{ color: {color}; }}"
        )
        self.banner_icono.setPixmap(tema.icono(ico, color).pixmap(22, 22))
        self.banner_texto.setText(texto)
        self._banner_wrapper_estilo()
        self.banner.setVisible(True)
        self._banner_interior.setVisible(True)
        QTimer.singleShot(0, self._recolocar_flotantes)

    def guardar(self) -> bool:
        if self.documento is None:
            return False
        if not self.documento.ruta:
            return self.guardar_como()
        if self.tenia_firmas:
            if self.documento.puede_guardar_incremental():
                return self._guardar_en(self.documento.ruta, incremental=True)
            r = QMessageBox.warning(
                self, "Documento firmado",
                "Este documento tiene firmas digitales y, tras los cambios hechos (p. ej. deshacer, "
                "eliminar o reordenar páginas), no se puede guardar sin invalidarlas.\n\n"
                "¿Quieres guardar una copia con otro nombre?",
                QMessageBox.Save | QMessageBox.Cancel,
            )
            return self.guardar_como() if r == QMessageBox.Save else False
        return self._guardar_en(self.documento.ruta)

    def guardar_como(self) -> bool:
        if self.documento is None:
            return False
        sugerido = self.documento.ruta or str(Path.home() / self.documento.nombre)
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar como", sugerido, FILTRO_PDF)
        if not ruta:
            return False
        if not ruta.lower().endswith(".pdf"):
            ruta += ".pdf"
        return self._guardar_en(ruta)

    def _guardar_en(self, ruta: str, incremental: bool = False) -> bool:
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.documento.guardar(ruta, incremental=incremental)
        except Exception as exc:
            QMessageBox.critical(self, "Error al guardar", str(exc))
            return False
        finally:
            QApplication.restoreOverrideCursor()
        self._añadir_reciente(ruta)
        self.aviso(f"Guardado en {ruta}", 5)
        self._comprobar_firmas()
        self._actualizar_estado_ui()
        return True

    def _confirmar_descartar(self) -> bool:
        if self.documento is None or not self.documento.modificado:
            return True
        r = QMessageBox.question(
            self, "Cambios sin guardar",
            f"¿Quieres guardar los cambios en «{self.documento.nombre}»?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save,
        )
        if r == QMessageBox.Save:
            return self.guardar()
        return r == QMessageBox.Discard

    def closeEvent(self, ev) -> None:
        if not self._confirmar_descartar():
            ev.ignore()
            return
        self.ajustes.setValue("ventana/geometria", self.saveGeometry())
        if self.documento:
            self.documento.cerrar()
        if self in _ventanas:
            _ventanas.remove(self)
        ev.accept()

    def _recientes(self) -> list[str]:
        return [r for r in self.ajustes.value("recientes", [], type=list) if os.path.exists(r)]

    def _añadir_reciente(self, ruta: str) -> None:
        recientes = [r for r in self.ajustes.value("recientes", [], type=list) if r != ruta]
        recientes.insert(0, ruta)
        self.ajustes.setValue("recientes", recientes[:MAX_RECIENTES])

    def _rellenar_recientes(self) -> None:
        self.menu_recientes.clear()
        recientes = self._recientes()
        for r in recientes:
            self.menu_recientes.addAction(os.path.basename(r), lambda _=False, x=r: abrir_en_ventana(x)).setToolTip(r)
        if not recientes:
            self.menu_recientes.addAction("(vacío)").setEnabled(False)
        else:
            self.menu_recientes.addSeparator()
            self.menu_recientes.addAction("Borrar lista", self._borrar_recientes)

    def _borrar_recientes(self) -> None:
        self.ajustes.setValue("recientes", [])
        self.bienvenida.actualizar_recientes([])

    def dragEnterEvent(self, ev) -> None:
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:
        for url in ev.mimeData().urls():
            ruta = url.toLocalFile()
            if ruta.lower().endswith(".pdf"):
                abrir_en_ventana(ruta)

    # ------------------------------------------------------------------
    # Panel lateral
    # ------------------------------------------------------------------
    def _cargar_panel_lateral(self) -> None:
        self.miniaturas.blockSignals(True)
        self.miniaturas.clear()
        blanco = QPixmap(140, 180)
        blanco.fill(Qt.white)
        for i in range(self.documento.num_paginas):
            it = QListWidgetItem(QIcon(blanco), str(i + 1))
            it.setTextAlignment(Qt.AlignHCenter)
            self.miniaturas.addItem(it)
        self.miniaturas.blockSignals(False)
        self._cola_miniaturas = list(range(self.documento.num_paginas))
        self._temporizador_mini.start(0)

        self.marcadores.clear()
        pilas: list[QTreeWidgetItem] = []
        for nivel, titulo, pagina, *resto in self.documento.doc.get_toc(simple=False):
            it = QTreeWidgetItem([titulo])
            destino = resto[0] if resto else {}
            y = destino.get("to").y if isinstance(destino, dict) and destino.get("to") else None
            it.setData(0, Qt.UserRole, (pagina - 1, y))
            pilas = pilas[: nivel - 1]
            if pilas:
                pilas[-1].addChild(it)
            else:
                self.marcadores.addTopLevelItem(it)
            pilas.append(it)
        hay_marcadores = self.marcadores.topLevelItemCount() > 0
        self.marcadores.setVisible(hay_marcadores)
        self.sin_marcadores.setVisible(not hay_marcadores)

    def _renderizar_miniaturas(self) -> None:
        if not self._cola_miniaturas or self.documento is None:
            self._temporizador_mini.stop()
            return
        for _ in range(4):
            if not self._cola_miniaturas:
                break
            self._actualizar_miniatura(self._cola_miniaturas.pop(0))

    def _actualizar_miniatura(self, i: int) -> None:
        if self.documento is None or not (0 <= i < self.miniaturas.count()):
            return
        pagina = self.documento.pagina(i)
        escala = 360 / max(pagina.rect.width, pagina.rect.height)
        pm = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala), alpha=False)
        img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888).copy()
        pix = QPixmap.fromImage(img)
        icono = QIcon()
        icono.addPixmap(pix, QIcon.Normal)
        icono.addPixmap(pix, QIcon.Selected)
        self.miniaturas.item(i).setIcon(icono)

    def _ir_a_marcador(self, it: QTreeWidgetItem) -> None:
        pagina, y = it.data(0, Qt.UserRole)
        if pagina >= 0:
            self.vista.ir_a_pagina(pagina, y)

    def _miniatura_movida(self, _padre, inicio, _fin, _destino, fila) -> None:
        if self.documento is None:
            return
        destino = fila if fila > inicio else fila
        self.documento.instantanea()
        self.documento.mover_pagina(inicio, -1 if destino >= self.documento.num_paginas else destino)
        QTimer.singleShot(0, self._tras_cambio_estructura)

    def _menu_miniatura(self, pos) -> None:
        it = self.miniaturas.itemAt(pos)
        if it is None:
            return
        i = self.miniaturas.row(it)
        menu = QMenu(self)
        menu.addAction("Girar a la derecha", lambda: self.girar_pagina(90, i))
        menu.addAction("Girar a la izquierda", lambda: self.girar_pagina(-90, i))
        menu.addAction("Insertar página en blanco después", lambda: self.insertar_blanco(i))
        menu.addAction("Extraer esta página…", lambda: self.extraer_paginas(str(i + 1)))
        menu.addSeparator()
        menu.addAction("Eliminar página", lambda: self.eliminar_pagina(i))
        menu.exec(self.miniaturas.mapToGlobal(pos))

    def _alternar_panel(self) -> None:
        self.panel.setVisible(not self.panel.isVisible())
        self.ajustes.setValue("ventana/panel", self.panel.isVisible())

    def _tras_cambio_estructura(self) -> None:
        self.vista.recargar()
        self._cargar_panel_lateral()
        self._actualizar_estado_ui()

    # ------------------------------------------------------------------
    # Operaciones con páginas
    # ------------------------------------------------------------------
    def girar_pagina(self, grados: int, indice: int | None = None) -> None:
        if self.documento is None:
            return
        i = self.vista.pagina_actual() if indice is None else indice
        pagina = self.documento.pagina(i)
        self.documento.instantanea()
        pagina.set_rotation((pagina.rotation + grados) % 360)
        self.vista.recargar()
        self._actualizar_miniatura(i)
        self._actualizar_estado_ui()

    def eliminar_pagina(self, indice: int | None = None) -> None:
        if self.documento is None:
            return
        if self.documento.num_paginas <= 1:
            QMessageBox.information(self, "Eliminar página", "Un PDF debe tener al menos una página.")
            return
        i = self.vista.pagina_actual() if indice is None else indice
        if QMessageBox.question(self, "Eliminar página", f"¿Eliminar la página {i + 1}?") != QMessageBox.Yes:
            return
        self.documento.instantanea()
        self.documento.eliminar_pagina(i)
        self._tras_cambio_estructura()

    def insertar_blanco(self, despues_de: int | None = None) -> None:
        if self.documento is None:
            return
        i = self.vista.pagina_actual() if despues_de is None else despues_de
        r = self.documento.pagina(i).rect
        self.documento.instantanea()
        self.documento.nueva_pagina(i + 1, r.width, r.height)
        self._tras_cambio_estructura()
        self.vista.ir_a_pagina(i + 1)

    def insertar_desde_archivo(self) -> None:
        if self.documento is None:
            return
        ruta, _ = QFileDialog.getOpenFileName(self, "Insertar páginas de…", self.ajustes.value("ultima_carpeta", ""), FILTRO_PDF)
        if not ruta:
            return
        i = self.vista.pagina_actual()
        try:
            otro = pymupdf.open(ruta)
            self.documento.instantanea()
            self.documento.insertar_pdf(otro, i + 1)
            otro.close()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        self._tras_cambio_estructura()

    def combinar(self) -> None:
        if self.documento is None:
            return
        rutas, _ = QFileDialog.getOpenFileNames(self, "PDF que se añadirán al final", self.ajustes.value("ultima_carpeta", ""), FILTRO_PDF)
        if not rutas:
            return
        self.documento.instantanea()
        for ruta in rutas:
            try:
                otro = pymupdf.open(ruta)
                self.documento.insertar_pdf(otro)
                otro.close()
            except Exception as exc:
                QMessageBox.warning(self, "Combinar", f"No se pudo añadir {os.path.basename(ruta)}:\n{exc}")
        self._tras_cambio_estructura()
        self.aviso(f"Se han añadido {len(rutas)} documento(s) al final", 5)

    def extraer_paginas(self, rango: str | None = None) -> None:
        if self.documento is None:
            return
        n = self.documento.num_paginas
        if rango is None:
            rango, ok = QInputDialog.getText(
                self, "Extraer páginas", f"Páginas a extraer (p. ej. 1-3, 5, 8-10). Total: {n}",
                text=str(self.vista.pagina_actual() + 1))
            if not ok or not rango.strip():
                return
        try:
            paginas = _parsear_rango(rango, n)
        except ValueError:
            QMessageBox.warning(self, "Extraer páginas", "El rango de páginas no es válido.")
            return
        base = Path(self.documento.ruta or self.documento.nombre).stem
        sugerido = str(Path(self.documento.ruta or Path.home()).with_name(f"{base}_paginas.pdf"))
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar páginas extraídas", sugerido, FILTRO_PDF)
        if not ruta:
            return
        nuevo = pymupdf.open()
        for p in paginas:
            nuevo.insert_pdf(self.documento.doc, from_page=p, to_page=p)
        nuevo.save(ruta, garbage=3, deflate=True)
        nuevo.close()
        self.aviso(f"{len(paginas)} página(s) guardadas en {ruta}", 6)

    def mover_pagina(self, delta: int) -> None:
        if self.documento is None:
            return
        i = self.vista.pagina_actual()
        j = i + delta
        if not (0 <= j < self.documento.num_paginas):
            return
        self.documento.instantanea()
        if delta > 0:
            self.documento.mover_pagina(i, j + 1 if j + 1 < self.documento.num_paginas else -1)
        else:
            self.documento.mover_pagina(i, j)
        self._tras_cambio_estructura()
        self.vista.ir_a_pagina(j)

    # ------------------------------------------------------------------
    # Deshacer / rehacer
    # ------------------------------------------------------------------
    def deshacer(self) -> None:
        if self.documento and self.documento.deshacer():
            self._tras_cambio_estructura()

    def rehacer(self) -> None:
        if self.documento and self.documento.rehacer():
            self._tras_cambio_estructura()

    # ------------------------------------------------------------------
    # Búsqueda
    # ------------------------------------------------------------------
    def _enfocar_busqueda(self) -> None:
        self.campo_buscar.setFocus()
        self.campo_buscar.selectAll()

    def _buscar(self) -> None:
        texto = self.campo_buscar.text().strip()
        if self.vista.resultados and texto == getattr(self, "_ultima_busqueda", None):
            self.vista.siguiente_resultado(1)
        else:
            self._ultima_busqueda = texto
            n = self.vista.buscar(texto)
            if texto and n == 0:
                self.aviso(f"No se ha encontrado «{texto}»")
        self._actualizar_contador_busqueda()

    def _paso_busqueda(self, paso: int) -> None:
        self.vista.siguiente_resultado(paso)
        self._actualizar_contador_busqueda()

    def _actualizar_contador_busqueda(self) -> None:
        n = len(self.vista.resultados)
        hay = n > 0
        self.contador_busqueda.setText(f"{self.vista.resultado_actual + 1} de {n}" if hay else "")
        for w in (self.contador_busqueda, self.boton_buscar_ant, self.boton_buscar_sig):
            w.setVisible(hay)

    def _busqueda_editada(self, texto: str) -> None:
        if not texto:
            self.vista.limpiar_busqueda()
            self._ultima_busqueda = None
            self._actualizar_contador_busqueda()

    # ------------------------------------------------------------------
    # Edición: texto, notas, imágenes, formularios
    # ------------------------------------------------------------------
    def _anadir_texto(self, indice: int, punto: pymupdf.Point) -> None:
        dlg = DialogoTexto(self, "Añadir texto",
                           tamano=float(self.ajustes.value("texto/tamano", 12)),
                           color=QColor(self.ajustes.value("texto/color", "#000000")),
                           fuente=self.ajustes.value("texto/fuente", "Helvetica"))
        if dlg.exec() != QDialog.Accepted or not dlg.texto.strip():
            return
        self.ajustes.setValue("texto/tamano", dlg.tamano)
        self.ajustes.setValue("texto/color", dlg.color.name())
        self.ajustes.setValue("texto/fuente", dlg.fuente)
        pagina = self.documento.pagina(indice)
        fuente_corta, fuente_annot = FUENTES_PDF[dlg.fuente]
        lineas = dlg.texto.splitlines() or [""]
        # Margen generoso: el cuadro de la anotación añade relleno interno
        ancho = max(pymupdf.get_text_length(l, fontname=fuente_corta, fontsize=dlg.tamano) for l in lineas) * 1.08 + dlg.tamano * 1.5
        alto = len(lineas) * dlg.tamano * 1.3 + dlg.tamano * 0.9
        if pagina.rotation in (90, 270):
            ancho, alto = alto, ancho
        r = pymupdf.Rect(punto.x, punto.y - dlg.tamano * 0.3, punto.x + ancho, punto.y - dlg.tamano * 0.3 + alto)
        self.documento.instantanea()
        annot = pagina.add_freetext_annot(
            r, dlg.texto, fontsize=dlg.tamano, fontname=fuente_annot,
            text_color=a_rgb(dlg.color), rotate=pagina.rotation,
        )
        annot.set_border(width=0)
        annot.update()
        self.vista._modificado(indice)

    def _editar_anotacion(self, indice: int, xref: int) -> None:
        pagina = self.documento.pagina(indice)
        annot = pagina.load_annot(xref)
        if annot is None:
            return
        contenido = annot.info.get("content", "")
        if annot.type[0] == pymupdf.PDF_ANNOT_FREE_TEXT:
            dlg = DialogoTexto(self, "Editar texto", texto=contenido, mostrar_formato=False)
            if dlg.exec() != QDialog.Accepted:
                return
            nuevo = dlg.texto
        else:
            nuevo, ok = QInputDialog.getMultiLineText(self, "Nota", "Texto de la nota:", contenido)
            if not ok:
                return
        self.documento.instantanea()
        annot = self.documento.pagina(indice).load_annot(xref)
        annot.set_info(content=nuevo)
        annot.update()
        self.vista._modificado(indice)

    def _anadir_nota(self, indice: int, punto: pymupdf.Point) -> None:
        texto, ok = QInputDialog.getMultiLineText(self, "Nota", "Texto de la nota:")
        if not ok or not texto.strip():
            return
        self.documento.instantanea()
        annot = self.documento.pagina(indice).add_text_annot(punto, texto, icon="Note")
        annot.set_info(title=os.environ.get("USER", ""))
        annot.update()
        self.vista._modificado(indice)

    def _rect_para_imagen(self, pagina, destino, ancho_img: int, alto_img: int, ancho_def: float) -> pymupdf.Rect:
        if isinstance(destino, pymupdf.Rect):
            return destino
        w = ancho_def
        h = w * alto_img / max(1, ancho_img)
        if pagina.rotation in (90, 270):
            w, h = h, w
        r = pymupdf.Rect(destino.x - w / 2, destino.y - h / 2, destino.x + w / 2, destino.y + h / 2)
        # Mantenerla dentro de la página
        limites = pagina.mediabox
        dx = max(0, limites.x0 - r.x0) - max(0, r.x1 - limites.x1)
        dy = max(0, limites.y0 - r.y0) - max(0, r.y1 - limites.y1)
        return r + (dx, dy, dx, dy)

    def _anadir_imagen(self, indice: int, destino) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Insertar imagen", self.ajustes.value("ultima_carpeta_img", str(Path.home())),
                                              "Imágenes (*.png *.jpg *.jpeg *.gif *.bmp *.tif *.tiff)")
        if not ruta:
            return
        self.ajustes.setValue("ultima_carpeta_img", os.path.dirname(ruta))
        img = QImage(ruta)
        if img.isNull():
            QMessageBox.warning(self, "Imagen", "No se pudo leer la imagen.")
            return
        pagina = self.documento.pagina(indice)
        r = self._rect_para_imagen(pagina, destino, img.width(), img.height(), 200)
        self.documento.instantanea()
        pagina.insert_image(r, filename=ruta, keep_proportion=True, rotate=(-pagina.rotation) % 360)
        self.vista._modificado(indice)
        self.set_herramienta(Herramienta.SELECCIONAR)

    def _editar_campo(self, indice: int, xref: int) -> None:
        pagina = self.documento.pagina(indice)
        campo = next((w for w in pagina.widgets() if w.xref == xref), None)
        if campo is None:
            return
        tipo = campo.field_type
        nombre = campo.field_label or campo.field_name or "Campo"
        valor = None
        if tipo == pymupdf.PDF_WIDGET_TYPE_TEXT:
            actual = campo.field_value or ""
            if campo.field_flags & pymupdf.PDF_TX_FIELD_IS_MULTILINE:
                valor, ok = QInputDialog.getMultiLineText(self, "Rellenar formulario", nombre, actual)
            else:
                valor, ok = QInputDialog.getText(self, "Rellenar formulario", nombre, text=actual)
            if not ok:
                return
        elif tipo == pymupdf.PDF_WIDGET_TYPE_CHECKBOX:
            activo = campo.field_value not in (False, "Off", "", None)
            valor = "Off" if activo else campo.on_state()
        elif tipo == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
            valor = campo.on_state()
        elif tipo in (pymupdf.PDF_WIDGET_TYPE_COMBOBOX, pymupdf.PDF_WIDGET_TYPE_LISTBOX):
            opciones = [o if isinstance(o, str) else o[1] for o in (campo.choice_values or [])]
            if not opciones:
                return
            actual = opciones.index(campo.field_value) if campo.field_value in opciones else 0
            valor, ok = QInputDialog.getItem(self, "Rellenar formulario", nombre, opciones, actual, False)
            if not ok:
                return
        else:
            return
        self.documento.instantanea()
        campo = next(w for w in self.documento.pagina(indice).widgets() if w.xref == xref)
        campo.field_value = valor
        campo.update()
        self.vista._modificado(indice)

    def _editar_linea(self, indice: int, linea: dict) -> None:
        flags = linea["flags"]
        nombre = linea["fuente"].lower()
        if flags & 8 or "courier" in nombre or "mono" in nombre:
            familia = "Courier"
        elif flags & 4 or "times" in nombre or "serif" in nombre and "sans" not in nombre:
            familia = "Times"
        else:
            familia = "Helvetica"
        negrita = bool(flags & 16) or "bold" in nombre
        cursiva = bool(flags & 2) or "italic" in nombre or "oblique" in nombre
        c = linea["color"]
        color = QColor((c >> 16) & 255, (c >> 8) & 255, c & 255)
        dlg = DialogoTexto(self, "Editar texto del PDF", texto=linea["texto"],
                           tamano=round(linea["tamano"], 1), color=color, fuente=familia)
        if dlg.exec() != QDialog.Accepted or dlg.texto == linea["texto"]:
            return
        base = {"Helvetica": "he", "Times": "ti", "Courier": "co"}[dlg.fuente]
        if negrita and cursiva:
            fuente = base + "bi"
        elif negrita:
            fuente = base + "bo"
        elif cursiva:
            fuente = base + "it"
        else:
            fuente = {"he": "helv", "ti": "tiro", "co": "cour"}[base]
        pagina = self.documento.pagina(indice)
        r = pymupdf.Rect(linea["rect"])
        margen = r.height * 0.15
        r.y0 += margen
        r.y1 -= margen
        self.documento.instantanea()
        pagina.add_redact_annot(r, fill=False)
        pagina.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                                graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        dx, dy = linea["dir"]
        import math
        angulo = round(math.degrees(math.atan2(-dy, dx)))
        pagina.insert_text(linea["origen"], dlg.texto, fontname=fuente, fontsize=dlg.tamano,
                           color=a_rgb(dlg.color), rotate=angulo if angulo in (0, 90, 180, 270, -90) else 0)
        self.vista._modificado(indice)

    # ------------------------------------------------------------------
    # Firmas
    # ------------------------------------------------------------------
    def elegir_firma_manuscrita(self) -> None:
        dlg = DialogoFirmas(self)
        if dlg.exec() == QDialog.Accepted and dlg.ruta_elegida:
            self.firma_actual = dlg.ruta_elegida
            if self.vista.herramienta != Herramienta.FIRMA:
                self.set_herramienta(Herramienta.FIRMA)
        elif self.vista.herramienta == Herramienta.FIRMA and self.firma_actual is None:
            self.set_herramienta(Herramienta.SELECCIONAR)

    def _colocar_firma(self, indice: int, destino) -> None:
        if self.firma_actual is None or not self.firma_actual.exists():
            self.firma_actual = None
            self.elegir_firma_manuscrita()
            return
        img = QImage(str(self.firma_actual))
        pagina = self.documento.pagina(indice)
        r = self._rect_para_imagen(pagina, destino, img.width(), img.height(), 150)
        self.documento.instantanea()
        pagina.insert_image(r, filename=str(self.firma_actual), keep_proportion=True,
                            rotate=(-pagina.rotation) % 360)
        self.vista._modificado(indice)
        self.set_herramienta(Herramienta.SELECCIONAR)
        self.aviso("Firma colocada. Guarda el documento para conservarla (⌘S).", 8)

    def iniciar_firma_digital(self) -> None:
        self.set_herramienta(Herramienta.FIRMA_DIGITAL)

    def firma_digital_invisible(self) -> None:
        self._firmar_digital(None, None)

    def _preparar_para_firmar(self) -> bytes | None:
        """La firma se calcula sobre el fichero en disco: hay que guardar antes."""
        if self.documento.modificado or not self.documento.ruta:
            r = QMessageBox.question(
                self, "Guardar antes de firmar",
                "Para firmar digitalmente hay que guardar primero los cambios del documento. "
                "¿Guardar ahora?", QMessageBox.Save | QMessageBox.Cancel, QMessageBox.Save)
            if r != QMessageBox.Save or not self.guardar():
                return None
        return Path(self.documento.ruta).read_bytes()

    def _firmar_digital(self, indice: int | None, rect: pymupdf.Rect | None) -> None:
        if self.documento is None:
            return
        datos = self._preparar_para_firmar()
        if datos is None:
            self.set_herramienta(Herramienta.SELECCIONAR)
            return
        dlg = DialogoFirmaDigital(self, visible=rect is not None)
        if dlg.exec() != QDialog.Accepted:
            self.set_herramienta(Herramienta.SELECCIONAR)
            return

        caja = None
        if rect is not None:
            pagina = self.documento.pagina(indice)
            r = pymupdf.Rect(rect) * ~pagina.transformation_matrix
            r.normalize()
            caja = (r.x0, r.y0, r.x1, r.y1)

        base = Path(self.documento.ruta)
        sugerido = str(base.with_name(f"{base.stem}_firmado.pdf"))
        destino, _ = QFileDialog.getSaveFileName(self, "Guardar documento firmado", sugerido, FILTRO_PDF)
        if not destino:
            self.set_herramienta(Herramienta.SELECCIONAR)
            return
        if not destino.lower().endswith(".pdf"):
            destino += ".pdf"

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            firmado = fd.firmar_pdf(
                datos, dlg.firmante,
                pagina=indice, caja=caja,
                imagen_png=dlg.rubrica_png if rect is not None else None,
                motivo=dlg.campo_motivo.text().strip(),
                lugar=dlg.campo_lugar.text().strip(),
                contacto=dlg.campo_contacto.text().strip(),
                url_sello_tiempo=dlg.url_tsa,
                certificar=dlg.chk_certificar.isChecked(),
            )
            tmp = destino + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(firmado)
            os.replace(tmp, destino)
        except fd.ErrorFirma as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Firma digital", str(exc))
            return
        except OSError as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Firma digital", f"No se pudo guardar el archivo:\n{exc}")
            return
        QApplication.restoreOverrideCursor()

        self.documento.reabrir(destino)
        self.vista.recargar()
        self._cargar_panel_lateral()
        self._añadir_reciente(destino)
        self._comprobar_firmas()
        self._actualizar_estado_ui()
        self.set_herramienta(Herramienta.SELECCIONAR)
        QMessageBox.information(self, "Documento firmado",
                                f"El documento se ha firmado correctamente y se ha guardado en:\n{destino}")

    def verificar_firmas(self) -> None:
        if self.documento is None or not self.documento.ruta:
            return
        datos = Path(self.documento.ruta).read_bytes()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            resultados = fd.verificar_firmas(datos)
        finally:
            QApplication.restoreOverrideCursor()
        DialogoVerificacion(resultados, self).exec()

    # ------------------------------------------------------------------
    # Compartir
    # ------------------------------------------------------------------
    def _archivo_para_compartir(self) -> str | None:
        """Devuelve la ruta del PDF guardado, pidiendo guardar si hay cambios pendientes."""
        if self.documento is None:
            return None
        if self.documento.modificado or not self.documento.ruta:
            caja = QMessageBox(self)
            caja.setIcon(QMessageBox.Question)
            caja.setWindowTitle("Compartir")
            caja.setText("El documento tiene cambios sin guardar.")
            caja.setInformativeText("Para compartirlo con los cambios hay que guardarlo antes.")
            b_guardar = caja.addButton("Guardar y compartir", QMessageBox.AcceptRole)
            b_sin = (caja.addButton("Compartir la versión guardada", QMessageBox.ActionRole)
                     if self.documento.ruta and os.path.exists(self.documento.ruta) else None)
            caja.addButton("Cancelar", QMessageBox.RejectRole)
            caja.setDefaultButton(b_guardar)
            caja.exec()
            pulsado = caja.clickedButton()
            if pulsado == b_guardar:
                if not self.guardar():
                    return None
            elif b_sin is None or pulsado != b_sin:
                return None
        return self.documento.ruta

    def _rellenar_menu_compartir(self) -> None:
        m = self.menu_compartir
        m.clear()
        hay = self.documento is not None
        for a in (self.a_correo, self.a_whatsapp):
            a.setEnabled(hay)
            m.addAction(a)
        ruta = self.documento.ruta if hay else None
        servicios = compartir.servicios_sistema(ruta) if ruta and os.path.exists(ruta) else []
        if servicios:
            m.addSeparator()
            for serv in servicios:
                icono = QIcon(serv.icono) if serv.icono else QIcon()
                m.addAction(icono, serv.titulo, lambda _=False, s=serv: self._compartir_servicio(s))
        m.addSeparator()
        for a in (self.a_copiar_archivo, self.a_finder):
            a.setEnabled(hay)
            m.addAction(a)

    def compartir_correo(self) -> None:
        ruta = self._archivo_para_compartir()
        if not ruta:
            return
        nombre = Path(ruta).name
        metodo = compartir.enviar_por_correo(
            ruta, Path(ruta).stem, f"Hola:\n\nTe adjunto el documento «{nombre}».\n\nUn saludo."
        )
        mensajes = {
            "Mail": "Mensaje nuevo en Mail con el PDF adjunto: añade el destinatario y envíalo",
            "Outlook": "Mensaje nuevo en Outlook con el PDF adjunto",
            "mailto": "Se ha abierto tu correo: adjunta el PDF desde la carpeta que se ha abierto",
        }
        self.aviso(mensajes.get(metodo, "Mensaje creado"), 6)

    def compartir_whatsapp(self) -> None:
        ruta = self._archivo_para_compartir()
        if not ruta:
            return
        dlg = DialogoWhatsApp(ruta, self)
        if dlg.exec() == QDialog.Accepted:
            if dlg.modo == "app":
                self.aviso("PDF copiado · en el chat de WhatsApp pulsa ⌘V y envía", 8)
            else:
                self.aviso("PDF copiado · pégalo (⌘V) o arrástralo al chat de WhatsApp Web", 8)

    def _compartir_servicio(self, servicio) -> None:
        ruta = self._archivo_para_compartir()
        if ruta:
            servicio.compartir(ruta)

    def copiar_archivo(self) -> None:
        ruta = self._archivo_para_compartir()
        if ruta:
            compartir.copiar_archivo(ruta)
            self.aviso("Archivo copiado: pégalo con ⌘V en un correo, chat o carpeta")

    def mostrar_en_finder(self) -> None:
        if self.documento and self.documento.ruta:
            compartir.mostrar_en_carpeta(self.documento.ruta)

    # ------------------------------------------------------------------
    # Documento y firmas guardadas
    # ------------------------------------------------------------------
    def cerrar_documento(self) -> None:
        if self.documento is None:
            self.close()
            return
        if not self._confirmar_descartar():
            return
        self.vista.set_documento(None)
        self.documento.cerrar()
        self.documento = None
        self.tenia_firmas = False
        self.banner.setVisible(False)
        self.miniaturas.clear()
        self.marcadores.clear()
        self.campo_buscar.clear()
        self.set_herramienta(Herramienta.SELECCIONAR)
        self._actualizar_estado_ui()
        self._mostrar_bienvenida()

    def gestionar_firmas(self) -> None:
        DialogoFirmas(self, seleccionar=False).exec()

    # ------------------------------------------------------------------
    # Imprimir y propiedades
    # ------------------------------------------------------------------
    def imprimir(self) -> None:
        if self.documento is None:
            return
        impresora = QPrinter(QPrinter.HighResolution)
        impresora.setDocName(self.documento.nombre)
        impresora.setFromTo(1, self.documento.num_paginas)
        dlg = QPrintDialog(impresora, self)
        dlg.setMinMax(1, self.documento.num_paginas)
        if dlg.exec() != QDialog.Accepted:
            return
        desde, hasta = impresora.fromPage(), impresora.toPage()
        if desde == 0:
            desde, hasta = 1, self.documento.num_paginas
        dpi = min(impresora.resolution(), 300)
        painter = QPainter()
        if not painter.begin(impresora):
            QMessageBox.critical(self, "Imprimir", "No se pudo iniciar la impresión.")
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for n in range(desde - 1, hasta):
                if n > desde - 1:
                    impresora.newPage()
                pm = self.documento.pagina(n).get_pixmap(dpi=dpi, alpha=False)
                img = QImage(pm.samples, pm.width, pm.height, pm.stride, QImage.Format_RGB888)
                area = painter.viewport()
                tam = img.size().scaled(area.size(), Qt.KeepAspectRatio)
                x = area.x() + (area.width() - tam.width()) // 2
                y = area.y() + (area.height() - tam.height()) // 2
                painter.drawImage(x, y, img.scaled(tam, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        finally:
            painter.end()
            QApplication.restoreOverrideCursor()

    def propiedades(self) -> None:
        if self.documento is None:
            return
        doc = self.documento.doc
        meta = doc.metadata or {}
        dlg = QDialog(self)
        dlg.setWindowTitle("Propiedades del documento")
        dlg.setMinimumWidth(480)
        form = QFormLayout(dlg)
        campos = {}
        for clave, etiqueta in (("title", "Título"), ("author", "Autor"), ("subject", "Asunto"), ("keywords", "Palabras clave")):
            campos[clave] = QLineEdit(meta.get(clave, "") or "")
            form.addRow(etiqueta + ":", campos[clave])
        tam = os.path.getsize(self.documento.ruta) if self.documento.ruta and os.path.exists(self.documento.ruta) else 0
        p0 = doc[0].rect
        info = [
            ("Archivo", self.documento.ruta or "—"),
            ("Páginas", str(doc.page_count)),
            ("Tamaño de página", f"{p0.width / 72 * 25.4:.0f} × {p0.height / 72 * 25.4:.0f} mm"),
            ("Tamaño del archivo", f"{tam / 1024:.0f} KB" if tam else "—"),
            ("Versión PDF", meta.get("format", "—")),
            ("Creado con", meta.get("creator", "") or "—"),
            ("Productor", meta.get("producer", "") or "—"),
            ("Cifrado", meta.get("encryption") or "No"),
        ]
        for k, v in info:
            l = QLabel(v)
            l.setTextInteractionFlags(Qt.TextSelectableByMouse)
            l.setWordWrap(True)
            form.addRow(k + ":", l)
        botones = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        botones.accepted.connect(dlg.accept)
        botones.rejected.connect(dlg.reject)
        form.addRow(botones)
        if dlg.exec() == QDialog.Accepted:
            nuevo = dict(meta)
            for clave, campo in campos.items():
                nuevo[clave] = campo.text()
            self.documento.instantanea()
            doc.set_metadata(nuevo)
            self._actualizar_estado_ui()

    def _acerca_de(self) -> None:
        caja = QMessageBox(self)
        caja.setWindowTitle(f"Acerca de {tema.NOMBRE_APP}")
        caja.setIconPixmap(tema.pixmap_logo(72))
        caja.setText(f"<h2 style='margin-bottom:0'>{tema.NOMBRE_APP}</h2><p>Versión {tema.VERSION}</p>")
        caja.setInformativeText(
            "Visor y editor de PDF con firma manuscrita y firma electrónica con certificado.<br><br>"
            "Su imagen se inspira en los arcos de herradura de la Mezquita de Córdoba.<br><br>"
            "<small>Construido con PySide6 (Qt), PyMuPDF y pyHanko.</small>"
        )
        caja.exec()


def _parsear_rango(texto: str, total: int) -> list[int]:
    paginas: list[int] = []
    for parte in texto.replace(" ", "").split(","):
        if not parte:
            continue
        if "-" in parte:
            a, b = parte.split("-", 1)
            a, b = int(a or 1), int(b or total)
            if a > b:
                a, b = b, a
            paginas.extend(range(a, b + 1))
        else:
            paginas.append(int(parte))
    if not paginas or any(p < 1 or p > total for p in paginas):
        raise ValueError
    return [p - 1 for p in paginas]
