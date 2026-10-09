"""Drive Citra without touching the real mouse/keyboard: window messages in, gfxcapture frames out.

    python citra.py launch <rom>            start citra-qt, print pid
    python citra.py info                    pid, hwnds, client size, screen layout
    python citra.py shot <out.png>          one frame of the Citra window
    python citra.py press <button> [ms]     a b x y up down left right l r start select
    python citra.py windows                 list Citra's visible top-level windows
    python citra.py drag x1 y1 x2 y2 [ms] [shot.png]   touch-drag on the bottom screen (shot while held;
                                            CITRA_HOLD_MS = press time before moving, default 400)
    python citra.py tap <x> <y> [ms]        touch the bottom screen at 3DS coords (320x240)
    python citra.py kill                    stop the citra-qt we launched (exact pid)
    python citra.py reset                   restore the test instance's pristine save

By default this drives the portable TEST instance (Pokedachi-data/citra-test: its own user dir,
fixed clock, a copy of a save). Set POKEDACHI_REAL=1 (and CITRA_EXE) to launch your own Citra.

Buttons follow this Citra keyboard map (A=Left arrow, B=Down, X=Up, Y=Right, D-pad=TGFH,
L=Q, R=E, Start=M, Select=N). Layout assumed: Citra "Default" (top screen above bottom screen,
both scaled to the window width, centred).
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import DATA, CITRA_EXE  # noqa: E402

CITRA = (CITRA_EXE if os.environ.get("POKEDACHI_REAL")
         else os.path.join(DATA, "citra-test", "citra-qt.exe"))
STATE = os.path.join(os.environ.get("TEMP", "."), "pokedachi_citra.json")

user32 = ctypes.WinDLL("user32", use_last_error=True)
# Citra (Qt6) is per-monitor DPI aware; match it so client coordinates are physical pixels.
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
user32.EnumChildWindows.argtypes = [wt.HWND, WNDENUMPROC, wt.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.MapVirtualKeyW.argtypes = [wt.UINT, wt.UINT]

WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
MK_LBUTTON = 1

VK = {"left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28}
BUTTONS = {
    "a": VK["left"], "b": VK["down"], "x": VK["up"], "y": VK["right"],
    "dup": ord("T"), "ddown": ord("G"), "dleft": ord("F"), "dright": ord("H"),
    "l": ord("Q"), "r": ord("E"), "start": ord("M"), "select": ord("N"),
}
EXTENDED = {0x25, 0x26, 0x27, 0x28}


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except OSError:
        return {}


def save_state(s):
    with open(STATE, "w") as f:
        json.dump(s, f)


def text(hwnd, fn):
    buf = ctypes.create_unicode_buffer(256)
    fn(hwnd, buf, 256)
    return buf.value


def windows_of(pid):
    tops = []

    def cb(h, _):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(h):
            tops.append(h)
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return tops


def children(hwnd):
    out = []

    def cb(h, _):
        out.append(h)
        return True

    user32.EnumChildWindows(hwnd, WNDENUMPROC(cb), 0)
    return out


def client_size(h):
    r = wt.RECT()
    user32.GetClientRect(h, ctypes.byref(r))
    return r.right - r.left, r.bottom - r.top


def find(pid):
    """Main window = the biggest visible top-level of pid; render = its biggest child window."""
    tops = windows_of(pid)
    if not tops:
        raise SystemExit("no Citra window for pid %d" % pid)
    main = max(tops, key=lambda h: client_size(h)[0] * client_size(h)[1])
    kids = [h for h in children(main) if user32.IsWindowVisible(h)]
    render = max(kids, key=lambda h: client_size(h)[0] * client_size(h)[1]) if kids else main
    return main, render


def layout(w, h):
    """Default layout: top 400x240 and bottom 320x240 stacked, scaled to fit, centred."""
    scale = min(w / 400.0, h / 480.0)
    top_w, top_h = 400 * scale, 240 * scale
    bot_w, bot_h = 320 * scale, 240 * scale
    oy = (h - (top_h + bot_h)) / 2.0
    top = ((w - top_w) / 2.0, oy, top_w, top_h)
    bottom = ((w - bot_w) / 2.0, oy + top_h, bot_w, bot_h)
    return top, bottom, scale


def post_key(h, vk, ms):
    scan = user32.MapVirtualKeyW(vk, 0)
    ext = 1 << 24 if vk in EXTENDED else 0
    down = 1 | (scan << 16) | ext
    up = down | (1 << 30) | (1 << 31)
    user32.PostMessageW(h, WM_KEYDOWN, vk, down)
    time.sleep(ms / 1000.0)
    user32.PostMessageW(h, WM_KEYUP, vk, up)


def post_tap(h, x, y, ms):
    lp = (int(y) << 16) | (int(x) & 0xFFFF)
    user32.PostMessageW(h, WM_MOUSEMOVE, 0, lp)
    user32.PostMessageW(h, WM_LBUTTONDOWN, MK_LBUTTON, lp)
    time.sleep(ms / 1000.0)
    user32.PostMessageW(h, WM_LBUTTONUP, 0, lp)


def shot(hwnd, out):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-filter_complex",
           "gfxcapture=hwnd=%d:capture_cursor=0:max_framerate=10,hwdownload,format=bgra" % hwnd,
           "-frames:v", "1", out]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise SystemExit(r.stderr[-800:])


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd, args = sys.argv[1], sys.argv[2:]
    st = load_state()
    if cmd == "launch":
        # Show the window without taking keyboard focus: you may be typing elsewhere, and keys
        # that land in Citra press 3DS buttons (E = R flips Pokédex pages).
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 4                      # SW_SHOWNOACTIVATE
        p = subprocess.Popen([CITRA, args[0]], cwd=os.path.dirname(CITRA), startupinfo=si)
        save_state({"pid": p.pid})
        print(p.pid)
        return
    if cmd == "reset":
        import shutil
        dst = os.path.join(DATA, "citra-test", "user", "sdmc")
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(os.path.join(DATA, "citra-test-pristine", "sdmc"), dst)
        print("test save restored")
        return
    pid = int(st.get("pid", 0))
    if cmd == "kill":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        print("killed", pid)
        return
    main_w, render = find(pid)
    if cmd == "info":
        w, h = client_size(render)
        print(json.dumps({"pid": pid, "main": main_w, "render": render, "render_class": text(render, user32.GetClassNameW),
                          "title": text(main_w, user32.GetWindowTextW), "client": [w, h],
                          "layout": layout(w, h)}, indent=1))
    elif cmd == "shot":
        shot(main_w, args[0])
        print(args[0])
    elif cmd == "windows":
        for h in windows_of(pid):
            print(h, "main" if h == main_w else "", repr(text(h, user32.GetWindowTextW)),
                  text(h, user32.GetClassNameW), client_size(h))
    elif cmd == "drag":
        # drag x1 y1 x2 y2 [ms] [shot.png]: press at (x1,y1), glide to (x2,y2) over ms, optionally grab a
        # frame while still holding, then release.
        w, h = client_size(render)
        _, (bx, by, bw, bh), _ = layout(w, h)
        pts = [float(a) for a in args[:4]]
        ms = int(args[4]) if len(args) > 4 else 800
        p1 = (bx + pts[0] * bw / 320.0, by + pts[1] * bh / 240.0)
        p2 = (bx + pts[2] * bw / 320.0, by + pts[3] * bh / 240.0)
        lp = lambda x, y: (int(y) << 16) | (int(x) & 0xFFFF)
        user32.PostMessageW(render, WM_MOUSEMOVE, 0, lp(*p1))
        user32.PostMessageW(render, WM_LBUTTONDOWN, MK_LBUTTON, lp(*p1))
        time.sleep(float(os.environ.get("CITRA_HOLD_MS", "400")) / 1000.0)
        steps = max(1, ms // 40)
        for i in range(1, steps + 1):
            t = i / steps
            user32.PostMessageW(render, WM_MOUSEMOVE, MK_LBUTTON, lp(p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t))
            time.sleep(0.04)
        if len(args) > 5:
            time.sleep(0.6)
            shot(main_w, args[5])
        user32.PostMessageW(render, WM_LBUTTONUP, 0, lp(*p2))
    elif cmd == "press":
        post_key(render, BUTTONS[args[0]], int(args[1]) if len(args) > 1 else 120)
    elif cmd == "tap":
        w, h = client_size(render)
        _, (bx, by, bw, bh), _ = layout(w, h)
        x = bx + float(args[0]) * bw / 320.0
        y = by + float(args[1]) * bh / 240.0
        post_tap(render, x, y, int(args[2]) if len(args) > 2 else 120)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
