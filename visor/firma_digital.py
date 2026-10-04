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
from pyhanko.pdf_utils import images
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


def componer_sello(
    *, ancho_pt: float, alto_pt: float, titular: str, motivo: str, lugar: str,
    rubrica_png: bytes | None,
) -> Image.Image:
    """Dibuja la apariencia visible de la firma: rúbrica a la izquierda y datos a la derecha."""
    escala = 6  # resolución alta para que se vea nítido al ampliar
    w, h = max(int(ancho_pt * escala), 60), max(int(alto_pt * escala), 30)
    img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    dibujo = ImageDraw.Draw(img)

    zona_texto_x = 0
    if rubrica_png:
        rubrica = Image.open(io.BytesIO(rubrica_png)).convert("RGBA")
        caja_w, caja_h = int(w * 0.45), h
        rubrica.thumbnail((caja_w - 2 * escala, caja_h - 2 * escala), Image.LANCZOS)
        img.alpha_composite(
            rubrica, ((caja_w - rubrica.width) // 2, (caja_h - rubrica.height) // 2)
        )
        zona_texto_x = caja_w + 2 * escala
        dibujo.line([(caja_w, h * 0.12), (caja_w, h * 0.88)], fill=(120, 120, 120, 255), width=escala // 2)

    lineas = [("Firmado digitalmente por:", False), (titular, True),
              (f"Fecha: {datetime.now().astimezone().strftime('%d/%m/%Y %H:%M:%S %z')}", False)]
    if motivo:
        lineas.append((f"Motivo: {motivo}", False))
    if lugar:
        lineas.append((f"Lugar: {lugar}", False))

    disponible_w = w - zona_texto_x - 2 * escala
    tam = int(h / (len(lineas) * 1.3 + 0.5))
    while tam > 6:
        normal, negrita = _fuente(_FUENTES, tam), _fuente(_FUENTES_NEGRITA, tam)
        anchos = [dibujo.textlength(t, font=negrita if b else normal) for t, b in lineas]
        if max(anchos) <= disponible_w:
            break
        tam -= 2
    interlinea = tam * 1.25
    y = (h - interlinea * len(lineas)) / 2
    for texto, es_negrita in lineas:
        dibujo.text((zona_texto_x + escala, y), texto, fill=(20, 20, 20, 255),
                    font=negrita if es_negrita else normal)
        y += interlinea
    return img


_raices_cache: list | None = None


def raices_confianza_sistema() -> list:
    """Certificados raíz del sistema (macOS incluye AC RAIZ FNMT-RCM, ACCV, Izenpe...)."""
    global _raices_cache
    if _raices_cache is not None:
        return _raices_cache
    raices = []
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
