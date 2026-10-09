"""Measure where the hidden Mii head ends up for each Pokédex entry (= hair style).

    python -I measure_heads.py <raw dir> <page order> [calib]

<raw dir> holds full-resolution editor top screens sNN_cMM.png from `QA_RAW=1 qa_pokedex.py`, taken with
the probe build: every body invisible (vanilla skeleton, head bone at the vanilla height), Mii heads
visible. <page order> lists the Pokédex page shown on each sheet, e.g. 6,7,8,9,10,11,1,2,3,4,5.

Prints, per hair style, the head's top and bottom rows (pixels) and writes head_tops.json
{hair: top_row}. The editor's full-body camera is fixed, so rows compare directly between styles.
"""
import json
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import DATA  # noqa: E402


def is_bg(p):
    r, g, b = p[:3]
    return r >= 235 and g >= 215          # the editor's yellow backdrop (incl. its pale circles)


def head_rows(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    px = im.load()
    x0, x1 = int(w * 0.35), int(w * 0.65)
    rows = [y for y in range(int(h * 0.13), int(h * 0.70))
            if sum(1 for x in range(x0, x1, 2) if not is_bg(px[x, y])) >= 3]
    return (rows[0], rows[-1]) if rows else (None, None)


def main():
    raw, order = sys.argv[1], [int(x) for x in sys.argv[2].split(",")]
    manifest = json.load(open(os.path.join(DATA, "pokedex_manifest.json")))
    out = {}
    for sheet, page in enumerate(order, 1):
        for cell in range(12):
            slot = (page - 1) * 12 + cell
            f = os.path.join(raw, "s%02d_c%02d.png" % (sheet, cell))
            if slot >= len(manifest) or not os.path.exists(f):
                continue
            top, bottom = head_rows(f)
            e = manifest[slot]
            out[e["hair"]] = {"top": top, "bottom": bottom, "slot": slot, "name": e["name"]}
            print("%3d hair %3d %-12s top %s bottom %s" % (slot, e["hair"], e["name"], top, bottom))
    json.dump(out, open(os.path.join(DATA, "head_tops.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
