"""Actualizaciones: avisa cuando hay una versión nueva publicada en GitHub y la instala.

- Comprueba como mucho una vez al día (o al pedirlo en Ayuda). Solo consulta la última
  versión publicada: no se envía ningún dato del usuario ni de sus documentos.
- Nada se instala sin que el usuario pulse «Actualizar». Se descarga el instalador de su
  Mac, se comprueba (tamaño, huella SHA-256, identificador y firma de la app) y la app se
  sustituye cuando Mezquita PDF se cierra; después se abre la versión nueva.
- Si no se puede sustituir en su sitio (sin permiso de escritura, o la app se ejecuta desde
  el propio .dmg), se abre el instalador para arrastrarla a Aplicaciones.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import plistlib
import shlex
import shutil
import ssl
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressDialog,
    QPushButton, QTextBrowser, QVBoxLayout,
)

from . import tema
from .version import VERSION

REPO = "Draparla987/mezquita-pdf"
URL_ULTIMA = f"https://api.github.com/repos/{REPO}/releases/latest"
ID_APP = "local.mezquitapdf.app"
CADA = 24 * 3600            # s entre comprobaciones automáticas
ESPERA_INICIO = 6000        # ms tras abrir la app
CARPETA = Path.home() / "Library" / "Caches" / "MezquitaPDF" / "actualizacion"


@dataclass
class Version:
    numero: str          # «2.6.0»
    notas: str           # novedades (Markdown)
    pagina: str          # página de la publicación
    url: str | None      # instalador de este Mac
    tam: int = 0
    sha256: str | None = None


def tupla(numero: str) -> tuple[int, ...]:
    partes = []
    for p in numero.strip().lstrip("vV").split("."):
        digitos = "".join(c for c in p if c.isdigit())
        partes.append(int(digitos or 0))
    return tuple(partes + [0] * (3 - len(partes)))


def es_mas_nueva(numero: str, actual: str = VERSION) -> bool:
    return tupla(numero) > tupla(actual)


def arquitectura() -> str:
    """«apple-silicon» o «intel» (un Mac con chip de Apple bajo Rosetta pasa a la versión nativa)."""
    if platform.machine() == "arm64":
        return "apple-silicon"
    try:
        traducido = subprocess.run(["/usr/sbin/sysctl", "-n", "sysctl.proc_translated"],
                                   capture_output=True, text=True, timeout=5).stdout.strip() == "1"
    except Exception:
        traducido = False
    return "apple-silicon" if traducido else "intel"


def _contexto_ssl() -> ssl.SSLContext:
    """Certificados de certifi (van dentro de la app): la ruta por defecto de OpenSSL depende
    del Python con el que se compiló la app y en otros Mac puede no existir."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _pedir(url: str, timeout: float = 15):
    peticion = urllib.request.Request(url, headers={
        "User-Agent": f"MezquitaPDF/{VERSION}", "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(peticion, timeout=timeout, context=_contexto_ssl())


def interpretar(datos: dict, arq: str) -> Version:
    """Datos de la API de GitHub → Version (con el instalador de esta arquitectura)."""
    nombre = f"MezquitaPDF-{arq}.dmg"
    activo = next((a for a in datos.get("assets") or [] if a.get("name") == nombre), None)
    notas = datos.get("body") or ""
    if "## Novedades" in notas:  # sin las instrucciones de instalación del principio
        notas = notas[notas.index("## Novedades"):]
    sha = None
    if activo and str(activo.get("digest") or "").startswith("sha256:"):
        sha = activo["digest"].split(":", 1)[1].lower()
    return Version(numero=str(datos.get("tag_name", "")).lstrip("vV"), notas=notas.strip(),
                   pagina=datos.get("html_url") or f"https://github.com/{REPO}/releases/latest",
                   url=activo.get("browser_download_url") if activo else None,
                   tam=int(activo.get("size") or 0) if activo else 0, sha256=sha)


def consultar() -> Version:
    with _pedir(URL_ULTIMA) as r:
        return interpretar(json.load(r), arquitectura())


# ----------------------------------------------------------------------------
# Descargar, comprobar y preparar la app nueva
# ----------------------------------------------------------------------------
class Cancelado(Exception):
    pass


def descargar(v: Version, destino: Path, progreso=None, cancelar: threading.Event | None = None) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    dmg = destino / f"MezquitaPDF-{v.numero}.dmg"
    huella = hashlib.sha256()
    hecho = 0
    with _pedir(v.url, timeout=60) as r, open(dmg, "wb") as f:
        total = int(r.headers.get("Content-Length") or v.tam or 0)
        while True:
            if cancelar is not None and cancelar.is_set():
                raise Cancelado
            trozo = r.read(1 << 18)
            if not trozo:
                break
            f.write(trozo)
            huella.update(trozo)
            hecho += len(trozo)
            if progreso:
                progreso(hecho, total)
    if v.tam and hecho != v.tam:
        raise ValueError(f"la descarga está incompleta ({hecho} de {v.tam} bytes)")
    if v.sha256 and huella.hexdigest() != v.sha256:
        raise ValueError("la huella del instalador no coincide con la publicada")
    return dmg


def preparar_app(dmg: Path, numero: str, destino: Path) -> Path:
    """Monta el .dmg, comprueba la app y la copia a `destino`. Devuelve la ruta de la copia."""
    salida = subprocess.run(["/usr/bin/hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen",
                             "-plist", str(dmg)], capture_output=True, check=True, timeout=120).stdout
    montaje = next(e["mount-point"] for e in plistlib.loads(salida)["system-entities"] if e.get("mount-point"))
    try:
        app = Path(montaje) / "Mezquita PDF.app"
        info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
        if info.get("CFBundleIdentifier") != ID_APP:
            raise ValueError("el instalador no contiene Mezquita PDF")
        if tupla(info.get("CFBundleShortVersionString", "0")) != tupla(numero):
            raise ValueError("la versión del instalador no es la anunciada")
        subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)],
                       check=True, capture_output=True, timeout=120)
        nueva = destino / "nueva" / "Mezquita PDF.app"
        if nueva.parent.exists():
            shutil.rmtree(nueva.parent)
        nueva.parent.mkdir(parents=True)
        subprocess.run(["/usr/bin/ditto", str(app), str(nueva)], check=True, capture_output=True, timeout=300)
        return nueva
    finally:
        subprocess.run(["/usr/bin/hdiutil", "detach", montaje, "-quiet", "-force"], capture_output=True, timeout=60)


