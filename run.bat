@echo off
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM ---- ffprobe check & auto-install via winget ------------------------------
where ffprobe >nul 2>&1
if errorlevel 1 (
    echo ffprobe not found on PATH.
    where winget >nul 2>&1
    if errorlevel 1 (
        echo winget is not available. Please install FFmpeg manually:
        echo   https://www.gyan.dev/ffmpeg/builds/
        pause
        exit /b 1
    )
    echo Installing FFmpeg via winget...
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo FFmpeg install failed.
        pause
        exit /b 1
    )
    REM Look for ffprobe.exe in the winget install location and prepend to PATH
    REM so this shell session can find it without needing a restart.
    for /f "delims=" %%P in ('dir /b /s /a:-d "%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_*\ffprobe.exe" 2^>nul') do (
        for %%D in ("%%~dpP.") do set "FFPROBE_DIR=%%~fD"
        goto :ffprobe_found
    )
    echo FFmpeg installed but ffprobe.exe was not located. Please restart this shell.
    pause
    exit /b 1
    :ffprobe_found
    set "PATH=!FFPROBE_DIR!;%PATH%"
    echo FFmpeg installed: !FFPROBE_DIR!
)

REM ---- venv setup -----------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create venv. Make sure Python 3.10+ is installed.
        pause
        exit /b 1
    )
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

set PYTHONPATH=%SCRIPT_DIR%src
python -m kaburi_kenchi
endlocal
