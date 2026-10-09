"""Editor layout -> Pokédex: Pokémon icons on the hair grid (one per Pokédex slot), every other control hidden.
Town Hall "Who's moving in?" -> only "Choose from Pokédex" (photo and Mii Maker buttons hidden).

    python -I build_editor.py      (needs pokedex_manifest.json from build_pokedex.py)

Writes work/layout/layout_editor.bin and layout_cityhall.bin (darc, original entry order kept).
"""
import importlib.util
import json
import os
import struct
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import DATA  # noqa: E402
HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


darc, bclim, bclyt = load("darc"), load("bclim"), load("bclyt")

# Panes hidden (and moved off-screen so they can't be tapped).
HIDE = {
    "blyt/EditorCommon.bclyt": ["N_BtnTabs", "N_Camera"],      # face/hair/eyes/... tabs, photo button
    "blyt/EditHair.bclyt": ["N_BtnChanges", "B_Color_06", "B_Color_07"],  # hair flip, 2 spare colours
}
# The other 6 hair-colour buttons become jump tabs (codepatch.py: Gen I-V, then the alternate forms),
# each showing a Pokémon: (tab, Rumble icon).
TABS = [(0, "N001_u_00"), (1, "N152_u_00"), (2, "N252_u_00"), (3, "N387_u_00"), (4, "N495_u_00"), (5, "N201_u_27")]
TAB_X, TAB_TOP, TAB_STEP = 72.0, -8.0, 31.0   # column position (layout units, y up) and spacing
TAB_DISC, TAB_HIT, TAB_ICON = (32.0, 32.0), (30.0, 30.0), (28.0, 24.5)
HIDE_CITYHALL = {
    "blyt/EditFirst.bclyt": ["N_BtnEFirst_01", "N_BtnEFirst_02"],  # Create from Photo, Transfer from Mii Maker
}


ICON_W, ICON_H = 32, 28   # logical size; stored as 32x32. The grid buttons stretch it to 52x44
                          # (the hair icons were 52x44 in 64x64; 720 of those wouldn't fit in memory)


