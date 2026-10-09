"""Where everything lives. Defaults suit this layout (override any of them with environment variables):

    <somewhere>/Pokedachi-Life/      this repo (scripts, PokeTool source, tools/ after setup)
    <somewhere>/Pokedachi-data/      your extracted games, build output, test Citra, save backups

POKEDACHI_DATA   the data folder above
TOMODACHI_ROM    your decrypted Tomodachi Life (USA) .3ds, only needed to launch the test Citra
CITRA_DIR        your Citra user folder for --real installs (default %APPDATA%/Citra)
CITRA_EXE        your citra-qt.exe, only for POKEDACHI_REAL=1 citra.py launch
POKEDACHI_DOTNET dotnet executable (default: tools/dotnet/dotnet.exe if setup put one there, else dotnet)
"""
import os
import shutil

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("POKEDACHI_DATA") or os.path.join(os.path.dirname(REPO), "Pokedachi-data")
TOMODACHI_ROM = os.environ.get("TOMODACHI_ROM") or os.path.join(DATA, "roms", "tomodachi.3ds")
CITRA_DIR = os.environ.get("CITRA_DIR") or os.path.join(os.environ.get("APPDATA", ""), "Citra")
CITRA_EXE = os.environ.get("CITRA_EXE", "")
TITLE_ID = "000400000008C300"

_local_dotnet = os.path.join(REPO, "tools", "dotnet", "dotnet.exe")
DOTNET = os.environ.get("POKEDACHI_DOTNET") or (_local_dotnet if os.path.exists(_local_dotnet) else shutil.which("dotnet") or "dotnet")
POKETOOL = [DOTNET, os.path.join(REPO, "build", "PokeTool", "PokeTool.dll")]
