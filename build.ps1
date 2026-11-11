$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$originalPath = $env:PATH
try {
    # Prevent unrelated tools on PATH from supplying incompatible ICU DLLs.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$PSScriptRoot\.venv\Scripts"
    & .venv/Scripts/python.exe -m PyInstaller --clean --noconfirm --windowed --onedir --name Nook --collect-all winrt main.py
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
} finally {
    $env:PATH = $originalPath
}
