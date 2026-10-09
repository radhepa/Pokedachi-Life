"""Read Pokémon Rumble Blast's model roster out of its code.bin -> POKEDACHI_DATA/rumble_roster.json.

    python -I rumble_roster.py        (after extract_games.sh)

The table at 0x4f68ac (USA) has one 0x3C-byte entry per model: two pointers to the male/female model
names (UTF-16, e.g. PIKATYUU_M / PIKATYUU_F), and at +20 a u16 species number + 1. The species
number drifts on alternate forms (Unown letters, Rotom, ...); build_pokedex.py regroups those by
model name. English names come from msg/US_English/pokemon.msbt.
"""
import importlib.util
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import DATA  # noqa: E402

BASE = 0x100000
TABLE = 0x4F68AC
ENTRY = 0x3C


def main():
    spec = importlib.util.spec_from_file_location("msbt", os.path.join(os.path.dirname(os.path.abspath(__file__)), "msbt.py"))
    msbt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(msbt)
    labels, texts = msbt.read(open(os.path.join(DATA, "dec", "rumble", "msg", "US_English", "pokemon.msbt"), "rb").read())
    eng = {int(labels[i][5:]): t for i, t in enumerate(texts) if labels.get(i, "").startswith("POKE_") and labels[i][5:].isdigit()}
    d = open(os.path.join(DATA, "rumble", "exefs", "code.bin"), "rb").read()

    def wstr(va):
        o = va - BASE
        if not 0 <= o < len(d):
            return None
        e = o
        while d[e:e + 2] != b"\0\0" and e - o < 64:
            e += 2
        try:
            return d[o:e].decode("utf-16-le")
        except UnicodeDecodeError:
            return None

    pii = set(f[:-6] for f in os.listdir(os.path.join(DATA, "dec", "rumble", "pii")))
    icons = set(f[:-4] for f in os.listdir(os.path.join(DATA, "rumble", "romfs", "pokeicon", "face")))
    rows = []
    e = TABLE - BASE
    while True:
        p1, p2 = struct.unpack_from("<II", d, e)
        n1, n2 = wstr(p1), wstr(p2)
        if not n1 or n1 not in pii and n1 not in ("NOTUSED", "TEST"):
            break
        dex = struct.unpack_from("<H", d, e + 20)[0] - 1
        rows.append(dict(idx=len(rows), dex=dex, model_m=n1, model_f=n2, name=eng.get(dex, "?")))
        e += ENTRY
    for r in rows:
        g = "u" if r["model_m"] == r["model_f"] else "m"
        cand = ["N%03d_%s_00" % (r["dex"], g), "N%03d_u_00" % r["dex"], "N%03d_m_00" % r["dex"]]
        r["icon"] = next((c for c in cand if c in icons), None)
    json.dump(rows, open(os.path.join(DATA, "rumble_roster.json"), "w"), indent=1)
    print("%d models, %d species numbers" % (len(rows), len(set(r["dex"] for r in rows))))


if __name__ == "__main__":
    main()
