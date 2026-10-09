"""BCLIM (CTR layout image) <-> PNG, for the common PICA formats (8x8 Morton-tiled, bottom-up rows).

    python -I bclim.py topng <in.bclim> <out.png>
    python -I bclim.py frompng <in.png> <out.bclim> [--like <template.bclim>] [--format rgba8|rgba5551|la4|rgba4]

frompng keeps the template's width/height/format unless --format is given; the image is resized
(Lanczos) to the template size.
"""
import struct
import sys

from PIL import Image

FORMATS = {0: "l8", 1: "a8", 2: "la4", 3: "la8", 4: "hilo8", 5: "rgb565", 6: "rgb8", 7: "rgba5551",
           8: "rgba4", 9: "rgba8", 10: "etc1", 11: "etc1a4", 12: "l4", 13: "a4"}
BPP = {"l8": 8, "a8": 8, "la4": 8, "la8": 16, "hilo8": 16, "rgb565": 16, "rgb8": 24, "rgba5551": 16,
       "rgba4": 16, "rgba8": 32, "l4": 4, "a4": 4}
CODE = {v: k for k, v in FORMATS.items()}


def morton(x, y):
    m = 0
    for i in range(3):
        m |= ((x >> i) & 1) << (2 * i) | ((y >> i) & 1) << (2 * i + 1)
    return m


def pot(n):
    p = 8
    while p < n:
        p *= 2
    return p


def parse(data):
    imag = data.rfind(b"imag")
    w, h, fmt = struct.unpack_from("<HHI", data, imag + 8)
    return w, h, FORMATS[fmt], data[:imag - 0x14] if False else data[:struct.unpack_from("<I", data, imag + 0x14)[0]] if False else None


def read(data):
    clim = data.rfind(b"CLIM")
    imag = data.rfind(b"imag")
    w, h, fmt = struct.unpack_from("<HHI", data, imag + 8)
    size = struct.unpack_from("<I", data, imag + 16)[0]
    return w, h, FORMATS[fmt], data[:size]


def decode(raw, w, h, fmt):
    tw, th = pot(w), pot(h)
    img = Image.new("RGBA", (tw, th))
    px = img.load()
    bpp = BPP[fmt]
    tiles_x = tw // 8
    for ty in range(th // 8):
        for tx in range(tiles_x):
            tile = ty * tiles_x + tx
            for p in range(64):
                x = (p & 1) | ((p >> 1) & 2) | ((p >> 2) & 4)
                y = ((p >> 1) & 1) | ((p >> 2) & 2) | ((p >> 3) & 4)
                bit = (tile * 64 + p) * bpp
                o = bit // 8
                if fmt == "rgba8":
                    a, b, g, r = raw[o:o + 4]
                elif fmt == "rgb8":
                    b, g, r = raw[o:o + 3]; a = 255
                elif fmt in ("rgba5551", "rgb565", "rgba4", "la8", "hilo8"):
                    v = struct.unpack_from("<H", raw, o)[0]
                    if fmt == "rgba5551":
                        r, g, b, a = (v >> 11 & 31) * 255 // 31, (v >> 6 & 31) * 255 // 31, (v >> 1 & 31) * 255 // 31, (v & 1) * 255
                    elif fmt == "rgb565":
                        r, g, b, a = (v >> 11 & 31) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31, 255
                    elif fmt == "rgba4":
                        r, g, b, a = (v >> 12 & 15) * 17, (v >> 8 & 15) * 17, (v >> 4 & 15) * 17, (v & 15) * 17
                    elif fmt == "la8":
                        a, l = v & 255, v >> 8; r = g = b = l
                    else:
                        r, g, b, a = v >> 8, v & 255, 0, 255
                elif fmt == "la4":
                    v = raw[o]; l, a = (v >> 4) * 17, (v & 15) * 17; r = g = b = l
                elif fmt in ("l8", "a8"):
                    v = raw[o]; r = g = b = v if fmt == "l8" else 255; a = 255 if fmt == "l8" else v
                elif fmt in ("l4", "a4"):
                    v = (raw[o] >> (4 if bit % 8 else 0)) & 15
                    r = g = b = v * 17 if fmt == "l4" else 255; a = 255 if fmt == "l4" else v * 17
                else:
                    raise NotImplementedError(fmt)
                px[tx * 8 + x, ty * 8 + y] = (r, g, b, a)
    # Layout textures are stored top row first; the image is the top-left w x h of the POT texture.
    return img.crop((0, 0, w, h))


def encode(img, fmt):
    w, h = img.size
    tw, th = pot(w), pot(h)
    canvas = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    canvas.paste(img.convert("RGBA"), (0, 0))
    px = canvas.load()
    bpp = BPP[fmt]
    out = bytearray(tw * th * bpp // 8)
    tiles_x = tw // 8
    for ty in range(th // 8):
        for tx in range(tiles_x):
            tile = ty * tiles_x + tx
            for p in range(64):
                x = (p & 1) | ((p >> 1) & 2) | ((p >> 2) & 4)
                y = ((p >> 1) & 1) | ((p >> 2) & 2) | ((p >> 3) & 4)
                r, g, b, a = px[tx * 8 + x, ty * 8 + y]
                o = (tile * 64 + p) * bpp // 8
                if fmt == "rgba8":
                    out[o:o + 4] = bytes((a, b, g, r))
                elif fmt == "rgba5551":
                    struct.pack_into("<H", out, o, (r >> 3) << 11 | (g >> 3) << 6 | (b >> 3) << 1 | (1 if a >= 128 else 0))
                elif fmt == "rgba4":
                    struct.pack_into("<H", out, o, (r >> 4) << 12 | (g >> 4) << 8 | (b >> 4) << 4 | (a >> 4))
                elif fmt == "la4":
                    l = (r * 77 + g * 151 + b * 28) >> 8
                    out[o] = (l >> 4) << 4 | (a >> 4)
                else:
                    raise NotImplementedError(fmt)
    return bytes(out)


def write_bclim(raw, w, h, fmt):
    body = raw
    clim = struct.pack("<4sHHIIHH", b"CLIM", 0xFEFF, 0x14, 0x02020000, len(body) + 0x28, 1, 0)
    imag = struct.pack("<4sIHHII", b"imag", 0x10, w, h, CODE[fmt], len(body))
    return body + clim + imag


def main():
    cmd = sys.argv[1]
    if cmd == "topng":
        with open(sys.argv[2], "rb") as f:
            w, h, fmt, raw = read(f.read())
        decode(raw, w, h, fmt).save(sys.argv[3])
        print(sys.argv[2], w, h, fmt)
    elif cmd == "frompng":
        img = Image.open(sys.argv[2]).convert("RGBA")
        w, h, fmt = img.size + ("rgba8",)
        if "--like" in sys.argv:
            with open(sys.argv[sys.argv.index("--like") + 1], "rb") as f:
                w, h, fmt, _ = read(f.read())
        if "--format" in sys.argv:
            fmt = sys.argv[sys.argv.index("--format") + 1]
        if img.size != (w, h):
            img = img.resize((w, h), Image.LANCZOS)
        with open(sys.argv[3], "wb") as f:
            f.write(write_bclim(encode(img, fmt), w, h, fmt))


if __name__ == "__main__":
    main()
