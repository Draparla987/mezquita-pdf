"""Documento PDF abierto: envoltorio sobre PyMuPDF con deshacer/rehacer."""

from __future__ import annotations

import os

import pymupdf

MAX_HISTORIAL = 40


class Documento:
    def __init__(self, ruta: str | None = None, datos: bytes | None = None):
        if datos is not None:
            self.doc = pymupdf.open(stream=datos, filetype="pdf")
        else:
            self.doc = pymupdf.open(ruta)
        self.ruta = ruta
        self.modificado = False
        # Las anotaciones y campos de PyMuPDF dejan de ser válidos (y pueden cerrar la
        # aplicación) si su página se libera: mantenemos vivas las páginas en caché.
        self._paginas: dict[int, pymupdf.Page] = {}
        self._deshacer: list[bytes] = []
        self._rehacer: list[bytes] = []

    # --- Información -----------------------------------------------------
    @property
    def nombre(self) -> str:
        return os.path.basename(self.ruta) if self.ruta else "Sin título.pdf"

    @property
    def num_paginas(self) -> int:
        return self.doc.page_count

    def pagina(self, n: int) -> pymupdf.Page:
        pag = self._paginas.get(n)
        if pag is None:
            pag = self._paginas[n] = self.doc[n]
        return pag

    def invalidar_paginas(self) -> None:
        self._paginas.clear()

    # --- Cambios de estructura (invalidan la caché de páginas) -------------
    def eliminar_pagina(self, n: int) -> None:
        self.invalidar_paginas()
        self.doc.delete_page(n)

    def nueva_pagina(self, posicion: int, ancho: float, alto: float) -> None:
        self.invalidar_paginas()
        self.doc.new_page(posicion, width=ancho, height=alto)

    def mover_pagina(self, origen: int, destino: int) -> None:
        """Mueve la página `origen` delante de `destino` (-1 = al final)."""
        self.invalidar_paginas()
        self.doc.move_page(origen, destino)

    def insertar_pdf(self, otro: pymupdf.Document, en: int = -1) -> None:
        self.invalidar_paginas()
        self.doc.insert_pdf(otro, start_at=en)

    def necesita_contrasena(self) -> bool:
        return self.doc.needs_pass

    def autenticar(self, contrasena: str) -> bool:
        return bool(self.doc.authenticate(contrasena))

    def bytes_actuales(self) -> bytes:
        return self.doc.tobytes(garbage=0, deflate=True)

    # --- Historial ---------------------------------------------------------
    def instantanea(self) -> None:
        """Guarda el estado actual antes de modificar (para poder deshacer)."""
        self._deshacer.append(self.doc.tobytes())
        if len(self._deshacer) > MAX_HISTORIAL:
            self._deshacer.pop(0)
        self._rehacer.clear()
        self.modificado = True

    def puede_deshacer(self) -> bool:
        return bool(self._deshacer)

    def puede_rehacer(self) -> bool:
        return bool(self._rehacer)

    def deshacer(self) -> bool:
        if not self._deshacer:
            return False
        self._rehacer.append(self.doc.tobytes())
        self._cargar(self._deshacer.pop())
        self.modificado = True
        return True

    def rehacer(self) -> bool:
        if not self._rehacer:
            return False
        self._deshacer.append(self.doc.tobytes())
        self._cargar(self._rehacer.pop())
        self.modificado = True
        return True

    def reabrir(self, ruta: str) -> None:
        """Vuelve a abrir desde disco (p. ej. tras firmar) y vacía el historial."""
        self.invalidar_paginas()
        self.doc.close()
        self.doc = pymupdf.open(ruta)
        self.ruta = ruta
        self.modificado = False
        self._deshacer.clear()
        self._rehacer.clear()

    def _cargar(self, datos: bytes) -> None:
        self.invalidar_paginas()
        self.doc.close()
        self.doc = pymupdf.open(stream=datos, filetype="pdf")

    # --- Guardado ----------------------------------------------------------
    def guardar(self, ruta: str | None = None, incremental: bool = False) -> None:
        destino = ruta or self.ruta
        if not destino:
            raise ValueError("Falta la ruta de destino")
        if incremental and not self.puede_guardar_incremental(destino):
            raise ValueError("No se puede guardar de forma incremental")
        if incremental:
            # Añade los cambios al final del fichero: conserva válidas las firmas previas.
            self.doc.saveIncr()
        else:
            datos = self.doc.tobytes(garbage=3, deflate=True)
            tmp = destino + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(datos)
            os.replace(tmp, destino)
            self.invalidar_paginas()
            self.doc.close()
            self.doc = pymupdf.open(destino)
        self.ruta = destino
        self.modificado = False

    def puede_guardar_incremental(self, destino: str | None = None) -> bool:
        destino = destino or self.ruta
        return bool(
            destino
            and self.doc.name
            and os.path.abspath(destino) == os.path.abspath(self.doc.name)
            and self.doc.can_save_incrementally()
        )

    def cerrar(self) -> None:
        self.invalidar_paginas()
        self.doc.close()
