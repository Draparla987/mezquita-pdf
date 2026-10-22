"""Mover de sitio el texto original del PDF y las anotaciones añadidas (sin interfaz).

- Anotaciones (cuadros de texto, notas, rectángulos, elipses, flechas y dibujos a mano): se
  desplazan o redimensionan conservando su aspecto. Las flechas y los dibujos no admiten un
  rectángulo nuevo en PDF: se vuelven a crear iguales en la nueva posición.
- Texto original: cada fragmento (span) de la línea se borra de su sitio y se vuelve a escribir
  desplazado, con su tamaño, color, negrita y cursiva. La letra pasa a ser la estándar más
  parecida (Helvetica, Times o Courier), estirada o encogida para ocupar el mismo ancho que la
  original; así el resto de la línea no se descoloca y el texto sigue siendo seleccionable.
  Se escribe con TextWriter, que admite «€», «ñ», tildes, etc. (insert_text no).
"""

from __future__ import annotations

import math

import pymupdf

# Lo que se puede mover (los resaltados, subrayados y tachados van unidos a su texto)
MOVIBLES = {
    pymupdf.PDF_ANNOT_FREE_TEXT, pymupdf.PDF_ANNOT_TEXT, pymupdf.PDF_ANNOT_SQUARE,
    pymupdf.PDF_ANNOT_CIRCLE, pymupdf.PDF_ANNOT_LINE, pymupdf.PDF_ANNOT_INK, pymupdf.PDF_ANNOT_STAMP,
}
REDIMENSIONABLES = {pymupdf.PDF_ANNOT_FREE_TEXT, pymupdf.PDF_ANNOT_SQUARE, pymupdf.PDF_ANNOT_CIRCLE}
TAM_MINIMO = 8.0  # pt


def es_movible(annot) -> bool:
    return annot is not None and annot.type[0] in MOVIBLES


def es_redimensionable(annot) -> bool:
    return annot is not None and annot.type[0] in REDIMENSIONABLES


def _dentro(rect: pymupdf.Rect, pagina: pymupdf.Page) -> tuple[float, float]:
    """Corrección para que `rect` no se salga de la página."""
    limite = pagina.cropbox if pagina.rotation == 0 else pagina.mediabox
    dx = max(limite.x0 - rect.x0, 0) - max(rect.x1 - limite.x1, 0)
    dy = max(limite.y0 - rect.y0, 0) - max(rect.y1 - limite.y1, 0)
    return dx, dy


# ----------------------------------------------------------------------------
# Anotaciones
# ----------------------------------------------------------------------------
def _poner_rect(annot, rect: pymupdf.Rect) -> None:
    """set_rect conservando el tamaño: en rectángulos y elipses el borde lo agranda al actualizar."""
    annot.set_rect(rect)
    annot.update()
    crecido = annot.rect
    gx, gy = (crecido.width - rect.width) / 2, (crecido.height - rect.height) / 2
    if abs(gx) > 0.01 or abs(gy) > 0.01:
        annot.set_rect(pymupdf.Rect(rect.x0 + gx, rect.y0 + gy, rect.x1 - gx, rect.y1 - gy))
        annot.update()


def _copiar_estilo(origen, destino) -> None:
    colores = origen.colors or {}
    destino.set_colors(stroke=colores.get("stroke"), fill=colores.get("fill"))
    borde = origen.border or {}
    if borde.get("width") is not None and borde["width"] >= 0:
        destino.set_border(width=borde["width"], dashes=borde.get("dashes") or None)
    if origen.opacity is not None and 0 <= origen.opacity < 1:
        destino.set_opacity(origen.opacity)
    info = origen.info or {}
    destino.set_info(title=info.get("title", ""), content=info.get("content", ""),
                     subject=info.get("subject", ""))


def mover_anotacion(pagina: pymupdf.Page, xref: int, dx: float, dy: float) -> int:
    """Desplaza la anotación `xref` (sin salirse de la página). Devuelve su xref (puede cambiar)."""
    annot = pagina.load_annot(xref)
    if not es_movible(annot):
        raise ValueError("Esta anotación no se puede mover")
    destino = pymupdf.Rect(annot.rect) + (dx, dy, dx, dy)
    cx, cy = _dentro(destino, pagina)
    dx, dy = dx + cx, dy + cy
    tipo = annot.type[0]
    if tipo == pymupdf.PDF_ANNOT_LINE:
        (x0, y0), (x1, y1) = annot.vertices[:2]
        nueva = pagina.add_line_annot((x0 + dx, y0 + dy), (x1 + dx, y1 + dy))
        nueva.set_line_ends(*annot.line_ends)
    elif tipo == pymupdf.PDF_ANNOT_INK:
        trazos = [[(x + dx, y + dy) for x, y in trazo] for trazo in annot.vertices]
        nueva = pagina.add_ink_annot(trazos)
    else:
        _poner_rect(annot, pymupdf.Rect(annot.rect) + (dx, dy, dx, dy))
        return annot.xref
    _copiar_estilo(annot, nueva)
    nueva.update()
    xref_nueva = nueva.xref
    pagina.delete_annot(annot)
    return xref_nueva


