"""Ajustes de Mezquita PDF: lo que el usuario elige una vez y vale para siempre.

En el Mac están en Mezquita PDF → Ajustes (⌘,); en Windows, en Edición → Ajustes (Ctrl+,).
Los cambios se aplican al momento, como en las demás apps del Mac.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QPushButton, QRadioButton, QVBoxLayout,
)

from . import marcas, sistema
from .plataforma import teclas

PESTANAS = "ventana/pestanas"   # True: con un PDF abierto, los demás se abren en pestañas de esa ventana
ZOOM = "ventana/zoom_inicial"   # "ancho", "pagina" o "real"
PANEL = "ventana/panel"         # panel de miniaturas visible
ACTUALIZAR = "actualizaciones/automatico"

ZOOMS = {
    "ancho": "Ajustar al ancho",
    "pagina": "Página completa",
    "real": "Tamaño real (100 %)",
}


def en_pestanas() -> bool:
    return QSettings().value(PESTANAS, True, type=bool)


def zoom_inicial() -> str:
    valor = QSettings().value(ZOOM, "ancho")
    return valor if valor in ZOOMS else "ancho"


def _nota(texto: str) -> QLabel:
    etiqueta = QLabel(texto)
    etiqueta.setObjectName("nota")  # en una línea: Qt recorta las de varias dentro de un QGroupBox
    return etiqueta


class DialogoAjustes(QDialog):
    """Opciones por defecto. Lo que afecta a las ventanas abiertas se avisa con señales."""
    panel_cambiado = Signal(bool)
    actualizar_cambiado = Signal(bool)
    predeterminada_pedida = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajustes")
        self.setMinimumWidth(520)
        self.ajustes = QSettings()
        capa = QVBoxLayout(self)
        capa.setSpacing(6)

        # --- Documentos ---------------------------------------------------------
        grupo = QGroupBox("Documentos")
        cg = QVBoxLayout(grupo)
        cg.setSpacing(6)
        cg.addWidget(QLabel("<b>Si ya tienes un PDF abierto, los que abras después se abren:</b>"))
        self.radio_pestanas = QRadioButton("En pestañas de la misma ventana")
        self.radio_ventanas = QRadioButton("Cada uno en su propia ventana")
        botones = QButtonGroup(self)
        for r in (self.radio_pestanas, self.radio_ventanas):
            botones.addButton(r)
            cg.addWidget(r)
        (self.radio_pestanas if en_pestanas() else self.radio_ventanas).setChecked(True)
        self.radio_pestanas.toggled.connect(lambda si: self.ajustes.setValue(PESTANAS, si))
        cg.addWidget(_nota(teclas("Siempre puedes abrir otra ventana con Archivo → Nueva ventana (⌘N).")))
        cg.addSpacing(6)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        self.combo_zoom = QComboBox()
        for clave, texto in ZOOMS.items():
            self.combo_zoom.addItem(texto, clave)
        self.combo_zoom.setCurrentIndex(self.combo_zoom.findData(zoom_inicial()))
        self.combo_zoom.currentIndexChanged.connect(
            lambda _i: self.ajustes.setValue(ZOOM, self.combo_zoom.currentData()))
        form.addRow("Zoom al abrir un documento:", self.combo_zoom)
        cg.addLayout(form)
        self.chk_panel = QCheckBox("Mostrar las miniaturas de las páginas")
        self.chk_panel.setChecked(self.ajustes.value(PANEL, True, type=bool))
        self.chk_panel.toggled.connect(self._panel)
        cg.addWidget(self.chk_panel)
        capa.addWidget(grupo)

        # --- Firma ----------------------------------------------------------------
        grupo = QGroupBox("Firma con certificado")
        cg = QVBoxLayout(grupo)
        form = QFormLayout()
        self.combo_marca = QComboBox()
        actual = marcas.elegida() or marcas.NINGUNA
        for valor in (marcas.MEZQUITA, *(str(r) for r in marcas.guardadas()), marcas.NINGUNA):
            self.combo_marca.addItem(marcas.nombre(valor or None), valor)
        self.combo_marca.setCurrentIndex(max(0, self.combo_marca.findData(actual)))
        self.combo_marca.currentIndexChanged.connect(lambda _i: marcas.elegir(self.combo_marca.currentData()))
        form.addRow("Marca de agua del sello:", self.combo_marca)
        cg.addLayout(form)
        cg.addWidget(_nota("Para añadir o quitar logotipos: menú Firmar → Marca de agua del sello."))
        capa.addWidget(grupo)

        # --- La app ---------------------------------------------------------------
        grupo = QGroupBox("La app")
        cg = QVBoxLayout(grupo)
        self.chk_actualizar = QCheckBox("Buscar actualizaciones automáticamente")
        self.chk_actualizar.setChecked(self.ajustes.value(ACTUALIZAR, True, type=bool))
        self.chk_actualizar.toggled.connect(self._actualizar)
        cg.addWidget(self.chk_actualizar)
        fila = QHBoxLayout()
        if sistema.ruta_app() is not None and sistema.es_predeterminada():
            fila.addWidget(QLabel("✓  Los PDF se abren con Mezquita PDF al hacer doble clic."))
        else:
            boton = QPushButton("Usar Mezquita PDF para abrir los PDF")
            boton.setAutoDefault(False)  # si no, Qt lo pone en negrita y el texto no cabe
            boton.setEnabled(sistema.ruta_app() is not None)
            if not boton.isEnabled():
                boton.setToolTip("Disponible en la app instalada")
            boton.clicked.connect(self.predeterminada_pedida)
            fila.addWidget(boton)
        fila.addStretch(1)
        cg.addLayout(fila)
        capa.addWidget(grupo)

        cerrar = QDialogButtonBox(QDialogButtonBox.Close)
        cerrar.button(QDialogButtonBox.Close).setText("Cerrar")
        cerrar.rejected.connect(self.reject)
        capa.addSpacing(4)
        capa.addWidget(cerrar)

    def _panel(self, si: bool) -> None:
        self.ajustes.setValue(PANEL, si)
        self.panel_cambiado.emit(si)

    def _actualizar(self, si: bool) -> None:
        self.ajustes.setValue(ACTUALIZAR, si)
        self.actualizar_cambiado.emit(si)
