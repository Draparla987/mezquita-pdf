"""Aspecto visual de Mezquita PDF: paleta, hoja de estilos, iconos y logotipo.

La identidad se inspira en los arcos de herradura de la Mezquita de Córdoba:
dovelas alternas rojo ladrillo y crema, sobre un granate profundo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPalette, QPen, QPixmap,
)
from PySide6.QtWidgets import QAbstractButton, QApplication, QWidget

NOMBRE_APP = "Mezquita PDF"
VERSION = "2.2.0"


@dataclass(frozen=True)
class Paleta:
    oscuro: bool
    acento: str
    acento_hover: str
    acento_pulsado: str
    acento_suave: str
    fondo: str
    panel: str
    superficie: str
    borde: str
    borde_fuerte: str
    texto: str
    texto_suave: str
    lienzo: str
    exito: str
    exito_suave: str
    error: str
    error_suave: str
    crema: str
    ladrillo: str


CLARO = Paleta(
    oscuro=False,
    acento="#8E1B2C", acento_hover="#A3263A", acento_pulsado="#741524", acento_suave="#F6E6E8",
    fondo="#FBF8F4", panel="#F5F0E9", superficie="#FFFFFF", borde="#E8E0D5", borde_fuerte="#D8CDBE",
    texto="#2B2321", texto_suave="#7D7068", lienzo="#EAE4DB",
    exito="#1E7B4F", exito_suave="#E4F3EA", error="#B3261E", error_suave="#FBE8E6",
    crema="#F4E7CF", ladrillo="#C0402E",
)

OSCURO = Paleta(
    oscuro=True,
    acento="#C9475C", acento_hover="#D65E71", acento_pulsado="#B03A4E", acento_suave="#3B2429",
    fondo="#1D1A19", panel="#23201E", superficie="#2B2725", borde="#3A3431", borde_fuerte="#4B433F",
    texto="#F1EBE5", texto_suave="#A99D94", lienzo="#151312",
    exito="#5CC08D", exito_suave="#1D3328", error="#F2867D", error_suave="#3D2422",
    crema="#E9D9B8", ladrillo="#D0533D",
)

COLOR_WHATSAPP = "#25D366"

_paleta: Paleta = CLARO


def paleta() -> Paleta:
    return _paleta


def sistema_oscuro() -> bool:
    try:
        return QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        return QApplication.palette().color(QPalette.Window).lightness() < 128


def aplicar_tema(app: QApplication, oscuro: bool | None = None) -> Paleta:
    global _paleta
    _paleta = OSCURO if (sistema_oscuro() if oscuro is None else oscuro) else CLARO
    p = _paleta
    app.setStyle("Fusion")
    pal = QPalette()
    roles = {
        QPalette.Window: p.fondo, QPalette.WindowText: p.texto, QPalette.Base: p.superficie,
        QPalette.AlternateBase: p.panel, QPalette.Text: p.texto, QPalette.Button: p.superficie,
        QPalette.ButtonText: p.texto, QPalette.Highlight: p.acento, QPalette.HighlightedText: "#FFFFFF",
        QPalette.ToolTipBase: p.texto, QPalette.ToolTipText: p.superficie,
        QPalette.PlaceholderText: p.texto_suave, QPalette.Link: p.acento, QPalette.Mid: p.borde_fuerte,
        QPalette.Midlight: p.borde, QPalette.Light: p.superficie, QPalette.Dark: p.borde_fuerte,
    }
    for rol, color in roles.items():
        pal.setColor(rol, QColor(color))
    for rol in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, rol, QColor(p.texto_suave))
    app.setPalette(pal)
    app.setStyleSheet(hoja_estilos(p))
    return p


def _rgba(color: str, alfa: float) -> str:
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alfa})"


def hoja_estilos(p: Paleta) -> str:
    return f"""
    QWidget {{ font-size: 13px; }}
    QMainWindow, QDialog {{ background: {p.fondo}; color: {p.texto}; }}
    QToolTip {{ background: {p.texto}; color: {p.superficie}; border: none; padding: 5px 9px;
                border-radius: 6px; }}

    /* ---------- Barra superior ---------- */
    QWidget#barraSuperior {{ background: {p.superficie}; border-bottom: 1px solid {p.borde}; }}
    QLabel#nombreApp {{ font-size: 15px; font-weight: 700; color: {p.texto}; }}
    QLabel#nombreDoc {{ color: {p.texto_suave}; }}
    QFrame#separador {{ background: {p.borde}; }}

    QToolButton {{ border: none; border-radius: 8px; padding: 6px; color: {p.texto};
                   background: transparent; }}
    QToolButton:hover {{ background: {_rgba(p.texto, 0.07)}; }}
    QToolButton:pressed {{ background: {_rgba(p.texto, 0.12)}; }}
    QToolButton:checked {{ background: {p.acento_suave}; color: {p.acento}; }}
    QToolButton:disabled {{ color: {_rgba(p.texto_suave, 0.6)}; }}
    QToolButton::menu-indicator {{ image: none; width: 0; }}

    QToolButton#botonPrimario {{ background: {p.acento}; color: #FFFFFF; font-weight: 600;
                                 padding: 7px 14px; }}
    QToolButton#botonPrimario:hover {{ background: {p.acento_hover}; }}
    QToolButton#botonPrimario:pressed {{ background: {p.acento_pulsado}; }}
    QToolButton#botonPrimario:disabled {{ background: {p.borde_fuerte}; color: {p.superficie}; }}
    QToolButton#botonSecundario {{ border: 1px solid {p.borde_fuerte}; font-weight: 600;
                                   padding: 6px 13px; background: {p.superficie}; }}
    QToolButton#botonSecundario:hover {{ border-color: {p.acento}; color: {p.acento}; }}
    QToolButton#botonSecundario:disabled {{ color: {p.texto_suave}; }}

    QLineEdit#busqueda {{ border-radius: 16px; padding: 6px 10px; background: {p.panel};
                          border: 1px solid {p.borde}; min-width: 200px; }}
    QLineEdit#busqueda:focus {{ background: {p.superficie}; border-color: {p.acento}; }}
    QLabel#contadorBusqueda {{ color: {p.texto_suave}; }}

    /* ---------- Barra de herramientas lateral ---------- */
    QWidget#rail, QScrollArea#railScroll {{ background: {p.panel}; border: none; }}
    QScrollArea#railScroll {{ border-right: 1px solid {p.borde}; }}
    QToolButton#botonRail {{ font-size: 11px; padding: 4px 0px 3px 0px; border-radius: 10px;
                             color: {p.texto_suave}; }}
    QToolButton#botonRail:hover {{ color: {p.texto}; background: {_rgba(p.texto, 0.06)}; }}
    QToolButton#botonRail:checked {{ color: {p.acento}; background: {p.acento_suave}; }}
    QFrame#lineaRail {{ background: {p.borde}; }}

    /* ---------- Panel lateral ---------- */
    QWidget#panelLateral {{ background: {p.panel}; border-right: 1px solid {p.borde}; }}
    QToolButton#segmento {{ padding: 5px 2px; border-radius: 7px; color: {p.texto_suave}; font-weight: 600;
                            font-size: 12px; }}
    QToolButton#segmento:checked {{ background: {p.superficie}; color: {p.texto};
                                    border: 1px solid {p.borde}; }}
    QWidget#segmentos {{ background: {_rgba(p.texto, 0.06)}; border-radius: 9px; }}
    QListWidget#miniaturas {{ background: transparent; border: none; outline: none; }}
    QListWidget#miniaturas::item {{ border: 2px solid transparent; border-radius: 8px; padding: 6px 4px 2px 4px;
                                    color: {p.texto_suave}; }}
    QListWidget#miniaturas::item:hover {{ background: {_rgba(p.texto, 0.05)}; }}
    QListWidget#miniaturas::item:selected {{ border-color: {p.acento}; background: {p.acento_suave};
                                             color: {p.acento}; }}
    QTreeWidget#marcadores {{ background: transparent; border: none; outline: none; }}
    QTreeWidget#marcadores::item {{ padding: 5px 2px; border-radius: 6px; }}
    QTreeWidget#marcadores::item:selected, QTreeWidget#marcadores::item:hover {{
        background: {p.acento_suave}; color: {p.acento}; }}
    QLabel#vacio {{ color: {p.texto_suave}; padding: 20px; }}

    /* ---------- Elementos flotantes ---------- */
    QFrame#pildora {{ background: {p.superficie}; border: 1px solid {p.borde}; border-radius: 19px; }}
    QFrame#pildora QLabel {{ color: {p.texto_suave}; }}
    QFrame#pildora QSpinBox {{ border: none; background: transparent; padding: 2px; font-weight: 600; }}
    QFrame#pildora QComboBox {{ border: none; background: transparent; font-weight: 600; padding: 2px 6px; }}
    QLabel#toast {{ background: {_rgba('#1E1A19', 0.93)}; color: #FFFFFF; border-radius: 17px;
                    padding: 9px 18px; font-weight: 500; }}
    QFrame#banner {{ border-radius: 10px; }}
    QFrame#banner QLabel {{ background: transparent; }}

    /* ---------- Bienvenida ---------- */
    QLabel#tituloBienvenida {{ font-size: 32px; font-weight: 800; color: {p.texto}; }}
    QLabel#subtituloBienvenida {{ font-size: 15px; color: {p.texto_suave}; }}
    QLabel#seccion {{ font-size: 12px; font-weight: 700; color: {p.texto_suave}; letter-spacing: 1px; }}
    QFrame#filaReciente {{ border: 1px solid transparent; border-radius: 12px; background: transparent; }}
    QFrame#filaReciente:hover {{ background: {p.superficie}; border-color: {p.borde}; }}

    /* ---------- Controles generales ---------- */
    QPushButton {{ background: {p.superficie}; border: 1px solid {p.borde_fuerte}; border-radius: 8px;
                   padding: 6px 14px; color: {p.texto}; min-height: 18px; }}
    QPushButton:hover {{ border-color: {p.acento}; }}
    QPushButton:pressed {{ background: {p.panel}; }}
    QPushButton:default, QPushButton#primario {{ background: {p.acento}; color: #FFFFFF; border: none;
                                                 font-weight: 600; }}
    QPushButton:default:hover, QPushButton#primario:hover {{ background: {p.acento_hover}; }}
    QPushButton:default:disabled, QPushButton#primario:disabled {{ background: {p.borde_fuerte}; }}
    QPushButton#botonWhatsApp {{ background: {COLOR_WHATSAPP}; color: #FFFFFF; border: none; font-weight: 600; }}
    QPushButton#botonWhatsApp:hover {{ background: #1EBE5A; }}
    QPushButton:disabled {{ color: {p.texto_suave}; }}

    QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {p.superficie}; border: 1px solid {p.borde_fuerte}; border-radius: 8px;
        padding: 5px 8px; selection-background-color: {p.acento}; selection-color: #FFFFFF; }}
    QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border-color: {p.acento}; }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox QAbstractItemView {{ background: {p.superficie}; border: 1px solid {p.borde};
                                   selection-background-color: {p.acento_suave}; selection-color: {p.acento}; }}

    QMenu {{ background: {p.superficie}; border: 1px solid {p.borde}; border-radius: 10px; padding: 6px; }}
    QMenu::item {{ padding: 7px 26px 7px 10px; border-radius: 6px; color: {p.texto}; }}
    QMenu::item:selected {{ background: {p.acento_suave}; color: {p.acento}; }}
    QMenu::item:disabled {{ color: {p.texto_suave}; }}
    QMenu::separator {{ height: 1px; background: {p.borde}; margin: 5px 8px; }}
    QMenu::icon {{ padding-left: 8px; }}

    QGroupBox {{ border: 1px solid {p.borde}; border-radius: 10px; margin-top: 16px;
                 padding: 14px 10px 10px 10px; background: {p.superficie}; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {p.texto_suave};
                        font-weight: 700; }}
    QTabWidget::pane {{ border: 1px solid {p.borde}; border-radius: 10px; background: {p.superficie}; top: -1px; }}
    QTabBar::tab {{ padding: 8px 16px; border: none; color: {p.texto_suave}; background: transparent;
                    font-weight: 600; }}
    QTabBar::tab:selected {{ color: {p.acento}; border-bottom: 2px solid {p.acento}; }}
    QListWidget, QTreeWidget {{ background: {p.superficie}; border: 1px solid {p.borde}; border-radius: 10px; }}
    QListWidget::item {{ border-radius: 8px; margin: 1px 3px; }}
    QListWidget::item:selected {{ background: {p.acento_suave}; border: 1px solid {p.acento}; }}
    QListWidget::item:hover:!selected {{ background: {_rgba(p.texto, 0.04)}; }}

    QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {_rgba(p.texto, 0.22)}; border-radius: 4px; min-height: 36px; }}
    QScrollBar::handle:vertical:hover {{ background: {_rgba(p.texto, 0.38)}; }}
    QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {_rgba(p.texto, 0.22)}; border-radius: 4px; min-width: 36px; }}
    QScrollBar::handle:horizontal:hover {{ background: {_rgba(p.texto, 0.38)}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
    QSlider::groove:horizontal {{ height: 4px; background: {p.borde_fuerte}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {p.acento}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {p.superficie}; border: 2px solid {p.acento}; width: 12px;
                                  height: 12px; margin: -6px 0; border-radius: 8px; }}
    """


# ----------------------------------------------------------------------------
# Iconos (Material Design Icons vía QtAwesome)
# ----------------------------------------------------------------------------
def icono(nombre: str, color: str | None = None, color_activo: str | None = None) -> QIcon:
    p = _paleta
    try:
        import qtawesome as qta
        return qta.icon(
            f"mdi6.{nombre}",
            color=color or p.texto,
            color_active=color or p.texto,
            color_on=color_activo or p.acento,
            color_on_active=color_activo or p.acento,
            color_disabled=_rgba_hex(p.texto_suave, 0.5),
        )
    except Exception:
        return QIcon()


def _rgba_hex(color: str, alfa: float) -> QColor:
    c = QColor(color)
    c.setAlphaF(alfa)
    return c


def poner_icono(objeto, nombre: str, color: str | None = None, color_activo: str | None = None) -> None:
    """Asigna un icono y recuerda su nombre para poder recolorearlo al cambiar de tema."""
    objeto.setProperty("icono", nombre)
    objeto.setProperty("icono_color", color or "")
    objeto.setProperty("icono_color_activo", color_activo or "")
    objeto.setIcon(icono(nombre, color, color_activo))


def refrescar_iconos(raiz: QWidget) -> None:
    from PySide6.QtGui import QAction
    for obj in raiz.findChildren(QAction) + raiz.findChildren(QAbstractButton):
        nombre = obj.property("icono")
        if nombre:
            obj.setIcon(icono(nombre, obj.property("icono_color") or None,
                              obj.property("icono_color_activo") or None))


# ----------------------------------------------------------------------------
# Logotipo: arco de herradura con dovelas alternas
# ----------------------------------------------------------------------------
def dibujar_arco(p: QPainter, r: QRectF, color_a: QColor, color_b: QColor,
                 hueco: QColor | None = None, dovelas: int = 11, columnas: bool = True,
                 color_columna: QColor | None = None) -> QRectF:
    """Dibuja un arco de herradura dentro de `r`. Devuelve el rectángulo del vano."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    w, h = r.width(), r.height()
    cx = r.center().x()
    radio_ext = min(w * 0.46, h * 0.40)
    radio_int = radio_ext * 0.66
    cy = r.top() + radio_ext + h * 0.03
    extra = 28  # grados que el arco baja por debajo del semicírculo (herradura)
    inicio, total = -extra, 180 + 2 * extra
    paso = total / dovelas
    for i in range(dovelas):
        a0 = inicio + i * paso
        camino = QPainterPath()
        ext = QRectF(cx - radio_ext, cy - radio_ext, 2 * radio_ext, 2 * radio_ext)
        intr = QRectF(cx - radio_int, cy - radio_int, 2 * radio_int, 2 * radio_int)
        camino.arcMoveTo(ext, a0)
        camino.arcTo(ext, a0, paso)
        camino.arcTo(intr, a0 + paso, -paso)
        camino.closeSubpath()
        p.fillPath(camino, color_a if i % 2 == 0 else color_b)
        if hueco is not None:
            p.setPen(QPen(hueco, max(0.6, radio_ext * 0.025)))
            p.drawPath(camino)
    vano = QRectF()
    if columnas:
        ang = math.radians(extra)
        y_arranque = cy + radio_int * math.sin(ang)
        grosor = (radio_ext - radio_int) * 0.55
        for signo in (-1, 1):
            x = cx + signo * (radio_ext + radio_int) / 2 * math.cos(ang)
            fuste = QRectF(x - grosor / 2, y_arranque, grosor, r.bottom() - y_arranque - grosor * 0.5)
            capitel = QRectF(x - grosor * 0.9, y_arranque - grosor * 0.15, grosor * 1.8, grosor * 0.55)
            basa = QRectF(x - grosor * 0.8, r.bottom() - grosor * 0.6, grosor * 1.6, grosor * 0.6)
            for parte in (fuste, capitel, basa):
                p.fillRect(parte, color_columna or color_b)
        x0 = cx - radio_int * math.cos(ang)
        vano = QRectF(x0 + grosor * 0.4, cy - radio_int * 0.55, 2 * (cx - x0) - grosor * 0.8,
                      r.bottom() - (cy - radio_int * 0.55))
    p.restore()
    return vano


def imagen_icono_app(tam: int = 1024, sin_margen: bool = False) -> QImage:
    """Icono de la aplicación: arco de la Mezquita con un documento firmado en el vano.

    `sin_margen` genera la versión cuadrada a sangre que pide iOS (el sistema redondea las esquinas).
    """
    img = QImage(tam, tam, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s = tam / 1024
    if sin_margen:
        p.scale(1024 / 824, 1024 / 824)
        p.translate(-100 * s, -100 * s)
    fondo = QPainterPath()
    if sin_margen:
        fondo.addRect(QRectF(90 * s, 90 * s, 844 * s, 844 * s))
    else:
        fondo.addRoundedRect(QRectF(100 * s, 100 * s, 824 * s, 824 * s), 185 * s, 185 * s)
    g = QLinearGradient(0, 100 * s, 0, 924 * s)
    g.setColorAt(0, QColor("#A3263A"))
    g.setColorAt(1, QColor("#5E0F1C"))
    p.fillPath(fondo, g)
    zona = QRectF(205 * s, 190 * s, 614 * s, 640 * s)
    crema, ladrillo = QColor("#F6EAD2"), QColor("#D9533F")
    vano = dibujar_arco(p, zona, ladrillo, crema, hueco=QColor("#7A1424"), dovelas=13)
    # Documento dentro del vano
    hoja = QRectF(vano.center().x() - 120 * s, vano.top() + 60 * s, 240 * s, 300 * s)
    camino = QPainterPath()
    camino.addRoundedRect(hoja, 16 * s, 16 * s)
    p.fillPath(camino, QColor("#FFFFFF"))
    p.setPen(QPen(QColor("#D8CDBE"), 9 * s, Qt.SolidLine, Qt.RoundCap))
    for i in range(3):
        y = hoja.top() + (55 + i * 38) * s
        p.drawLine(QPointF(hoja.left() + 36 * s, y), QPointF(hoja.right() - (36 + i * 30) * s, y))
    p.setPen(QPen(QColor("#1F2A7A"), 13 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    firma = QPainterPath(QPointF(hoja.left() + 40 * s, hoja.bottom() - 62 * s))
    firma.cubicTo(QPointF(hoja.left() + 80 * s, hoja.bottom() - 130 * s),
                  QPointF(hoja.left() + 100 * s, hoja.bottom() - 20 * s),
                  QPointF(hoja.left() + 135 * s, hoja.bottom() - 75 * s))
    firma.cubicTo(QPointF(hoja.left() + 160 * s, hoja.bottom() - 115 * s),
                  QPointF(hoja.left() + 175 * s, hoja.bottom() - 40 * s),
                  QPointF(hoja.right() - 35 * s, hoja.bottom() - 85 * s))
    p.setBrush(Qt.NoBrush)
    p.drawPath(firma)
    p.end()
    return img


def pixmap_logo(tam: int, dpr: float = 2.0) -> QPixmap:
    img = imagen_icono_app(int(tam * dpr * 1.25))
    # El icono tiene margen transparente (estándar de macOS); lo recortamos para el logo.
    m = int(img.width() * 0.09)
    img = img.copy(m, m, img.width() - 2 * m, img.height() - 2 * m)
    pix = QPixmap.fromImage(img.scaled(int(tam * dpr), int(tam * dpr), Qt.KeepAspectRatio,
                                       Qt.SmoothTransformation))
    pix.setDevicePixelRatio(dpr)
    return pix


def dibujar_arqueria(p: QPainter, r: QRectF, n: int, pal: Paleta, opacidad: float = 1.0) -> None:
    """Friso decorativo con una arquería (para la pantalla de bienvenida)."""
    p.save()
    p.setOpacity(opacidad)
    ancho = r.width() / n
    for i in range(n):
        celda = QRectF(r.left() + i * ancho, r.top(), ancho, r.height())
        piedra = QColor(pal.crema).darker(118 if not pal.oscuro else 140)
        dibujar_arco(p, celda.adjusted(ancho * 0.02, 0, -ancho * 0.02, 0),
                     QColor(pal.ladrillo), QColor(pal.crema).darker(104), dovelas=13,
                     color_columna=piedra)
    p.restore()
