# Cyberpunk 2077 Mod Manager (CLI + GUI)

This project now includes a full mod manager on top of the existing extractor logic.

## What it does

- Keeps existing extraction workflow (download folder -> structured output folder).
- Adds a manager workflow for direct install/uninstall into your game folder.
- Supports:
  - Single mod archives: `.zip` files such as `M3 GTR-9871-1-03-1697184904.zip`
  - Mod packs: folders where zip files are in the pack root (example: `2.31FemaleCreatorRomanceEnhance/*.zip`)
- Tracks installed files in `mods.json` at your game root.
- Supports uninstall by tracked item and full wipe/reset.

## Requirements

1. Python 3.8+
2. Optional: 7-Zip at `C:\Program Files\7-Zip\7z.exe` (falls back to Python zip extraction)
3. Optional GUI dependency:

```bash
pip install PySide6
```

For building executables:

```bash
pip install pyinstaller
```

## GUI Usage

Run:

```bash
python main.py ui
```

Main window tab is **Mod Manager**:

1. Set **Game Folder** (Cyberpunk root).
2. Set **Download Folder** (contains `.zip` mods and/or pack folders).
3. Click **Refresh Lists**.
4. Select available item and click **Install Selected**.
   Use **Install Workers** to control parallel zip extraction for large packs.
5. Select installed item and click **Uninstall Selected**.
6. Click **Wipe All Mods** to clear known mod folders and reset `mods.json`.

Legacy tabs are still available:

- **Extract Mods**
- **Uninstall From Template**
- **Wipe (Legacy Clear)**

## CLI Usage

### Launch GUI

```bash
python main.py ui
```

(also supports `python main.py gui`)

### Legacy extractor

```bash
python main.py extract -i "C:\Mods\Downloads" -o "C:\Mods\Extracted" -w 4
```

### Legacy template uninstall

```bash
python main.py uninstall -p "C:\Games\Cyberpunk 2077" -m "C:\Mods\ExtractedPack"
```

### Legacy clear

```bash
python main.py clear -p "C:\Games\Cyberpunk 2077"
```

### Manager commands

List tracked installs and optionally available downloads:

```bash
python main.py manager-list -g "C:\Games\Cyberpunk 2077" -d "C:\Mods\Downloads"
```

Install one mod zip or one pack folder by name:

```bash
python main.py manager-install -g "C:\Games\Cyberpunk 2077" -d "C:\Mods\Downloads" -n "M3 GTR-9871-1-03-1697184904.zip"
python main.py manager-install -g "C:\Games\Cyberpunk 2077" -d "C:\Mods\Downloads" -n "2.31FemaleCreatorRomanceEnhance"
python main.py manager-install -g "C:\Games\Cyberpunk 2077" -d "C:\Mods\Downloads" -n "2.31FemaleCreatorRomanceEnhance" -w 16
```

Uninstall one tracked install by id:

```bash
python main.py manager-uninstall -g "C:\Games\Cyberpunk 2077" -i "mod:M3 GTR-9871-1-03-1697184904.zip"
python main.py manager-uninstall -g "C:\Games\Cyberpunk 2077" -i "pack:2.31FemaleCreatorRomanceEnhance"
```

Wipe and reset state:

```bash
python main.py manager-wipe -g "C:\Games\Cyberpunk 2077"
```

## State file

The manager writes `mods.json` in the game root with:

- Installed entries (`id`, type, source, archive list, tracked files)
- File ownership map so uninstall can avoid deleting files still owned by another installed item

## Build two EXEs

### PowerShell script

```powershell
./scripts/build.ps1 -All
```

Options:

- `-Cli`
- `-Gui`
- `-All`

### Makefile

```bash
make build-all
```

Targets:

- `build-cli`
- `build-gui`
- `build-all`
- `clean`

Output binaries are in `dist/`:

- `cp77mod-cli.exe`
- `cp77mod-gui.exe`
