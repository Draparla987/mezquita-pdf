"""Mezquita PDF ↔ Claude: atiende las peticiones de la extensión (visor/mcp_servidor.py).

Escucha en un socket local privado (solo tu usuario puede conectarse). Cada petición se
ejecuta en el hilo de la interfaz, sobre los documentos abiertos: los cambios se ven al
momento, se avisan en la ventana y se deshacen con ⌘Z. Nada se guarda en disco.
"""

from __future__ import annotations

import base64
import json
import os
import traceback
from pathlib import Path

import pymupdf
from PySide6.QtCore import QObject, QSettings, Qt
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout,
)

from . import mcp_servidor as mcp
from . import tema
from .combinar import Parte, abrir_archivo, combinar
from .documento import Documento, parsear_rango

LIMITE_TEXTO = 120_000
LADO_IMAGEN = 1500
MAX_MARCAS = 500
COLORES = {"amarillo": "#FFD60A", "verde": "#8CE99A", "azul": "#74C0FC", "rosa": "#FFA8C5",
           "naranja": "#FFC078", "rojo": "#E03131"}
TIPOS_CAMPO = {
    pymupdf.PDF_WIDGET_TYPE_TEXT: "texto", pymupdf.PDF_WIDGET_TYPE_CHECKBOX: "casilla",
    pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON: "opción", pymupdf.PDF_WIDGET_TYPE_COMBOBOX: "desplegable",
    pymupdf.PDF_WIDGET_TYPE_LISTBOX: "lista", pymupdf.PDF_WIDGET_TYPE_SIGNATURE: "firma",
}


class ErrorClaude(Exception):
    """Error que se le explica a Claude (y él al usuario)."""


def acceso_permitido() -> bool:
    return QSettings().value("claude/permitido", True, type=bool)


