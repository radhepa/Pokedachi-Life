"""Minimal MSBT (Nintendo message) reader/writer: LBL1 labels + TXT2 strings (UTF-16LE).

    python -I msbt.py dump <file.msbt>            label<TAB>text (control tags shown as {tag:hex})
"""
import struct
import sys


def read(data):
    if data[:8] != b"MsgStdBn":
        raise ValueError("not msbt")
    nsec = struct.unpack_from("<H", data, 0x0E)[0]
    pos = 0x20
    sections = {}
    for _ in range(nsec):
        magic = data[pos:pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        sections[magic] = data[pos + 0x10:pos + 0x10 + size]
        pos += 0x10 + size
        pos = (pos + 15) & ~15
    labels = {}
    lbl = sections.get(b"LBL1")
    if lbl:
        nslots = struct.unpack_from("<I", lbl, 0)[0]
        for i in range(nslots):
            count, off = struct.unpack_from("<II", lbl, 4 + i * 8)
            for _ in range(count):
                ln = lbl[off]
                name = lbl[off + 1:off + 1 + ln].decode("ascii")
                idx = struct.unpack_from("<I", lbl, off + 1 + ln)[0]
                labels[idx] = name
                off += 1 + ln + 4
    txt = sections[b"TXT2"]
    n = struct.unpack_from("<I", txt, 0)[0]
    offs = list(struct.unpack_from("<%dI" % n, txt, 4)) + [len(txt)]
    texts = []
    for i in range(n):
        raw = txt[offs[i]:offs[i + 1]]
        out, j = [], 0
        while j + 1 < len(raw):
            c = struct.unpack_from("<H", raw, j)[0]
            if c == 0:
                break
            if c == 0x0E:  # control tag: group, type, size, payload
                grp, typ, sz = struct.unpack_from("<HHH", raw, j + 2)
                out.append("{%d.%d:%s}" % (grp, typ, raw[j + 8:j + 8 + sz].hex()))
                j += 8 + sz
                continue
            out.append(chr(c))
            j += 2
        texts.append("".join(out))
    return labels, texts


def set_texts(data, changes):
    """Return a copy of an MSBT with the plain-text entries for the given labels replaced.

    Only TXT2 is rebuilt; untouched entries keep their exact bytes (control tags included).
    """
    labels, _ = read(data)
    by_label = {v: k for k, v in labels.items()}
    nsec = struct.unpack_from("<H", data, 0x0E)[0]
    out = bytearray(data[:0x20])
    pos = 0x20
    found = set()
    for _ in range(nsec):
        magic = data[pos:pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        body = data[pos + 0x10:pos + 0x10 + size]
        if magic == b"TXT2":
            n = struct.unpack_from("<I", body, 0)[0]
            offs = list(struct.unpack_from("<%dI" % n, body, 4)) + [len(body)]
            entries = [body[offs[i]:offs[i + 1]] for i in range(n)]
            for label, text in changes.items():
                if label in by_label:
                    entries[by_label[label]] = text.encode("utf-16-le") + b"\0\0"
                    found.add(label)
            table = bytearray(struct.pack("<I", n))
            blob = bytearray()
            start = 4 + 4 * n
            for e in entries:
                table += struct.pack("<I", start + len(blob))
                blob += e
            body = bytes(table + blob)
            size = len(body)
        out += magic + struct.pack("<I", size) + data[pos + 8:pos + 0x10] + body
        while len(out) % 16:
            out.append(0xAB)
        pos += 0x10 + struct.unpack_from("<I", data, pos + 4)[0]
        pos = (pos + 15) & ~15
    struct.pack_into("<I", out, 0x12, len(out))
    missing = set(changes) - found
    if missing:
        raise KeyError("labels not found: %s" % ", ".join(sorted(missing)))
    return bytes(out)


if __name__ == "__main__":
    with open(sys.argv[2], "rb") as f:
        labels, texts = read(f.read())
    for i, t in enumerate(texts):
        print("%s\t%s" % (labels.get(i, str(i)), t))
