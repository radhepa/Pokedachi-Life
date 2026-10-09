"""Nintendo DARC archives (layouts, Rumble Blast *.arc): list, extract, rebuild.

    python -I darc.py list <file>
    python -I darc.py extract <file> <out_dir>
    python -I darc.py build <in_dir> <out_file> [--align N]
"""
import os
import struct
import sys


def parse(data):
    if data[:4] != b"darc":
        raise ValueError("not a darc")
    hdr_len, version, file_size, tbl_off, tbl_len, data_off = struct.unpack_from("<HIIIII", data, 6)
    root_next = struct.unpack_from("<I", data, tbl_off + 8)[0]
    names_off = tbl_off + root_next * 12
    entries = []
    for i in range(root_next):
        nm, off, size = struct.unpack_from("<III", data, tbl_off + i * 12)
        is_dir = bool(nm & 0x01000000)
        no = names_off + (nm & 0xFFFFFF)
        end = no
        while data[end:end + 2] != b"\0\0":
            end += 2
        name = data[no:end].decode("utf-16-le")
        entries.append((name, is_dir, off, size))
    return entries


def walk(entries):
    """Yield (path, offset, size) for files; directory entry 'size' = index after its last child."""
    stack = []
    for i, (name, is_dir, off, size) in enumerate(entries):
        while stack and i >= stack[-1][1]:
            stack.pop()
        if is_dir:
            stack.append((name, size))
            continue
        path = "/".join(n for n, _ in stack if n not in ("", ".")) + "/" + name
        yield path.lstrip("/"), off, size


def build(in_dir, align=0x80):
    """Rebuild a darc from a directory tree (root '' and '.' entries like Nintendo's tools)."""
    files = []
    for root, dirs, fs in os.walk(in_dir):
        dirs.sort()
        for f in sorted(fs):
            files.append(os.path.relpath(os.path.join(root, f), in_dir).replace("\\", "/"))
    # node list: '' root, '.' dir, then nested dirs/files in sorted order
    nodes = [("", True), (".", True)]
    tree = {}
    for f in files:
        parts = f.split("/")
        d = tree
        for p in parts[:-1]:
            d = d.setdefault(p, {})
        d[parts[-1]] = None

    def add(d):
        for k in sorted(d):
            if d[k] is None:
                nodes.append((k, False, None))
            else:
                nodes.append((k, True, None))
                start = len(nodes) - 1
                add(d[k])
                nodes[start] = (k, True, len(nodes))

    nodes = [("", True, None), (".", True, None)]
    add(tree)
    nodes[0] = ("", True, len(nodes))
    nodes[1] = (".", True, len(nodes))
    names = b""
    name_offs = []
    for n in nodes:
        name_offs.append(len(names))
        names += n[0].encode("utf-16-le") + b"\0\0"
    tbl_off = 0x1C
    tbl_len = len(nodes) * 12 + len(names)
    data_off = (tbl_off + tbl_len + align - 1) // align * align
    blob = bytearray()
    entries = bytearray()
    paths = []
    stack = []
    file_iter = iter(files)
    # recompute file paths in node order
    def node_paths(d, prefix):
        for k in sorted(d):
            if d[k] is None:
                yield prefix + k
            else:
                yield from node_paths(d[k], prefix + k + "/")
    order = list(node_paths(tree, ""))
    fi = 0
    for i, n in enumerate(nodes):
        if n[1]:
            parent = 0
            entries += struct.pack("<III", name_offs[i] | 0x01000000, parent, n[2])
        else:
            with open(os.path.join(in_dir, order[fi]), "rb") as f:
                content = f.read()
            fi += 1
            while (data_off + len(blob)) % align:
                blob.append(0)
            entries += struct.pack("<III", name_offs[i], data_off + len(blob), len(content))
            blob += content
    out = bytearray(b"darc")
    out += struct.pack("<HHIIIII", 0xFEFF, 0x1C, 0x01000000, 0, tbl_off, tbl_len, data_off)
    out += entries + names
    out += b"\0" * (data_off - len(out))
    out += blob
    struct.pack_into("<I", out, 0x0C, len(out))
    return bytes(out)


