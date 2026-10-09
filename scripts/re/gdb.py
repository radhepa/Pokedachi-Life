"""Tiny GDB remote-serial-protocol client for Citra's gdbstub (ARM11 app core).

Used as a library:
    g = Gdb(); g.cont()                       # connect (Citra halts at boot until a client continues)
    g.break_at(0x73246c); stop = g.wait()     # software breakpoint, block until hit
    regs = g.regs(); g.mem(addr, n)           # r0..r15 list, bytes
    g.watch(addr, 1, 'w')                     # write watchpoint (Z2), 'r' read (Z3), 'a' access (Z4)
"""
import socket
import struct
import time


class Gdb:
    def __init__(self, host="127.0.0.1", port=24689, timeout=600):
        self.s = socket.create_connection((host, port), timeout=10)
        self.s.settimeout(timeout)
        self.buf = b""
        self.no_ack = False

    # --- packet layer ---
    def _send(self, data):
        pkt = b"$" + data.encode() + b"#%02x" % (sum(data.encode()) & 0xFF)
        while True:
            self.s.sendall(pkt)
            if self.no_ack:
                return
            c = self._read(1)
            if c == b"+":
                return

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(65536)
            if not chunk:
                raise ConnectionError("gdbstub closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _recv(self):
        while True:
            c = self._read(1)
            if c == b"$":
                break
        data = b""
        while True:
            c = self._read(1)
            if c == b"#":
                self._read(2)
                break
            data += c
        if not self.no_ack:
            self.s.sendall(b"+")
        return data.decode(errors="replace")

    def cmd(self, data):
        self._send(data)
        return self._recv()

    # --- helpers ---
    def regs(self):
        r = self.cmd("g")
        # Citra may still have a queued stop reply (another core/thread stopping); skip those.
        for _ in range(8):
            if len(r) >= 128 and all(c in "0123456789abcdefABCDEFx" for c in r[:128]):
                break
            self.stray = getattr(self, "stray", []) + [r]
            r = self._recv()
        vals = [struct.unpack("<I", bytes.fromhex(r[i * 8:i * 8 + 8].replace("x", "0")))[0] for i in range(16)]
        return vals

    def set_reg(self, n, v):
        return self.cmd("P%x=%s" % (n, struct.pack("<I", v).hex()))

    def mem(self, addr, n):
        out = b""
        while n > 0:
            k = min(n, 0x400)
            r = self.cmd("m%x,%x" % (addr, k))
            if r.startswith("E"):
                raise IOError("read %#x: %s" % (addr, r))
            out += bytes.fromhex(r)
            addr += k
            n -= k
        return out

    def write(self, addr, data):
        return self.cmd("M%x,%x:%s" % (addr, len(data), data.hex()))

    def u32(self, addr):
        return struct.unpack("<I", self.mem(addr, 4))[0]

    def break_at(self, addr):
        return self.cmd("Z0,%x,4" % addr)

    def unbreak(self, addr):
        return self.cmd("z0,%x,4" % addr)

    def watch(self, addr, size=1, kind="w"):
        z = {"w": 2, "r": 3, "a": 4}[kind]
        return self.cmd("Z%d,%x,%x" % (z, addr, size))

    def unwatch(self, addr, size=1, kind="w"):
        z = {"w": 2, "r": 3, "a": 4}[kind]
        return self.cmd("z%d,%x,%x" % (z, addr, size))

    def cont(self):
        self._send("c")

    def wait(self, timeout=None):
        """Wait for a stop reply after cont(); returns the raw stop packet (e.g. 'T05...')."""
        old = self.s.gettimeout()
        if timeout is not None:
            self.s.settimeout(timeout)
        try:
            while True:
                p = self._recv()
                if p[:1] in ("T", "S", "W", "X"):
                    return p
                self.stray = getattr(self, "stray", []) + [p]
        finally:
            self.s.settimeout(old)

    def interrupt(self):
        self.s.sendall(b"\x03")
        return self._recv()

    def step(self):
        return self.cmd("s")