# ----------------------------------------------------------------------------
# Servidor local
# ----------------------------------------------------------------------------
class PuenteClaude(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.servidor = QLocalServer(self)
        self.servidor.setSocketOptions(QLocalServer.UserAccessOption)
        self.servidor.newConnection.connect(self._nueva_conexion)
        self._buffers: dict[int, bytearray] = {}

    def activar(self, si: bool) -> bool:
        if not si:
            if self.servidor.isListening():
                self.servidor.close()
            QLocalServer.removeServer(mcp.ruta_socket())
            return True
        if self.servidor.isListening():
            return True
        ruta = mcp.ruta_socket()
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        QLocalServer.removeServer(ruta)  # restos de una ejecución anterior
        return self.servidor.listen(ruta)

    def _nueva_conexion(self) -> None:
        while self.servidor.hasPendingConnections():
            sock = self.servidor.nextPendingConnection()
            self._buffers[id(sock)] = bytearray()
            sock.readyRead.connect(lambda s=sock: self._leer(s))
            sock.disconnected.connect(lambda s=sock: (self._buffers.pop(id(s), None), s.deleteLater()))

    def _leer(self, sock) -> None:
        buf = self._buffers.get(id(sock))
        if buf is None:
            return
        buf += bytes(sock.readAll())
        if b"\n" not in buf:
            return
        linea = bytes(buf.split(b"\n", 1)[0])
        self._buffers[id(sock)] = bytearray()
        respuesta = atender(linea)
        sock.write(json.dumps(respuesta, ensure_ascii=False).encode() + b"\n")
        sock.flush()
        sock.disconnectFromServer()


def atender(linea: bytes) -> dict:
    try:
        peticion = json.loads(linea)
        nombre = peticion.get("herramienta", "")
        args = peticion.get("argumentos") or {}
    except Exception:
        return {"error": "Petición no válida."}
    if not acceso_permitido():
        return {"error": "El usuario ha desactivado el acceso de Claude en Mezquita PDF "
                         "(Herramientas → Conectar con Claude…)."}
    funcion = HERRAMIENTAS.get(nombre)
    if funcion is None:
        return {"error": f"Herramienta desconocida: {nombre}"}
    try:
        resultado = funcion(args)
    except ErrorClaude as exc:
        return {"error": str(exc)}
    except Exception as exc:
        traceback.print_exc()
        return {"error": f"Error inesperado en Mezquita PDF: {exc}"}
    return resultado if isinstance(resultado, dict) else {"texto": str(resultado)}


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def _V():
    from . import ventana  # importación tardía: ventana.py importa este módulo
    return ventana


def _con_documento() -> list:
    return [v for v in _V()._ventanas if v.documento is not None]


def _ventana(args: dict):
    docs = _con_documento()
    if not docs:
        raise ErrorClaude("No hay ningún documento abierto en Mezquita PDF. Usa «abrir_documento».")
    clave = str(args.get("documento") or "").strip()
    if not clave:
        return _V().ventana_activa() or docs[0]
    if clave.isdigit() and 1 <= int(clave) <= len(docs):
        return docs[int(clave) - 1]
    clave_m = clave.lower()
    for criterio in (lambda n: n == clave_m, lambda n: n.startswith(clave_m), lambda n: clave_m in n):
        for v in docs:
            if criterio(v.documento.nombre.lower()):
                return v
    raise ErrorClaude(f"No encuentro el documento «{clave}». Abiertos: "
                      + ", ".join(f"{i}. {v.documento.nombre}" for i, v in enumerate(docs, 1)))


def _paginas(v, texto, por_defecto_todas: bool = True) -> list[int]:
    n = v.documento.num_paginas
    if texto in (None, ""):
        if por_defecto_todas:
            return list(range(n))
        raise ErrorClaude("Indica las páginas.")
    try:
        return parsear_rango(str(texto), n)
    except ValueError:
        raise ErrorClaude(f"Páginas no válidas: «{texto}». El documento tiene {n} páginas.") from None


def _pagina(v, numero) -> int:
    n = v.documento.num_paginas
    try:
        i = int(numero) - 1
    except (TypeError, ValueError):
        i = -1
    if not 0 <= i < n:
        raise ErrorClaude(f"La página {numero} no existe: el documento tiene {n} páginas.")
    return i


def _rutas(lista) -> list[str]:
    if not lista:
        raise ErrorClaude("Indica al menos un archivo.")
    rutas = []
    for r in lista:
        ruta = os.path.abspath(os.path.expanduser(str(r)))
        if not os.path.isfile(ruta):
            raise ErrorClaude(f"No existe el archivo: {ruta}")
        rutas.append(ruta)
    return rutas


def _aviso(v, texto: str) -> None:
    v.aviso(f"Claude: {texto}", 4)


def _refrescar(v, paginas) -> None:
    for i in sorted(set(paginas)):
        v.vista.refrescar_pagina(i)
        v._actualizar_miniatura(i)
    v.miniaturas.viewport().update()
    v._actualizar_estado_ui()


def _lista(nums: list[int]) -> str:
    return ", ".join(str(i + 1) for i in nums)


# ----------------------------------------------------------------------------
# Herramientas
# ----------------------------------------------------------------------------
def h_estado(_args) -> dict:
    activa = _V().ventana_activa()
    docs = []
    for k, v in enumerate(_con_documento(), 1):
        d = v.documento
        seleccion = v.vista._seleccion[2] if v.vista._seleccion and v.vista._seleccion[2] else ""
        campos = d.doc.is_form_pdf or 0
        docs.append({
            "numero": k, "nombre": d.nombre, "ruta": d.ruta or "(sin guardar)", "activo": v is activa,
            "paginas": d.num_paginas, "pagina_visible": v.vista.pagina_actual() + 1,
            "cambios_sin_guardar": d.modificado, "firmado_digitalmente": v.tenia_firmas,
            "campos_de_formulario": int(campos), "texto_seleccionado": seleccion[:4000],
            "titulo": (d.doc.metadata or {}).get("title") or "",
        })
    if not docs:
        return {"texto": "Mezquita PDF está abierta, pero sin documentos. Usa «abrir_documento»."}
    return {"texto": json.dumps({"documentos": docs}, ensure_ascii=False, indent=1)}


def h_abrir_documento(args) -> dict:
    ruta = _rutas([args.get("ruta")])[0]
    V = _V()
    def abierta():
        return next((v for v in V._ventanas if v.documento and v.documento.ruta
                     and os.path.abspath(v.documento.ruta) == ruta), None)
    v = abierta()
    if v is None:
        vacia = next((v for v in V._ventanas if v.documento is None), None)
        if vacia is not None:
            vacia.abrir_ruta(ruta)
        else:
            V.nueva_ventana(ruta)
        v = abierta()
    if v is None:
        raise ErrorClaude("No se ha abierto (no es un PDF válido o el usuario canceló la contraseña).")
    V.marcar_activa(v)
    _aviso(v, "ha abierto el documento")
    return {"texto": f"Abierto «{v.documento.nombre}» ({v.documento.num_paginas} páginas). "
                     "Es ahora el documento activo."}


def h_leer_texto(args) -> dict:
    v = _ventana(args)
    paginas = _paginas(v, args.get("paginas"))
    partes, total, leidas = [], 0, []
    for i in paginas:
        texto = v.documento.pagina(i).get_text("text", sort=True).strip()
        bloque = f"--- Página {i + 1} ---\n{texto or '(sin texto: quizá es un escaneo; usa ver_pagina)'}\n"
        if total + len(bloque) > LIMITE_TEXTO and partes:
            resto = paginas[paginas.index(i):]
            partes.append(f"[Texto cortado por longitud: faltan las páginas {resto[0] + 1}–{resto[-1] + 1}; "
                          "pídelas con el parámetro «paginas».]")
            break
        partes.append(bloque)
        total += len(bloque)
        leidas.append(i)
    _aviso(v, f"ha leído {len(leidas)} página{'s' if len(leidas) != 1 else ''}")
    return {"texto": f"«{v.documento.nombre}» ({v.documento.num_paginas} páginas)\n\n" + "\n".join(partes)}


def h_ver_pagina(args) -> dict:
    v = _ventana(args)
    i = _pagina(v, args.get("pagina"))
    pagina = v.documento.pagina(i)
    escala = LADO_IMAGEN / max(pagina.rect.width, pagina.rect.height)
    pm = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala), alpha=False)
    datos = base64.b64encode(pm.tobytes("jpeg", jpg_quality=85)).decode()
    _aviso(v, f"ha mirado la página {i + 1}")
    return {"texto": f"Página {i + 1} de {v.documento.num_paginas} de «{v.documento.nombre}».",
            "imagen": {"datos": datos, "tipo": "image/jpeg"}}


