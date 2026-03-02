param(
    [switch]$Cli,
    [switch]$Gui,
    [switch]$All
)

if (-not $Cli -and -not $Gui -and -not $All) {
    $All = $true
}

$ErrorActionPreference = "Stop"

function Build-Cli {
    python -m PyInstaller --noconfirm --clean --onefile --name cp77mm-cli cli_entry.py
}

function Build-Gui {
    python -m PyInstaller --noconfirm --clean --windowed --onefile --name cp77mm-gui gui_entry.py
}

if ($All -or $Cli) { Build-Cli }
if ($All -or $Gui) { Build-Gui }
