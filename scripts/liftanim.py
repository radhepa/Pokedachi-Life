"""Raise the 'body' bone in CGFX skeletal animations by editing the original file in place.

    python -I liftanim.py <anims.bin> <out.bin> <dy> [name prefix]

Only the numbers of the body's translation-Y curve change (constant value, the quantized curve's value
offset, or each float key), so the file layout stays byte-identical otherwise. (SPICA can read these
animation files but writes curves the game can't read back.)
"""
import struct
import sys

SKELANIMS = 9   # index of the skeletal-animation dictionary in the DATA block


def s32(d, o):
    return struct.unpack_from("<i", d, o)[0]


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def cstr(d, o):
    return d[o:d.index(b"\0", o)].decode("ascii")


def dict_entries(d, off):
    """(name, data offset) for every node of a CGFX DICT."""
    assert d[off:off + 4] == b"DICT", d[off:off + 4]
    n = u32(d, off + 8)
    out = []
    for i in range(1, n + 1):
        p = off + 12 + i * 16
        out.append((cstr(d, p + 8 + s32(d, p + 8)), p + 12 + s32(d, p + 12)))
    return out


def add_to_group(d, grp, dy):
    """Add dy to every value of a GfxFloatKeyFrameGroup (non-constant slot)."""
    flags = u32(d, grp + 12)
    if flags & 2:                                  # IsConstantValue
        struct.pack_into("<f", d, grp + 16, struct.unpack_from("<f", d, grp + 16)[0] + dy)
        return
    curve = grp + 20 + s32(d, grp + 20)
    fmt, keys = u32(d, curve + 8), u32(d, curve + 12)
    quant = fmt >> 5
    if quant in (0, 3, 6):                         # float keys: Hermite128, UnifiedHermite96, StepLinear64
        stride = {0: 16, 3: 12, 6: 8}[quant]
        for k in range(keys):
            p = curve + 20 + k * stride + 4
            struct.pack_into("<f", d, p, struct.unpack_from("<f", d, p)[0] + dy)
    else:                                          # quantized: value = q * scale + offset
        p = curve + 24
        struct.pack_into("<f", d, p, struct.unpack_from("<f", d, p)[0] + dy)


def main():
    src, dst, dy = sys.argv[1], sys.argv[2], float(sys.argv[3])
    prefix = sys.argv[4] if len(sys.argv) > 4 else ""
    d = bytearray(open(src, "rb").read())
    assert d[:4] == b"CGFX"
    data = struct.unpack_from("<H", d, 6)[0]
    cnt, rel = struct.unpack_from("<Ii", d, data + 8 + SKELANIMS * 8)
    assert cnt, "no skeletal animations"
    lifted = 0
    for name, anim in dict_entries(d, data + 8 + SKELANIMS * 8 + 4 + rel):
        if not name.startswith(prefix):
            continue
        assert d[anim:anim + 4] == b"CANM", name
        for ename, elem in dict_entries(d, anim + 28 + s32(d, anim + 28)):
            if ename != "body":
                continue
            # content follows Flags, Name (+ Name2, Dummy in old revisions) and PrimitiveType
            content = next(c for c in (elem + 12, elem + 20) if u32(d, c - 4) == 5)   # 5 = Transform
            flags = u32(d, elem)
            slot = content + 8 * 4                 # slot 8 = translation Y
            if flags & (1 << 24):                  # IsTranslationYInexistent
                continue
            if flags & (1 << 14):                  # IsTranslationYConstant: the float is inline
                struct.pack_into("<f", d, slot, struct.unpack_from("<f", d, slot)[0] + dy)
            else:
                add_to_group(d, slot + s32(d, slot), dy)
            lifted += 1
    open(dst, "wb").write(d)
    print("lifted body by %g in %d animations" % (dy, lifted))


if __name__ == "__main__":
    main()
