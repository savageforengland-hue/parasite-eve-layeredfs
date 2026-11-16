@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
echo Scanning mods\layeredfs\romfs\ and rebuilding v0.12-alpha LayeredFS overrides...
python "tools\pe_layeredfs_tool.py" sync --root "." --disc 1 --virtual-disc
echo.
echo Done! override_cache.bin, 0.12 asset packs, and Parasite_Eve_LayeredFS_Disc1.cue are updated.
pause
