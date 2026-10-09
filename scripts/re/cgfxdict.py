"""Check the patricia-tree dictionaries in a CGFX file: does a tree lookup find every name?

    python -I cgfxdict.py <file.bcres|body.bin> ...

Tries two bit orders (bit counted from the start / from the end of the name) and reports, per
dictionary, which names a lookup misses.
"""
import struct
import sys

SECTIONS = ["models", "textures", "luts", "materials", "shaders", "cameras", "lights", "fogs",
            "scenes", "skelanims", "matanims", "visanims", "camanims", "lightanims", "foganims", "emitters"]


def cstr(d, o):
    return d[o:d.index(b"\0", o)].decode("ascii", "replace")


def read_dict(d, off):
    assert d[off:off + 4] == b"DICT", d[off:off + 4]
    n = struct.unpack_from("<I", d, off + 8)[0]
    nodes = []
    for i in range(n + 1):
        p = off + 12 + i * 16
        ref, left, right, no, do = struct.unpack_from("<IHHii", d, p)
        name = cstr(d, p + 8 + no) if i and no else None
        nodes.append((ref, left, right, name))
    return nodes


def bit_front(name, b):
    i = b >> 3
    return (ord(name[i]) >> (b & 7)) & 1 if i < len(name) else 0


def bit_back(name, b):
    i = b >> 3
    return (ord(name[len(name) - 1 - i]) >> (b & 7)) & 1 if i < len(name) else 0


def lookup(nodes, name, getbit):
    prev = nodes[0]
    cur = nodes[prev[1]]
    while prev[0] > cur[0]:
        prev = cur
        cur = nodes[cur[2] if getbit(name, cur[0]) else cur[1]]
    return cur[3]


def main():
    for path in sys.argv[1:]:
        d = open(path, "rb").read()
        assert d[:4] == b"CGFX", path
        hdr = struct.unpack_from("<H", d, 6)[0]
        data = hdr
        assert d[data:data + 4] == b"DATA"
        print("==", path)
        for i, sec in enumerate(SECTIONS):
            cnt, rel = struct.unpack_from("<Ii", d, data + 8 + i * 8)
            if not cnt:
                continue
            nodes = read_dict(d, data + 8 + i * 8 + 4 + rel)
            names = [x[3] for x in nodes[1:]]
            res = {}
            for label, gb in (("front", bit_front), ("back", bit_back)):
                res[label] = [n for n in names if lookup(nodes, n, gb) != n]
            print("  %-10s %3d  root.ref=%#x  miss(front)=%s  miss(back)=%s" % (
                sec, cnt, nodes[0][0], res["front"] or "-", res["back"] or "-"))


if __name__ == "__main__":
    main()
