"""Nintendo CX decompression: LZ10 (0x10), LZ11 (0x11) and LH = LZ77 + Huffman (0x40).

Tomodachi Life's *_LZ.bin files are LZ11. Pokemon Rumble Blast's *.cx files are LH.

Usage:
    python -I cx.py <in> <out>        decompress one file
    python -I cx.py --tree <dir> <out_dir>   decompress every *.cx / *_LZ.bin under dir
"""
import os
import struct
import sys


def _size(data):
    size = data[1] | (data[2] << 8) | (data[3] << 16)
    pos = 4
    if size == 0:
        size = struct.unpack_from("<I", data, 4)[0]
        pos = 8
    return size, pos


def lz11(data):
    size, src = _size(data)
    out = bytearray()
    lz10 = data[0] == 0x10
    while len(out) < size:
        flags = data[src]
        src += 1
        for bit in range(8):
            if len(out) >= size:
                break
            if not flags & (0x80 >> bit):
                out.append(data[src])
                src += 1
                continue
            if lz10:
                b0, b1 = data[src], data[src + 1]
                src += 2
                n = (b0 >> 4) + 3
                disp = (((b0 & 0xF) << 8) | b1) + 1
            else:
                b0 = data[src]
                ind = b0 >> 4
                if ind == 0:
                    b1, b2 = data[src + 1], data[src + 2]
                    n = (((b0 & 0xF) << 4) | (b1 >> 4)) + 0x11
                    disp = (((b1 & 0xF) << 8) | b2) + 1
                    src += 3
                elif ind == 1:
                    b1, b2, b3 = data[src + 1], data[src + 2], data[src + 3]
                    n = (((b0 & 0xF) << 12) | (b1 << 4) | (b2 >> 4)) + 0x111
                    disp = (((b2 & 0xF) << 8) | b3) + 1
                    src += 4
                else:
                    b1 = data[src + 1]
                    n = ind + 1
                    disp = (((b0 & 0xF) << 8) | b1) + 1
                    src += 2
            start = len(out) - disp
            for i in range(n):
                out.append(out[start + i])
    return bytes(out[:size])


def lz11_compress(data):
    """LZ11 encoder (window 4096, hash chains). Output is padded to 4 bytes like Nintendo's.

    Never emits a back-reference with distance 1, like Nintendo's encoder (a precaution: decoders
    that copy halfwords at a time can't do them). Runs use distance 2 instead.
    """
    n = len(data)
    out = bytearray([0x11, n & 0xFF, (n >> 8) & 0xFF, (n >> 16) & 0xFF])
    if n >= 1 << 24:
        out[1:4] = b"\0\0\0"
        out += struct.pack("<I", n)
    chains = {}
    pos = 0
    while pos < n:
        flag_at = len(out)
        out.append(0)
        flags = 0
        for bit in range(8):
            if pos >= n:
                break
            best_len, best_disp = 0, 0
            if pos + 3 <= n:
                key = data[pos:pos + 3]
                cands = chains.get(key)
                if cands:
                    max_len = min(0x10110, n - pos)
                    for c in reversed(cands[-64:]):
                        d = pos - c
                        if d > 0x1000:
                            break
                        if d < 2:
                            continue
                        l = 3
                        while l < max_len and data[c + l] == data[pos + l]:
                            l += 1
                        if l > best_len:
                            best_len, best_disp = l, d
                            if l == max_len:
                                break
            if best_len >= 3:
                flags |= 0x80 >> bit
                d = best_disp - 1
                if best_len <= 0x10:
                    out += bytes([((best_len - 1) << 4) | (d >> 8), d & 0xFF])
                elif best_len <= 0x110:
                    l = best_len - 0x11
                    out += bytes([l >> 4, ((l & 0xF) << 4) | (d >> 8), d & 0xFF])
                else:
                    l = best_len - 0x111
                    out += bytes([0x10 | (l >> 12), (l >> 4) & 0xFF, ((l & 0xF) << 4) | (d >> 8), d & 0xFF])
                step = best_len
            else:
                out.append(data[pos])
                step = 1
            for p in range(pos, min(pos + step, n - 2)):
                chains.setdefault(data[p:p + 3], []).append(p)
            pos += step
        out[flag_at] = flags
    while len(out) % 4:
        out.append(0)
    return bytes(out)


class _Bits:
    """MSB-first bit reader, one byte at a time."""

    def __init__(self, data, pos):
        self.data, self.pos, self.word, self.left = data, pos, 0, 0

    def bit(self):
        if self.left == 0:
            self.word = self.data[self.pos] if self.pos < len(self.data) else 0
            self.pos += 1
            self.left = 8
        self.left -= 1
        return (self.word >> self.left) & 1

    def bits(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | self.bit()
        return v


def _read_table(data, pos, width, size_bytes):
    if size_bytes == 2:
        size = (struct.unpack_from("<H", data, pos)[0] + 1) * 4
    else:
        size = (data[pos] + 1) * 4
    br = _Bits(data, pos + size_bytes)
    count = (size - size_bytes) * 8 // width
    table = [0] + [br.bits(width) for _ in range(count)]
    return table, pos + size


def _decode_sym(table, br, width):
    off_mask = (1 << (width - 2)) - 1
    left_leaf = 1 << (width - 1)
    i = 1
    while True:
        node = table[i]
        b = br.bit()
        nxt = (i & ~1) + ((node & off_mask) + 1) * 2 + b
        if node & (left_leaf >> b):
            return table[nxt]
        i = nxt


def lh(data):
    size, pos = _size(data)
    t9, pos = _read_table(data, pos, 9, 2)
    t5, pos = _read_table(data, pos, 5, 1)
    br = _Bits(data, pos)
    out = bytearray()
    while len(out) < size:
        v = _decode_sym(t9, br, 9)
        if v < 0x100:
            out.append(v)
            continue
        n = (v & 0xFF) + 3
        nb = _decode_sym(t5, br, 5)
        disp = nb if nb <= 1 else (1 << (nb - 1)) | br.bits(nb - 1)
        start = len(out) - disp - 1
        for i in range(n):
            out.append(out[start + i])
    return bytes(out[:size])


def decompress(data):
    if data[0] in (0x10, 0x11):
        return lz11(data)
    if data[0] == 0x40:
        return lh(data)
    raise ValueError("unknown CX type %#x" % data[0])


def out_name(name):
    if name.endswith(".cx"):
        return name[:-3]
    if name.endswith("_LZ.bin"):
        return name[:-7] + ".bcres" if False else name[:-7] + ".bin"
    return name


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "--tree":
        src, dst = sys.argv[2], sys.argv[3]
        n = 0
        for root, _, files in os.walk(src):
            for fn in files:
                if not (fn.endswith(".cx") or fn.endswith("_LZ.bin")):
                    continue
                p = os.path.join(root, fn)
                q = os.path.join(dst, os.path.relpath(root, src), out_name(fn))
                os.makedirs(os.path.dirname(q), exist_ok=True)
                with open(p, "rb") as f:
                    data = f.read()
                try:
                    res = decompress(data)
                except Exception as e:  # keep going, report at the end
                    print("FAIL", p, e)
                    continue
                with open(q, "wb") as f:
                    f.write(res)
                n += 1
        print("decompressed", n)
        return
    with open(sys.argv[1], "rb") as f:
        data = f.read()
    with open(sys.argv[2], "wb") as f:
        f.write(decompress(data))


if __name__ == "__main__":
    main()
