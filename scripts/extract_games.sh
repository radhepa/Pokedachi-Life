#!/bin/sh
# Unpack your own decrypted game dumps into POKEDACHI_DATA (default ../Pokedachi-data):
#   extract_games.sh <Tomodachi Life (USA).3ds> <Pokemon Rumble Blast (USA).3ds>
# -> tomodachi/ + rumble/ (raw ExeFS/RomFS), dec/ (decompressed models, layouts, text),
#    rumble_roster.json (Rumble's model list). Takes a few minutes; ~3 GB.
set -e
cd "$(dirname "$0")/.."
D=${POKEDACHI_DATA:-../Pokedachi-data}
[ $# -eq 2 ] || { echo "usage: $0 <tomodachi.3ds> <rumble_blast.3ds>"; exit 1; }
PY="python -I"
$PY scripts/ctr_extract.py "$1" "$D/tomodachi"
$PY scripts/ctr_extract.py "$2" "$D/rumble"
$PY scripts/cx.py --tree "$D/tomodachi/romfs" "$D/dec/tomodachi"
$PY scripts/cx.py --tree "$D/rumble/romfs" "$D/dec/rumble"
$PY scripts/rumble_roster.py
echo "extracted into $D"
