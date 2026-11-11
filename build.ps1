$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& .venv/Scripts/python.exe -m PyInstaller --noconfirm --windowed --onedir --name Nook --collect-all winrt main.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
