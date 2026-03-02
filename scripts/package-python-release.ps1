param(
    [Parameter(Mandatory = $true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$distDir = Join-Path $repoRoot "dist"
$stagingRoot = Join-Path $distDir "python-package"
$packageDir = Join-Path $stagingRoot "cp77mod-python-$Version"
$zipPath = Join-Path $distDir "cp77mod-python-$Version.zip"

if (Test-Path $stagingRoot) {
    Remove-Item -Recurse -Force $stagingRoot
}

New-Item -ItemType Directory -Force -Path $packageDir | Out-Null
New-Item -ItemType Directory -Force -Path $distDir | Out-Null

$filesToCopy = @(
    "main.py",
    "cli_entry.py",
    "gui_entry.py",
    "requirements.txt",
    "README.md",
    "LICENSE",
    "VERSION",
    "run-cli.bat",
    "run-gui.bat"
)

foreach ($relPath in $filesToCopy) {
    $source = Join-Path $repoRoot $relPath
    if (-not (Test-Path $source)) {
        throw "Required file missing: $relPath"
    }
    Copy-Item -Path $source -Destination (Join-Path $packageDir $relPath) -Force
}

if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}

Compress-Archive -Path (Join-Path $packageDir "*") -DestinationPath $zipPath -Force
Write-Host "Created: $zipPath"
