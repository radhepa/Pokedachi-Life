"""Find instructions that compute an address PC-relatively (ADD/SUB rd, pc, #imm) or load a literal
whose value is that address (LDR rd, [pc, #imm] -> =addr), for one or more target VAs.

    python -I pcrefs.py <code.bin> <va_hex> [...]   (a target matches if it falls in [va, va+0x40))
"""
import struct
import sys

BASE = 0x100000


def ror(v, r):
    return ((v >> r) | (v << (32 - r))) & 0xFFFFFFFF


def main():
    with open(sys.argv[1], "rb") as f:
        d = f.read()
    targets = [int(t, 16) for t in sys.argv[2:]]
    n = 0x750000 // 4
    words = struct.unpack_from("<%dI" % n, d)
    for i, w in enumerate(words):
        va = BASE + i * 4
        hit = None
        if (w & 0x0FEF0000) == 0x028F0000 or (w & 0x0FEF0000) == 0x024F0000:   # ADD/SUB rd, pc, #imm
            imm = ror(w & 0xFF, ((w >> 8) & 0xF) * 2)
            hit = va + 8 + imm if (w & 0x00E00000) == 0x00800000 else va + 8 - imm
        elif (w & 0x0F7F0000) == 0x051F0000:                                     # LDR rd, [pc, #imm]
            imm = w & 0xFFF
            lit = va + 8 + (imm if w & 0x00800000 else -imm)
            if BASE <= lit < BASE + len(d) - 4:
                hit = struct.unpack_from("<I", d, lit - BASE)[0]
        if hit is None:
            continue
        for t in targets:
            if t <= hit < t + 0x40:
                print("%08x -> %08x (target %08x)" % (va, hit, t))


if __name__ == "__main__":
    main()
