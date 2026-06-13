param(
    [string]$Flutter = "C:\flutter\flutter\bin\flutter.bat"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$app = Join-Path $root "gumusvet_admin"
$release = Join-Path $app "build\windows\x64\runner\Release"
$dist = Join-Path $root "dist"
$stage = Join-Path $dist "GumusVetAdmin-Windows"
$zip = Join-Path $dist "GumusVetAdmin-Windows.zip"

if (-not (Test-Path -LiteralPath $Flutter)) {
    throw "Flutter bulunamadı: $Flutter"
}

Push-Location $app
try {
    & $Flutter pub get
    & $Flutter build windows --release
    if ($LASTEXITCODE -ne 0) {
        throw "Flutter Windows build başarısız oldu."
    }
}
finally {
    Pop-Location
}

New-Item -ItemType Directory -Path $dist -Force | Out-Null
if (Test-Path -LiteralPath $stage) {
    Remove-Item -LiteralPath $stage -Recurse -Force
}
Copy-Item -LiteralPath $release -Destination $stage -Recurse
Copy-Item -LiteralPath (Join-Path $root "docs\KULLANIM_KILAVUZU.md") -Destination $stage

if (Test-Path -LiteralPath $zip) {
    Remove-Item -LiteralPath $zip -Force
}
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip
Write-Host "Paket hazır: $zip"

