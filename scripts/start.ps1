# Windows wrapper: powershell -ExecutionPolicy Bypass -File scripts\start.ps1 [start|stop|status|restart] [--no-browser]
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$cmd = if ($args.Count -gt 0) { $args } else { @("start") }
$py = (Get-Command py -ErrorAction SilentlyContinue)
if ($py) { & py -3 scripts/run.py @cmd } else { & python scripts/run.py @cmd }
exit $LASTEXITCODE
