@echo off
cd /d "%~dp0"
if exist "dist\Snippy\Nook\Nook.exe" (
 start "" "dist\Snippy\Nook\Nook.exe"
) else if exist "dist\Nook\Nook.exe" (
 start "" "dist\Nook\Nook.exe"
) else (
 start "" ".venv\Scripts\pythonw.exe" "main.py"
)
