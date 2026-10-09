#!/bin/sh
# One-time setup (Windows, Git Bash): fetch SPICA at the tested commit, apply Pokedachi's fixes to it,
# and build PokeTool into build/PokeTool.
#   needs: git, a .NET 8 SDK (dotnet on PATH, or POKEDACHI_DOTNET), Python 3.10+ with Pillow, uv
set -e
cd "$(dirname "$0")"
SPICA_COMMIT=bd29a78
if [ ! -d tools/SPICA ]; then
  git clone --quiet https://github.com/gdkchan/SPICA.git tools/SPICA
  git -C tools/SPICA checkout --quiet $SPICA_COMMIT
  git -C tools/SPICA apply --ignore-whitespace ../../patches/SPICA.patch
  echo "SPICA $SPICA_COMMIT + patches/SPICA.patch"
fi
DOTNET=${POKEDACHI_DOTNET:-tools/dotnet/dotnet.exe}
[ -x "$DOTNET" ] || DOTNET=dotnet
"$DOTNET" build src/PokeTool/PokeTool.csproj -c Release -o build/PokeTool | tail -2
python -c "import PIL" 2>/dev/null || echo "note: pip install pillow"
command -v uv >/dev/null || echo "note: install uv (https://docs.astral.sh/uv/) for the code patch step"
echo "ready: see README.md -> Build it yourself"
