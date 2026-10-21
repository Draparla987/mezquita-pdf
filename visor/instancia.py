"""Una sola Mezquita PDF por usuario (Windows).

Al abrir un PDF con doble clic, Windows lanza otra copia de la app. Esa copia le pasa los
archivos a la que ya está abierta (por un canal local privado) y se cierra: así los PDF se abren
en la misma app, como en el Mac.
"""

from __future__ import annotations

import json

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .plataforma import ES_WINDOWS, usuario

NOMBRE = f"mezquita-pdf-instancia-{usuario()}"


def enviar_a_la_abierta(rutas: list[str]) -> bool:
    """Si ya hay una Mezquita PDF abierta, le pasa `rutas` y devuelve True."""
    s = QLocalSocket()
    s.connectToServer(NOMBRE)
    if not s.waitForConnected(400):
        return False
    if ES_WINDOWS:  # permite que la app abierta se ponga delante (Windows lo impide si no)
        try:
            import ctypes
            ctypes.windll.user32.AllowSetForegroundWindow(-1)
        except Exception:
            pass
    s.write(json.dumps(rutas).encode() + b"\n")
    s.flush()
    s.waitForBytesWritten(2000)
    s.disconnectFromServer()
    if s.state() != QLocalSocket.UnconnectedState:
        s.waitForDisconnected(1000)
    return True


class Instancia(QObject):
    """Escucha a las copias que se abran después. `al_recibir(rutas)` se llama en la interfaz."""

    def __init__(self, parent, al_recibir):
        super().__init__(parent)
        self._al_recibir = al_recibir
        self._buffers: dict[int, bytearray] = {}
        self.servidor = QLocalServer(self)
        self.servidor.setSocketOptions(QLocalServer.UserAccessOption)
        self.servidor.newConnection.connect(self._nueva)
        QLocalServer.removeServer(NOMBRE)
        self.escuchando = self.servidor.listen(NOMBRE)

    def _nueva(self) -> None:
        while self.servidor.hasPendingConnections():
            sock = self.servidor.nextPendingConnection()
            self._buffers[id(sock)] = bytearray()
            sock.readyRead.connect(lambda s=sock: self._leer(s))
            sock.disconnected.connect(lambda s=sock: self._cerrado(s))
            if sock.bytesAvailable():  # los datos pueden llegar junto con la conexión
                self._leer(sock)

    def _cerrado(self, sock) -> None:
        if sock.bytesAvailable():  # …o justo antes de que la otra copia se desconecte
            self._leer(sock)
        self._buffers.pop(id(sock), None)
        sock.deleteLater()

    def _leer(self, sock) -> None:
        buf = self._buffers.get(id(sock))
        if buf is None:
            return
        buf += bytes(sock.readAll())
        if b"\n" not in buf:
            return
        try:
            rutas = [str(r) for r in json.loads(bytes(buf).split(b"\n", 1)[0])]
        except Exception:
            rutas = []
        self._buffers[id(sock)] = bytearray()
        self._al_recibir(rutas)
