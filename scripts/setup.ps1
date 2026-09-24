# Windows wrapper: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 [--cpu] [--dev] [--hf-mirror] [--skip-models]
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$py = (Get-Command py -ErrorAction SilentlyContinue)
if ($py) { & py -3 scripts/setup.py @args } else { & python scripts/setup.py @args }
exit $LASTEXITCODE
