"""Extract a decrypted 3DS cart image (.3ds/.cci): NCSD -> NCCH -> ExHeader, ExeFS, RomFS.

Usage:
    python -I ctr_extract.py <game.3ds> <out_dir> [--list]

Only handles images that are already decrypted (NCCH NoCrypto flag set).
Writes into out_dir: ncch_header.bin, exheader.bin, exefs/<files>, exefs/code.bin
(decompressed when the ExHeader says it's compressed), romfs/<tree>.
"""
import os
import struct
import sys

MEDIA = 0x200


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def u64(b, o):
    return struct.unpack_from("<Q", b, o)[0]


def read_at(f, off, size):
    f.seek(off)
    return f.read(size)


def copy_range(f, off, size, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    f.seek(off)
    left = size
    with open(path, "wb") as out:
        while left:
            chunk = f.read(min(left, 1 << 20))
            if not chunk:
                raise IOError("short read at %#x" % f.tell())
            out.write(chunk)
            left -= len(chunk)


def blz_decompress(data):
    """Nintendo 'bottom LZ' used for compressed code.bin."""
    if len(data) < 8:
        return data
    top_bottom = u32(data, len(data) - 8)
    delta = u32(data, len(data) - 4)
    if delta == 0:
        return data
    top = top_bottom & 0xFFFFFF
    bottom = top_bottom >> 24
    out = bytearray(len(data) + delta)
    out[: len(data)] = data
    src = len(data) - bottom
    dst = len(out)
    stop = len(data) - top
    while src > stop:
        src -= 1
        flags = out[src]
        for _ in range(8):
            if src <= stop or dst <= stop:
                break
            if flags & 0x80:
                src -= 2
                seg = out[src] | (out[src + 1] << 8)
                n = ((seg >> 12) & 0xF) + 3
                off = (seg & 0x0FFF) + 3
                for _ in range(n):
                    dst -= 1
                    out[dst] = out[dst + off]
            else:
                src -= 1
                dst -= 1
                out[dst] = out[src]
            flags = (flags << 1) & 0xFF
    return bytes(out)


def walk_romfs(f, base, listing_only, out_root):
    ivfc = read_at(f, base, 0x60)
    if ivfc[:4] != b"IVFC":
        raise ValueError("RomFS: no IVFC magic")
    master_hash = u32(ivfc, 0x08)
    lvl3_bs = 1 << u32(ivfc, 0x4C)
    lvl3 = base + ((0x60 + master_hash + lvl3_bs - 1) // lvl3_bs) * lvl3_bs
    h = read_at(f, lvl3, 0x28)
    dir_meta = read_at(f, lvl3 + u32(h, 0x0C), u32(h, 0x10))
    file_meta = read_at(f, lvl3 + u32(h, 0x1C), u32(h, 0x20))
    data_off = lvl3 + u32(h, 0x24)
    NONE = 0xFFFFFFFF
    files = []

    def name_at(meta, o, hdr):
        n = u32(meta, o + hdr - 4)
        return meta[o + hdr: o + hdr + n].decode("utf-16-le")

    def walk_dir(o, path):
        child = u32(dir_meta, o + 8)
        fo = u32(dir_meta, o + 12)
        while fo != NONE:
            name = name_at(file_meta, fo, 0x20)
            files.append((path + "/" + name, data_off + u64(file_meta, fo + 8), u64(file_meta, fo + 16)))
            fo = u32(file_meta, fo + 4)
        while child != NONE:
            walk_dir(child, path + "/" + name_at(dir_meta, child, 0x18))
            child = u32(dir_meta, child + 4)

    walk_dir(0, "")
    for p, off, size in files:
        if listing_only:
            print("%10d  %s" % (size, p))
        else:
            copy_range(f, off, size, os.path.join(out_root, p.lstrip("/")))
    return files


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    src, out = sys.argv[1], sys.argv[2]
    listing_only = "--list" in sys.argv
    with open(src, "rb") as f:
        hdr = read_at(f, 0, 0x200)
        if hdr[0x100:0x104] == b"NCSD":
            ncch = u32(hdr, 0x120) * MEDIA
        elif hdr[0x100:0x104] == b"NCCH":
            ncch = 0
        else:
            raise ValueError("not an NCSD/NCCH image")
        nh = read_at(f, ncch, 0x200)
        if nh[0x100:0x104] != b"NCCH":
            raise ValueError("partition 0 is not NCCH")
        flags = nh[0x188:0x190]
        program_id = u64(nh, 0x118)
        product = nh[0x150:0x160].rstrip(b"\0").decode("ascii", "replace")
        print("program id %016X  product %s  flags %s" % (program_id, product, flags.hex()))
        if not flags[7] & 0x4:
            raise ValueError("NCCH is encrypted (NoCrypto flag not set); decrypt it first")
        exh_size = u32(nh, 0x180)
        exefs_off, exefs_size = u32(nh, 0x1A0) * MEDIA, u32(nh, 0x1A4) * MEDIA
        romfs_off, romfs_size = u32(nh, 0x1B0) * MEDIA, u32(nh, 0x1B4) * MEDIA
        print("exheader %#x  exefs %#x+%#x  romfs %#x+%#x" % (exh_size, exefs_off, exefs_size, romfs_off, romfs_size))
        if not listing_only:
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, "ncch_header.bin"), "wb") as w:
                w.write(nh)
        exh = read_at(f, ncch + 0x200, 0x800) if exh_size else b""
        compressed = bool(exh and exh[0x0D] & 1)
        if exh and not listing_only:
            with open(os.path.join(out, "exheader.bin"), "wb") as w:
                w.write(exh)
        if exefs_size:
            eh = read_at(f, ncch + exefs_off, 0x200)
            for i in range(10):
                name = eh[i * 16: i * 16 + 8].rstrip(b"\0").decode("ascii", "replace")
                off, size = u32(eh, i * 16 + 8), u32(eh, i * 16 + 12)
                if not name:
                    continue
                print("exefs %-8s %#x" % (name, size))
                if listing_only:
                    continue
                data = read_at(f, ncch + exefs_off + 0x200 + off, size)
                if name == ".code" and compressed:
                    data = blz_decompress(data)
                    print("  .code decompressed -> %#x" % len(data))
                p = os.path.join(out, "exefs", "code.bin" if name == ".code" else name + ".bin")
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as w:
                    w.write(data)
        if romfs_size:
            files = walk_romfs(f, ncch + romfs_off, listing_only, os.path.join(out, "romfs"))
            print("romfs: %d files, %d bytes" % (len(files), sum(s for _, _, s in files)))


if __name__ == "__main__":
    main()
