# Cyberpunk2077-ModManager

Short name: `cp77mm`.

A Windows-first Cyberpunk 2077 mod utility with both a command-line interface and a desktop GUI.

This project helps you:

- Install single mod archives (`.zip`) directly into the game folder
- Install large mod packs (folder containing many root-level `.zip` files)
- Track exactly what was installed in `mods.json`
- Uninstall individual installed entries safely
- Wipe all tracked mod files reliably
- Keep a legacy extractor workflow for staging/organizing loose downloads

The core design goal is safe, repeatable mod management with traceable installs.

## Why this project exists

Cyberpunk mods are often packaged inconsistently. Some archives include game-root folders (`archive`, `r6`, `bin`, etc.), others contain loose files.

This tool normalizes installation behavior and records installed file ownership in `mods.json`, so removal and repair are deterministic instead of manual guesswork.

## Key Features

- Mod Manager (primary workflow):
  - Install from a download directory
  - Single-click install/uninstall/wipe
  - Reinstall/repair installed entries
  - Parallel install workers for large packs
- Safe tracking:
  - Writes `mods.json` in game root
  - Tracks installed entries and per-file ownership
- Legacy tools (kept intentionally):
  - `extract`: archive-to-structured-output workflow
  - `uninstall`: template-based removal from extracted folders
  - `clear`: folder-based legacy wipe
- GUI + CLI parity for manager operations

## Supported Input Layout

### Single mod archive

Example file in your downloads folder:

`M3 GTR-9871-1-03-1697184904.zip`

### Mod pack directory

Example folder in downloads:

`2.31FemaleCreatorRomanceEnhance/`

Inside that folder, zip files are expected at the folder root:

- `.../2.31FemaleCreatorRomanceEnhance/modA.zip`
- `.../2.31FemaleCreatorRomanceEnhance/modB.zip`
- etc.

## Requirements

- Python 3.8+
- Windows (primary target)
- Optional, recommended: 7-Zip installed at:
  - `C:\Program Files\7-Zip\7z.exe`
- GUI dependency:
  - `PySide6`
- Build dependency:
  - `pyinstaller`

Install dependencies:

```bash
pip install -r requirements.txt
```

## Quick Start (GUI)

Run:

```bash
python main.py ui
```

In **Mod Manager** tab:

1. Set **Game Folder** (Cyberpunk 2077 root)
2. Set **Download Folder** (mods + packs location)
3. Click **Refresh Lists**
4. Select an item and click **Install Selected**
5. To repair/reinstall, select from **Installed** and click **Install Selected**
6. Use **Uninstall Selected** for one installed entry
7. Use **Wipe All Mods** to delete tracked files from `mods.json`

### GUI note

`Install Selected` has two behaviors:

- If **Available** selection exists: performs install
- Else if **Installed** selection exists: performs reinstall/repair

## CLI Usage

### Show help

```bash
python main.py -h
```

### Launch GUI

```bash
python main.py ui
```

(also `python main.py gui`)

### Manager: list

```bash
python main.py manager-list -g "C:\Games\Cyberpunk 2077" -d "C:\Mods\Downloads"
```

### Manager: install

Install a single archive:

```bash
python main.py manager-install -g "C:\Games\Cyberpunk 2077" -d "C:\Mods\Downloads" -n "M3 GTR-9871-1-03-1697184904.zip"
```

Install a pack folder:

```bash
python main.py manager-install -g "C:\Games\Cyberpunk 2077" -d "C:\Mods\Downloads" -n "2.31FemaleCreatorRomanceEnhance"
```

Install with parallel workers for large packs:

```bash
python main.py manager-install -g "C:\Games\Cyberpunk 2077" -d "C:\Mods\Downloads" -n "2.31FemaleCreatorRomanceEnhance" -w 16
```

### Manager: uninstall one tracked entry

```bash
python main.py manager-uninstall -g "C:\Games\Cyberpunk 2077" -i "pack:2.31FemaleCreatorRomanceEnhance"
```

Example single-mod id:

`mod:M3 GTR-9871-1-03-1697184904.zip`

### Manager: wipe tracked installs

```bash
python main.py manager-wipe -g "C:\Games\Cyberpunk 2077"
```

This deletes files tracked in `mods.json` and resets state.

## Legacy Commands (still available)

These are preserved for users who rely on old workflows.

### Extract and normalize downloads

```bash
python main.py extract -i "C:\Mods\Downloads" -o "C:\Mods\Extracted" -w 4
```

### Template-based uninstall

```bash
python main.py uninstall -p "C:\Games\Cyberpunk 2077" -m "C:\Mods\ExtractedPack"
```

### Folder-based legacy clear

```bash
python main.py clear -p "C:\Games\Cyberpunk 2077"
```

## `mods.json` state model

`mods.json` is stored at the game root and contains:

- `installed`: list of installed entries
  - id (`mod:...` or `pack:...`)
  - source path
  - archive names
  - tracked file list
- `file_owners`: map of relative game paths -> owning install ids

This ownership map is used to avoid deleting files still used by another installed entry.

## Build EXE files

Two standalone executables are supported:

- `cp77mm-cli.exe`
- `cp77mm-gui.exe`

### PowerShell

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

Build outputs are in `dist/`.

### Raw Python release zip

Release automation also creates a portable raw Python package zip:

- `cp77mm-python-<version>.zip`

Contents include:

- core Python scripts (`main.py`, `cli_entry.py`, `gui_entry.py`)
- `README.md`, `LICENSE`, `VERSION`, `requirements.txt`
- Windows launchers: `run-cli.bat`, `run-gui.bat`

## Release automation

- Project version is defined in `VERSION` (example: `1.0.0`)
- GitHub workflow on push:
  - reads `VERSION`
  - checks if tag already exists
  - if tag exists: does nothing
  - if tag does not exist: builds both EXEs and creates release

Workflow file:

`.github/workflows/release.yml`

## Troubleshooting

- GUI does not launch:
  - install `PySide6` via `pip install -r requirements.txt`
- Slow pack install:
  - increase `-w` in CLI or **Install Workers** in GUI
- Missing source path during reinstall:
  - reinstall from downloads manually so source can be tracked again
- 7-Zip not found:
  - Python zip fallback is used; install 7-Zip for best compatibility/performance

## License

This project is licensed under the MIT License. See `LICENSE` for details.
