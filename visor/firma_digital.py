"""Firma electrónica con certificado digital (PAdES) y verificación de firmas.

Usa pyHanko. El certificado se carga desde un fichero PKCS#12 (.p12 / .pfx),
que es el formato en el que se exportan los certificados de la FNMT, DNIe, etc.
"""

from __future__ import annotations

import io
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime

from asn1crypto import pem as pem_armor
from asn1crypto import x509 as asn1_x509
from PIL import Image, ImageDraw, ImageFont
from pyhanko import stamp
from pyhanko.pdf_utils import images, layout
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields, signers, timestamps
from pyhanko.sign.fields import SigSeedSubFilter
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko_certvalidator import ValidationContext


logging.getLogger("pyhanko").setLevel(logging.CRITICAL)
logging.getLogger("pyhanko_certvalidator").setLevel(logging.CRITICAL)

_FUENTES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",  # macOS
    "C:/Windows/Fonts/arial.ttf",  # Windows
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
]
_FUENTES_NEGRITA = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


class ErrorFirma(Exception):
    pass


def _fuente(candidatas: list[str], tam: int) -> ImageFont.ImageFont:
    for ruta in candidatas:
        if os.path.exists(ruta):
            return ImageFont.truetype(ruta, tam)
    return ImageFont.load_default(size=tam)


OPACIDAD_MARCA = 0.13  # intensidad del arco de fondo


def _marca_agua(alto_px: int) -> Image.Image | None:
    """El arco de la Mezquita para el fondo del sello (necesita Qt; sin él, el sello va sin marca)."""
    try:
        from PySide6.QtCore import QBuffer, QIODevice
        from PySide6.QtGui import QGuiApplication

        from . import tema
        if QGuiApplication.instance() is None:
            return None
        qimg = tema.imagen_marca_agua(alto_px)
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        qimg.save(buf, "PNG")
        return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")
    except Exception:
        return None


def _recortar_trazo(img: Image.Image) -> Image.Image:
    """Quita el margen transparente (o blanco) de la rúbrica para que ocupe su sitio de verdad."""
    alfa = img.getchannel("A")
    caja = alfa.point(lambda a: 255 if a > 24 else 0).getbbox()
    if caja is None or alfa.getextrema() == (255, 255):  # imagen opaca: recortar el blanco
        gris = img.convert("L").point(lambda v: 255 if v < 235 else 0)
        caja = gris.getbbox()
    return img.crop(caja) if caja else img


