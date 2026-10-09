"""BCLYT (CTR layout) pane lister / visibility editor.

    python -I bclyt.py list <file.bclyt>
    python -I bclyt.py hide <file.bclyt> <out.bclyt> <pane> [<pane> ...]

Pane record (pan1/pic1/txt1/wnd1/bnd1/prt1 sections) after the 8-byte section header:
  u8 flags (bit0 = visible), u8 origin, u8 alpha, u8 pad, char name[16], char userinfo[8],
  vec3 translate, vec3 rotate, vec2 scale, vec2 size
pas1/pae1 open/close the children of the previous pane.
"""
import struct
import sys

PANES = (b"pan1", b"pic1", b"txt1", b"wnd1", b"bnd1", b"prt1")


def sections(data):
    hdr_size = struct.unpack_from("<H", data, 6)[0]
    count = struct.unpack_from("<I", data, 0x10)[0]
    pos = hdr_size
    for _ in range(count):
        magic = data[pos:pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        yield magic, pos, size
        pos += size


def panes(data):
    depth = 0
    for magic, pos, size in sections(data):
        if magic == b"pas1":
            depth += 1
        elif magic == b"pae1":
            depth -= 1
        elif magic in PANES:
            flags = data[pos + 8]
            name = data[pos + 0xC:pos + 0x1C].split(b"\0")[0].decode("ascii", "replace")
            tx, ty, tz = struct.unpack_from("<3f", data, pos + 0x24)
            sx, sy = struct.unpack_from("<2f", data, pos + 0x3C)
            w, h = struct.unpack_from("<2f", data, pos + 0x44)
            yield dict(kind=magic.decode(), name=name, visible=bool(flags & 1), depth=depth, pos=pos,
                       t=(tx, ty), size=(w, h))


def main():
    cmd, path = sys.argv[1], sys.argv[2]
    data = bytearray(open(path, "rb").read())
    if cmd == "list":
        for p in panes(data):
            print("%s%-5s %-24s %s t=(%.0f,%.0f) size=(%.0f,%.0f)" % ("  " * p["depth"], p["kind"], p["name"],
                  "vis" if p["visible"] else "HIDDEN", p["t"][0], p["t"][1], p["size"][0], p["size"][1]))
    elif cmd == "hide":
        # Hidden AND moved far off-screen, so hit tests on child bounding panes can't fire either.
        names = set(sys.argv[4:])
        done = set()
        for p in panes(data):
            if p["name"] in names:
                data[p["pos"] + 8] &= 0xFE
                struct.pack_into("<2f", data, p["pos"] + 0x24, 5000.0, 5000.0)
                done.add(p["name"])
        missing = names - done
        if missing:
            raise SystemExit("panes not found: %s" % ", ".join(sorted(missing)))
        open(sys.argv[3], "wb").write(data)
        print("hid", len(done), "panes")


if __name__ == "__main__":
    main()
