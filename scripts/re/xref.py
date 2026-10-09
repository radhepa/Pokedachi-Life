"""Find BL/BLX/B callers of a VA and pointer references to it in Tomodachi Life code.bin.

    python -I xref.py <code.bin> <va_hex> [<va_hex> ...]
"""
import struct
import sys

BASE = 0x100000


def callers(d, target):
    out = []
    n = len(d) // 4
    words = struct.unpack_from("<%dI" % n, d)
    for i, w in enumerate(words):
        va = BASE + i * 4
        if (w & 0x0E000000) == 0x0A000000 and (w >> 28) != 0xF:   # B/BL
            imm = w & 0xFFFFFF
            if imm & 0x800000:
                imm -= 0x1000000
            if va + 8 + imm * 4 == target:
                out.append((va, "bl" if w & 0x01000000 else "b"))
        elif (w >> 25) == 0x7D:                                     # BLX imm
            imm = w & 0xFFFFFF
            if imm & 0x800000:
                imm -= 0x1000000
            h = (w >> 24) & 1
            if va + 8 + imm * 4 + h * 2 == target:
                out.append((va, "blx"))
        elif w == target or w == (target | 1):
            out.append((va, "ptr"))
    return out


if __name__ == "__main__":
    with open(sys.argv[1], "rb") as f:
        d = f.read()
    for t in sys.argv[2:]:
        t = int(t, 16)
        print("%08x:" % t, " ".join("%08x(%s)" % c for c in callers(d, t)))
