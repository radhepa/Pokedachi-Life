"""Editor layout -> Pokédex: Pokémon icons on the hair grid (one per Pokédex slot), every other control hidden.
Town Hall "Who's moving in?" -> only "Choose from Pokédex" (photo and Mii Maker buttons hidden).

    python -I build_editor.py      (needs pokedex_manifest.json from build_pokedex.py)

Writes work/layout/layout_editor.bin and layout_cityhall.bin (darc, original entry order kept).
"""
import importlib.util
import json
import os
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
    "blyt/EditHair.bclyt": ["N_BtnChanges", "N_BtnColors"],    # hair flip, hair colours
}
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
    import struct
    found = set()
    for p in bclyt.panes(data):
        if p["name"] in names:
            data[p["pos"] + 8] &= 0xFE
            struct.pack_into("<2f", data, p["pos"] + 0x24, 5000.0, 5000.0)
            found.add(p["name"])
    assert found == set(names), set(names) - found
    return bytes(data)


def source(name):
    """Decompressed original layout archive (decompressed from the RomFS on first use)."""
    path = os.path.join(DATA, "dec", "tomodachi", "layout", "layout_%s.bin" % name)
    if not os.path.exists(path):
        cx = load("cx")
        raw = open(os.path.join(DATA, "tomodachi", "romfs", "layout", "layout_%s_LZ.bin" % name), "rb").read()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "wb").write(cx.lz11(raw))
    return open(path, "rb").read()


def build(name, repl_fn, hide_map):
    src = source(name)
    files = {p: src[o:o + s] for p, o, s in darc.walk(darc.parse(src))}
    repl = repl_fn()
    for path, names in hide_map.items():
        repl[path] = hide(files[path], names)
    added = {p: b for p, b in repl.items() if p not in files}
    for p in added:
        del repl[p]
    out = darc.repack(src, repl, additions=added)
    dst = os.path.join(DATA, "work", "layout")
    os.makedirs(dst, exist_ok=True)
    open(os.path.join(dst, "layout_%s.bin" % name), "wb").write(out)
    print("%s layout: %d files replaced, %d added, %d bytes" % (name, len(repl), len(added), len(out)))


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
    build("editor", icons, HIDE)
    build("cityhall", dict, HIDE_CITYHALL)


if __name__ == "__main__":
    main()