def repack(data, replacements, align=None, additions=None):
    """Rebuild a darc with some file contents replaced, keeping the original node table, order and
    names. replacements: {path: bytes}. Each file keeps its original alignment (the largest power
    of two <= 0x80 dividing its old offset): textures (.bclim) must stay 0x80-aligned or the game
    draws them as garbage. Pass align to force one alignment for every file.
    additions: {path: bytes} new files, appended (0x80-aligned) at the end of their existing
    directory. The game looks files up by name, not by position."""
    entries = parse(data)
    tbl_off, tbl_len, data_off = struct.unpack_from("<III", data, 0x10)
    names_off = tbl_off + len(entries) * 12
    raw = [list(struct.unpack_from("<III", data, tbl_off + i * 12)) for i in range(len(entries))]
    # node index -> (path, original content, original offset) for files
    content, stack = {}, []
    for i, (name, is_dir, off, size) in enumerate(entries):
        while stack and i >= stack[-1][1]:
            stack.pop()
        if is_dir:
            stack.append((name, size, i))
            continue
        path = ("/".join(n for n, _, _ in stack if n not in ("", ".")) + "/" + name).lstrip("/")
        content[i] = (path, replacements.get(path, data[off:off + size]), off)
    names = bytearray(data[names_off:tbl_off + tbl_len])
    for path, blob in sorted((additions or {}).items()):
        folder, name = path.rsplit("/", 1)
        dirs = [i for i, (n, d, _, _) in enumerate(entries) if d and n == folder.rsplit("/", 1)[-1]]
        assert len(dirs) == 1, (path, dirs)
        pos = raw[dirs[0]][2]                      # index right after the directory's last child
        for r in raw:
            if r[0] & 0x01000000:
                if r[2] >= pos:
                    r[2] += 1
                if r[1] >= pos:
                    r[1] += 1
        raw.insert(pos, [len(names), 0, 0])
        entries.insert(pos, (name, False, 0, 0))
        content = {(k + 1 if k >= pos else k): v for k, v in content.items()}
        content[pos] = (path, blob, 0)
        names += name.encode("utf-16-le") + b"\0\0"
    tbl_len = len(raw) * 12 + len(names)
    new_data_off = data_off if tbl_off + tbl_len <= data_off else (tbl_off + tbl_len + 0x7F) // 0x80 * 0x80
    out = bytearray(data[:tbl_off]) + b"\0" * (len(raw) * 12) + names
    out += b"\0" * (new_data_off - len(out))
    for i, r in enumerate(raw):
        if i in content:
            path, blob, off = content[i]
            a = align
            if a is None:
                a = 0x80
                while a > 1 and off % a:
                    a //= 2
            while len(out) % a:
                out.append(0)
            r[1], r[2] = len(out), len(blob)
            out += blob
        struct.pack_into("<III", out, tbl_off + i * 12, *r)
    struct.pack_into("<III", out, 0x10, tbl_off, tbl_len, new_data_off)
    struct.pack_into("<I", out, 0x0C, len(out))
    return bytes(out)


def main():
    cmd = sys.argv[1]
    if cmd == "build":
        align = int(sys.argv[sys.argv.index("--align") + 1], 0) if "--align" in sys.argv else 0x80
        with open(sys.argv[3], "wb") as f:
            f.write(build(sys.argv[2], align))
        return
    with open(sys.argv[2], "rb") as f:
        data = f.read()
    entries = parse(data)
    for path, off, size in walk(entries):
        if cmd == "list":
            print("%8d  %s" % (size, path))
        else:
            p = os.path.join(sys.argv[3], path)
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            with open(p, "wb") as f:
                f.write(data[off:off + size])


if __name__ == "__main__":
    main()