def guion_sustitucion(pid: int, app: Path, nueva: Path, anterior: Path, abrir: bool) -> str:
    """Guion que espera a que se cierre la app, la sustituye por la nueva y (si se pide) la abre."""
    q = shlex.quote
    return f"""#!/bin/bash
# Generado por Mezquita PDF: instala la actualización cuando la app se ha cerrado.
for i in $(seq 1 600); do kill -0 {pid} 2>/dev/null || break; sleep 0.2; done
rm -rf {q(str(anterior))}
if mv {q(str(app))} {q(str(anterior))}; then
  if ! mv {q(str(nueva))} {q(str(app))}; then mv {q(str(anterior))} {q(str(app))}; fi
fi
{"/usr/bin/open " + q(str(app)) if abrir else ":"}
"""


def se_puede_sustituir(app: Path | None) -> bool:
    if app is None:
        return False
    ruta = str(app)
    if "/AppTranslocation/" in ruta or ruta.startswith("/Volumes/"):
        return False
    return os.access(app.parent, os.W_OK) and os.access(app, os.W_OK)


def limpiar() -> None:
    """Restos de una actualización anterior (la app antigua y el instalador)."""
    shutil.rmtree(CARPETA, ignore_errors=True)


# ----------------------------------------------------------------------------
# Interfaz
# ----------------------------------------------------------------------------
def automatico() -> bool:
    return QSettings().value("actualizaciones/automatico", True, type=bool)


def _padre():
    from . import ventana
    return QApplication.activeWindow() or ventana.ventana_activa() or (ventana._ventanas[-1] if ventana._ventanas else None)


