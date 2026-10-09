"""Disassemble Tomodachi Life code.bin (ARM, loaded at 0x100000).

    uv run --with capstone python -I dis.py <code.bin> <va_start> <va_end>    # hex VAs
    uv run --with capstone python -I dis.py <code.bin> func <va>              # whole function containing va
"""
import struct
import sys

import capstone

BASE = 0x100000


def load(p):
    with open(p, "rb") as f:
        return f.read()


def func_bounds(d, va):
    """Walk back to the nearest 'push {..lr}' / 'stmdb sp!' and forward to a pop {..pc} after va."""
    off = va - BASE
    start = off
    while start > 0:
        w = struct.unpack_from("<I", d, start)[0]
        if (w & 0xFFFF4000) == 0xE92D4000:   # push {..., lr}
            break
        start -= 4
    end = off
    while end < len(d) - 4:
        w = struct.unpack_from("<I", d, end)[0]
        if (w & 0xFFFF8000) == 0xE8BD8000 or w == 0xE12FFF1E:  # pop {..., pc} / bx lr
            # keep going if more code follows inside the same function (literal pool check is crude)
            end += 4
            break
        end += 4
    return start + BASE, end + BASE


def dis(d, a, b):
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
    md.detail = False
    md.skipdata = True
    code = d[a - BASE:b - BASE]
    for ins in md.disasm(code, a):
        extra = ""
        try:
            extra = annotate(d, ins)
        except (ValueError, IndexError, struct.error):
            extra = ""
        print("%08x  %-8s %s%s" % (ins.address, ins.mnemonic, ins.op_str, extra))


def annotate(d, ins):
    extra = ""
    if True:
        if ins.mnemonic == "ldr" and "[pc, #" in ins.op_str:
            imm = int(ins.op_str.split("#")[1].rstrip("]"), 0)
            lit = ins.address + 8 + imm
            val = struct.unpack_from("<I", d, lit - BASE)[0]
            extra = "  ; =0x%08x" % val
        elif ins.mnemonic == "add" and ", pc, #" in ins.op_str:
            imm = int(ins.op_str.split("#")[1], 0)
            extra = "  ; =0x%08x" % (ins.address + 8 + imm)
    return extra


if __name__ == "__main__":
    d = load(sys.argv[1])
    if sys.argv[2] == "func":
        a, b = func_bounds(d, int(sys.argv[3], 16))
        print("; function %08x-%08x" % (a, b))
        dis(d, a, b)
    else:
        dis(d, int(sys.argv[2], 16), int(sys.argv[3], 16))