def h_buscar(args) -> dict:
    v = _ventana(args)
    texto = str(args.get("texto") or "").strip()
    if not texto:
        raise ErrorClaude("Indica el texto que hay que buscar.")
    hallazgos = []
    for i in range(v.documento.num_paginas):
        pagina = v.documento.pagina(i)
        for r in pagina.search_for(texto):
            linea = pagina.get_textbox(pymupdf.Rect(pagina.rect.x0, r.y0 + 1, pagina.rect.x1, r.y1 - 1))
            hallazgos.append({"pagina": i + 1, "linea": " ".join(linea.split())[:240]})
            if len(hallazgos) >= 200:
                break
    _aviso(v, f"ha buscado «{texto}» ({len(hallazgos)} resultados)")
    if not hallazgos:
        return {"texto": f"«{texto}» no aparece en el documento."}
    return {"texto": json.dumps({"resultados": len(hallazgos), "apariciones": hallazgos}, ensure_ascii=False)}


def _texto_marcado(pagina, annot) -> str:
    """Palabras cuyo centro cae dentro del resaltado (sin letras sueltas de los lados)."""
    v = annot.vertices or []
    zonas = [pymupdf.Quad(v[k:k + 4]).rect for k in range(0, len(v) - 3, 4)] or [annot.rect]
    palabras = []
    for x0, y0, x1, y1, palabra, *_ in pagina.get_text("words", sort=True):
        centro = pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)
        if any(centro in z for z in zonas):
            palabras.append(palabra)
    return " ".join(palabras)


