# Cyberpunk 2077 Mod Manager

A lightweight, concurrent Python utility designed to extract, organize, install, and cleanly remove Cyberpunk 2077 mods. It handles poorly packaged mods by strictly enforcing the official game folder structure and provides both a Command Line Interface (CLI) and a Graphical User Interface (GUI).

## Features

- **Smart Extraction:** Automatically routes `.archive`, `.xl`, and core mod folders (`bin`, `r6`, `red4ext`, etc.) to their proper subdirectories, keeping your staging area clean.
- **Concurrent Processing:** Uses multi-threading to extract multiple heavy mod archives simultaneously.
- **Targeted Uninstaller:** Removes specific mod files from your game directory based on an extracted mod pack template without touching vanilla files.
- **Nuclear Clear:** Safely wipes all known mod framework folders and files from your game directory to restore a vanilla state.
- **GUI Mode:** Includes a PySide6-powered graphical interface for ease of use.

## Prerequisites

1. **Python 3.7+**
2. **7-Zip:** Must be installed at the default Windows directory: `C:\Program Files\7-Zip\7z.exe`
3. **PySide6 (Optional):** Only required if you want to use the GUI.

```bash
pip install PySide6

```

## CLI Usage

Run the script from your terminal or command prompt. The tool is split into four main commands: `extract`, `uninstall`, `clear`, and `ui`.

### 1. Extract and Organize Mods

Takes a folder full of downloaded mod files (zips, rars, 7z) and extracts them into a perfectly structured copy-paste ready folder.

```bash
python script.py extract -i "C:\Path\To\Downloads" -o "C:\Path\To\ExtractedMods" -w 4

```

- `-i` or `--input`: The folder containing your downloaded mod archives.
- `-o` or `--output`: The destination folder where the structured files will be dumped.
- `-w` or `--workers`: (Optional) The number of concurrent extractions to run. Default is 3.

### 2. Uninstall Specific Mods

Safely removes a specific mod pack from your game directory. It compares the files inside your extracted mod folder and deletes the exact matches from the game folder.

```bash
python script.py uninstall -p "C:\Path\To\Cyberpunk 2077" -m "C:\Path\To\ExtractedMods"

```

- `-p` or `--path`: Your main Cyberpunk 2077 game directory.
- `-m` or `--modpack`: The folder containing the extracted, correctly structured mod files you want to remove.

### 3. Clear All Mods (Wipe)

Wipes all known mod folders (`red4ext`, `mods`, custom `archive/pc/mod` files, `r6/scripts`, CET plugins, etc.) to reset the game to a near-vanilla state.

```bash
python script.py clear -p "C:\Path\To\Cyberpunk 2077"

```

- `-p` or `--path`: Your main Cyberpunk 2077 game directory.
- _Note: It will prompt you for a `y/n` confirmation before deleting._

## GUI Usage

If you prefer not to use the command line, you can launch the graphical interface.

```bash
python script.py ui

```

This opens a window with three tabs:

1. **Extract Mods:** Select your input/output folders and worker count.
2. **Uninstall Mod Pack:** Select your game folder and the extracted mod folder to perform a targeted cleanup.
3. **Wipe All Mods:** Select your game folder to nuke all mod files.

All console output and progress will be displayed safely in the built-in log window.

## Troubleshooting

- **Extraction fails constantly:** Ensure 7-Zip is installed exactly at `C:\Program Files\7-Zip\7z.exe`. If it is installed elsewhere, open `script.py` in a text editor and change the `SEVEN_ZIP_EXE` variable at the top of the file to match your path.
- **GUI won't launch:** Ensure you have installed the UI framework by running `pip install PySide6`.
