# MODLOG: Pokedachi Life (Tomodachi Life × Pokémon Rumble Blast)

Goal: Tomodachi Life (3DS, USA) where every Mii is a Pokémon model from Pokémon Rumble Blast.
New-Mii flow: pick a Pokémon from a Pokédex → name, voice, personality (outfits, accessories and
face editing skipped for now). Runs in Citra (LayeredFS mod), built from your own game files.

## Inputs (never committed; never shipped)
| Game | File | Title ID | Product |
|---|---|---|---|
| Tomodachi Life (USA, v1.1) | decrypted `.3ds` | 000400000008C300 | CTR-P-EC6E |
| Pokémon Rumble Blast (USA) | decrypted `.3ds` | 0004000000066C00 | CTR-P-ACCE |

Emulator: Citra (canary 2745 / nightly 2073, Jan 2024). User data `%APPDATA%/Citra`.
Mods load from `%APPDATA%/Citra/load/mods/000400000008C300/romfs/...` (LayeredFS).

Extracted data lives OUTSIDE the repo: `../Pokedachi-data/{tomodachi,rumble}` (raw),
`.../dec/...` (decompressed); see `scripts/paths.py` for the overrides.

## Route
Universal Modder has no 3DS playbook (PC-focused), so: its loop (recon → lab → vertical slice →
verify in the real game) with 3DS tooling. Route = data mod (LayeredFS romfs replacement) first;
code mod (exefs `code.ips`) later for per-Mii species and the Pokédex creation screen.

## Tooling (own code in this repo)
- `scripts/ctr_extract.py` — NCSD → NCCH → ExHeader/ExeFS/RomFS (decrypted images only), BLZ code.bin.
- `scripts/cx.py` — CX decompression: LZ10/LZ11 (Tomodachi `*_LZ.bin`) and LH = LZ77+Huffman
  (type 0x40, Rumble `*.cx`). LH layout found by experiment: u16 table size for the 9-bit
  length/literal tree ((n+1)*4 bytes incl. the field), u8 size for the 5-bit offset tree, MSB-first
  bits read byte by byte, node = offset bits + two leaf flags (0x100>>bit for 9-bit), disp =
  nb<=1 ? nb : (1<<(nb-1))|bits(nb-1), copy from out[-disp-1], length = (v&0xFF)+3.
- `src/PokeTool` — C# (.NET 8) that compiles SPICA (gdkchan, `tools/SPICA` at bd29a78 +
  `patches/SPICA.patch`, set up by `setup.sh`) for CGFX read/write. Run via `pt.sh`.
- `scripts/build_mod.sh [--real]` — whole mod from extracted data: 717 bodies + 96 female ones (`build_pokedex.py`),
  hidden faces/hats, editor layout (`build_editor.py`), text (`build_text.py`), `code.ips`
  (`codepatch.py`), then installs into the test Citra (or your own with `--real`, after
  `backup_save.py` copies the island out). `SKIP_BODIES=1` reuses the converted bodies.
- `scripts/citra.py` drives a portable test Citra (`Pokedachi-data/citra-test`, pristine save via
  `reset`); `scripts/qa_pokedex.py` taps through every Pokédex entry and writes contact sheets.
- `scripts/re/` — Ghidra headless (`ghidra.sh decomp <addr>`), capstone helpers, `cgfxdict.py`
  (checks CGFX patricia dictionaries).

## Facts
### Tomodachi Life
- RomFS: 2880 files. Models `model/<category>/<category>_<name>_LZ.bin` = LZ11 → CGFX (BCRES).
- Mii body = `model/body/body_bodyNNN[F|Ot|Sp|OtF|SpF]_LZ.bin` (outfits, 464 + variants).
  Animations = `model/body/body_common_anim<Group>_LZ.bin` (2701 skeletal anims total, names like
  `bodyCmWalk00`, `bodySpPersonality05`).
- Head = libMPFace (`libMPFace/MPFaceData_LZ.bin`), attached at the body skeleton's `head` bone.
- Voice = Nuance Vocalizer TTS (`libNTTS/`).
- body000: 1 skinned shape (7 submeshes, Smooth skinning, 48-byte vertices incl. tangent), material
  `mtBdDef` (normal map + 2 textures), meshNode `ankleModel`, 26-bone skeleton:
  all_root, body, hips, L/R_leg, L/R_knee, L/R_ankle, back/front_skirt1/2, waist, L/R_shoulder,
  L/R_elbow, L/R_hand1, L/R_handItem, neck, head, waistItem, shadow.
- **All 2701 anims rotate limbs/neck/waist/hips only** (0 translation keys, 0 scale keys on them).
  Only `body` (root motion, Y≈0.6), `*Item`, `shadow` get translation. ⇒ limb joint positions in the
  bind pose can be moved freely per species.