def h_leer_anotaciones(args) -> dict:
    v = _ventana(args)
    anotaciones = []
    for i in _paginas(v, args.get("paginas")):
        pagina = v.documento.pagina(i)
        for a in pagina.annots():
            tipo = a.type[1]
            if tipo in ("Widget", "Link", "Popup"):
                continue
            info = a.info or {}
            elemento = {"pagina": i + 1, "tipo": tipo, "autor": info.get("title", ""), "contenido": info.get("content", "")}
            if tipo in ("Highlight", "Underline", "StrikeOut", "Squiggly"):
                elemento["texto_marcado"] = _texto_marcado(pagina, a)[:500]
            anotaciones.append(elemento)
    _aviso(v, f"ha leído {len(anotaciones)} anotaciones")
    if not anotaciones:
        return {"texto": "El documento no tiene anotaciones en esas páginas."}
    return {"texto": json.dumps({"anotaciones": anotaciones}, ensure_ascii=False)}


def h_resaltar(args) -> dict:
    v = _ventana(args)
    textos = [str(t) for t in (args.get("textos") or []) if str(t).strip()]
    if not textos:
        raise ErrorClaude("Indica los textos que hay que marcar.")
    estilo = args.get("estilo") or "resaltar"
    color = COLORES.get(args.get("color") or ("amarillo" if estilo == "resaltar" else "rojo"), "#FFD60A")
    rgb = tuple(int(color[k:k + 2], 16) / 255 for k in (1, 3, 5))
    paginas = _paginas(v, args.get("paginas"))
    hechos, por_texto, tocadas = 0, {}, set()
    for t in textos:
        por_texto[t] = 0
        for i in paginas:
            pagina = v.documento.pagina(i)
            for quad in pagina.search_for(t, quads=True):
                if hechos >= MAX_MARCAS:
                    break
                if hechos == 0:
                    v.documento.instantanea()
                if estilo == "subrayar":
                    a = pagina.add_underline_annot(quad)
                elif estilo == "tachar":
                    a = pagina.add_strikeout_annot(quad)
                else:
                    a = pagina.add_highlight_annot(quad)
                a.set_colors(stroke=rgb)
                a.set_info(title="Claude")
                a.update()
                hechos += 1
                por_texto[t] += 1
                tocadas.add(i)
    if hechos:
        _refrescar(v, tocadas)
        v.vista.ir_a_pagina(min(tocadas))
        verbo = {"resaltar": "resaltado", "subrayar": "subrayado", "tachar": "tachado"}[estilo]
        _aviso(v, f"ha {verbo} {hechos} fragmento{'s' if hechos != 1 else ''} · ⌘Z para deshacer")
    detalle = "\n".join(f"· «{t}»: {n}" for t, n in por_texto.items())
    nota = "" if hechos < MAX_MARCAS else f"\n(Se ha parado en {MAX_MARCAS} marcas.)"
    return {"texto": f"{hechos} marcas en total.\n{detalle}{nota}"
            + ("" if hechos else "\nNo se ha encontrado ningún texto: cópialo exactamente como aparece.")}


def h_anadir_nota(args) -> dict:
    v = _ventana(args)
    i = _pagina(v, args.get("pagina"))
    texto = str(args.get("texto") or "").strip()
    if not texto:
        raise ErrorClaude("La nota está vacía.")
    pagina = v.documento.pagina(i)
    r = pagina.rect
    punto = pymupdf.Point(r.x1 - 36, r.y0 + 24)
    cerca = str(args.get("cerca_de") or "").strip()
    encontrado = False
    if cerca:
        hits = pagina.search_for(cerca)
        if hits:
            punto = pymupdf.Point(min(hits[0].x1 + 4, r.x1 - 24), max(hits[0].y0 - 2, r.y0 + 2))
            encontrado = True
    v.documento.instantanea()
    nota = pagina.add_text_annot(punto, texto, icon="Comment")
    nota.set_info(title="Claude", content=texto)
    nota.update()
    _refrescar(v, [i])
    v.vista.ir_a_pagina(i)
    _aviso(v, f"ha añadido una nota en la página {i + 1}")
    sitio = f"junto a «{cerca}»" if encontrado else "en el margen superior"
    extra = f" (no encontré «{cerca}» en esa página)" if cerca and not encontrado else ""
    return {"texto": f"Nota añadida en la página {i + 1}, {sitio}{extra}."}


