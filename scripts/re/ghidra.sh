#!/bin/sh
# ghidra.sh analyze            first-time import + full auto-analysis of Tomodachi code.bin
# ghidra.sh decomp <hex> ...   decompile the functions containing these addresses
# Needs a JDK 21 and Ghidra 12.1.4 under tools/ (JDK_HOME / GHIDRA_HOME override), Git Bash (cygpath).
R=$(cd "$(dirname "$0")/../.." && pwd)
D=${POKEDACHI_DATA:-$R/../Pokedachi-data}
export JAVA_HOME="${JDK_HOME:-$R/tools/jdk/jdk-21.0.12.1+1}"
export PATH="$JAVA_HOME/bin:$PATH"
H="${GHIDRA_HOME:-$R/tools/ghidra/ghidra_12.1.4_PUBLIC}/support/analyzeHeadless.bat"
mkdir -p "$D/ghidra"
P=$(cygpath -w "$D/ghidra")
S=$(cygpath -w "$R/scripts/re/ghidra")
case "$1" in
  analyze)
    "$H" "$P" tomodachi -import "$(cygpath -w "$D/tomodachi/exefs/code.bin")" \
      -processor ARM:LE:32:v6 -loader BinaryLoader -loader-baseAddr 0x100000 \
      -scriptPath "$S" -preScript PokedachiPre.java -analysisTimeoutPerFile 14400 -max-cpu 6 ;;
  decomp)
    shift
    "$H" "$P" tomodachi -process code.bin -noanalysis -readOnly -scriptPath "$S" -postScript Decomp.java "$@" 2>&1 \
      | sed -n '/^INFO  Decomp.java>/,$p' | sed 's/^INFO  Decomp.java> //; /^INFO  /d; /^ *(GhidraScript)/d' ;;
esac