def componer_sello(
    *, ancho_pt: float, alto_pt: float, titular: str, motivo: str, lugar: str,
    rubrica_png: bytes | None, marca: bool = True,
) -> Image.Image:
    """Apariencia visible de la firma, del tamaño exacto del recuadro dibujado.

    Rúbrica a la izquierda (a toda la altura), datos a la derecha con la letra más grande que
    quepa y, de fondo, el arco de la Mezquita muy suave (como el logotipo de Acrobat).
    """
    escala = 6  # resolución alta para que se vea nítido al ampliar
    w, h = max(int(ancho_pt * escala), 60), max(int(alto_pt * escala), 30)
    margen = max(2, int(min(w, h) * 0.05))
    img = Image.new("RGBA", (w, h), (255, 255, 255, 0))

    if marca:
        arco = _marca_agua(int(h * 0.94))
        if arco is not None:
            arco.putalpha(arco.getchannel("A").point(lambda a: int(a * OPACIDAD_MARCA)))
            img.alpha_composite(arco, ((w - arco.width) // 2, (h - arco.height) // 2))

    dibujo = ImageDraw.Draw(img)
    lineas = [("Firmado digitalmente por:", False), (titular, True),
              (f"Fecha: {datetime.now().astimezone().strftime('%d/%m/%Y %H:%M:%S')}", False)]
    if motivo:
        lineas.append((f"Motivo: {motivo}", False))
    if lugar:
        lineas.append((f"Lugar: {lugar}", False))
    interlinea = 1.18

    def letra_que_cabe(ancho: float, alto: float) -> int:
        """La letra más grande con la que todas las líneas caben en ancho × alto."""
        def cabe(tam: int) -> bool:
            normal, negrita = _fuente(_FUENTES, tam), _fuente(_FUENTES_NEGRITA, tam)
            mayor = max(dibujo.textlength(t, font=negrita if b else normal) for t, b in lineas)
            return mayor <= ancho and tam * interlinea * len(lineas) <= alto
        bajo, alto_max = 6, max(7, int(alto / len(lineas)))
        while bajo < alto_max:
            medio = (bajo + alto_max + 1) // 2
            if cabe(medio):
                bajo = medio
            else:
                alto_max = medio - 1
        return bajo

    def escribir(x: float, y: float, ancho: float, tam: int, centrado: bool) -> None:
        normal, negrita = _fuente(_FUENTES, tam), _fuente(_FUENTES_NEGRITA, tam)
        y += tam * (interlinea - 1) / 2
        for texto, es_negrita in lineas:
            fuente = negrita if es_negrita else normal
            dx = (ancho - dibujo.textlength(texto, font=fuente)) / 2 if centrado else 0
            dibujo.text((x + dx, y), texto, fill=(20, 20, 20, 255), font=fuente)
            y += tam * interlinea

    if not rubrica_png:
        tam = letra_que_cabe(w - 2 * margen, h - 2 * margen)
        escribir(margen, (h - tam * interlinea * len(lineas)) / 2, w - 2 * margen, tam, False)
        return img

    # Con rúbrica: se prueban dos disposiciones (al lado o encima de los datos) y varios repartos,
    # y se queda la que hace más grandes a la vez la rúbrica y el texto.
    rubrica = _recortar_trazo(Image.open(io.BytesIO(rubrica_png)).convert("RGBA"))
    mejor = None
    for modo in ("lado", "encima"):
        for parte in (0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65):
            if modo == "lado":
                caja_r = (int(w * parte) - margen, h - 2 * margen)
            else:
                caja_r = (w - 2 * margen, int(h * parte) - margen)
            factor = min(caja_r[0] / rubrica.width, caja_r[1] / rubrica.height)
            rw, rh = rubrica.width * factor, rubrica.height * factor
            if modo == "lado":
                texto_w, texto_h = w - (margen + rw + 2 * margen) - margen, h - 2 * margen
            else:
                texto_w, texto_h = w - 2 * margen, h - (margen + rh + margen) - margen
            if texto_w < 20 or texto_h < 20:
                continue
            tam = letra_que_cabe(texto_w, texto_h)
            # Proporción del alto que ocupa cada uno: se busca que el menor sea lo mayor posible
            puntuacion = min(tam * interlinea * len(lineas) / h, rh / h)
            if mejor is None or puntuacion > mejor[0]:
                mejor = (puntuacion, modo, factor, tam)
    _, modo, factor, tam = mejor
    rubrica = rubrica.resize((max(1, int(rubrica.width * factor)), max(1, int(rubrica.height * factor))),
                             Image.LANCZOS)
    bloque = tam * interlinea * len(lineas)
    gris, grosor = (150, 150, 150, 255), max(1, escala // 3)
    if modo == "lado":
        img.alpha_composite(rubrica, (margen, (h - rubrica.height) // 2))
        separador = margen + rubrica.width + margen
        dibujo.line([(separador, h * 0.12), (separador, h * 0.88)], fill=gris, width=grosor)
        texto_x = separador + margen
        escribir(texto_x, (h - bloque) / 2, w - texto_x - margen, tam, False)
    else:
        hueco = (h - rubrica.height - bloque - 2 * margen) / 3  # reparte el espacio que sobra
        y = max(margen, hueco + margen / 2)
        img.alpha_composite(rubrica, ((w - rubrica.width) // 2, int(y)))
        y += rubrica.height + margen / 2 + hueco / 2
        dibujo.line([(w * 0.2, y), (w * 0.8, y)], fill=gris, width=grosor)
        escribir(margen, y + margen / 2, w - 2 * margen, tam, True)
    return img


_raices_cache: list | None = None


def raices_confianza_sistema() -> list:
    """Certificados raíz del sistema (macOS incluye AC RAIZ FNMT-RCM, ACCV, Izenpe...)."""
    global _raices_cache
    if _raices_cache is not None:
        return _raices_cache
    raices = []
    if sys.platform == "win32":
        from . import almacen_windows
        raices = almacen_windows.raices()
    if sys.platform == "darwin":
        try:
            pem = subprocess.run(
                ["security", "find-certificate", "-a", "-p",
                 "/System/Library/Keychains/SystemRootCertificates.keychain"],
                capture_output=True, check=True, timeout=20,
            ).stdout
            for _, _, der in pem_armor.unarmor(pem, multiple=True):
                try:
                    raices.append(asn1_x509.Certificate.load(der))
                except Exception:
                    pass
        except Exception:
            pass
    _raices_cache = raices
    return raices


@dataclass
class InfoCertificado:
    titular: str
    emisor: str
    valido_desde: datetime
    valido_hasta: datetime
    numero_serie: str


def cargar_certificado(ruta_p12: str, contrasena: str) -> signers.SimpleSigner:
    try:
        signer = signers.SimpleSigner.load_pkcs12(
            ruta_p12, passphrase=contrasena.encode("utf-8") if contrasena else None
        )
    except Exception as exc:  # pyHanko lanza distintos tipos según el fallo
        raise ErrorFirma(f"No se pudo abrir el certificado: {exc}") from exc
    if signer is None:
        raise ErrorFirma("No se pudo abrir el certificado. ¿La contraseña es correcta?")
    return signer


def info_certificado(signer: signers.SimpleSigner) -> InfoCertificado:
    cert = signer.signing_cert
    validity = cert["tbs_certificate"]["validity"]
    return InfoCertificado(
        titular=_nombre_legible(cert.subject),
        emisor=_nombre_legible(cert.issuer),
        valido_desde=validity["not_before"].native,
        valido_hasta=validity["not_after"].native,
        numero_serie=format(cert.serial_number, "X"),
    )


def _nombre_legible(name) -> str:
    datos = name.native
    for clave in ("common_name", "organization_name"):
        if datos.get(clave):
            return str(datos[clave])
    return name.human_friendly


def firmar_pdf(
    pdf_bytes: bytes,
    signer: signers.SimpleSigner,
    *,
    pagina: int | None = None,
    caja: tuple[float, float, float, float] | None = None,
    imagen_png: bytes | None = None,
    motivo: str = "",
    lugar: str = "",
    contacto: str = "",
    url_sello_tiempo: str | None = None,
    certificar: bool = False,
) -> bytes:
    """Firma el PDF y devuelve los bytes del documento firmado.

    `caja` va en coordenadas PDF (origen abajo-izquierda): (x0, y0, x1, y1).
    Si `pagina` o `caja` son None la firma es invisible.
    """
    writer = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes), strict=False)

    existentes = {
        nombre for nombre, *_ in fields.enumerate_sig_fields(writer, filled_status=None)
    }
    n = 1
    while f"Firma{n}" in existentes:
        n += 1
    nombre_campo = f"Firma{n}"

    titular = info_certificado(signer).titular
    meta = signers.PdfSignatureMetadata(
        field_name=nombre_campo,
        md_algorithm="sha256",
        reason=motivo or None,
        location=lugar or None,
        contact_info=contacto or None,
        name=titular,
        subfilter=SigSeedSubFilter.PADES,
        certify=certificar,
    )

    spec = None
    estilo = None
    if pagina is not None and caja is not None:
        x0, y0, x1, y1 = (int(round(v)) for v in caja)
        spec = fields.SigFieldSpec(sig_field_name=nombre_campo, on_page=pagina, box=(x0, y0, x1, y1))
        imagen_sello = componer_sello(
            ancho_pt=x1 - x0,
            alto_pt=y1 - y0,
            titular=titular,
            motivo=motivo,
            lugar=lugar,
            rubrica_png=imagen_png,
        )
        estilo = stamp.StaticStampStyle(
            background=images.PdfImage(imagen_sello),
            background_opacity=1.0,
            border_width=0,
            # Sin el margen de 5 pt de pyHanko: el sello ocupa exactamente el recuadro dibujado
            background_layout=layout.SimpleBoxLayoutRule(
                x_align=layout.AxisAlignment.ALIGN_MID, y_align=layout.AxisAlignment.ALIGN_MID,
                margins=layout.Margins(0, 0, 0, 0), inner_content_scaling=layout.InnerScaling.STRETCH_FILL),
        )
    else:
        spec = fields.SigFieldSpec(sig_field_name=nombre_campo)

    tsa = timestamps.HTTPTimeStamper(url_sello_tiempo, timeout=15) if url_sello_tiempo else None

    pdf_signer = signers.PdfSigner(
        meta, signer=signer, timestamper=tsa, stamp_style=estilo, new_field_spec=spec
    )
    salida = io.BytesIO()
    try:
        pdf_signer.sign_pdf(writer, output=salida)
    except Exception as exc:
        causa = exc
        while causa is not None:
            if type(causa).__name__ == "ErrorLlavero":
                raise ErrorFirma(str(causa)) from exc
            causa = causa.__cause__ or causa.__context__
        raise ErrorFirma(f"Error al firmar: {exc}") from exc
    return salida.getvalue()


@dataclass
class ResultadoVerificacion:
    campo: str
    firmante: str
    emisor: str
    fecha: str
    integra: bool
    confiable: bool
    cubre_todo: bool
    resumen: str


def verificar_firmas(pdf_bytes: bytes) -> list[ResultadoVerificacion]:
    reader = PdfFileReader(io.BytesIO(pdf_bytes), strict=False)
    resultados = []
    # Sin raíces de confianza configuradas: comprobamos integridad y mostramos
    # quién firmó; la "confianza" solo será True si la cadena se valida.
    contexto = ValidationContext(
        trust_roots=raices_confianza_sistema() or None, allow_fetching=False
    )
    for firma in reader.embedded_regular_signatures:
        try:
            estado = validate_pdf_signature(firma, contexto)
            cert = estado.signing_cert
            fecha = firma.self_reported_timestamp
            if estado.timestamp_validity is not None:
                fecha = estado.timestamp_validity.timestamp
            cubre_todo = estado.coverage is not None and estado.coverage.name == "ENTIRE_FILE"
            if estado.intact and estado.valid:
                if cubre_todo:
                    resumen = "La firma es válida y el documento no se ha modificado desde que se firmó."
                else:
                    resumen = (
                        "La firma es válida, pero el documento tiene cambios posteriores "
                        "(p. ej., otras firmas o anotaciones añadidas después)."
                    )
            else:
                resumen = "LA FIRMA NO ES VÁLIDA: el documento se ha alterado o la firma está dañada."
            resultados.append(
                ResultadoVerificacion(
                    campo=firma.field_name,
                    firmante=_nombre_legible(cert.subject),
                    emisor=_nombre_legible(cert.issuer),
                    fecha=fecha.strftime("%d/%m/%Y %H:%M:%S") if fecha else "desconocida",
                    integra=bool(estado.intact and estado.valid),
                    confiable=bool(estado.trusted),
                    cubre_todo=cubre_todo,
                    resumen=resumen,
                )
            )
        except Exception as exc:
            resultados.append(
                ResultadoVerificacion(
                    campo=getattr(firma, "field_name", "?"),
                    firmante="?", emisor="?", fecha="?",
                    integra=False, confiable=False, cubre_todo=False,
                    resumen=f"No se pudo verificar la firma: {exc}",
                )
            )
    return resultados


def tiene_firmas(pdf_bytes: bytes) -> bool:
    try:
        reader = PdfFileReader(io.BytesIO(pdf_bytes), strict=False)
        return len(reader.embedded_regular_signatures) > 0
    except Exception:
        return False
