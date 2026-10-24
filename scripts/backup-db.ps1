# Dumps the Docker Compose PostgreSQL database to backups\recruitmentdesk-<timestamp>.dump (custom format, compressed).
# Works in Windows PowerShell 5.1 and PowerShell 7 (the dump is written inside the container and copied out, avoiding text-encoding pipes).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Force backups | Out-Null
$name = "recruitmentdesk-$(Get-Date -Format 'yyyyMMdd-HHmmss').dump"
docker compose exec -T db pg_dump -U recruitment -d recruitmentdesk -Fc -f "/tmp/$name"
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed" }
docker compose cp "db:/tmp/$name" "backups\$name"
if ($LASTEXITCODE -ne 0) { throw "could not copy the dump out of the container" }
docker compose exec -T db rm -f "/tmp/$name" | Out-Null
$size = [math]::Round((Get-Item "backups\$name").Length / 1KB)
Write-Host "Backup written to backups\$name ($size KB)."
Write-Host "Also back up your ENCRYPTION_KEY (without it stored Gmail tokens cannot be decrypted) and the 'storage' volume if you need old exports."
