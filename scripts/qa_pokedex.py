"""Visual QA of every Pokédex entry in the test Citra.

    python -I qa_pokedex.py [pages] [first]   (editor must already be open on the Pokédex step)
    QA_RAW=1 also keeps every full-resolution top screen in shots/qa/raw/sNN_cMM.png

Taps each of the 12 grid cells on a page, grabs the top screen after each pick, then turns the
page. Writes one contact sheet per page to Pokedachi-data/shots/qa/page_NN.png (page label from
the bottom screen in the corner of each sheet). Pages default to the whole Pokédex (manifest);
first = the page number to start from (the editor must be showing that page).
"""
import json
import os
import subprocess
import sys
import time

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import DATA  # noqa: E402

OUT = os.path.join(DATA, "shots", "qa")
CITRA = [sys.executable, "-I", os.path.join(HERE, "citra.py")]
CELLS = [(x, y) for y in (50, 96, 141, 187) for x in (74, 128, 182)]
LEFT, RIGHT = (69, 14), (185, 14)
TOP = (552, 30, 1367, 519)          # top screen inside the Citra window grab
LABEL = (740, 522, 1050, 572)       # "n / 60" on the bottom screen
WAIT = float(os.environ.get("QA_WAIT", "4.5"))   # seconds for the picked model to load


def citra(*args):
    subprocess.run(CITRA + [str(a) for a in args], check=True, capture_output=True)


def shot():
    path = os.path.join(OUT, "_tmp.png")
    citra("shot", path)
    return Image.open(path).convert("RGB")


def main():
    dex = json.load(open(os.path.join(DATA, "pokedex_manifest.json")))
    pages = int(sys.argv[1]) if len(sys.argv) > 1 else -(-len(dex) // 12)
    first = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    os.makedirs(OUT, exist_ok=True)
    for page in range(first - 1, first - 1 + pages):
        tiles = []
        for x, y in CELLS:
            citra("tap", x, y, 120)
            time.sleep(WAIT)
            top = shot().crop(TOP)
            if os.environ.get("QA_RAW"):         # full-res top screens too, for measuring
                os.makedirs(os.path.join(OUT, "raw"), exist_ok=True)
                top.save(os.path.join(OUT, "raw", "s%02d_c%02d.png" % (page + 1, len(tiles))))
            tiles.append(top.resize((407, 244)))
        label = shot().crop(LABEL)
        sheet = Image.new("RGB", (407 * 3, 244 * 4))
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % 3) * 407, (i // 3) * 244))
        sheet.paste(label, (0, 0))
        sheet.save(os.path.join(OUT, "page_%02d.png" % (page + 1)))
        print("page", page + 1, flush=True)
        citra("tap", *RIGHT, 120)
        time.sleep(1.5)


if __name__ == "__main__":
    main()
