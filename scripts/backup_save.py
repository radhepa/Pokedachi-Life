"""Copy your Tomodachi Life island (save + extdata) and the currently installed mod out of Citra before
an install, so nothing about your island can be lost or mixed up between mod versions.

    python -I backup_save.py            (build_mod.sh --real runs this first)

Writes POKEDACHI_DATA/backups/citra-YYYYMMDD-HHMMSS/{title-0008c300, extdata-000008C3, mod-before}.
Read-only towards Citra: it never writes into the save folders. Restore by copying the folders back
while Citra is closed.
"""
import glob
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import CITRA_DIR, DATA, TITLE_ID  # noqa: E402


def main():
    sdmc = os.path.join(CITRA_DIR, "sdmc", "Nintendo 3DS", "*", "*")
    saves = glob.glob(os.path.join(sdmc, "title", "00040000", "0008c300"))
    extdata = glob.glob(os.path.join(sdmc, "extdata", "00000000", "000008C3"))
    mod = os.path.join(CITRA_DIR, "load", "mods", TITLE_ID)
    out = os.path.join(DATA, "backups", time.strftime("citra-%Y%m%d-%H%M%S"))
    copied = []
    for name, src in (("title-0008c300", saves), ("extdata-000008C3", extdata), ("mod-before", [mod])):
        if src and os.path.isdir(src[0]):
            shutil.copytree(src[0], os.path.join(out, name))
            copied.append(name)
    if not copied:
        print("nothing to back up in", CITRA_DIR)
        return
    print("backed up %s to %s" % (", ".join(copied), out))


if __name__ == "__main__":
    main()
