param([string]$OutputDirectory = 'dist/Snippy', [switch]$Clean, [switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$originalPath = $env:PATH
try {
    # Prevent unrelated tools on PATH from supplying incompatible ICU DLLs.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$PSScriptRoot\.venv\Scripts"
    # Build into staging, then update the same installed folder. Do not create version-named copies.
    $cleanArguments = @()
    if ($Clean) { $cleanArguments = @('--clean') }
    if (!$SkipBuild) {
        & .venv/Scripts/python.exe -m PyInstaller @cleanArguments --noconfirm --windowed --onedir --name Nook --distpath build/package --collect-all winrt --collect-all tzdata --collect-all vosk --collect-all _sounddevice_data --collect-data mcp --copy-metadata mcp --collect-data jsonschema_specifications --hidden-import anyio._backends._asyncio main.py
        if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    }
    if (!(Test-Path 'build/package/Nook/Nook.exe')) { throw 'No staged executable. Run the build first.' }
    if (!(Test-Path 'vendor/ollama/ollama.exe') -or !(Test-Path 'vendor/models/manifests')) {
        throw 'Bundled Ollama runtime and starter model must be prepared in vendor before distribution.'
    }
    if (!(Test-Path 'vendor/speech/vosk-model-small-en-us-0.15/am/final.mdl') -or !(Test-Path 'vendor/speech/vosk-model-small-en-in-0.4/am/final.mdl')) {
        throw 'Run prepare-speech.py before packaging offline dictation.'
    }
    # Refuse known locked destinations before replacing any application file.
    $stagedRoot = (Resolve-Path -LiteralPath 'build/package/Nook').Path
    foreach ($stagedFile in Get-ChildItem -LiteralPath $stagedRoot -Recurse -File) {
        $relativeFile = $stagedFile.FullName.Substring($stagedRoot.Length + 1)
        $destinationFile = Join-Path "$OutputDirectory/Nook" $relativeFile
        if (Test-Path -LiteralPath $destinationFile) {
            try {
                $fileProbe = [IO.File]::Open($destinationFile, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
                $fileProbe.Dispose()
            } catch { throw "Quit Notch from its tray menu before updating. Locked file: $destinationFile" }
        }
    }
    New-Item -ItemType Directory -Path "$OutputDirectory/Nook" -Force | Out-Null
    Copy-Item -Path 'build/package/Nook/*' -Destination "$OutputDirectory/Nook" -Recurse -Force
    New-Item -ItemType Directory -Path "$OutputDirectory/Nook/ollama" -Force | Out-Null
    & robocopy.exe vendor/ollama "$OutputDirectory/Nook/ollama" /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw 'AI runtime copy failed' }
    & .venv/Scripts/python.exe packaging/copy_model.py "$OutputDirectory/Nook/models"
    if ($LASTEXITCODE -ne 0) { throw 'Model packaging failed' }
    & robocopy.exe vendor/speech "$OutputDirectory/Nook/speech" /E /XF *.zip /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw 'Speech model copy failed' }
    Copy-Item -LiteralPath 'packaging/AppxManifest.xml','packaging/Register-Nook.ps1','packaging/Notification-setup.md' -Destination "$OutputDirectory/Nook" -Force
    New-Item -ItemType Directory -Path "$OutputDirectory/Nook/Assets" -Force | Out-Null
    Copy-Item -Path 'packaging/Assets/*' -Destination "$OutputDirectory/Nook/Assets" -Recurse -Force
} finally {
    $env:PATH = $originalPath
}
