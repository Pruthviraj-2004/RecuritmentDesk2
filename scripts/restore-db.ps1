# Restores a dump produced by backup-db.ps1 into the Docker Compose database. DESTRUCTIVE: existing objects are dropped first.
param([Parameter(Mandatory = $true)][string]$File, [switch]$Force)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not (Test-Path $File)) { throw "File not found: $File" }
if (-not $Force) {
  $answer = Read-Host "This replaces all data in the recruitmentdesk database with '$File'. Type RESTORE to continue"
  if ($answer -ne "RESTORE") { Write-Host "Cancelled."; exit 1 }
}
docker compose stop api worker beat
docker compose cp (Resolve-Path $File).Path "db:/tmp/restore.dump"
docker compose exec -T db pg_restore -U recruitment -d recruitmentdesk --clean --if-exists --no-owner /tmp/restore.dump
docker compose exec -T db rm -f /tmp/restore.dump | Out-Null
docker compose start api worker beat
Write-Host "Restore finished. If the backup came from an older version run: docker compose run --rm migrate"