class DialogoActualizacion(QDialog):
    def __init__(self, v: Version, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Actualización disponible")
        self.setMinimumWidth(520)
        p = tema.paleta()
        capa = QVBoxLayout(self)
        capa.setContentsMargins(22, 20, 22, 16)
        capa.setSpacing(12)
        cab = QHBoxLayout()
        cab.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(tema.pixmap_logo(52))
        cab.addWidget(logo, 0, Qt.AlignTop)
        textos = QVBoxLayout()
        textos.setSpacing(3)
        titulo = QLabel("Hay una versión nueva de Mezquita PDF")
        titulo.setStyleSheet("font-size: 17px; font-weight: 700;")
        sub = QLabel(f"Ya está disponible la <b>{v.numero}</b> (tienes la {VERSION}). "
                     "Se descarga, se comprueba y se instala sola; tus documentos y firmas no se tocan.")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {p.texto_suave};")
        textos.addWidget(titulo)
        textos.addWidget(sub)
        cab.addLayout(textos, 1)
        capa.addLayout(cab)
        if v.notas:
            notas = QTextBrowser()
            notas.setOpenExternalLinks(True)
            notas.setMarkdown(v.notas)
            notas.setMinimumHeight(170)
            notas.setMaximumHeight(260)
            capa.addWidget(notas)
        self.c_auto = QCheckBox("Buscar actualizaciones automáticamente")
        self.c_auto.setChecked(automatico())
        self.c_auto.toggled.connect(lambda si: QSettings().setValue("actualizaciones/automatico", si))
        capa.addWidget(self.c_auto)
        pie = QHBoxLayout()
        pie.addStretch(1)
        luego = QPushButton("Más tarde")
        luego.setAutoDefault(False)
        luego.clicked.connect(self.reject)
        actualizar = QPushButton("  Actualizar")
        actualizar.setObjectName("primario")
        tema.poner_icono(actualizar, "download", "#FFFFFF")
        actualizar.setDefault(True)
        actualizar.clicked.connect(self.accept)
        pie.addWidget(luego)
        pie.addWidget(actualizar)
        capa.addLayout(pie)


class Actualizador(QObject):
    """Coordina la comprobación, la descarga y la instalación (una para toda la app)."""
    _consultado = Signal(object, object, bool)    # Version | None, error | None, manual
    _progreso = Signal(int, int)
    _preparado = Signal(object, object)           # (ruta app nueva | ruta dmg) | None, error | None

    def __init__(self, app: QApplication):
        super().__init__(app)
        self.app = app
        self._ocupado = False
        self._pendiente: tuple[Path, Path, Path] | None = None  # (app, nueva, anterior)
        self._abrir_tras_instalar = False
        self._cancelar = threading.Event()
        self._dialogo_progreso: QProgressDialog | None = None
        self._consultado.connect(self._tras_consultar)
        self._progreso.connect(self._mostrar_progreso)
        self._preparado.connect(self._tras_preparar)
        app.aboutToQuit.connect(self._instalar_al_salir)

    # --- Comprobar -------------------------------------------------------------
    def comprobar_si_toca(self) -> None:
        if not automatico() or self._app_actual() is None:
            return
        ultima = QSettings().value("actualizaciones/ultima", 0.0, type=float)
        if time.time() - ultima >= CADA:
            self.comprobar(manual=False)

    def comprobar(self, manual: bool = True) -> None:
        if self._ocupado:
            return
        self._ocupado = True

        def trabajo():
            try:
                self._consultado.emit(consultar(), None, manual)
            except Exception as exc:
                self._consultado.emit(None, exc, manual)
        threading.Thread(target=trabajo, daemon=True).start()

    def _tras_consultar(self, v: Version | None, error, manual: bool) -> None:
        self._ocupado = False
        if error is not None or v is None:
            if manual:
                QMessageBox.warning(_padre(), "Buscar actualizaciones",
                                    "No se ha podido consultar si hay versiones nuevas. "
                                    f"Comprueba la conexión a internet.\n\n({error})")
            return
        QSettings().setValue("actualizaciones/ultima", time.time())
        if not es_mas_nueva(v.numero):
            if manual:
                QMessageBox.information(_padre(), "Buscar actualizaciones",
                                        f"Tienes la última versión de Mezquita PDF ({VERSION}).")
            return
        if not v.url:
            if manual:
                QMessageBox.information(_padre(), "Buscar actualizaciones",
                                        f"La versión {v.numero} se está preparando. Prueba dentro de unos minutos.")
            return
        if self._pendiente is not None:
            return  # ya está descargada y se instalará al salir
        if DialogoActualizacion(v, _padre()).exec() == QDialog.Accepted:
            self.descargar(v)

    # --- Descargar y preparar --------------------------------------------------------
    def descargar(self, v: Version) -> None:
        app = self._app_actual()
        en_su_sitio = se_puede_sustituir(app)
        self._cancelar.clear()
        dlg = QProgressDialog(f"Descargando Mezquita PDF {v.numero}…", "Cancelar", 0, 100, _padre())
        dlg.setWindowTitle("Actualizar Mezquita PDF")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.canceled.connect(self._cancelar.set)
        dlg.show()
        self._dialogo_progreso = dlg
        self._version = v

        def trabajo():
            try:
                limpiar()
                dmg = descargar(v, CARPETA, lambda h, t: self._progreso.emit(h, t), self._cancelar)
                if not en_su_sitio:
                    self._preparado.emit(("dmg", dmg), None)
                    return
                self._progreso.emit(-1, 0)
                nueva = preparar_app(dmg, v.numero, CARPETA)
                dmg.unlink(missing_ok=True)
                self._preparado.emit(("app", nueva), None)
            except Exception as exc:
                self._preparado.emit(None, exc)
        threading.Thread(target=trabajo, daemon=True).start()

    def _mostrar_progreso(self, hecho: int, total: int) -> None:
        dlg = self._dialogo_progreso
        if dlg is None:
            return
        if hecho < 0:
            dlg.setLabelText("Comprobando e instalando la versión nueva…")
            dlg.setRange(0, 0)
            dlg.setCancelButton(None)
        elif total:
            dlg.setValue(int(hecho * 100 / total))
            dlg.setLabelText(f"Descargando Mezquita PDF {self._version.numero}…  "
                             f"{hecho / 1048576:.0f} de {total / 1048576:.0f} MB")

    def _tras_preparar(self, resultado, error) -> None:
        if self._dialogo_progreso is not None:
            self._dialogo_progreso.close()
            self._dialogo_progreso = None
        if isinstance(error, Cancelado):
            limpiar()
            return
        if error is not None:
            limpiar()
            QMessageBox.warning(_padre(), "Actualizar Mezquita PDF",
                                f"No se ha podido actualizar:\n{error}\n\n"
                                "También puedes descargarla de la página de la versión.")
            return
        tipo, ruta = resultado
        if tipo == "dmg":
            subprocess.run(["/usr/bin/open", str(ruta)], check=False)
            QMessageBox.information(_padre(), "Actualizar Mezquita PDF",
                                    "Se ha abierto el instalador. Cierra Mezquita PDF, arrastra la app nueva a "
                                    "Aplicaciones (sustituye la anterior) y vuelve a abrirla.")
            return
        app = self._app_actual()
        self._pendiente = (app, ruta, CARPETA / "anterior.app")
        caja = QMessageBox(_padre())
        caja.setIconPixmap(tema.pixmap_logo(56))
        caja.setWindowTitle("Actualizar Mezquita PDF")
        caja.setText(f"<b>La versión {self._version.numero} está lista.</b>")
        caja.setInformativeText("Mezquita PDF se cerrará y se abrirá la versión nueva (si tienes cambios sin "
                                "guardar, te preguntará antes). También puedes seguir y se instalará al salir.")
        ahora = caja.addButton("Reiniciar ahora", QMessageBox.AcceptRole)
        caja.addButton("Al salir", QMessageBox.RejectRole)
        caja.setDefaultButton(ahora)
        caja.exec()
        if caja.clickedButton() is ahora:
            self.reiniciar()

    # --- Instalar ----------------------------------------------------------------
    def reiniciar(self) -> None:
        from .ventana import VentanaPrincipal
        self._abrir_tras_instalar = True
        QApplication.closeAllWindows()
        abiertas = [w for w in QApplication.topLevelWidgets() if isinstance(w, VentanaPrincipal) and w.isVisible()]
        if abiertas:  # el usuario ha cancelado el cierre de algún documento
            self._abrir_tras_instalar = False
            QMessageBox.information(abiertas[0], "Actualizar Mezquita PDF",
                                    "La versión nueva se instalará cuando cierres Mezquita PDF.")
            return
        self.app.quit()

    def _instalar_al_salir(self) -> None:
        if self._pendiente is None:
            return
        app, nueva, anterior = self._pendiente
        guion = CARPETA / "instalar.sh"
        guion.write_text(guion_sustitucion(os.getpid(), app, nueva, anterior, self._abrir_tras_instalar))
        subprocess.Popen(["/bin/bash", str(guion)], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._pendiente = None

    @staticmethod
    def _app_actual() -> Path | None:
        from . import sistema
        return sistema.ruta_app()


_actualizador: Actualizador | None = None


def iniciar(app: QApplication) -> Actualizador:
    global _actualizador
    limpiar()  # restos de la actualización anterior (la versión antigua de la app)
    _actualizador = Actualizador(app)
    QTimer.singleShot(ESPERA_INICIO, _actualizador.comprobar_si_toca)
    return _actualizador


def buscar_ahora() -> None:
    if _actualizador is not None:
        _actualizador.comprobar(manual=True)
