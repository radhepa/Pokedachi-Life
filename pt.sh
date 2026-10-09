#!/bin/sh
# Run PokeTool (the CGFX converter in src/PokeTool) with the .NET runtime setup.sh put in tools/, or the
# system one. POKEDACHI_DOTNET overrides.
R=$(cd "$(dirname "$0")" && pwd)
DOTNET=${POKEDACHI_DOTNET:-$R/tools/dotnet/dotnet.exe}
[ -x "$DOTNET" ] || DOTNET=dotnet
exec "$DOTNET" "$R/build/PokeTool/PokeTool.dll" "$@"