def _campos(v):
    for i in range(v.documento.num_paginas):
        for w in v.documento.pagina(i).widgets():
            yield i, w


def _opciones(w) -> list[str]:
    return [o if isinstance(o, str) else o[1] for o in (w.choice_values or [])]


def h_campos_formulario(args) -> dict:
    v = _ventana(args)
    campos: dict[str, dict] = {}
    for i, w in _campos(v):
        nombre = w.field_name or f"(sin nombre, página {i + 1})"
        tipo = TIPOS_CAMPO.get(w.field_type, w.field_type_string)
        c = campos.setdefault(nombre, {"nombre": nombre, "tipo": tipo, "pagina": i + 1,
                                       "etiqueta": w.field_label or "", "valor": None})
        if tipo == "casilla":
            c["valor"] = w.field_value not in (False, "Off", "", None)
        elif tipo == "opción":
            c.setdefault("opciones", []).append(w.on_state())
            if w.field_value not in (False, "Off", "", None):
                c["valor"] = w.on_state()
        else:
            c["valor"] = w.field_value
            if tipo in ("desplegable", "lista"):
                c["opciones"] = _opciones(w)
        if tipo == "firma":
            c["nota"] = "Campo de firma: se firma desde Mezquita PDF, no se puede rellenar."
    _aviso(v, "ha leído los campos del formulario")
    if not campos:
        return {"texto": "Este documento no tiene campos de formulario rellenables."}
    return {"texto": json.dumps({"campos": list(campos.values())}, ensure_ascii=False)}


def _verdadero(valor) -> bool:
    return valor is True or str(valor).strip().lower() in ("true", "1", "sí", "si", "x", "yes", "on", "marcada")


def h_rellenar_formulario(args) -> dict:
    v = _ventana(args)
    valores = args.get("valores")
    if not isinstance(valores, dict) or not valores:
        raise ErrorClaude("Indica los valores como {nombre del campo: valor}.")
    rellenados, errores, tocadas, instantanea = set(), [], set(), False
    vistos = set()
    for i, w in _campos(v):
        if w.field_name not in valores:
            continue
        vistos.add(w.field_name)
        valor = valores[w.field_name]
        tipo = TIPOS_CAMPO.get(w.field_type)
        if tipo == "firma":
            errores.append(f"«{w.field_name}» es un campo de firma.")
            continue
        if tipo == "texto":
            nuevo = "" if valor is None else str(valor)
        elif tipo == "casilla":
            nuevo = w.on_state() if _verdadero(valor) else "Off"
        elif tipo == "opción":
            nuevo = w.on_state() if str(valor) == str(w.on_state()) else "Off"
        elif tipo in ("desplegable", "lista"):
            opciones = _opciones(w)
            if str(valor) not in opciones:
                errores.append(f"«{w.field_name}»: «{valor}» no es una opción ({', '.join(opciones)}).")
                continue
            nuevo = str(valor)
        else:
            errores.append(f"«{w.field_name}»: tipo de campo no admitido.")
            continue
        if not instantanea:
            v.documento.instantanea()
            instantanea = True
        w.field_value = nuevo
        w.update()
        rellenados.add(w.field_name)
        tocadas.add(i)
    for nombre in valores:
        if nombre not in vistos:
            errores.append(f"No hay ningún campo llamado «{nombre}».")
    if rellenados:
        _refrescar(v, tocadas)
        v.vista.ir_a_pagina(min(tocadas))
        _aviso(v, f"ha rellenado {len(rellenados)} campo{'s' if len(rellenados) != 1 else ''} · ⌘Z para deshacer")
    texto = f"Campos rellenados: {len(rellenados)}."
    if errores:
        texto += "\nProblemas:\n" + "\n".join(f"· {e}" for e in errores)
    return {"texto": texto}


