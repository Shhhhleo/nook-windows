@echo off
cd /d "%~dp0"
if exist "dist\Notch\Nook\Nook.exe" (
 start "" "dist\Notch\Nook\Nook.exe"
) else (
 start "" ".venv\Scripts\pythonw.exe" "main.py"
)
