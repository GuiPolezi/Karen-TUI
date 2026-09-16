"""Gera o ícone do executável (packaging/cmd-all-in-one.ico) sem dependência nenhuma.

Desenha um quadrado arredondado com o fundo do tema `carbon` e um prompt `>_` no accent
ciano, nos tamanhos que o Windows usa (16, 32, 48, 64, 128, 256). Cada tamanho entra no
.ico como PNG, escrito na mão com zlib + struct — nada de Pillow, para o build não
precisar de mais um pacote.

Uso: python scripts/gerar_icone.py [destino.ico]
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "packaging" / "cmd-all-in-one.ico"
TAMANHOS = (16, 32, 48, 64, 128, 256)

FUNDO = (0x15, 0x17, 0x1A, 255)     # surface do tema carbon
BORDA = (0x2A, 0x2E, 0x35, 255)
ACCENT = (0x4F, 0xC1, 0xE9, 255)
TRANSPARENTE = (0, 0, 0, 0)

Pixel = tuple[int, int, int, int]


def _dentro_do_quadrado(x: float, y: float, lado: float, raio: float) -> bool:
    """Ponto dentro de um quadrado de cantos arredondados que ocupa [0, lado]?"""
    cx = min(max(x, raio), lado - raio)
    cy = min(max(y, raio), lado - raio)
    return (x - cx) ** 2 + (y - cy) ** 2 <= raio ** 2


def _na_linha(x: float, y: float, x1: float, y1: float, x2: float, y2: float, grossura: float) -> bool:
    """Distância do ponto ao segmento (x1,y1)-(x2,y2) menor que meia grossura?"""
    dx, dy = x2 - x1, y2 - y1
    comprimento = dx * dx + dy * dy
    t = 0.0 if comprimento == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / comprimento))
    px, py = x1 + t * dx, y1 + t * dy
    return (x - px) ** 2 + (y - py) ** 2 <= (grossura / 2) ** 2


def desenhar(tamanho: int) -> list[Pixel]:
    """Pixels RGBA do ícone, linha a linha. Amostragem 2x2 para suavizar as bordas."""
    lado = float(tamanho)
    raio = lado * 0.22
    margem = lado * 0.06
    # o prompt ">_" ocupa o miolo do quadrado
    chevron = (lado * 0.30, lado * 0.32, lado * 0.50, lado * 0.50, lado * 0.30, lado * 0.68)
    sublinha = (lado * 0.56, lado * 0.68, lado * 0.74, lado * 0.68)
    grossura = max(lado * 0.085, 1.4)

    pixels: list[Pixel] = []
    for y in range(tamanho):
        for x in range(tamanho):
            amostras: list[Pixel] = []
            for sy in (0.25, 0.75):
                for sx in (0.25, 0.75):
                    px, py = x + sx, y + sy
                    if not _dentro_do_quadrado(px - margem, py - margem, lado - 2 * margem, raio):
                        amostras.append(TRANSPARENTE)
                        continue
                    if (_na_linha(px, py, chevron[0], chevron[1], chevron[2], chevron[3], grossura)
                            or _na_linha(px, py, chevron[2], chevron[3], chevron[4], chevron[5], grossura)
                            or _na_linha(px, py, *sublinha, grossura)):
                        amostras.append(ACCENT)
                    elif not _dentro_do_quadrado(px - margem - 1, py - margem - 1,
                                                 lado - 2 * margem - 2, raio):
                        amostras.append(BORDA)
                    else:
                        amostras.append(FUNDO)
            pixels.append(tuple(sum(c[i] for c in amostras) // 4 for i in range(4)))  # type: ignore[arg-type]
    return pixels


def png(tamanho: int, pixels: list[Pixel]) -> bytes:
    """PNG RGBA de 8 bits, sem filtro por linha (tipo 0)."""
    linhas = bytearray()
    for y in range(tamanho):
        linhas.append(0)
        for x in range(tamanho):
            linhas.extend(bytes(pixels[y * tamanho + x]))

    def bloco(tipo: bytes, dados: bytes) -> bytes:
        corpo = tipo + dados
        return struct.pack(">I", len(dados)) + corpo + struct.pack(">I", zlib.crc32(corpo) & 0xFFFFFFFF)

    cabecalho = struct.pack(">IIBBBBB", tamanho, tamanho, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + bloco(b"IHDR", cabecalho)
            + bloco(b"IDAT", zlib.compress(bytes(linhas), 9))
            + bloco(b"IEND", b""))


def dib(tamanho: int, pixels: list[Pixel]) -> bytes:
    """Imagem clássica (BITMAPINFOHEADER + BGRA de baixo para cima + máscara AND).

    Tamanho pequeno vai como DIB, não como PNG: é o formato que todo mundo lê, inclusive
    compiladores antigos de instalador e caixas de diálogo legadas do Windows.
    """
    cabecalho = struct.pack("<IiiHHIIiiII", 40, tamanho, tamanho * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    corpo = bytearray()
    for y in range(tamanho - 1, -1, -1):          # DIB é de baixo para cima
        for x in range(tamanho):
            r, g, b, a = pixels[y * tamanho + x]
            corpo.extend((b, g, r, a))            # e em BGRA
    mascara = bytes((((tamanho + 31) // 32) * 4) * tamanho)  # tudo zero: a transparência é o alfa
    return cabecalho + bytes(corpo) + mascara


def ico(tamanhos=TAMANHOS, limite_png: int = 64) -> bytes:
    """Junta as imagens num .ico: DIB até `limite_png`, PNG acima (256x256 só cabe assim)."""
    imagens = [png(t, desenhar(t)) if t > limite_png else dib(t, desenhar(t)) for t in tamanhos]
    cabecalho = struct.pack("<HHH", 0, 1, len(imagens))
    offset = len(cabecalho) + 16 * len(imagens)
    entradas = bytearray()
    for tamanho, dados in zip(tamanhos, imagens):
        entradas.extend(struct.pack("<BBBBHHII", tamanho % 256, tamanho % 256, 0, 0, 1, 32,
                                    len(dados), offset))
        offset += len(dados)
    return cabecalho + bytes(entradas) + b"".join(imagens)


def main() -> int:
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else DESTINO
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(ico())
    print(f"{destino} ({destino.stat().st_size / 1024:.1f} KB, {len(TAMANHOS)} tamanhos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
