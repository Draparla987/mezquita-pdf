"""Valida con pyHanko los PDF firmados por la versión web (solo lectura).

Uso (con el entorno virtual de la app de escritorio):
    cd <raíz del repositorio>
    .venv/bin/python web/pruebas/validar_pyhanko.py web/pruebas/salida

Para cada firma muestra:
  - el resultado de `visor.firma_digital.verificar_firmas` (la verificación de la app de
    escritorio): integra, cubre_todo y resumen;
  - el detalle de pyHanko: intact/valid, cobertura, nivel de modificaciones posteriores
    (`modification_level`) y si esas modificaciones están permitidas (`docmdp_ok`),
    además de los atributos CMS y el /SubFilter.
"""

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pyhanko.pdf_utils.reader import PdfFileReader  # noqa: E402
from pyhanko.sign.validation import validate_pdf_signature  # noqa: E402
from pyhanko_certvalidator import ValidationContext  # noqa: E402

from visor import firma_digital as fd  # noqa: E402

logging.disable(logging.CRITICAL)

ARCHIVOS = ["firmado.pdf", "firmado_dos_veces.pdf", "tres_firmas.pdf", "xref_stream_firmado.pdf"]
# En estos archivos, entre firma y firma solo se añaden firmas: pyHanko debe aceptarlo
# (docmdp_ok=True). En «tres_firmas.pdf» se añaden además anotaciones después de firmar;
# pyHanko no reconoce ese tipo de cambio en su análisis de diferencias (lo clasifica como
# «OTHER»), aunque la firma siga siendo íntegra, igual que con la app de escritorio.
ESTRICTOS = {"firmado.pdf", "firmado_dos_veces.pdf", "xref_stream_firmado.pdf"}


def detalle(datos: bytes, estricto: bool) -> list[str]:
    lineas = []
    lector = PdfFileReader(io.BytesIO(datos), strict=False)
    contexto = ValidationContext(allow_fetching=False)
    for firma in lector.embedded_regular_signatures:
        estado = validate_pdf_signature(firma, contexto)
        attrs = [a["type"].native for a in firma.signer_info["signed_attrs"]]
        subfilter = firma.sig_object.get("/SubFilter")
        nivel = estado.modification_level.name if estado.modification_level is not None else "-"
        lineas.append(
            f"    pyHanko {firma.field_name}: intact={estado.intact} valid={estado.valid} "
            f"coverage={estado.coverage.name} modification_level={nivel} docmdp_ok={estado.docmdp_ok} "
            f"subfilter={subfilter} md={estado.md_algorithm} attrs={attrs}"
        )
        if not (estado.intact and estado.valid):
            lineas.append("    FALLO: la firma no es íntegra")
        elif not estado.docmdp_ok:
            if estricto:
                lineas.append("    FALLO: pyHanko considera no permitidos los cambios posteriores")
            else:
                lineas.append(
                    "    AVISO: firma íntegra; pyHanko marca como «OTHER» las anotaciones añadidas "
                    "después (su análisis de diferencias no contempla anotaciones)"
                )
    return lineas


def main() -> None:
    carpeta = Path(sys.argv[1] if len(sys.argv) > 1 else "web/pruebas/salida")
    for nombre in ARCHIVOS:
        ruta = carpeta / nombre
        if not ruta.exists():
            print(f"  {nombre}: no existe")
            continue
        datos = ruta.read_bytes()
        resultados = fd.verificar_firmas(datos)
        print(f"  {nombre}:")
        print("    verificar_firmas →", [(r.integra, r.cubre_todo, r.resumen) for r in resultados])
        if not resultados or not all(r.integra for r in resultados):
            print("    FALLO: alguna firma no es íntegra")
        for linea in detalle(datos, nombre in ESTRICTOS):
            print(linea)


if __name__ == "__main__":
    main()