def h_ir_a_pagina(args) -> dict:
    v = _ventana(args)
    i = _pagina(v, args.get("pagina"))
    v.vista.ir_a_pagina(i)
    return {"texto": f"Mostrando la página {i + 1}."}


def h_girar_paginas(args) -> dict:
    v = _ventana(args)
    paginas = _paginas(v, args.get("paginas"), por_defecto_todas=False)
    grados = int(args.get("grados") or 90)
    if grados not in (90, -90, 180):
        raise ErrorClaude("Los grados deben ser 90, -90 o 180.")
    v.girar_pagina(grados, paginas)
    _aviso(v, f"ha girado {len(paginas)} página{'s' if len(paginas) != 1 else ''}")
    return {"texto": f"Páginas {_lista(paginas)} giradas {grados}°."}


def h_eliminar_paginas(args) -> dict:
    v = _ventana(args)
    paginas = sorted(set(_paginas(v, args.get("paginas"), por_defecto_todas=False)))
    if len(paginas) >= v.documento.num_paginas:
        raise ErrorClaude("No se pueden eliminar todas las páginas: un PDF debe tener al menos una.")
    v.eliminar_paginas(paginas, confirmar=False)
    return {"texto": f"Eliminadas las páginas {_lista(paginas)}. Ahora tiene {v.documento.num_paginas} "
                     "(el usuario puede deshacerlo con ⌘Z)."}


def h_mover_paginas(args) -> dict:
    v = _ventana(args)
    paginas = _paginas(v, args.get("paginas"), por_defecto_todas=False)
    n = v.documento.num_paginas
    try:
        delante = int(args.get("delante_de"))
    except (TypeError, ValueError):
        delante = 0
    if not 1 <= delante <= n + 1:
        raise ErrorClaude(f"«delante_de» debe estar entre 1 y {n + 1}.")
    v.mover_paginas_a(paginas, delante - 1)
    _aviso(v, "ha cambiado el orden de las páginas · ⌘Z para deshacer")
    nuevas = v.miniaturas.seleccionadas()
    return {"texto": f"Páginas movidas; ahora ocupan las posiciones {_lista(nuevas)}."}


def h_insertar_archivos(args) -> dict:
    v = _ventana(args)
    rutas = _rutas(args.get("rutas"))
    n = v.documento.num_paginas
    delante = args.get("delante_de")
    posicion = n if delante in (None, "") else int(delante) - 1
    if not 0 <= posicion <= n:
        raise ErrorClaude(f"«delante_de» debe estar entre 1 y {n + 1}.")
    v.insertar_archivos(rutas, posicion)
    añadidas = v.documento.num_paginas - n
    if not añadidas:
        raise ErrorClaude("No se ha insertado nada (archivos no válidos o contraseña cancelada).")
    return {"texto": f"Insertadas {añadidas} páginas a partir de la {posicion + 1}. "
                     f"El documento tiene ahora {v.documento.num_paginas}."}


def h_combinar_documentos(args) -> dict:
    V = _V()
    rutas = _rutas(args.get("rutas"))
    padre = V.ventana_activa()
    partes: list[Parte] = []
    try:
        if args.get("incluir_abierto"):
            v = _ventana({})
            doc = pymupdf.open(stream=v.documento.bytes_actuales(), filetype="pdf")
            partes.append(Parte(v.documento.nombre, doc, origen="abierto"))
        for ruta in rutas:
            abierto = abrir_archivo(ruta, padre)
            if abierto is None:
                raise ErrorClaude(f"El usuario ha cancelado la contraseña de «{os.path.basename(ruta)}».")
            partes.append(Parte(os.path.basename(ruta), abierto[0], ruta=ruta, origen=abierto[1]))
        if len(partes) < 2:
            raise ErrorClaude("Hacen falta al menos dos documentos para combinar.")
        salida = combinar(partes, bool(args.get("marcadores", True)))
        datos = salida.tobytes(garbage=3, deflate=True)
        salida.close()
    except ErrorClaude:
        raise
    except Exception as exc:
        raise ErrorClaude(f"No se han podido combinar: {exc}") from None
    finally:
        for p in partes:
            p.doc.close()
    nuevo = Documento(datos=datos, nombre="Combinado.pdf")
    nuevo.modificado = True
    v = V.mostrar_en_ventana(nuevo, activar=False)
    _aviso(v, f"ha combinado {len(partes)} documentos · guárdalo con ⌘S")
    return {"texto": f"Creado «Combinado.pdf» con {nuevo.num_paginas} páginas a partir de {len(partes)} documentos. "
                     "Está abierto en Mezquita PDF sin guardar y es ahora el documento activo."}