- Paths are built from fragments in code (`rom:/layout/layout_` + name + `_LZ.bin` etc.).

### Pokémon Rumble Blast
- RomFS: 4910 files. Pokémon = `pii/<ROMAJI>[_M|_F|_form].bcres.cx` (829 models) + `pii/anim.bcres.cx`
  (shared animations `Pii_ROOT_...`). `.cx` = LH compression → CGFX.
- Model name encodes body type: twoleg 307, float 133, fourleg 129, fish 58, insect 43, bird 39,
  butterfly 31, bound 26, seal 22, glide 20, slime 15, rolling 6.
- Bone vocabulary: ROOT, BODY, ARM, HEAD, EAR, LEG, TAIL, TAILEND, NECK, LEFT_WING, RIGHT_WING, COLL.
  Parts are rigid toys (one bone per part, both arms share ARM, all legs share LEG).
- Pikachu: 2 shapes (body 36-byte verts, eyes 32-byte with fixed bone), textures 64x64 + 32x128 RGB565.
- Names in `msg/US_English/pokemon.msbt`.

## Plan
1. Pipeline check: SPICA round-trip of body000 → LZ11 → LayeredFS → game still renders.
2. Hide the Mii head (try head bone scale 0 in the body skeleton).
3. Converter: Pokémon parts rigidly skinned onto the Mii skeleton, joints moved to the Pokémon's
   anatomy. Mapping: HEAD/EAR/NECK→neck, BODY→waist, ARM/wings→L/R_shoulder (split by side),
   LEG→L/R_leg (split by side), TAIL/TAILEND→hips.
4. Vertical slice: every Mii = Pikachu, verified by screenshot in Citra.
5. Code mod: per-Mii species (stored in Mii data) + Pokédex picker replacing the face editor.

### Verified in game (Citra nightly 2073, driven by `scripts/citra.py` window messages, no real input)
- SPICA-resaved + `cx.py` LZ11 bodies load and render (pipeline OK).
- Bone scale on the body's `head` bone does NOT hide the Mii head (face attach ignores scale).
- **Mii heads are drawn with the material templates in `model/material/face/*`** (mtFaceDefault, Gold,
  Ice, ...). `pt.sh hideface` (colour+depth writes off, alpha test Never) on all 26 files ⇒ heads, hair and
  faces vanish while bubbles/cameras still track the head. Same trick on `model/headwear/*` hides hats.
- First Pokémon bodies were invisible. Causes found:
  1. SPICA `GfxBoundingBox` lacked the leading u32 type word (0x80000000) of ResOrientedBoundingBox, so every
     OBB field was shifted. Patched `tools/SPICA/.../GfxBoundingBox.cs` (added `Type`).
  2. Tomodachi outfits have NO MeshNodeVisibilities and their mesh has MeshNodeIndex = -1. Pokémon meshes
     kept index 0 into an empty table ⇒ garbage visibility. Converter now writes -1.
- Stored bone WorldTransform is identity in both games (runtime-filled); InvWorldTransform matches
  inverse(local chain) to 6e-8; local = S·Rx·Ry·Rz·T (row vectors).
- Material LUT refs: Tomodachi body uses TableName=`defSpc0`, SamplerName=`lutCommon`, LightSetIndex 2.
- Pokémon materials must clone the Mii body material `mtBdDef` (Look 5) or room lighting washes them out.

### Code patch (`scripts/codepatch.py` → `exefs/code.ips`, USA v1.1)
- **Pokédex slot = hair style + 132 × hair colour** (both invisible: heads are hidden), up to 1056 slots.
  The Pokédex has 717 entries: species #1–646 in dex order (slots 0–645), then 71 alternate forms
  (Unown B–?, Castform, Deoxys, Burmy/Wormadam, Cherrim, Shellos/Gastrodon, Rotom, Giratina, Shaymin,
  Arceus, Basculin, Darmanitan, Deerling/Sawsbuck). Keldeo/Meloetta/Genesect are red placeholders in
  Rumble Blast (texture `Pii_tmpmdl`), so they're left out.
