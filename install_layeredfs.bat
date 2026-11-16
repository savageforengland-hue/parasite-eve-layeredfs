@echo off
setlocal EnableDelayedExpansion
title Parasite Eve PC (v0.12-alpha+) - LayeredFS Mod System Installer
echo ======================================================================
echo   Parasite Eve PC (v0.11 / v0.12-alpha+) - LayeredFS Override System
echo ======================================================================
echo.
cd /d "%~dp0"

if not exist "mods\layeredfs\romfs" mkdir "mods\layeredfs\romfs"

REM Auto-detect Disc 1 .chd, .bin, or .iso image in the game directory
set "DISC1_IMG="
for %%F in (*.chd *.bin *.iso) do (
    echo %%~nxF | findstr /i /c:"LayeredFS" >nul
    if errorlevel 1 (
        if not defined DISC1_IMG set "DISC1_IMG=%%~fF"
    )
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    set "PY_CMD=python"
) else (
    where py >nul 2>nul
    if !errorlevel! equ 0 (
        set "PY_CMD=py -3"
    ) else (
        echo [WARN] Python 3 not found in PATH. Pre-built v0.12-alpha romfs\ tree is ready:
        echo        %~dp0mods\layeredfs\romfs\
        goto :done
    )
)

if defined DISC1_IMG (
    echo [1/2] Indexing original disc structure from: "!DISC1_IMG!"
    !PY_CMD! "tools\pe_layeredfs_tool.py" init-tree --bin "!DISC1_IMG!" --root "." --disc 1
    echo [2/2] Building initial v0.12-alpha LayeredFS override cache...
    !PY_CMD! "tools\pe_layeredfs_tool.py" sync --root "." --disc 1
) else (
    echo [INFO] No .chd/.bin disc image found in the current folder yet.
    echo        Copy your Parasite Eve Disc 1 .chd or .bin/.cue here and run extract_disc_structure.bat
)

:done
echo.
echo [OK] LayeredFS (v0.12-alpha compatible) is installed!
echo   - Mod folder: %~dp0mods\layeredfs\romfs\
echo   - Supports DISC1/DISC2 PE.IMG packages, SKINS, PACKS, FONTS, CALLS, LANG, and HD_BACKGROUNDS.
echo   - Any asset not in romfs\ is loaded from your original game disc.
echo   - Run sync_layeredfs_mods.bat after adding or removing mod files.
pause
