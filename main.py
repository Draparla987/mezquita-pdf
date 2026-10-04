"""Mezquita PDF: visor y editor de PDF con firma electrónica."""

import sys

from PySide6.QtCore import QEvent, QSettings, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from visor import tema
from visor.ventana import _ventanas, abrir_en_ventana, al_cambiar_tema, nueva_ventana


class Aplicacion(QApplication):
    def event(self, ev):
        # macOS: abrir un PDF desde Finder ("Abrir con…") o arrastrándolo al Dock
        if ev.type() == QEvent.FileOpen:
            abrir_en_ventana(ev.file())
            return True
        return super().event(ev)


def migrar_ajustes() -> None:
    """Conserva recientes, certificado y preferencias de la versión «Visor PDF»."""
    nuevos = QSettings()
    if nuevos.value("migrado", False, type=bool):
        return
    antiguos = QSettings("VisorPDF", "Visor PDF")
    for clave in antiguos.allKeys():
        if not nuevos.contains(clave):
            nuevos.setValue(clave, antiguos.value(clave))
    nuevos.setValue("migrado", True)


def diagnostico() -> int:
    """Informe rápido (sin datos personales) para comprobar la instalación."""
    from visor import compartir, llavero
    print(f"{tema.NOMBRE_APP} {tema.VERSION}")
    certs = llavero.listar_certificados() if llavero.DISPONIBLE else []
    print(f"Llavero disponible: {llavero.DISPONIBLE} · certificados de firma: {len(certs)} "
          f"(vigentes: {sum(c.utilizable for c in certs)})")
    print(f"Correo predeterminado: {compartir.app_correo_predeterminada() or 'desconocido'}")
    print(f"WhatsApp instalado: {compartir.whatsapp_instalado()}")
    return 0


def main() -> int:
    if "--diagnostico" in sys.argv:
        return diagnostico()
    app = Aplicacion(sys.argv)
    app.setApplicationName(tema.NOMBRE_APP)
    app.setApplicationDisplayName(tema.NOMBRE_APP)
    app.setOrganizationName("MezquitaPDF")
    app.setOrganizationDomain("mezquitapdf.local")
    app.setApplicationVersion(tema.VERSION)
    app.setWindowIcon(QIcon(QPixmap.fromImage(tema.imagen_icono_app(512))))
    migrar_ajustes()
    tema.aplicar_tema(app)

    def cambio_de_tema(*_):
        tema.aplicar_tema(app)
        al_cambiar_tema()

    try:
        app.styleHints().colorSchemeChanged.connect(cambio_de_tema)
    except AttributeError:
        pass

    archivos = [a for a in sys.argv[1:] if a.lower().endswith(".pdf")]
    if archivos:
        for ruta in archivos:
            abrir_en_ventana(ruta)
    else:
        # Si macOS nos pasa un fichero por FileOpen, llegará enseguida
        QTimer.singleShot(300, lambda: nueva_ventana() if not _ventanas else None)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
