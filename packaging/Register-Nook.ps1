# Optional development registration for Windows notification-listener capability.
# Run from the complete built Nook folder. This never changes Developer Mode.
$ErrorActionPreference = 'Stop'
$manifestPath = Join-Path $PSScriptRoot 'AppxManifest.xml'
if (!(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'Nook.exe'))) {
    throw 'Run this script from the built Nook folder, alongside Nook.exe.'
}
$developerMode = Get-ItemPropertyValue -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock' -Name AllowDevelopmentWithoutDevLicense -ErrorAction SilentlyContinue
if ($developerMode -ne 1) {
    throw 'This unsigned development build requires Windows Developer Mode for app registration. Enable it in Windows Settings > For developers, or use the portable app without notification access.'
}
Add-AppxPackage -Register $manifestPath
Write-Host 'Nook is registered. Quit any running portable copy, open Nook from Start, then choose Settings > Assistant > Connect notifications.'
