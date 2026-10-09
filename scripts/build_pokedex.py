"""Build the Pokédex: every Pokémon in Rumble Blast -> body_pkNNN.bin (NNN = Pokédex slot) + a manifest.

    python -I build_pokedex.py

Slots 0..645 are the 646 species in National Dex order (default form), then the 71 alternate forms
(Unown letters, Castform weathers, Deoxys, Burmy/Wormadam cloaks, Rotom, Arceus types, ...): 717
entries. Species with a separate female model in Rumble Blast (96 of them) also get body_pkNNNF.bin,
which the code patch loads for female islanders.

A Mii stores its slot in its hair style and hair colour (both unused: heads are hidden):
slot = hair + 132 * colour (codepatch.py), so up to 1056 entries fit.
"""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import DATA, POKETOOL as PT  # noqa: E402

HEAD_TOP = 1.5  # Tomodachi units: top of the head at a Mii's head height, where the game lets you grab it
HEIGHT = 1.7    # never taller than this (Pokémon with tall ears/leaves); keeps them in the editor's view
# Keldeo, Meloetta and Genesect hadn't been revealed when Rumble Blast shipped: their slots hold a
# red placeholder model (texture Pii_tmpmdl) and icon, so they're left out.
PLACEHOLDERS = {647, 648, 649}


def species_groups():
    """Rumble's model roster grouped per species, in dex order: [[entry, form entries...], ...].
    The roster's own dex/name columns drift on forms, so species are split on the model name
    (ANNOON_A..ANNOON_QUE are all Unown, X649_F0..F4 all Genesect); eggs/cannons are dropped."""
    roster = json.load(open(os.path.join(DATA, "rumble_roster.json")))
    names = {}
    for r in roster:
        names.setdefault(r["dex"], r["name"])
    groups = []
    for r in roster:
        m = r["model_m"]
        if m in ("NOTUSED", "TEST") or m.startswith("TAMAGO"):
            continue
        if groups and groups[-1][0]["model_m"].split("_")[0] == m.split("_")[0]:
            groups[-1].append(r)
        else:
            groups.append([r])
    assert len(groups) == 649, len(groups)
    return groups, names


def entries():
    groups, names = species_groups()
    icons = set(f[:-4] for f in os.listdir(os.path.join(DATA, "rumble", "romfs", "pokeicon", "full")))
    out, forms = [], []
    for i, g in enumerate(groups):
        dex = i + 1
        if dex in PLACEHOLDERS:
            continue
        name = names[dex]
        for form, r in enumerate(g):
            icon = next(n for n in ("N%03d_%s_%02d" % (dex, k, form) for k in "umf") if n in icons)
            e = dict(dex=dex, name=name, form=form, model=r["model_m"],
                     model_f=r["model_f"] if r["model_f"] != r["model_m"] else None, icon=icon)
            if form:
                e["name"] = "%s (%s)" % (name, r["model_m"].split("_", 1)[1].title())
            (forms if form else out).append(e)
    out += forms
    for slot, e in enumerate(out):
        e["slot"] = slot
    return out


def convert(job):
    src, dst = job
    body = os.path.join(DATA, "dec", "tomodachi", "model", "body")
    res = subprocess.run(PT + ["pokebody", os.path.join(body, "body_body000.bin"), src, dst,
                               os.path.join(body, "body_common_animCm.bin"), str(HEIGHT), str(HEAD_TOP)],
                         capture_output=True, text=True)
    ok = res.returncode == 0 and os.path.exists(dst)
    return ok, (res.stdout + res.stderr)[-300:]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    dex = entries()
    out_dir = os.path.join(DATA, "work", "pokedex")
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):                  # drop bodies from older numberings
        os.remove(os.path.join(out_dir, f))
    pii = os.path.join(DATA, "dec", "rumble", "pii")
    jobs = []
    for e in dex:
        jobs.append((e, "", os.path.join(pii, e["model"] + ".bcres"), os.path.join(out_dir, "body_pk%03d.bin" % e["slot"])))
        if e["model_f"]:
            jobs.append((e, "F", os.path.join(pii, e["model_f"] + ".bcres"), os.path.join(out_dir, "body_pk%03dF.bin" % e["slot"])))
    failed = []
    with ThreadPoolExecutor(max_workers=max(2, (os.cpu_count() or 4) // 2)) as ex:
        for (e, sfx, _, _), (ok, log) in zip(jobs, ex.map(convert, [(s, d) for _, _, s, d in jobs])):
            e["ok" + sfx] = ok
            if not ok:
                failed.append((e["slot"], e["name"] + sfx, log))
    json.dump(dex, open(os.path.join(DATA, "pokedex_manifest.json"), "w"), indent=1)
    for f in failed:
        print("FAIL", f)
    print("built %d entries (%d with a female model), %d failed" % (len(dex), sum(1 for e in dex if e["model_f"]), len(failed)))


if __name__ == "__main__":
    main()