def h_extraer_paginas(args) -> dict:
    v = _ventana(args)
    paginas = _paginas(v, args.get("paginas"), por_defecto_todas=False)
    nuevo_doc = pymupdf.open()
    for p in paginas:
        nuevo_doc.insert_pdf(v.documento.doc, from_page=p, to_page=p)
    datos = nuevo_doc.tobytes(garbage=3, deflate=True)
    nuevo_doc.close()
    nombre = f"{Path(v.documento.nombre).stem} (páginas {_lista(paginas)}).pdf"
    nuevo = Documento(datos=datos, nombre=nombre)
    nuevo.modificado = True
    _aviso(_V().mostrar_en_ventana(nuevo, activar=False), f"ha copiado {len(paginas)} páginas aquí")
    return {"texto": f"Creado «{nombre}» ({len(paginas)} páginas), abierto en otra ventana sin guardar; "
                     "es ahora el documento activo."}


def h_deshacer(args) -> dict:
    v = _ventana(args)
    if not v.documento.puede_deshacer():
        raise ErrorClaude("No hay nada que deshacer.")
    v.deshacer()
    _aviso(v, "ha deshecho el último cambio")
    return {"texto": "Último cambio deshecho."}


HERRAMIENTAS = {
    "estado": h_estado, "abrir_documento": h_abrir_documento, "leer_texto": h_leer_texto,
    "ver_pagina": h_ver_pagina, "buscar": h_buscar, "leer_anotaciones": h_leer_anotaciones,
    "resaltar": h_resaltar, "anadir_nota": h_anadir_nota, "campos_formulario": h_campos_formulario,
    "rellenar_formulario": h_rellenar_formulario, "ir_a_pagina": h_ir_a_pagina,
    "girar_paginas": h_girar_paginas, "eliminar_paginas": h_eliminar_paginas,
    "mover_paginas": h_mover_paginas, "insertar_archivos": h_insertar_archivos,
    "combinar_documentos": h_combinar_documentos, "extraer_paginas": h_extraer_paginas,
    "deshacer": h_deshacer,
}
assert set(HERRAMIENTAS) == {h["name"] for h in mcp.HERRAMIENTAS}


_puente: PuenteClaude | None = None


def iniciar(app) -> PuenteClaude:
    """Arranca el puente al abrir la app (si el usuario no ha desactivado el acceso)."""
    global _puente
    _puente = PuenteClaude(app)
    if acceso_permitido():
        _puente.activar(True)
    return _puente


def mostrar_dialogo(parent=None) -> None:
    DialogoClaude(_puente, parent).exec()


