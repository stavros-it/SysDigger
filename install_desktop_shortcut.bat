@echo off
REM ============================================================
REM  SysPeek - Desktop Shortcut Installer
REM  Creates a "SysPeek" shortcut on the current user's
REM  Desktop pointing to syspeek.pyw with the custom app.ico.
REM ============================================================

echo.
echo  SysPeek - Desktop Shortcut Installer
echo  ====================================
echo.

REM  %~dp0 = directory of this .bat, with trailing backslash.
REM  We pass it to PowerShell, which handles the trailing slash fine.
set "APP_DIR=%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$appDir = $env:APP_DIR;" ^
  "if (-not $appDir) { Write-Host '  [ERROR] Could not resolve app folder.'; exit 1 };" ^
  "$launcher = Join-Path $appDir 'syspeek.pyw';" ^
  "$icon    = Join-Path $appDir 'app.ico';" ^
  "if (-not (Test-Path $launcher)) { Write-Host '  [ERROR] syspeek.pyw not found in:'; Write-Host ('          ' + $appDir); exit 1 };" ^
  "if (-not (Test-Path $icon))    { Write-Host '  [ERROR] app.ico not found in:';    Write-Host ('          ' + $appDir); exit 1 };" ^
  "$desktop = [Environment]::GetFolderPath('Desktop');" ^
  "if (-not $desktop) { $desktop = Join-Path $env:USERPROFILE 'Desktop' };" ^
  "$shortcut = Join-Path $desktop 'SysPeek.lnk';" ^
  "Write-Host ('  App folder : ' + $appDir);" ^
  "Write-Host ('  Target     : ' + $launcher);" ^
  "Write-Host ('  Icon       : ' + $icon);" ^
  "Write-Host ('  Shortcut   : ' + $shortcut);" ^
  "Write-Host '';" ^
  "$ws  = New-Object -ComObject WScript.Shell;" ^
  "$lnk = $ws.CreateShortcut($shortcut);" ^
  "$lnk.TargetPath       = $launcher;" ^
  "$lnk.IconLocation     = $icon + ',0';" ^
  "$lnk.WorkingDirectory = $appDir;" ^
  "$lnk.Description      = 'SysPeek - System Information Viewer';" ^
  "$lnk.WindowStyle       = 7;" ^
  "$lnk.Save();" ^
  "Write-Host '';" ^
  "Write-Host '  [OK] Shortcut created.'"

set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo  [ERROR] Failed to create the shortcut ^(exit %RC%^).
    echo.
    pause
    exit /b %RC%
)

echo.
echo  Done! A "SysPeek" shortcut is now on your Desktop.
echo  Double-click it to launch the app with the custom icon.
echo.
pause