def icon_for(entry):
    """Rumble Blast's 32x32 box icon, cropped and bottom-centred at native size (only the few
    sprites taller than 28 px are shrunk)."""
    data = open(os.path.join(DATA, "rumble", "romfs", "pokeicon", "full", entry["icon"] + ".arc"), "rb").read()
    (path, off, size), = [x for x in darc.walk(darc.parse(data)) if x[0].endswith(".bclim")]
    w, h, fmt, raw = bclim.read(data[off:off + size])
    icon = bclim.decode(raw, w, h, fmt)
    icon = icon.crop(icon.getbbox() or (0, 0, w, h))
    if icon.width > ICON_W or icon.height > ICON_H:
        s = min(ICON_W / icon.width, ICON_H / icon.height)
        icon = icon.resize((max(1, round(icon.width * s)), max(1, round(icon.height * s))), Image.LANCZOS)
    canvas = Image.new("RGBA", (ICON_W, ICON_H), (0, 0, 0, 0))
    canvas.alpha_composite(icon, ((ICON_W - icon.width) // 2, ICON_H - icon.height))
    return canvas


def hide(blyt, names):
    data = bytearray(blyt)
    found = set()
    for p in bclyt.panes(data):
        if p["name"] in names:
            data[p["pos"] + 8] &= 0xFE
            struct.pack_into("<2f", data, p["pos"] + 0x24, 5000.0, 5000.0)
            found.add(p["name"])
    assert found == set(names), set(names) - found
    return bytes(data)


def _sections(data):
    """[(magic, bytes)] of a BCLYT, after the 0x14-byte header."""
    out, pos = [], struct.unpack_from("<H", data, 6)[0]
    for _ in range(struct.unpack_from("<I", data, 0x10)[0]):
        size = struct.unpack_from("<I", data, pos + 4)[0]
        out.append((data[pos:pos + 4], bytearray(data[pos:pos + size])))
        pos += size
    return data[:struct.unpack_from("<H", data, 6)[0]], out


def _join(header, sections):
    body = b"".join(bytes(s) for _, s in sections)
    head = bytearray(header)
    struct.pack_into("<I", head, 0x0C, len(head) + len(body))
    struct.pack_into("<I", head, 0x10, len(sections))
    return bytes(head) + body


def _pane_name(sec):
    return bytes(sec[0xC:0x1C]).split(b"\0")[0].decode()


def add_tabs(blyt):
    """EditHair: colour buttons 0..5 -> jump tabs. Each swatch (P_Color_0i) turns white and bigger, and
    gets a child picture pane I_Color_0i showing PkTab<i>.bclim, built like the grid's P_Part/I_Part pair
    (it reuses I_Part_00's material and pane as templates, so it draws the same way and pops with the
    button's own press animation). The 6 textures are appended to txl1, their materials to mat1."""
    header, secs = _sections(blyt)
    get = lambda magic: next(s for m, s in secs if m == magic)
    # txl1: count, offsets (relative to the offset table), names
    txl = get(b"txl1")
    ntex = struct.unpack_from("<I", txl, 8)[0]
    toffs = struct.unpack_from("<%dI" % ntex, txl, 12)
    names = [bytes(txl[12 + o:]).split(b"\0")[0] for o in toffs] + [b"PkTab%d.bclim" % i for i, _ in TABS]
    table = bytearray()
    blob = bytearray()
    for n in names:
        table += struct.pack("<I", 4 * len(names) + len(blob))
        blob += n + b"\0"
    while len(blob) % 4:
        blob += b"\0"
    new_txl = bytearray(b"txl1" + struct.pack("<II", 12 + len(table) + len(blob), len(names))) + table + blob
    # mat1: count, offsets (relative to the section), materials
    mat = get(b"mat1")
    nmat = struct.unpack_from("<I", mat, 8)[0]
    moffs = list(struct.unpack_from("<%dI" % nmat, mat, 12)) + [len(mat)]
    mats = [bytearray(mat[moffs[i]:moffs[i + 1]]) for i in range(nmat)]
    by_name = {bytes(m[:20]).split(b"\0")[0].decode(): i for i, m in enumerate(mats)}
    template = mats[by_name["I_Part_00"]]
    for i, _ in TABS:
        disc = mats[by_name["P_Color_%02d" % i]]
        struct.pack_into("<I", disc, 24, 0xFFFFFFFF)             # konst0 = the swatch colour -> white
        m = bytearray(template)
        m[:20] = ("I_Color_%02d" % i).encode().ljust(20, b"\0")
        struct.pack_into("<H", m, 52, ntex + i)                 # texMap 0 -> PkTab<i>
        mats.append(m)
    table = bytearray()
    off = 12 + 4 * len(mats)
    for m in mats:
        table += struct.pack("<I", off)
        off += len(m)
    new_mat = bytearray(b"mat1" + struct.pack("<II", off, len(mats))) + table + b"".join(mats)
    # panes
    out = []
    pic_template = next(s for m, s in secs if m == b"pic1" and _pane_name(s) == "I_Part_00")
    for magic, sec in secs:
        if magic == b"txl1":
            sec = new_txl
        elif magic == b"mat1":
            sec = new_mat
        name = _pane_name(sec) if magic in (b"pan1", b"pic1", b"bnd1") else ""
        if name == "N_BtnColors":
            struct.pack_into("<2f", sec, 0x24, TAB_X, struct.unpack_from("<f", sec, 0x28)[0])
        for i, _ in TABS:
            if name == "B_Color_%02d" % i:
                struct.pack_into("<2f", sec, 0x24, 0.0, TAB_TOP - TAB_STEP * i)
                struct.pack_into("<2f", sec, 0x44, *TAB_HIT)
            if name == "P_Color_%02d" % i:
                struct.pack_into("<2f", sec, 0x44, *TAB_DISC)
        out.append((magic, sec))
        for i, _ in TABS:
            if name == "P_Color_%02d" % i:
                icon = bytearray(pic_template)
                icon[0xC:0x1C] = ("I_Color_%02d" % i).encode().ljust(16, b"\0")
                struct.pack_into("<3f", icon, 0x24, 0.0, 0.0, 0.0)
                struct.pack_into("<2f", icon, 0x44, *TAB_ICON)
                struct.pack_into("<H", icon, 0x5C, nmat + i)
                out += [(b"pas1", bytearray(b"pas1" + struct.pack("<I", 8))), (b"pic1", icon),
                        (b"pae1", bytearray(b"pae1" + struct.pack("<I", 8)))]
    return _join(header, out)


def tab_icon(name):
    """A tab's Pokémon, scaled up to fill the tile (the grid keeps sprites at native size)."""
    small = icon_for({"icon": name})
    small = small.crop(small.getbbox())
    s = min((ICON_W - 2) / small.width, (ICON_H - 2) / small.height)
    small = small.resize((round(small.width * s), round(small.height * s)), Image.LANCZOS)
    canvas = Image.new("RGBA", (ICON_W, ICON_H), (0, 0, 0, 0))
    canvas.alpha_composite(small, ((ICON_W - small.width) // 2, (ICON_H - small.height) // 2))
    return canvas


def tab_textures():
    files = {}
    for i, icon in TABS:
        img = tab_icon(icon)
        files["timg/PkTab%d.bclim" % i] = bclim.write_bclim(bclim.encode(img, "rgba5551"), ICON_W, ICON_H, "rgba5551")
    return files


def source(name):
    """Decompressed original layout archive (decompressed from the RomFS on first use)."""
    path = os.path.join(DATA, "dec", "tomodachi", "layout", "layout_%s.bin" % name)
    if not os.path.exists(path):
        cx = load("cx")
        raw = open(os.path.join(DATA, "tomodachi", "romfs", "layout", "layout_%s_LZ.bin" % name), "rb").read()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "wb").write(cx.lz11(raw))
    return open(path, "rb").read()


def build(name, repl_fn, hide_map, post=None):
    src = source(name)
    files = {p: src[o:o + s] for p, o, s in darc.walk(darc.parse(src))}
    repl = repl_fn()
    for path, names in hide_map.items():
        repl[path] = hide(repl.get(path, files[path]), names)
    if post:
        post(repl, files)
    added = {p: b for p, b in repl.items() if p not in files}
    for p in added:
        del repl[p]
    out = darc.repack(src, repl, additions=added)
    dst = os.path.join(DATA, "work", "layout")
    os.makedirs(dst, exist_ok=True)
    open(os.path.join(dst, "layout_%s.bin" % name), "wb").write(out)
    print("%s layout: %d files replaced, %d added, %d bytes" % (name, len(repl), len(added), len(out)))


def jump_tabs(repl, files):
    repl["blyt/EditHair.bclyt"] = add_tabs(repl["blyt/EditHair.bclyt"])
    repl.update(tab_textures())


def icons():
    """IconHair<slot>.bclim for every Pokédex slot (the code patch names icons by slot); the blank
    slots after the last entry on the last page get an empty icon."""
    dex = json.load(open(os.path.join(DATA, "pokedex_manifest.json")))
    slots = -(-len(dex) // 12) * 12
    blank = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    repl = {}
    for slot in range(slots):
        if slot < len(dex):
            repl["timg/IconHair%03d.bclim" % slot] = bclim.write_bclim(bclim.encode(icon_for(dex[slot]), "rgba5551"), ICON_W, ICON_H, "rgba5551")
        else:
            repl["timg/IconHair%03d.bclim" % slot] = bclim.write_bclim(bclim.encode(blank, "rgba5551"), 8, 8, "rgba5551")
    return repl


def main():
    build("editor", icons, HIDE, jump_tabs)
    build("cityhall", dict, HIDE_CITYHALL)


if __name__ == "__main__":
    main()
