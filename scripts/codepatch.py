"""Build Pokedachi's code patch (exefs/code.ips) for Tomodachi Life (USA, v1.1, code.bin at 0x100000).

    uv run --with keystone-engine --with capstone python -I codepatch.py <code.bin> <out_dir>

Writes <out_dir>/code.ips (Citra/Luma IPS against the decompressed code.bin) and prints a disassembly
of every patched region. Each patch declares the address range it may overwrite and, where it edits the
game's own code, the instructions it expects there; the build fails if new code doesn't fit or the
original isn't what we expect (wrong game version).

Pokédex size and the female-model list come from Pokedachi-data/pokedex_manifest.json (build_pokedex.py).
"""
import hashlib
import json
import os
import struct
import sys

import capstone
import keystone

BASE = 0x100000
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import DATA  # noqa: E402

MANIFEST = os.path.join(DATA, "pokedex_manifest.json")

# --- Pokédex size --------------------------------------------------------------------------------
# A Mii's Pokédex slot lives in its hair style (0..131) and hair colour (0..7), both invisible because
# heads are hidden: slot = hair + 132 * colour, up to 1056 slots. The grid shows 12 per page.
DEX = json.load(open(MANIFEST))
SPECIES = len(DEX)                       # 717: 646 species + 71 alternate forms
PER_PAGE = 12
PAGES = -(-SPECIES // PER_PAGE)          # 60
SLOTS = PAGES * PER_PAGE                 # 720 icons (the last few blank)
FEMALE = bytearray((SPECIES + 7) // 8)   # bit set = body_pkNNNF exists (separate female model)
for e in DEX:
    if e.get("model_f"):
        FEMALE[e["slot"] >> 3] |= 1 << (e["slot"] & 7)
assert SPECIES <= 132 * 8


def utf16z(s):
    return s.encode("utf-16-le") + b"\0\0"


def words(b):
    """bytes -> '.byte ...' lines for keystone."""
    return "\n".join("    .byte " + ", ".join(str(x) for x in b[i:i + 16]) for i in range(0, len(b), 16))


# --- Game functions we call ----------------------------------------------------------------------
SWPRINTF = 0x1876EC          # (buf, size, count, fmt, ...)
WSTRCOPY = 0x39EFFC          # copies a wide string into the body object's path string (+0xc4)
DIVMOD = 0x30209C            # (a, b) -> r0 = a / b, r1 = a % b
REFRESH = 0x3C3C44           # editor: rebuild the preview Mii from the edit params (scene)
CHANGE_OUTFIT = 0x33394C     # (actor, outfit, colour): outfit path + reload (calls BODY_FN)
PAGE_ICONS = 0x32B3B8        # (page, per_page): puts the page's icons on the 12 grid buttons
BUTTON_ON = 0x4A8024         # (button, on, s0 = anim speed): selected-state highlight

# --- Free space: padding after .text (0x84f390..0x850000 is mapped r-x and all zero) ---------------
CAVE = 0x84F390
CAVE_END = 0x850000

# Patch 1 (in the cave, after patch 2): Mii body = the Pokémon in the Mii's Pokédex slot.
#
# 0x73246c is the game's "set outfit model" function: (this = MiiActor+0x690, clothes, female, Ot, Sp).
# It stored the outfit index at this+0x130, built rom:/model/body/body_body%03d[F|Ot|Sp]_LZ.bin and
# copied it to this+0xc4. We keep the index store and the flag at +0x128, and build
# rom:/model/body/body_pk%03d[F]_LZ.bin instead:
#   MiiActor+0xe64 -> the Mii's save record; its 3DS Mii data (CFL, 0x60 bytes) sits right before it:
#   version = rec[-0x60] (always 3), hair style = rec[-0x2e], hair colour = rec[-0x2d] & 7.
#   F when the Mii is female and the species has a separate female model in Rumble Blast.
# Slots past the end (old Miis with unused hair/colour combinations) wrap around.
#
# Patch 2 (at the start of the cave): Pokédex pick. The icon-tap branch of the hair page handler calls PICK with
# (scene, slot). A tap on one of the blank icons after the last entry re-picks the Mii's current slot
# (like tapping the selected icon; skipping the game's tap handling instead left those buttons dead
# for the rest of the session). It splits the slot into hair style + colour in the edit params (MiiActor+0xe80/+0xe84,
# flip +0xe88 off), rebuilds the preview, then copies both into the Mii's own data (where patch 1
# reads them) and re-runs the outfit setter so the preview switches to the new Pokémon.
CAVE_ASM = """
pick:
    push    {r4, r5, r6, lr}
    mov     r4, r0
    ldr     r5, [r4, #0x9c]
    ldr     r2, pick_species
    cmp     r1, r2
    blo     pick_slot
    add     r3, r5, #0xe00
    ldr     r1, [r3, #0x84]
    mov     r0, #132
    mul     r1, r0, r1
    ldr     r0, [r3, #0x80]
    add     r1, r1, r0
pick_slot:
    mov     r0, r1
    mov     r1, #132
    bl      %(divmod)#x
    add     r2, r5, #0xe00
    str     r1, [r2, #0x80]
    str     r0, [r2, #0x84]
    mov     r6, r0
    mov     r0, #0
    str     r0, [r2, #0x88]
    mov     r0, r4
    bl      %(refresh)#x
    ldr     r0, [r4, #0x9c]
    ldr     r3, [r0, #0xe64]
    cmp     r3, #0
    beq     pick_done
    ldr     r2, [r0, #0xe80]
    strb    r2, [r3, #-0x2e]
    ldrb    r2, [r3, #-0x2d]
    bic     r2, r2, #0xf
    orr     r2, r2, r6
    strb    r2, [r3, #-0x2d]
    ldrsh   r1, [r3, #0x72]
    ldr     r2, [r3, #0x40]
    lsr     r2, r2, #14
    and     r2, r2, #0xf
    bl      %(change)#x
pick_done:
    pop     {r4, r5, r6, pc}
pick_species:
    .word   %(species)d

body:
    push    {r4, r5, r6, lr}
    sub     sp, sp, #0x88
    mov     r5, r0
    mov     r6, r2
    cmp     r1, #0
    movlt   r1, #0
    add     r0, r5, #0x100
    strh    r1, [r0, #0x30]
    mov     r4, #0
    ldr     r0, [r5, #0x7d4]
    cmp     r0, #0
    beq     have_slot
    ldrb    r1, [r0, #-0x60]
    cmp     r1, #3
    bne     have_slot
    ldrb    r4, [r0, #-0x2e]
    ldrb    r1, [r0, #-0x2d]
    and     r1, r1, #7
    mov     r2, #132
    mla     r4, r1, r2, r4
have_slot:
    ldr     r1, species
    cmp     r4, r1
    subhs   r4, r4, r1
    cmp     r4, r1
    movhs   r4, #0
    adr     r3, fmt_m
    cmp     r6, #0
    beq     build_path
    adr     r2, female
    ldrb    r2, [r2, r4, lsr #3]
    and     r1, r4, #7
    lsr     r2, r2, r1
    tst     r2, #1
    adrne   r3, fmt_f
build_path:
    str     r4, [sp]
    add     r0, sp, #8
    mov     r1, #0x40
    mov     r2, #0x3f
    bl      %(swprintf)#x
    mov     r0, #0
    strb    r0, [r5, #0x128]
    add     r1, sp, #8
    add     r0, r5, #0xc4
    bl      %(wstrcopy)#x
    add     sp, sp, #0x88
    pop     {r4, r5, r6, pc}

species:
    .word   %(species)d
fmt_m:
%(fmt_m)s
fmt_f:
%(fmt_f)s
    .align  2
female:
%(female)s
    .align  2
""" % dict(swprintf=SWPRINTF, wstrcopy=WSTRCOPY, divmod=DIVMOD, refresh=REFRESH, change=CHANGE_OUTFIT,
           species=SPECIES, fmt_m=words(utf16z("rom:/model/body/body_pk%03d_LZ.bin")),
           fmt_f=words(utf16z("rom:/model/body/body_pk%03dF_LZ.bin")), female=words(FEMALE))

BODY_FN = 0x73246C

# Patch 3: the hair page = a Pokédex of SLOTS icons on PAGES pages.
#
# Hair page init (0x32c930): 11 pages, 132 icons named Icon<'Hair'><table[i]>.bclim (table 0x85e8e4 =
# grid order -> hair id), a TexInfo array of 132 * 0x14 bytes, and the icon count as a byte at +0x3b.
# Now: PAGES pages, SLOTS icons named IconHair<slot>.bclim (r6 = 0 makes the name use the index), a
# bigger array, and count byte 0 = "no limit" (patch 4) because 720 doesn't fit in a byte.
INIT_PAGES = 0x32CE88        # mov r0, #0xb      -> pages (+0x39)
INIT_COUNT = 0x32CE98        # mov r7, #0x84     -> icons to load
INIT_TABLE = 0x32CE9C        # ldr r6, =0x85e8e4 -> 0 (name = index)
INIT_ALLOC = 0x32CEA4        # mov r0, #0xa50    -> TexInfo array bytes
INIT_STORE = 0x32CEAC        # strb r7, [r4, #0x3b] -> 0

# Patch 4: shared page-icon updater (0x32b3b8): shows icon page*12+i only if it's < count byte +0x3b.
# Two spare nops before it load the count early and treat 0 as unlimited (no other page uses 0).
ICONS_NOP = 0x32B434         # nop; nop
ICONS_COUNT = 0x32B44C       # ldrb r1, [r5, #0x3b]

# Patch 5: icon tap (FUN_0032d084): hair = table[page*12 + i] -> PICK(scene, page*12 + i); the rest
# of the game's tap handling runs as before. The flip-button state lookups use the same index into a
# 132-entry table; read entry 0 instead.
TAP = 0x32D138
TAP_END = 0x32D15C
FLIP_IDX = (0x32D198, 0x32D19C, 0x32D1B0, 0x32D1B4)

# Patch 6: opening the page (FUN_0032c46c): it searched the 132-entry table for the Mii's hair style
# to find the page and button. Now slot = hair + 132 * colour (wrapped like patch 1) -> page, button.
SELECT = 0x32C478
SELECT_END = 0x32C524        # continues with the colour row
SELECT_LITERAL = 0x32C640    # was =0x85e8e4, now SPECIES
SELECT_ASM = """
    vpush   {d8}
    mov     r6, r1
    str     r1, [r0, #0x44]
    vldr    s16, [pc, #%(s16)d]
    ldr     r0, [r6, #0x20]
    ldr     r1, [r6, #0x24]
    and     r1, r1, #7
    mov     r2, #132
    mla     r5, r1, r2, r0
    ldr     r1, [pc, #%(lit)d]
    cmp     r5, r1
    subhs   r5, r5, r1
    cmp     r5, r1
    bhs     %(end)#x
    add     r7, r7, #0x3d
    ldrb    r8, [r4, #0x3a]
    mov     r0, r5
    mov     r1, r8
    bl      %(divmod)#x
    strb    r1, [r4, #0xa3d]
    strb    r0, [r4, #0x38]
    strb    r0, [r4, #0xa3e]
    mov     r1, r8
    mov     r0, r4
    bl      %(icons)#x
    ldrb    r0, [r7]
    vmov.f32 s0, s16
    rsb     r1, r0, r0, lsl #3
    add     r0, r1, r0, lsl #4
    mov     r1, #1
    add     r0, r4, r0, lsl #2
    add     r0, r0, #0x400
    add     r0, r0, #0x1ec
    bl      %(button_on)#x
    b       %(end)#x
"""
SELECT_S16 = 0x32C644        # 3.0f, the highlight animation speed the original loads into s16

# Patch 7: the editor's Appearance step is just the Pokédex.
#
# FUN_003c3fd4 (step change) enters Appearance with tab 0 (face) and camera 0 (face close-up);
# FUN_003c49a0 (tab change) goes back to camera 0 when leaving the body tab. Make Appearance open on
# tab 1 (hair = Pokédex) with camera 1 (whole body, as on the Profile/Voice steps) so the Pokémon,
# which is shorter than a Mii, stays in view. The tab buttons themselves are hidden in the layout.
EDITOR_TAB_ON_ENTER = 0x3C4218    # mov r1, #0 -> FUN_00163f88(tabState, 0)
EDITOR_CAM_ON_ENTER = 0x3C4260    # mov r1, #0 -> FUN_004eb57c(camCtrl, 0)
EDITOR_CAM_LEAVE_BODY = 0x3C4BE8  # mov r1, #0 -> FUN_004eb57c(camCtrl, 0)


def tap_asm():
    return """
    ldrb    r0, [r4, #0x38]
    add     r0, r0, r0, lsl #1
    add     r1, r5, r0, lsl #2
    mov     r0, r8
    mov     r0, r0
    mov     r0, r0
    mov     r0, r0
    mov     r0, r0
    bl      pick_placeholder
"""


def select_asm():
    # pc-relative offsets: vldr is the 4th instruction, the literal load the 10th
    return SELECT_ASM % dict(s16=SELECT_S16 - (SELECT + 3 * 4 + 8), lit=SELECT_LITERAL - (SELECT + 9 * 4 + 8),
                             end=SELECT_END, divmod=DIVMOD, icons=PAGE_ICONS, button_on=BUTTON_ON)


def assemble(asm, addr, labels=None):
    for name, value in (labels or {}).items():
        asm = asm.replace(name, "%#x" % value)
    ks = keystone.Ks(keystone.KS_ARCH_ARM, keystone.KS_MODE_ARM)
    enc, _ = ks.asm(asm, addr)
    return bytes(enc)


def cave_labels():
    """Addresses of the cave's functions (keystone doesn't report labels): pick comes first and is
    self-contained, so body starts right after it."""
    return dict(pick=CAVE, body=CAVE + len(assemble(CAVE_ASM.split("body:\n")[0], CAVE)))


def ips(patches):
    out = bytearray(b"PATCH")
    for off, data in patches:
        for i in range(0, len(data), 0xFFFF):
            chunk = data[i:i + 0xFFFF]
            o = off + i
            if o == 0x454F46:
                raise ValueError("IPS can't address the 'EOF' offset")
            out += struct.pack(">I", o)[1:] + struct.pack(">H", len(chunk)) + chunk
    out += b"EOF"
    return bytes(out)


def main():
    code_path, out_dir = sys.argv[1], sys.argv[2]
    with open(code_path, "rb") as f:
        code = bytearray(f.read())
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)

    def dis(addr, n):
        return [("%s %s" % (i.mnemonic, i.op_str)).strip() for i in md.disasm(bytes(code[addr - BASE:addr - BASE + 4 * n]), addr)]

    labels = cave_labels()
    pick = labels["pick"]
    alloc = (SLOTS * 0x14 + 0xFF) & ~0xFF
    # (name, address, end, asm or raw bytes, expected original disassembly or None)
    patches = [
        ("cave", CAVE, CAVE_END, CAVE_ASM, None),
        ("body_from_slot", BODY_FN, BODY_FN + 4, "b %#x" % labels["body"], ["push {r4, r5, r6, r7, r8, sb, sl, lr}"]),
        ("init_pages", INIT_PAGES, INIT_PAGES + 4, "mov r0, #%d" % PAGES, ["mov r0, #0xb"]),
        ("init_count", INIT_COUNT, INIT_COUNT + 4, "mov r7, #%d" % SLOTS, ["mov r7, #0x84"]),
        ("init_table", INIT_TABLE, INIT_TABLE + 4, "mov r6, #0", ["ldr r6, [pc, #0x194]"]),
        ("init_alloc", INIT_ALLOC, INIT_ALLOC + 4, "mov r0, #%d" % alloc, ["mov r0, #0xa50"]),
        ("init_store", INIT_STORE, INIT_STORE + 4, "strb r6, [r4, #0x3b]", ["strb r7, [r4, #0x3b]"]),
        ("icons_count", ICONS_NOP, ICONS_NOP + 8, "ldrb r1, [r5, #0x3b]\ncmp r1, #0", ["nop", "nop"]),
        ("icons_unlimited", ICONS_COUNT, ICONS_COUNT + 4, "moveq r1, #0x10000", ["ldrb r1, [r5, #0x3b]"]),
        ("tap", TAP, TAP_END, tap_asm().replace("pick_placeholder", "%#x" % pick),
         ["ldrb r0, [r4, #0x38]", "ldr r1, [pc, #0x1f0]", "add r0, r0, r0, lsl #1", "add r0, r5, r0, lsl #2",
          "ldr r0, [r1, r0, lsl #2]", "str r0, [r7, #0x20]", "mov r0, r3", "str sb, [r7, #0x28]", "bl #0x3c3c44"]),
        ("select", SELECT, SELECT_END, select_asm(), ["ldr r2, [pc, #0x1c0]", "mov r6, r1", "vpush {d8}"]),
        ("select_literal", SELECT_LITERAL, SELECT_LITERAL + 4, struct.pack("<I", SPECIES), None),
        ("editor_tab", EDITOR_TAB_ON_ENTER, EDITOR_TAB_ON_ENTER + 4, "mov r1, #1", ["mov r1, #0"]),
        ("editor_cam", EDITOR_CAM_ON_ENTER, EDITOR_CAM_ON_ENTER + 4, "mov r1, #1", ["mov r1, #0"]),
        ("editor_cam_body", EDITOR_CAM_LEAVE_BODY, EDITOR_CAM_LEAVE_BODY + 4, "mov r1, #1", ["mov r1, #0"]),
    ]
    flip_expect = [["add r0, r0, r0, lsl #1"], ["add r0, r5, r0, lsl #2"]] * 2
    for addr, expect in zip(FLIP_IDX, flip_expect):
        patches.append(("flip_index", addr, addr + 4, "mov r0, #0", expect))
    # the literals we repurpose must hold what we think they do
    assert struct.unpack_from("<I", code, SELECT_LITERAL - BASE)[0] == 0x85E8E4
    assert struct.unpack_from("<f", code, SELECT_S16 - BASE)[0] == 3.0
    assert not any(code[CAVE - BASE:CAVE_END - BASE]), "cave isn't empty"

    records = []
    for name, addr, end, src, expect in patches:
        off, limit = addr - BASE, end - BASE
        if expect is not None and dis(addr, len(expect)) != expect:
            raise SystemExit("%s: original code at %#x is %s, expected %s (wrong game version?)"
                             % (name, addr, dis(addr, len(expect)), expect))
        orig = bytes(code[off:limit])
        blob = src if isinstance(src, bytes) else assemble(src, addr)
        if len(blob) > limit - off:
            raise SystemExit("%s: %d bytes doesn't fit in %d" % (name, len(blob), limit - off))
        if name == "select":                       # pad with nops up to where the original continues
            blob += assemble("mov r0, r0", 0) * ((limit - off - len(blob)) // 4)
        print("== %s @ %#x (%d/%d bytes, original sha1 %s)" % (name, addr, len(blob), limit - off,
                                                              hashlib.sha1(orig).hexdigest()[:16]))
        code[off:off + len(blob)] = blob
        records.append((off, blob))
        if not isinstance(src, bytes):
            n = len(blob)
            if name == "cave":                     # list the code only, not the data after it
                n = len(assemble(CAVE_ASM.split("species:")[0] + "species:\nfmt_m:\nfmt_f:\nfemale:\n", addr))
            for ins in md.disasm(blob[:n], addr):
                print("  %08x  %-8s %s" % (ins.address, ins.mnemonic, ins.op_str))
    print("Pokédex: %d entries, %d pages, %d icons, %d female models; cave %d/%d bytes"
          % (SPECIES, PAGES, SLOTS, sum(bin(b).count("1") for b in FEMALE), len(records[0][1]), CAVE_END - CAVE))
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "code.ips"), "wb") as f:
        f.write(ips(records))
    print("wrote", os.path.join(out_dir, "code.ips"))


if __name__ == "__main__":
    main()
