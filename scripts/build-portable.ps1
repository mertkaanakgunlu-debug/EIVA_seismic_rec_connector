$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$desktop = Join-Path $root "desktop"
$packaging = Join-Path $root "packaging"
$engineOut = Join-Path $packaging "out"
$release = Join-Path $root "release"
$builderOut = Join-Path $env:TEMP "ShotLogFixer-release-builder"

Remove-Item -LiteralPath $engineOut, $builderOut, $release -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $engineOut, $release | Out-Null

Push-Location $root
try {
  py -m pytest
  py -m PyInstaller --noconfirm --clean --onedir --console --name shotlogfixer-engine --distpath $engineOut --workpath (Join-Path $packaging "build") --specpath $packaging --version-file (Join-Path $packaging "version_info.txt") (Join-Path $packaging "engine_entry.py")
  Push-Location $desktop
  try {
    npm run build
    npm exec electron-builder -- --win portable --x64 --publish never --config.directories.output=$builderOut
  } finally { Pop-Location }
  $artifact = Join-Path $builderOut "ShotLogFixer-Portable.exe"
  if (-not (Test-Path -LiteralPath $artifact)) { throw "Portable artifact not found: $artifact" }
  Copy-Item -LiteralPath $artifact -Destination (Join-Path $release "ShotLogFixer-Portable.exe")
  $final = Get-Item -LiteralPath (Join-Path $release "ShotLogFixer-Portable.exe")
  $sha256 = [System.Security.Cryptography.SHA256]::Create()
  try { $hash = -join ($sha256.ComputeHash([System.IO.File]::ReadAllBytes($final.FullName)) | ForEach-Object { $_.ToString("x2") }) } finally { $sha256.Dispose() }
  Write-Host ("Artifact: {0}`nSizeBytes: {1}`nSizeMB: {2:N2}`nSHA256: {3}" -f $final.FullName, $final.Length, ($final.Length / 1MB), $hash)
} finally { Pop-Location }
