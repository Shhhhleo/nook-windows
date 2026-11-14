$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force vendor | Out-Null
$archive = Join-Path $PSScriptRoot 'vendor/ollama.zip'
$expected = '50fcf5ad54277f2fa5d173ebfc93bcb017adbc0c9ef2314daabc96ca9e6aa64e'
if (!(Test-Path -LiteralPath $archive)) {
    curl.exe -L --fail --retry 2 -o $archive 'https://github.com/ollama/ollama/releases/download/v0.40.16/ollama-windows-amd64.zip'
    if ($LASTEXITCODE -ne 0) { throw 'Ollama download failed' }
}
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expected) {
    throw 'Ollama checksum mismatch'
}
Expand-Archive -LiteralPath $archive -DestinationPath vendor/ollama -Force
curl.exe -L --fail -o vendor/ollama/LICENSE 'https://raw.githubusercontent.com/ollama/ollama/v0.40.16/LICENSE'
if ($LASTEXITCODE -ne 0) { throw 'License download failed' }
.venv/Scripts/python.exe -c "from nook import assistant,local_ai; print(assistant.ollama_request('/api/pull', {'model':local_ai.MODEL,'stream':False},timeout=1800)); local_ai.stop()"
if ($LASTEXITCODE -ne 0) { throw 'Starter model preparation failed' }
