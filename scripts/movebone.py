"""Move a bone up/down in a CGFX file by editing it in place (no re-serialisation).

    python -I movebone.py <in.bin> <out.bin> <bone name> <dy> [--if-y=<current y>]

Changes the bone's translation Y, the matching entry of its local matrix and of its stored inverse
world matrix (world itself is stored as identity). With --if-y, only bones whose translation Y equals
that value are moved (to pick some of several same-named bones).
"""
import struct
import sys


def main():
    src, dst, name, dy = sys.argv[1], sys.argv[2], sys.argv[3].encode() + b"\0", float(sys.argv[4])
    only_y = next((float(a.split("=", 1)[1]) for a in sys.argv[5:] if a.startswith("--if-y=")), None)
    d = bytearray(open(src, "rb").read())
    moved = 0
    for b in range(0, len(d) - 220, 4):
        p = b + struct.unpack_from("<i", d, b)[0]
        if not (0 <= p < len(d) and d[p:p + len(name)] == name):
            continue
        sx, sy, sz = struct.unpack_from("<3f", d, b + 32)
        ty = struct.unpack_from("<f", d, b + 60)[0]
        local_ty = struct.unpack_from("<f", d, b + 96)[0]
        if not (abs(local_ty - ty) < 1e-4 and 0.01 < sy < 100):      # not a bone record
            continue
        if only_y is not None and abs(ty - only_y) > 1e-4:
            continue
        ty += dy
        struct.pack_into("<f", d, b + 60, ty)        # Translation.Y
        struct.pack_into("<f", d, b + 96, ty)        # LocalTransform M24
        struct.pack_into("<f", d, b + 192, -ty / sy)  # InvWorldTransform M24 (rotation-free bones)
        moved += 1
    open(dst, "wb").write(d)
    print("moved %d '%s' bones by %g" % (moved, name[:-1].decode(), dy))
    if not moved:
        sys.exit(1)


if __name__ == "__main__":
    main()
