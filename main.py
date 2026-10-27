"""Mezquita PDF: visor y editor de PDF con firma electrónica."""

import sys

if __name__ == "__main__" and "--mcp" in sys.argv:
    # Extensión para la app de Claude: sin ventanas ni Qt (ver visor/mcp_servidor.py)
    from visor.mcp_servidor import main as servidor_mcp
    sys.exit(servidor_mcp())

if __name__ == "__main__" and any(a.startswith("chrome-extension://") for a in sys.argv[1:]):
    # Extensión de Chrome: Chrome arranca la app para pasarle un PDF, sin ventanas ni Qt
    # (ver visor/chrome.py)
    from visor.chrome import main as anfitrion_chrome
    sys.exit(anfitrion_chrome())

if __name__ == "__main__" and "--registrar-chrome" in sys.argv:
    from visor import chrome
    print("Extensión de Chrome registrada en: " + (", ".join(chrome.registrar()) or "ningún navegador"))
    sys.exit(0)

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


def traduccion_qt():  # → QTranslator o None
    """Textos propios de Qt y del Mac en español: menú de la app («Ocultar», «Salir»…) y botones
    estándar («Guardar», «No guardar», «Cancelar»…). La app entera está en español."""
    from pathlib import Path

    import PySide6
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    traductor = QTranslator()
    base = Path(PySide6.__file__).resolve().parent
    for carpeta in (QLibraryInfo.path(QLibraryInfo.TranslationsPath),
                    str(base / "Qt" / "translations"), str(base / "translations")):  # macOS / Windows
        if traductor.load(QLocale(QLocale.Spanish, QLocale.Spain), "qtbase", "_", carpeta):
            return traductor
    return None


def diagnostico() -> int:
    """Informe rápido (sin datos personales) para comprobar la instalación."""
    from visor import compartir, llavero
    print(f"{tema.NOMBRE_APP} {tema.VERSION}")
    certs = llavero.listar_certificados() if llavero.DISPONIBLE else []
    almacen = "Llavero" if sys.platform == "darwin" else "Almacén de certificados"
    print(f"{almacen} disponible: {llavero.DISPONIBLE} · certificados de firma: {len(certs)} "
          f"(vigentes: {sum(c.utilizable for c in certs)})")
    print(f"Correo predeterminado: {compartir.app_correo_predeterminada() or 'desconocido'}")
    print(f"WhatsApp instalado: {compartir.whatsapp_instalado()}")
    print(f"Textos del sistema en español: {'sí' if traduccion_qt() else 'no'}")
    from visor import sistema
    print(f"Los PDF se abren ahora con: {sistema.app_predeterminada_pdf() or 'desconocido'}"
          f" · Mezquita PDF es la predeterminada: {sistema.es_predeterminada()}")
    from visor import actualizaciones
    try:
        v = actualizaciones.consultar()
        print(f"Última versión publicada: {v.numero} ({'hay una más nueva' if actualizaciones.es_mas_nueva(v.numero) else 'al día'})"
              f" · instalador para este Mac: {'sí' if v.url else 'no'}")
    except Exception as exc:
        print(f"No se ha podido consultar la última versión: {exc}")
    return 0


def _traer_delante(rutas: list[str]) -> None:
    """Otra copia de la app (Windows) nos pasa PDF para abrir; si no hay, se muestra una ventana."""
    for ruta in rutas:
        abrir_en_ventana(ruta)
    ventana = _ventanas[-1] if _ventanas else nueva_ventana()
    if ventana.isMinimized():
        ventana.showNormal()
    ventana.raise_()
    ventana.activateWindow()


def main() -> int:
    if "--diagnostico" in sys.argv:
        return diagnostico()
    if sys.platform == "win32":  # en la barra de tareas, «Mezquita PDF» con su icono (no Python)
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MezquitaPDF.App")
        except Exception:
            pass
    app = Aplicacion(sys.argv)
    app.setApplicationName(tema.NOMBRE_APP)
    app.setApplicationDisplayName(tema.NOMBRE_APP)
    app.setOrganizationName("MezquitaPDF")
    app.setOrganizationDomain("mezquitapdf.local")
    app.setApplicationVersion(tema.VERSION)
    archivos = [a for a in sys.argv[1:] if a.lower().endswith(".pdf")]
    if sys.platform == "win32":
        from visor import instancia
        if instancia.enviar_a_la_abierta(archivos):
            return 0  # ya estaba abierta: le hemos pasado los PDF
        app._instancia = instancia.Instancia(app, _traer_delante)
    traductor = traduccion_qt()
    if traductor is not None:
        app.installTranslator(traductor)
        app._traductor = traductor  # que no lo libere el recolector
    app.setWindowIcon(QIcon(QPixmap.fromImage(tema.imagen_icono_app(512))))
    migrar_ajustes()
    try:
        from visor import chrome
        chrome.registrar()  # para que la extensión de Chrome «Firmar con Mezquita PDF» encuentre la app
    except Exception:
        pass
    tema.aplicar_tema(app)
    from visor import puente_claude
    puente_claude.iniciar(app)  # para que Claude pueda trabajar con los documentos abiertos
    from visor import actualizaciones
    actualizaciones.iniciar(app)  # avisa si hay una versión nueva publicada (una vez al día)

    def cambio_de_tema(*_):
        tema.aplicar_tema(app)
        al_cambiar_tema()

    try:
        app.styleHints().colorSchemeChanged.connect(cambio_de_tema)
    except AttributeError:
        pass

    if archivos:
        for ruta in archivos:
            abrir_en_ventana(ruta)
    else:
        # Si macOS nos pasa un fichero por FileOpen, llegará enseguida
        QTimer.singleShot(300, lambda: nueva_ventana() if not _ventanas else None)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