# ----------------------------------------------------------------------------
# Ventana «Conectar con Claude»
# ----------------------------------------------------------------------------
class DialogoClaude(QDialog):
    def __init__(self, puente: PuenteClaude | None, parent=None):
        super().__init__(parent)
        self.puente = puente
        self.setWindowTitle("Conectar con Claude")
        self.setMinimumWidth(560)
        p = tema.paleta()
        capa = QVBoxLayout(self)
        capa.setContentsMargins(22, 20, 22, 16)
        capa.setSpacing(12)

        cab = QHBoxLayout()
        cab.setSpacing(12)
        ico = QLabel()
        ico.setPixmap(tema.icono("creation", p.acento).pixmap(34, 34))
        cab.addWidget(ico, 0, Qt.AlignTop)
        titulo = QLabel("Usa Mezquita PDF desde la app de Claude")
        titulo.setStyleSheet("font-size: 17px; font-weight: 700;")
        cab.addWidget(titulo, 1)
        capa.addLayout(cab)

        texto = QLabel(
            "Pídele a Claude, en su app del Mac, cosas como:<br>"
            "<i>«Resume el PDF que tengo abierto en Mezquita»</i> · <i>«Resalta todas las fechas y plazos»</i> · "
            "<i>«Rellena este formulario con estos datos…»</i> · <i>«Une estos tres PDF de Descargas»</i> · "
            "<i>«Explícame el texto que he seleccionado»</i><br><br>"
            "Claude trabaja sobre los documentos abiertos aquí: verás cada cambio al momento, firmado como "
            "«Claude», y podrás deshacerlo con ⌘Z. Nada se guarda en disco hasta que tú lo guardes.")
        texto.setWordWrap(True)
        texto.setTextFormat(Qt.RichText)
        capa.addWidget(texto)

        privacidad = QLabel(
            "🔒 Solo se envía a Claude lo que le pidas en su app, usando tu cuenta de Claude. "
            "La app de Claude te pide permiso antes de cada acción (puedes permitir las que quieras siempre). "
            "El enlace entre las dos apps es local y privado de tu usuario.")
        privacidad.setWordWrap(True)
        privacidad.setStyleSheet(f"color: {p.texto_suave}; font-size: 12px; background: {p.panel}; "
                                 f"border: 1px solid {p.borde}; border-radius: 10px; padding: 10px;")
        capa.addWidget(privacidad)

        fila = QHBoxLayout()
        self.estado = QLabel()
        self.estado.setWordWrap(True)
        fila.addWidget(self.estado, 1)
        self.b_instalar = QPushButton()
        self.b_instalar.clicked.connect(self._alternar_extension)
        fila.addWidget(self.b_instalar)
        capa.addLayout(fila)

        self.c_permitir = QCheckBox("Permitir que Claude acceda a los documentos abiertos en Mezquita PDF")
        self.c_permitir.setChecked(acceso_permitido())
        self.c_permitir.toggled.connect(self._permitir)
        capa.addWidget(self.c_permitir)

        pie = QHBoxLayout()
        pie.addStretch(1)
        cerrar = QPushButton("Cerrar")
        cerrar.setAutoDefault(False)
        cerrar.clicked.connect(self.accept)
        pie.addWidget(cerrar)
        capa.addLayout(pie)
        self._actualizar()

    def _actualizar(self) -> None:
        p = tema.paleta()
        if not mcp.claude_disponible():
            self.estado.setText(f"<span style='color:{p.error}'>●</span> No encuentro la app de Claude. "
                                "Descárgala de claude.ai/download e inicia sesión.")
            self.b_instalar.setText("Instalar igualmente")
            self.b_instalar.setObjectName("")
        elif mcp.extension_instalada():
            self.estado.setText(f"<span style='color:{p.exito}'>●</span> <b>Conectada.</b> Si acabas de "
                                "instalarla, cierra la app de Claude (⌘Q) y vuelve a abrirla.")
            self.b_instalar.setText("Quitar de Claude")
            self.b_instalar.setObjectName("")
        else:
            self.estado.setText(f"<span style='color:{p.texto_suave}'>●</span> Aún no está conectada a Claude.")
            self.b_instalar.setText("  Conectar con Claude")
            self.b_instalar.setObjectName("primario")
        self.b_instalar.style().unpolish(self.b_instalar)
        self.b_instalar.style().polish(self.b_instalar)

    def _alternar_extension(self) -> None:
        try:
            if mcp.extension_instalada():
                mcp.quitar_extension()
            else:
                mcp.instalar_extension()
                if not self.c_permitir.isChecked():
                    self.c_permitir.setChecked(True)
        except Exception as exc:
            QMessageBox.warning(self, "Conectar con Claude",
                                f"No se ha podido cambiar la configuración de la app de Claude:\n{exc}")
        self._actualizar()

    def _permitir(self, si: bool) -> None:
        QSettings().setValue("claude/permitido", si)
        if self.puente is not None:
            self.puente.activar(si)
