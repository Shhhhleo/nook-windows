param([string]$OutputDirectory = 'dist/Notch', [switch]$Clean, [switch]$SkipBuild)
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
        & .venv/Scripts/python.exe -m PyInstaller @cleanArguments --noconfirm --windowed --onedir --name Nook --distpath build/package --collect-all winrt --collect-all tzdata main.py
        if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    }
    if (!(Test-Path 'build/package/Nook/Nook.exe')) { throw 'No staged executable. Run the build first.' }
    # Refuse known locked destinations before replacing any application file.
    $stagedRoot = (Resolve-Path -LiteralPath 'build/package/Nook').Path
    foreach ($stagedFile in Get-ChildItem -LiteralPath $stagedRoot -Recurse -File) {
        $relativeFile = $stagedFile.FullName.Substring($stagedRoot.Length + 1)
        $destinationFile = Join-Path "$OutputDirectory/Nook" $relativeFile
        if (Test-Path -LiteralPath $destinationFile) {
            try {
                # Probe exclusivity with read access; normal portable install files may be read-only to standard users.
                $fileProbe = [IO.File]::Open($destinationFile, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
                $fileProbe.Dispose()
            } catch { throw "Quit Notch from its tray menu before updating. Locked file: $destinationFile" }
        }
    }
    New-Item -ItemType Directory -Path "$OutputDirectory/Nook" -Force | Out-Null
    Copy-Item -Path 'build/package/Nook/*' -Destination "$OutputDirectory/Nook" -Recurse -Force
    Copy-Item -LiteralPath 'packaging/AppxManifest.xml' -Destination "$OutputDirectory/Nook" -Force
    New-Item -ItemType Directory -Path "$OutputDirectory/Nook/Assets" -Force | Out-Null
    Copy-Item -Path 'packaging/Assets/*' -Destination "$OutputDirectory/Nook/Assets" -Recurse -Force
} finally {
    $env:PATH = $originalPath
}
