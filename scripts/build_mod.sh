#!/bin/sh
# Build the whole Pokedachi mod from the extracted game data and install it into a Citra instance.
#   build_mod.sh            -> portable test Citra (Pokedachi-data/citra-test)
#   build_mod.sh --real     -> your own Citra (%APPDATA%/Citra, or CITRA_DIR); backs up your island first
#   SKIP_BODIES=1 build_mod.sh   reuse work/pokedex (skip the model conversion, ~2 min)
#   NEWS_LIFT=0.2                how far the Mii News anchor is raised (Tomodachi units)
# Only Citra's load/mods/<title> folder is written. Saves are never touched, so your island stays as it
# is across installs and mod versions (backup_save.py keeps a copy anyway).
set -e
cd "$(dirname "$0")/.."
D=${POKEDACHI_DATA:-../Pokedachi-data}
PY="python -I"
export PYTHONIOENCODING=utf-8
[ "$1" != "--real" ] || $PY scripts/backup_save.py
[ -n "$SKIP_BODIES" ] || $PY scripts/build_pokedex.py | tail -1
./pt.sh hideface $D/dec/tomodachi/model/material/face $D/work/noface
./pt.sh hideface $D/dec/tomodachi/model/headwear $D/work/nohat
$PY scripts/build_editor.py
$PY scripts/build_text.py
# Mii News: the anchor sits behind a desk; Pokémon heads are lower than Mii heads, so lift the anchor.
mkdir -p $D/work/anims
$PY scripts/liftanim.py $D/dec/tomodachi/model/body/body_common_animNewsStudio.bin $D/work/anims/body_common_animNewsStudio.bin ${NEWS_LIFT:-0.2} bodySpNews
# Mii News interviews frame a Mii's head: raise the islander so the Pokémon's head is in the shot.
mkdir -p $D/work/news
$PY scripts/movebone.py $D/dec/tomodachi/model/news/news_common.bin $D/work/news/news_common.bin setMii00 ${INTERVIEW_LIFT:-0.15} --if-y=-1.8
uv run --quiet --with keystone-engine --with capstone python -I scripts/codepatch.py $D/tomodachi/exefs/code.bin $D/work/exefs | tail -1
I="$PY scripts/install_mod.py"
$I $D/work/pokedex model/body --clean $1
$I $D/work/anims model/body $1
$I $D/work/news model/news $1
$I $D/work/noface model/material/face $1
$I $D/work/nohat model/headwear $1
$I $D/work/layout layout $1
$I $D/work/message/Game message/Game $1
if [ "$1" = "--real" ]; then M="${CITRA_DIR:-$APPDATA/Citra}/load/mods/000400000008C300"; else M="$D/citra-test/user/load/mods/000400000008C300"; fi
mkdir -p "$M/exefs"
cp $D/work/exefs/code.ips "$M/exefs/code.ips"
echo "installed into $M"
