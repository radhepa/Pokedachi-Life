"""Dynamic RE session: which code applies a hair (= Pokédex) pick in the Mii editor?

1. enable Citra's gdbstub in the TEST instance, boot, continue
2. navigate to Rob's Edit Mii -> Appearance (breakpoint on the outfit function 0x73246c meanwhile)
3. from the breakpoint: actor body obj r0 -> record [r0+0x7d4] -> hair byte at record-0x2e
4. write-watch the hair byte, tap a Pokédex icon, report PC/LR/regs + a stack sample
"""
import importlib.util
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gdb import Gdb  # noqa: E402

spec = importlib.util.spec_from_file_location("citra", os.path.join(HERE, "..", "citra.py"))
citra = importlib.util.module_from_spec(spec)
spec.loader.exec_module(citra)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import DATA, TOMODACHI_ROM as ROM  # noqa: E402

CFG = os.path.join(DATA, "citra-test", "user", "config", "qt-config.ini")


def set_gdbstub(on):
    s = open(CFG, encoding="utf-8").read()
    bs = "\\"
    s = s.replace("use_gdbstub" + bs + "default=true", "use_gdbstub" + bs + "default=false")
    s = s.replace("use_gdbstub=true", "use_gdbstub=false") if not on else s.replace("use_gdbstub=false", "use_gdbstub=true")
    open(CFG, "w", encoding="utf-8").write(s)


def tap(x, y, wait):
    st = citra.load_state()
    main_w, render = citra.find(int(st["pid"]))
    w, h = citra.client_size(render)
    _, (bx, by, bw, bh), _ = citra.layout(w, h)
    citra.post_tap(render, bx + x * bw / 320.0, by + y * bh / 240.0, 150)
    time.sleep(wait)


def shot(name):
    st = citra.load_state()
    main_w, _ = citra.find(int(st["pid"]))
    citra.shot(main_w, os.path.join(DATA, "shots", name))


def main():
    import subprocess
    st = citra.load_state()
    if st.get("pid"):
        subprocess.run(["taskkill", "/PID", str(st["pid"]), "/F"], capture_output=True)
        time.sleep(3)
    set_gdbstub(True)
    import shutil
    dst = os.path.join(citra.DATA, "citra-test", "user", "sdmc")
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(os.path.join(citra.DATA, "citra-test-pristine", "sdmc"), dst)
    p = subprocess.Popen([citra.CITRA, ROM], cwd=os.path.dirname(citra.CITRA))
    citra.save_state({"pid": p.pid})
    g = None
    for _ in range(60):
        try:
            g = Gdb()
            break
        except OSError:
            time.sleep(1)
    print("gdb connected; halt reason:", g.cmd("?"))
    g.cont()
    time.sleep(45)
    tap(160, 120, 10)      # title
    tap(112, 69, 7)        # apartments
    tap(160, 226, 12)      # enter building
    tap(160, 226, 10)      # enter Rob's room
    g.interrupt()
    g.break_at(0x73246C)
    g.cont()
    tap(282, 19, 0)        # Edit Mii
    stop = g.wait(timeout=60)
    r = g.regs()
    print("break at 0x73246c:", stop[:20], "r0=%#x lr=%#x" % (r[0], r[14]))
    rec = g.u32(r[0] + 0x7D4)
    cfl = rec - 0x60
    data = g.mem(cfl, 0x60)
    print("record %#x cfl %#x ver %d hair %d name %r" % (rec, cfl, data[0], data[0x32], data[0x1A:0x2E].decode("utf-16-le")))
    g.unbreak(0x73246C)
    # let the editor finish opening (the outfit fn may run again; ignore)
    g.cont()
    time.sleep(10)
    tap(64, 229, 6)        # Appearance step
    tap(19, 41, 4)         # hair tab = Pokédex
    shot("gdb_editor.png")
    g.interrupt()
    hair_addrs = [rec - 0x2E]
    print("watch hair byte at %#x (now %d)" % (hair_addrs[0], g.mem(hair_addrs[0], 1)[0]))
    print("Z2:", g.watch(hair_addrs[0], 1, "w"))
    g.cont()
    tap(38, 32, 0)         # first icon of the current page
    stop = g.wait(timeout=60)
    r = g.regs()
    print("WATCH HIT:", stop[:40])
    print("pc=%#x lr=%#x sp=%#x" % (r[15], r[14], r[13]))
    print("regs:", " ".join("r%d=%#x" % (i, v) for i, v in enumerate(r[:13])))
    stack = g.mem(r[13], 0x100)
    words = struct.unpack("<64I", stack)
    print("stack code ptrs:", " ".join("%#x" % w for w in words if 0x100000 <= w < 0x84F390))
    g.unwatch(hair_addrs[0], 1, "w")
    g.cont()
    time.sleep(3)
    shot("gdb_after_pick.png")
    print("done; leaving Citra running (gdbstub still enabled in config)")


if __name__ == "__main__":
    main()
