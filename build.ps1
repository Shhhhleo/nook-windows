param([string]$OutputDirectory = 'dist')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$originalPath = $env:PATH
try {
    # Prevent unrelated tools on PATH from supplying incompatible ICU DLLs.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$PSScriptRoot\.venv\Scripts"
    & .venv/Scripts/python.exe -m PyInstaller --clean --noconfirm --windowed --onedir --name Nook --distpath $OutputDirectory --collect-all winrt --collect-all tzdata main.py
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    if (!(Test-Path 'vendor/ollama/ollama.exe') -or !(Test-Path 'vendor/models/manifests')) {
        throw 'Bundled Ollama runtime and starter model must be prepared in vendor before distribution.'
    }
    Copy-Item -LiteralPath 'vendor/ollama' -Destination "$OutputDirectory/Nook/ollama" -Recurse -Force
    Copy-Item -LiteralPath 'vendor/models' -Destination "$OutputDirectory/Nook/models" -Recurse -Force
} finally {
    $env:PATH = $originalPath
}