- New code lives in the zero padding after `.text` (0x84f390–0x850000, mapped r-x, 3184 bytes).
- Body: `0x73246c` (outfit path builder) jumps to the cave, which builds
  `rom:/model/body/body_pk%03d[F]_LZ.bin` from the CFL record (record at MiiActor+0xe64, CFL right
  before it: version rec[-0x60] = 3, hair rec[-0x2e], colour rec[-0x2d] & 7). Slots ≥ 717 (old Miis'
  unused combinations) wrap around. `F` = female (outfit setter's r2, MiiActor+0xf4c) and the species
  has a separate female model (bitmap in the cave; 96 species, e.g. Pikachu, Jellicent).
- Pokédex grid (hair page): init `0x32ce88..` → 60 pages, 720 icons named `IconHair<slot>.bclim`
  (name table pointer zeroed), TexInfo array 0x3900 bytes, icon-count byte 0 = unlimited (the shared
  page updater `0x32b3b8` got 2 spare nops to treat 0 that way; other pages are unaffected).
  Icon tap `0x32d138` → cave `pick(scene, slot)`: edit params +0xe80 = slot % 132, +0xe84 = slot / 132,
  +0xe88 = 0, preview rebuild, copy into the CFL, ChangeOutfit (`0x33394C`) so the preview swaps live.
  Taps on the 3 blank icons on page 60 re-pick the current slot (skipping the game's tap handling for
  them left those 3 buttons dead on every page afterwards). Page open `0x32c478` computes the page/button
  from hair + 132 × colour instead of searching the 132-entry table.
- Editor: Appearance opens on tab 1 (hair = Pokédex) with camera 1 (full body) and keeps it
  (`0x3C4218`, `0x3C4260`, `0x3C4BE8`). Tabs, photo button, hair flip and colours hidden in
  `layout_editor` (`build_editor.py`); 720 icons (32×28 in 32×32 RGBA5551, 2 KB each, stretched by
  the 52×44 buttons) added to the archive (`darc.repack(additions=...)`).
- Jump tabs: the hair page's 8 colour buttons (+0x30c + i×0x5c, selected index +0xa3c). Buttons 0–5
  became Gen I–V / Forms tabs (pages 1, 13, 21, 33, 42, 54); 6–7 hidden. Layout (`build_editor.add_tabs`):
  swatch material konst0 → white, swatch 32 px, plus a child pic pane `I_Color_0i` (I_Part_00's pane and
  material as templates) showing `PkTab<i>.bclim`, a Roman numeral I–VI (Arial Rounded MT Bold,
  RGBA4 for soft edges; txl1 + mat1 appended). The swatch material itself
  can't show an icon: its texture is an A4 mask tinted by konst0, and its Select/Decide animations
  drive texMap 1 (ring) + konst1, so it's kept for the highlight. Code: colour tap `0x32d1f8` →
  cave `tab_tap(i, this)` (page, icons, counter text, picked-icon highlight) then the game's colour
  sound; both arrow `bl 0x32b3b8` → `icons_tabs`; page open `0x32c524/0x32c52c` picks the tab from
  the page instead of the hair colour.
- keystone resolves `bl <absolute>` wrongly after `.byte` data in the same asm (every call target
  shifted by the data size), so all cave code comes before all cave data and `codepatch.py` checks
  every call target against the known functions.
- Text: editor title "Pokédex"; Town Hall entry dialog "Who's moving in?" / "Choose from Pokédex".

### File-format traps (Pokémon rendered solid black or as noise)
1. **IMAG data start must be 0x80-aligned.** The game relocates the IMAG block, so texture alignment
   counts from the byte after the IMAG header, not from the file start. SPICA wrote IMAG straight after
   the strings, so every texture was off by (start mod 8) bytes; the 8x8 helper textures then read their
   neighbours' bytes. Odd start ⇒ mask alpha 0 ⇒ the whole model black (73/132 at one point, 100%
   correlation; even start ⇒ fine). Found with Citra's texture dump: the helpers' hashes differed per
   species and decoded as `0F 00` read one byte off. SPICA patched: `Section.DataAlign`/`HeaderSize`
   pad before the IMAG header, DATA length runs up to it (as in Nintendo's files), and
   `Section.ValueAlign` = 0x80 puts each buffer on 0x80 too.
2. **ETC1** is transcoded to RGB565 (ETC1A4 → RGBA4) in the converter. Geodude's noise was probably
   trap 1, but the RGB565 path is proven, so it stays.
3. **LZ11 distance 1**: Nintendo's encoder never emits it, so `cx.lz11_compress` doesn't either now.
   This did NOT change which models were black (a precaution, not a fix).
4. `darc.repack` must keep each file's alignment (`.bclim` 0x80) or layout textures break.
5. `install_mod.py --clean` wipes the whole mod folder; use `build_mod.sh` to reinstall everything.
6. SPICA reads CGFX skeletal animations but writes curves the game (and SPICA) can't read back. Edit
   animation files in place instead (`scripts/liftanim.py`), same for bones (`scripts/movebone.py`).

### Grabbing (picking a Mii up)
- Gesture (vanilla): press the very top of the head and slide up; the Mii dangles from a closed hand.
  Touching the face/body pats it or zooms in instead.
- The game looks for that touch at a **fixed height**, about a Mii's head top (≈1.4–1.65 units for the
  default Mii height). It does not follow the model: moving the hidden head (the 'head' bone) or
  clamping the shapes' bounding boxes didn't move it (probed on Pikachu/Abra/Togekiss).
