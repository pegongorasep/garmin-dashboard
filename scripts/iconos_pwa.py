"""Genera los íconos PNG de la PWA (logo de 5 barras) sin librerías: `python scripts/iconos_pwa.py`."""
import struct
import sys
import zlib
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
FONDO = (0x11, 0x1a, 0x24)   # --page
BARRAS = [(6, 38, 16, (0x39, 0x87, 0xe5)), (17, 30, 24, (0x19, 0x9e, 0x70)), (28, 22, 32, (0x90, 0x85, 0xe9)),
          (39, 15, 39, (0xe5, 0x63, 0x2f)), (50, 8, 46, (0xc0, 0x41, 0x7f))]   # x, y, alto, color (viewBox 64)


def dentro(px, py, x, y, w, h, r):
    cx = min(max(px, x + r), x + w - r)
    cy = min(max(py, y + r), y + h - r)
    return (px - cx) ** 2 + (py - cy) ** 2 <= r * r


def pintar(tam, escala):
    """escala: fracción del lienzo que ocupa el logo (maskable usa menos)."""
    ss = 3
    n = tam * ss
    lado = 64 / escala
    off = (lado - 64) / 2
    filas = []
    for j in range(tam):
        fila = bytearray()
        for i in range(tam):
            acc = [0, 0, 0]
            for sj in range(ss):
                for si in range(ss):
                    px = (i * ss + si + .5) / n * lado - off
                    py = (j * ss + sj + .5) / n * lado - off
                    c = FONDO
                    for x, y, h, col in BARRAS:
                        if dentro(px, py, x, y, 8, h, 4):
                            c = col
                    for k in range(3):
                        acc[k] += c[k]
            fila += bytes(v // (ss * ss) for v in acc)
        filas.append(b"\x00" + bytes(fila))
    return filas


def png(tam, escala):
    def trozo(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    datos = zlib.compress(b"".join(pintar(tam, escala)), 9)
    return b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", tam, tam, 8, 2, 0, 0, 0)) + trozo(b"IDAT", datos) + trozo(b"IEND", b"")


if __name__ == "__main__":
    for nombre, tam, esc in [("icono-192.png", 192, .8), ("icono-512.png", 512, .8),
                             ("icono-maskable-512.png", 512, .55), ("apple-touch-icon.png", 180, .8)]:
        (SITE / nombre).write_bytes(png(tam, esc))
        print("escrito", nombre, file=sys.stderr)
