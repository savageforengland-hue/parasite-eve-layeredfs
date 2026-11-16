@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set "TARGET_IMG=%~1"
if not defined TARGET_IMG (
    for %%F in (*.chd *.bin *.iso) do (
        echo %%~nxF | findstr /i /c:"LayeredFS" >nul
        if errorlevel 1 if not defined TARGET_IMG set "TARGET_IMG=%%~fF"
    )
)
if not defined TARGET_IMG (
    echo Usage: extract_disc_structure.bat "Path\To\Parasite Eve (Disc 1).chd/.bin" [--extract-all]
    pause
    exit /b 1
)
python "tools\pe_layeredfs_tool.py" init-tree --bin "%TARGET_IMG%" --root "." --disc 1 %2
pause
