# build.ps1 — SysDigger build + sign pipeline
# Usage:  .\build.ps1
# Requires: Python 3.12+, pip packages (auto-installed), signtool.exe (optional)
#
# Set $env:SIGN_CERT_THUMBPRINT to your code-signing cert thumbprint to sign
# the output. Without it, the build succeeds but the exe is unsigned.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " SysDigger Build Pipeline" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Install dependencies
Write-Host "`n[1/5] Installing dependencies..." -ForegroundColor Yellow
python -m pip install -r requirements.txt --upgrade

# 2. Compile-check all Python files
Write-Host "`n[2/5] Compile-checking..." -ForegroundColor Yellow
python -m py_compile `
    app.py gui.py collectors.py sysdigger.pyw tools.py `
    sensors.py helpers.py config.py lhm_process.py `
    updater.py app_logger.py paths.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Compile check failed!" -ForegroundColor Red
    exit 1
}
Write-Host "  All files compile OK" -ForegroundColor Green

# 3. Clean previous build
Write-Host "`n[3/5] Cleaning previous build..." -ForegroundColor Yellow
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

# 4. Build with PyInstaller
Write-Host "`n[4/5] Building with PyInstaller..." -ForegroundColor Yellow
pyinstaller sysdigger.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}
Write-Host "  Build output: dist\SysDigger\" -ForegroundColor Green

# 5. Sign (if cert available)
if ($env:SIGN_CERT_THUMBPRINT) {
    Write-Host "`n[5/5] Signing executables and DLLs..." -ForegroundColor Yellow
    $signable = Get-ChildItem -Recurse -Path ".\dist\SysDigger" -Include *.exe, *.dll
    foreach ($f in $signable) {
        Write-Host "  Signing: $($f.Name)"
        & signtool sign /fd sha256 /td sha256 `
            /tr http://timestamp.digicert.com `
            /sha1 $env:SIGN_CERT_THUMBPRINT $f.FullName
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  Failed to sign: $($f.Name)" -ForegroundColor Red
        }
    }
    Write-Host "  Signing complete" -ForegroundColor Green
} else {
    Write-Host "`n[5/5] Skipping code signing (SIGN_CERT_THUMBPRINT not set)" -ForegroundColor DarkGray
}

# Done
$output = ".\dist\SysDigger"
$size = (Get-ChildItem -Recurse $output | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " Build complete!" -ForegroundColor Green
Write-Host " Output: $output" -ForegroundColor Cyan
Write-Host " Size:   $([math]::Round($size, 1)) MB" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