def redimensionar_anotacion(pagina: pymupdf.Page, xref: int, rect: pymupdf.Rect) -> int:
    annot = pagina.load_annot(xref)
    if not es_redimensionable(annot):
        raise ValueError("Esta anotación no se puede redimensionar")
    rect = pymupdf.Rect(rect)
    rect.normalize()
    if rect.width < TAM_MINIMO:
        rect.x1 = rect.x0 + TAM_MINIMO
    if rect.height < TAM_MINIMO:
        rect.y1 = rect.y0 + TAM_MINIMO
    _poner_rect(annot, rect)
    return annot.xref


# ----------------------------------------------------------------------------
# Texto original
# ----------------------------------------------------------------------------
SANS = ("helvetica", "arial", "sans", "verdana", "calibri", "tahoma", "segoe", "roboto", "gothic", "frutiger",
        "futura", "myriad", "univers", "lato", "open")
SERIF = ("times", "roman", "georgia", "garamond", "cambria", "palatino", "book", "minion", "serif", "baskerville")
MONO = ("courier", "mono", "consol", "menlo", "typewriter")


def fuente_estandar(nombre: str, flags: int) -> str:
    """Fuente estándar de PDF más parecida a la original: primero por su nombre y, si no lo dice,
    por sus marcas (que para fuentes como Helvetica a veces vienen mal: dicen «con remates»)."""
    nombre = nombre.lower().split("+")[-1]  # «ABCDEF+Arial-Bold» → «arial-bold»
    if any(m in nombre for m in MONO):
        base = "co"
    elif any(m in nombre for m in SANS) and "serif" not in nombre.replace("sans", ""):
        base = "he"
    elif any(m in nombre for m in SERIF):
        base = "ti"
    elif flags & 8:
        base = "co"
    elif flags & 4:
        base = "ti"
    else:
        base = "he"
    negrita = bool(flags & 16) or "bold" in nombre or "black" in nombre or "heavy" in nombre
    cursiva = bool(flags & 2) or "italic" in nombre or "oblique" in nombre
    if negrita and cursiva:
        return base + "bi"
    if negrita:
        return base + "bo"
    if cursiva:
        return base + "it"
    return {"he": "helv", "ti": "tiro", "co": "cour"}[base]


def _zona_a_borrar(rect: pymupdf.Rect) -> pymupdf.Rect:
    """Un poco más baja que la línea, para no tocar las de encima y debajo."""
    r = pymupdf.Rect(rect)
    margen = r.height * 0.15
    r.y0 += margen
    r.y1 -= margen
    return r


def tamano_real(span: dict) -> float:
    """Tamaño de letra según la altura del texto: si se ha estirado a lo ancho, PyMuPDF da un tamaño
    mayor y, al moverlo varias veces, iría creciendo."""
    asc, desc = span.get("ascender"), span.get("descender")
    bbox = span.get("bbox")
    if bbox and asc is not None and desc is not None and asc - desc > 0.3:
        estimado = (bbox[3] - bbox[1]) / (asc - desc)
        if 0.5 * span["size"] <= estimado <= 1.05 * span["size"]:
            return estimado
    return span["size"]


def escribir(pagina: pymupdf.Page, origen: pymupdf.Point, texto: str, fuente: str, tamano: float,
             color: tuple, angulo: int = 0, ancho: float | None = None) -> None:
    """Escribe texto con una fuente estándar (admite «€», «ñ», tildes…). Con `ancho`, lo estira o
    encoge (como mucho un 30 %) para que ocupe ese ancho."""
    if angulo != 0:  # texto girado (poco frecuente): como antes
        pagina.insert_text(origen, texto, fontname=fuente, fontsize=tamano, color=color,
                           rotate=angulo if angulo in (90, 180, 270, -90) else 0)
        return
    letra = pymupdf.Font(fuente)
    morph = None
    if ancho:
        actual = letra.text_length(texto, fontsize=tamano)
        if actual > 0:
            escala = max(0.7, min(1.3, ancho / actual))
            if abs(escala - 1) > 0.01:
                morph = (origen, pymupdf.Matrix(escala, 1))
    escritor = pymupdf.TextWriter(pagina.rect)
    escritor.append(origen, texto, font=letra, fontsize=tamano)
    escritor.write_text(pagina, color=color, morph=morph)


def color_rgb(c: int) -> tuple[float, float, float]:
    return ((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255


def mover_lineas(pagina: pymupdf.Page, lineas: list[dict], dx: float, dy: float) -> list[pymupdf.Rect]:
    """Mueve líneas de texto original (de VistaPDF._lineas_de). Devuelve dónde han quedado."""
    if not lineas:
        return []
    total = pymupdf.Rect(lineas[0]["rect"])
    for linea in lineas[1:]:
        total |= linea["rect"]
    cx, cy = _dentro(total + (dx, dy, dx, dy), pagina)
    dx, dy = dx + cx, dy + cy
    for linea in lineas:
        pagina.add_redact_annot(_zona_a_borrar(linea["rect"]), fill=False)
    pagina.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    destinos = []
    for linea in lineas:
        ddx, ddy = linea.get("dir", (1, 0))
        angulo = round(math.degrees(math.atan2(-ddy, ddx)))
        for span in linea.get("spans") or [linea]:
            if not span["texto"].strip():
                continue
            escribir(pagina, pymupdf.Point(span["origen"]) + (dx, dy), span["texto"],
                     fuente_estandar(span["fuente"], span["flags"]), span["tamano"], color_rgb(span["color"]),
                     angulo, span.get("ancho"))
        destinos.append(pymupdf.Rect(linea["rect"]) + (dx, dy, dx, dy))
    return destinos
