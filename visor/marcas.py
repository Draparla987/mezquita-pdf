"""Marcas de agua para el fondo del sello de la firma con certificado.

Además del arco de la Mezquita, cada usuario puede añadir los logotipos de su organización. Se
guardan ya limpios (fondo transparente y sin márgenes) en la carpeta de datos, junto a las firmas
manuscritas, así que las actualizaciones de la app no los tocan.
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageChops, ImageMath

MEZQUITA = "mezquita"  # el arco de la app (predeterminada)
NINGUNA = ""  # sello sin marca de agua
AJUSTE = "firma/marca"  # la elegida en Firmar → Marca de agua del sello
TAM_MAX = 1600  # px del lado mayor: de sobra para el sello
FILTRO = "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)"


def carpeta() -> Path:
    from .dialogos import carpeta_datos
    destino = carpeta_datos() / "marcas"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def guardadas() -> list[Path]:
    return sorted(carpeta().glob("*.png"), key=lambda p: p.stem.lower())


def limpiar(img: Image.Image) -> Image.Image:
    """Fondo blanco → transparente (si la imagen no lo trae ya), sin márgenes y de tamaño razonable.

    El blanco se quita «a lo GIMP» (color a transparencia): cada píxel pierde la parte de blanco que
    tiene y conserva su color, así los grises y los tonos claros del logotipo no se aclaran.
    """
    img = img.convert("RGBA")
    if img.getchannel("A").getextrema()[0] == 255:  # opaca
        r, g, b = (ImageChops.invert(c) for c in img.convert("RGB").split())
        oscuridad = ImageChops.lighter(ImageChops.lighter(r, g), b)  # 0 = blanco puro
        canales = [
            ImageMath.lambda_eval(
                lambda e: 255 - e["c"] * 255 / (e["a"] + (e["a"] == 0)), c=c, a=oscuridad).convert("L")
            for c in (r, g, b)
        ]
        # Lo casi blanco (ruido de la compresión JPEG) pasa a transparente del todo
        alfa = oscuridad.point(lambda v: 0 if v < 10 else min(255, (v - 10) * 255 // 235))
        img = Image.merge("RGBA", (*canales, alfa))
    caja = img.getchannel("A").point(lambda a: 255 if a > 12 else 0).getbbox()
    if caja:
        img = img.crop(caja)
    if max(img.size) > TAM_MAX:
        img.thumbnail((TAM_MAX, TAM_MAX), Image.LANCZOS)
    return img


def _nombre_libre(nombre: str) -> Path:
    base = re.sub(r'[\\/:*?"<>|]+', " ", nombre).strip() or "Logotipo"
    ruta, n = carpeta() / f"{base}.png", 2
    while ruta.exists():
        ruta, n = carpeta() / f"{base} {n}.png", n + 1
    return ruta


def anadir(origen: str | Path) -> Path:
    """Añade un logotipo (PNG, JPG…) como marca de agua. Devuelve dónde se ha guardado."""
    origen = Path(origen)
    try:
        img = limpiar(Image.open(origen))
    except Exception as exc:
        raise ValueError(f"No se ha podido abrir «{origen.name}» como imagen.") from exc
    destino = _nombre_libre(origen.stem)
    img.save(destino, "PNG")
    return destino


def elegida() -> str | None:
    """Marca de agua de todas las firmas: "mezquita", la ruta del logotipo o None (ninguna).

    Admite también solo el nombre del logotipo («IMIBIC»), que es como lo deja el instalador de una
    edición. Si el logotipo elegido ya no está, vuelve al arco."""
    from PySide6.QtCore import QSettings
    valor = QSettings().value(AJUSTE, MEZQUITA)
    valor = "" if valor is None else str(valor)
    if valor in (MEZQUITA, NINGUNA):
        return valor or None
    for ruta in guardadas():
        if str(ruta) == valor or ruta.stem == Path(valor).stem:
            return str(ruta)
    return MEZQUITA


def elegir(marca: str | None) -> None:
    from PySide6.QtCore import QSettings
    QSettings().setValue(AJUSTE, marca or NINGUNA)


def nombre(marca: str | None) -> str:
    if marca == MEZQUITA:
        return "Arco de Mezquita PDF"
    return Path(marca).stem if marca else "Sin marca de agua"


def quitar(ruta: str | Path) -> None:
    ruta = Path(ruta)
    if ruta.parent == carpeta():
        ruta.unlink(missing_ok=True)
