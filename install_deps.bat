@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title SysDigger - Dependency Installer

echo ============================================================
echo   SysDigger - Dependency Installer
echo ============================================================
echo.

REM ---- locate python ----
set "PY="
where pythonw >nul 2>&1 && set "PY=pythonw"
where python  >nul 2>&1 && set "PY=python"
if not defined PY (
    echo [ERROR] Python was not found on PATH.
    echo         Please install Python 3.10+ from https://www.python.org/downloads/
    echo         and tick "Add python.exe to PATH" during setup.
    echo.
    pause
    exit /b 1
)
echo Found Python:
%PY% --version
echo.

REM ---- upgrade pip quietly ----
echo Upgrading pip...
%PY% -m pip install --upgrade pip >nul 2>&1
echo.

REM ---- install dependencies ----
set "PACKAGES=psutil requests wmi pywin32 pythonnet PySide6"
echo Installing: %PACKAGES%
echo ------------------------------------------------------------
%PY% -m pip install %PACKAGES%
if errorlevel 1 (
    echo.
    echo [ERROR] One or more packages failed to install.
    pause
    exit /b 1
)
echo ------------------------------------------------------------

REM ---- post-install: pywin32 DLLs ----
echo.
echo Configuring pywin32 DLLs...
%PY% -m pywin32_postinstall -install >nul 2>&1
if errorlevel 1 (
    echo [warning] pywin32 post-install step reported an issue ^(may be harmless^).
) else (
    echo Done.
)

REM ---- verify imports ----
echo.
echo Verifying imports...
%PY% -c "import psutil, requests, wmi, win32api; print('Core packages OK.')"
if errorlevel 1 (
    echo [ERROR] Core verification failed.
    pause
    exit /b 1
)
%PY% -c "import clr; print('pythonnet OK.')"
if errorlevel 1 (
    echo [ERROR] pythonnet verification failed.
    pause
    exit /b 1
)
%PY% -c "from PySide6.QtWidgets import QApplication; print('PySide6 OK.')"
if errorlevel 1 (
    echo [ERROR] PySide6 verification failed.
    pause
    exit /b 1
)

REM ---- check LibreHardwareMonitorLib DLLs ----
echo.
echo Checking LibreHardwareMonitorLib DLLs...
if exist "%~dp0lib\LibreHardwareMonitorLib.dll" (
    if exist "%~dp0lib\HidSharp.dll" (
        echo LibreHardwareMonitorLib DLLs found in lib\ folder.
    ) else (
        echo [WARNING] HidSharp.dll missing in lib\ folder. Sensor data may not work.
    )
) else (
    echo [WARNING] LibreHardwareMonitorLib.dll missing in lib\ folder.
    echo          Sensor data (temperatures/fans) will not be available.
    echo          Download from https://www.nuget.org/packages/LibreHardwareMonitorLib/
)

echo.
echo ============================================================
echo   All dependencies installed successfully!
echo   Launch the app by double-clicking:  sysdigger.pyw
echo ============================================================
echo.
pause
endlocal
