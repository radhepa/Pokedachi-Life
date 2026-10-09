#!/bin/sh
# Boot Tomodachi Life in Citra and open apartment window (col,row given in 3DS touch coords; default Apt 205).
# usage: goto_room.sh <shot-prefix> [x y]      (TOMODACHI_ROM = your decrypted .3ds)
R=$(cd "$(dirname "$0")/.." && pwd)
D=${POKEDACHI_DATA:-$R/../Pokedachi-data}
C="python -I $R/scripts/citra.py"; S=$D/shots
X=${2:-179}; Y=${3:-63}
$C kill >/dev/null 2>&1; sleep 2
$C launch "${TOMODACHI_ROM:-$D/roms/tomodachi.3ds}" >/dev/null
sleep 28; $C shot $S/$1_0title.png >/dev/null
$C tap 160 120 150; sleep 7
$C tap 112 69 150; sleep 7
$C tap 160 226 150; sleep 7
$C tap $X $Y 150; sleep 6
$C shot $S/$1_room.png