- At 1.4 units tall every Pokémon's top was just *below* that band, so grabbing only worked by touching
  empty air above it. Fix: scale each Pokémon so the top of its head (HEAD part) is at 1.5, capped at
  1.7 total height (23 species with tall ears/leaves are grabbed by those). `build_pokedex.py`
  HEAD_TOP/HEIGHT. 'head' bone back at the centre of the HEAD part (face close-ups, bubbles).

### Mii News framing
- Anchor sits behind the studio desk (`bodySpNewsWait00-04`, body Y ≈ 0.13); Pokémon heads are lower
  than a Mii's, so the body is raised (`NEWS_LIFT`, 0.2) in `body_common_animNewsStudio`.
- Interviews (`model/news/news_common`, models newsInterview00/01) place the islander at bone
  `setMii00` (0, −1.8, −0.5, scale 1.4) for a head-and-shoulders shot; raised by `INTERVIEW_LIFT` (0.15).
- The 240 `news_newsImageNNN` scenes place Miis at 509 `setMii*` bones, mostly full-body; left as is.

## Log
- 2026-10-08: recon done, extractors + LH decoder written, SPICA builds, anim/skeleton survey done.
- 2026-10-08: pipeline + head hiding verified in game; Pikachu converter written; debugging visibility.
- 2026-10-08 ~11pm: **VERTICAL SLICE WORKS.** Every outfit (484 `body_body*`) converted from PIKATYUU_M,
  faces + headwear hidden ⇒ residents are Rumble Pikachu toys, animated by Tomodachi (head turns in idle).
  Delete `%APPDATA%/Citra/load/mods/000400000008C300` to undo any install.
  Known: colour a bit washed out under room lights (specular LUT swap), only checked idle/standing.

- 2026-10-08/09: lighting fixed (Look 5), 132 Pokémon (Gen 1–5) built, per-Mii species + live Pokédex
  pick via `code.ips`, Pokédex icons in the hair grid.
- 2026-10-09: editor reduced to the Pokédex (only the grid + page arrows; full-body camera), Pokémon
  height 1.4 so heads stay in view. Found and fixed the file-format traps above.
  `qa_pokedex.py` sweep: **132/132 render correctly** (`Pokedachi-data/shots/qa/overview_*.png`).
- 2026-10-09: Town Hall → New Mii shows only "Choose from Pokédex" (EditFirst buttons 01/02 hidden in
  `layout_cityhall`, intro text reworded) → gender → Pokédex → Profile (names via the real swkbd applet)
  → Voice → Personality → Done: verified end to end, the new Charmander moved into an apartment.
- 2026-10-09: installed into my own Citra (`build_mod.sh --real`, identical to the tested files),
  save + extdata + previous mod backed up first.

- 2026-10-09: Mii News anchor + interviews raised so the Pokémon are in shot; grabbing works by the top
  of the head (Pokémon scaled to head top 1.5). Gender step kept on purpose: Pokémon have genders.
  Final values NEWS_LIFT 0.2 / INTERVIEW_LIFT 0.15 were lowered for the taller scale and are NOT yet
  checked in game (0.3/0.3 were, at the old scale); Pikachu grab at the new scale also unchecked.
  Installed into my own Citra (backup first).

- 2026-10-09: **every Rumble Blast Pokémon**: 717 Pokédex entries (#1–646 + 71 forms), 60 pages;
  slot stored in hair style + 132 × hair colour; female models (96 species) for female islanders.
  Verified in the test Citra: page 35 opens on Bastiodon (an islander with hair 14, colour 3), picking
  Pachirisu swaps the preview, page 60's 3 blank icons change nothing, a female islander picking Jellicent
  gets the pink female model, Done saves it and reopening the editor lands on page 50 with Jellicent
  selected. SPICA `Gfx.Open` now opens read-only/shared so `build_pokedex.py` converts in parallel.
  Existing islanders get new Pokémon (hair + 132 × colour); re-pick them in Edit Mii → Pokédex.
  `qa_pokedex.py` sweep over all 60 pages: every entry renders. (Harness note: a long arrow tap can
  auto-repeat and skip pages, so check each sheet's page label; `citra.py launch` no longer steals focus.)
  Installed into my own Citra (`build_mod.sh --real` now backs the island up by itself first).

- 2026-10-09: **Gen I–V + Forms jump tabs** beside the Pokédex grid, labelled I–VI (VI = forms; first
  tried starter icons).
  Verified in the test Citra: each tab opens its page, the arrows move the lit tab, a pick made after a
  tab jump (Serperior) saves and reopens on page 42 with Gen V lit. README: the clipped nap shot is
  replaced by the tabs.

## Next
1. Polish: sitting/lying offsets, close-ups in other scenes, newsImage scenes that frame a head.
2. Swapping layout files while Citra runs and reopening the editor showed blank tab icons; a fresh
   boot is fine (3 reopen cycles checked). Always restart the test Citra after reinstalling.
