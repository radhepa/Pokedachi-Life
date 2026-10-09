"""LZ11-compress built files into Citra's LayeredFS folder for Tomodachi Life.

    python -I install_mod.py <src_dir> <romfs_subdir> [--glob 'body_body*.bin'] [--clean]

Each <src_dir>/<name>.bin becomes
%APPDATA%/Citra/load/mods/000400000008C300/romfs/<romfs_subdir>/<name>_LZ.bin.
--clean removes the whole mod folder first (the game then runs unmodded files for everything else).
--real targets your own Citra (%APPDATA%/Citra, or CITRA_DIR) instead of the portable test instance.
Only the mod folder is ever written; saves are never touched.
"""
import fnmatch
import importlib.util
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
# Default: the portable test Citra. --real installs into your own Citra.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import DATA, CITRA_DIR, TITLE_ID  # noqa: E402

TEST_ROOT = os.path.join(DATA, "citra-test", "user", "load", "mods", TITLE_ID)
REAL_ROOT = os.path.join(CITRA_DIR, "load", "mods", TITLE_ID)
MOD_ROOT = REAL_ROOT if "--real" in sys.argv else TEST_ROOT


def _cx():
    spec = importlib.util.spec_from_file_location("cx", os.path.join(HERE, "cx.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _one(job):
    src, dst = job
    with open(src, "rb") as f:
        data = f.read()
    packed = _cx().lz11_compress(data)
    with open(dst, "wb") as f:
        f.write(packed)
    return os.path.basename(dst), len(data), len(packed)


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    src_dir, sub = args[0], args[1]
    pattern = args[args.index("--glob") + 1] if "--glob" in args else "*.bin"
    if "--clean" in args and os.path.isdir(MOD_ROOT):
        shutil.rmtree(MOD_ROOT)
    out_dir = os.path.join(MOD_ROOT, "romfs", sub)
    os.makedirs(out_dir, exist_ok=True)
    jobs = []
    for fn in sorted(os.listdir(src_dir)):
        if fnmatch.fnmatch(fn, pattern) and fn.endswith(".bin"):
            jobs.append((os.path.join(src_dir, fn), os.path.join(out_dir, fn[:-4] + "_LZ.bin")))
    total = 0
    with ProcessPoolExecutor() as ex:
        for name, raw, packed in ex.map(_one, jobs, chunksize=4):
            total += packed
    print("installed %d files (%d KB) into %s" % (len(jobs), total // 1024, out_dir))


if __name__ == "__main__":
    main()
