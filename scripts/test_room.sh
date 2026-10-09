#!/bin/sh
# Deterministic in-game check on the portable test Citra (fixed clock, pristine save copy):
# boot -> island -> Mii Apartments -> window (x,y) -> top-screen shot -> enter -> close-up shot.
# usage: test_room.sh <shot-prefix> [x y]      (TOMODACHI_ROM = your decrypted .3ds)
R=$(cd "$(dirname "$0")/.." && pwd)
D=${POKEDACHI_DATA:-$R/../Pokedachi-data}
C="python -I $R/scripts/citra.py"
S=$D/shots
X=${2:-179}; Y=${3:-63}
$C kill >/dev/null 2>&1
$C reset >/dev/null
$C launch "${TOMODACHI_ROM:-$D/roms/tomodachi.3ds}" >/dev/null
sleep 45
$C tap 160 120 150; sleep 10
$C tap 112 69 150; sleep 7
$C tap 160 226 150; sleep 12
$C tap $X $Y 150; sleep 9
$C shot $S/$1_top.png >/dev/null
$C tap 160 226 150; sleep 10
$C shot $S/$1_in.png >/dev/null
echo "done $1"
