@echo off
setlocal DisableDelayedExpansion

:: 1. Έλεγχος και Αυτόματη Λήψη Δικαιωμάτων Administrator
openfiles >nul 2>&1
if %errorlevel% NEQ 0 (
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /B
)

:: 2. Ορισμός της διαδρομής του PS1 αρχείου (πρέπει να είναι στον ίδιο φάκελο)
set "PS_FILE=%~dp0SA_WinTools.ps1"

:: 3. Εκτέλεση με Bypass του Execution Policy και Hidden Console για το υπόβαθρο
if exist "%PS_FILE%" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_FILE%"
) else (
    echo [ERROR] To αρχειο %PS_FILE% δεν βρεθηκε!
    pause
)

exit /B