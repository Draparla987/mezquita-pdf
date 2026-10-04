"""Prepara las imágenes maestras de los iconos de la PWA a partir de recursos/icono.png.

El icono de escritorio tiene margen transparente y esquinas redondeadas (estilo macOS).
iOS aplica su propia máscara y rellena de negro lo transparente, así que aquí se crean:
  - maestro_lleno.png      (824×824) el azulejo a sangre, sin transparencias
  - maestro_maskable.png   (1024×1024) el dibujo dentro de la «zona segura» (80 %)
El degradado del fondo es el mismo del icono (#A3263A → #5E0F1C), sin costuras.
Después, generar_iconos.sh reescala con `sips -z`.
"""
import sys
from PIL import Image

origen, destino = sys.argv[1], sys.argv[2]
A, B = (0xA3, 0x26, 0x3A), (0x5E, 0x0F, 0x1C)


def degradado(ancho, alto, y0, y1):
    img = Image.new("RGBA", (ancho, alto))
    px = img.load()
    for y in range(alto):
        t = min(1.0, max(0.0, (y - y0) / max(1, (y1 - y0))))
        c = tuple(round(A[i] + (B[i] - A[i]) * t) for i in range(3)) + (255,)
        for x in range(ancho):
            px[x, y] = c
    return img


icono = Image.open(origen).convert("RGBA")
assert icono.size == (1024, 1024), icono.size
# Azulejo del icono: de 100 a 924 px (ver visor/tema.py, imagen_icono_app).
azulejo = icono.crop((100, 100, 924, 924))
lleno = degradado(824, 824, 0, 824)
lleno.alpha_composite(azulejo)
lleno.convert("RGB").save(f"{destino}/maestro_lleno.png")

# Maskable: el azulejo reducido al 78 % y centrado sobre el mismo degradado.
lado = round(1024 * 0.78)
off = (1024 - lado) // 2
fondo = degradado(1024, 1024, off, off + lado)
fondo.alpha_composite(lleno.resize((lado, lado), Image.LANCZOS), (off, off))
fondo.convert("RGB").save(f"{destino}/maestro_maskable.png")
print("maestros generados")
