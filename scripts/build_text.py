"""Pokedachi text changes (US English) -> work/message/Game/Game_US_English.bin

    python -I build_text.py
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import DATA  # noqa: E402
HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


darc, msbt = load("darc"), load("msbt")

CHANGES = {
    "ArcBase/Edit.msbt": {
        "Edit_Title_Face": "Pokédex",
    },
    "ArcBase/Cityhall.msbt": {
        "EntryDialog_New": "A new islander is moving in!\n\nPick a Pokémon from the Pokédex.",
        "EntryDialog_Intro_00": "Who's moving in?",
        "EntryDialog_Intro_01": "Choose from Pokédex",
        "EntryDialog_PhotoOrHand_01": "Who's moving in?",
        "EntryDialog_PhotoOrHand_02": "Choose from Pokédex",
    },
}


def main():
    src = os.path.join(DATA, "dec", "tomodachi", "message", "Game", "Game_US_English.bin")
    data = open(src, "rb").read()
    files = {p: data[o:o + s] for p, o, s in darc.walk(darc.parse(data))}
    repl = {path: msbt.set_texts(files[path], changes) for path, changes in CHANGES.items()}
    out = darc.repack(data, repl)
    dst = os.path.join(DATA, "work", "message", "Game")
    os.makedirs(dst, exist_ok=True)
    open(os.path.join(dst, "Game_US_English.bin"), "wb").write(out)
    # verify
    check = {p: out[o:o + s] for p, o, s in darc.walk(darc.parse(out))}
    for path, changes in CHANGES.items():
        labels, texts = msbt.read(check[path])
        inv = {v: k for k, v in labels.items()}
        for label, text in changes.items():
            assert texts[inv[label]] == text, (label, texts[inv[label]])
    print("text ok:", sum(len(c) for c in CHANGES.values()), "strings,", len(out), "bytes")


if __name__ == "__main__":
    main()
