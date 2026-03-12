<#
.SYNOPSIS
    Build Toty Desktop Pet into a Windows installer.

.DESCRIPTION
    Step 1: PyInstaller → dist/Toty/  (portable exe + deps)
    Step 2: Inno Setup  → dist/TotySetup-v15.0.0.exe (installer)

.EXAMPLE
    .\build.ps1            # full build (exe + installer)
    .\build.ps1 -ExeOnly   # only PyInstaller step
#>
param(
    [switch]$ExeOnly
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host "`n=== Toty Build Script ===" -ForegroundColor Cyan
Write-Host "Working dir: $root`n"

# ── Step 0: Check tools ──────────────────────────────────────────
Write-Host "[0/3] Checking tools..." -ForegroundColor Yellow

$pyinstaller = Get-Command pyinstaller -ErrorAction SilentlyContinue
if (-not $pyinstaller) {
    Write-Host "  PyInstaller not found. Installing..." -ForegroundColor Yellow
    pip install pyinstaller
}

# ── Step 1: Clean previous build ─────────────────────────────────
Write-Host "[1/3] Cleaning previous build..." -ForegroundColor Yellow
if (Test-Path "$root\build") { Remove-Item "$root\build" -Recurse -Force }
if (Test-Path "$root\dist")  { Remove-Item "$root\dist"  -Recurse -Force }

# ── Step 2: PyInstaller ──────────────────────────────────────────
Write-Host "[2/3] Building with PyInstaller..." -ForegroundColor Yellow
Push-Location $root
try {
    pyinstaller toty.spec --noconfirm 2>&1 | ForEach-Object { Write-Host "  $_" }
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

# Verify output
$exePath = Join-Path $root "dist\Toty\Toty.exe"
if (-not (Test-Path $exePath)) {
    throw "Build failed — $exePath not found"
}
$size = (Get-Item $exePath).Length / 1MB
Write-Host "  OK: Toty.exe ($([math]::Round($size, 1)) MB)" -ForegroundColor Green

if ($ExeOnly) {
    Write-Host "`nDone (exe only). Output: dist\Toty\" -ForegroundColor Green
    exit 0
}

# ── Step 3: Inno Setup ───────────────────────────────────────────
Write-Host "[3/3] Building installer with Inno Setup..." -ForegroundColor Yellow

$iscc = $null
$isccPaths = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    (Get-Command ISCC -ErrorAction SilentlyContinue).Source
)
foreach ($p in $isccPaths) {
    if ($p -and (Test-Path $p)) { $iscc = $p; break }
}

if (-not $iscc) {
    Write-Host "  Inno Setup not found. Skipping installer creation." -ForegroundColor Yellow
    Write-Host "  Download from: https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
    Write-Host "`nPortable build ready: dist\Toty\Toty.exe" -ForegroundColor Green
    exit 0
}

& $iscc "$root\installer.iss" 2>&1 | ForEach-Object { Write-Host "  $_" }
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE"
}

$installer = Get-ChildItem "$root\dist\TotySetup-*.exe" | Select-Object -First 1
if ($installer) {
    $isize = $installer.Length / 1MB
    Write-Host "`nBuild complete!" -ForegroundColor Green
    Write-Host "  Portable: dist\Toty\Toty.exe" -ForegroundColor Green
    Write-Host "  Installer: $($installer.Name) ($([math]::Round($isize, 1)) MB)" -ForegroundColor Green
} else {
    Write-Host "`nPortable build ready: dist\Toty\Toty.exe" -ForegroundColor Green
}
