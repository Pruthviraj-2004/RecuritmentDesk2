<#
  One-time local setup (Windows PowerShell 5.1+). Creates the Python venv, installs backend + frontend dependencies,
  and writes backend\.env and .env with freshly generated keys. Never overwrites an existing .env.
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Checking prerequisites..." -ForegroundColor Cyan
foreach ($tool in "python", "node", "npm") { if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool is not installed or not on PATH" } }

Write-Host "Backend: creating virtual environment and installing packages..." -ForegroundColor Cyan
Set-Location "$root\backend"
if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python -m pip install --quiet -e ".[dev]"

Write-Host "Generating keys..." -ForegroundColor Cyan
$keys = & .\.venv\Scripts\python -m app.cli generate-keys
$secret = ($keys | Where-Object { $_ -like "SECRET_KEY=*" }) -replace "^SECRET_KEY=", ""
$enc = ($keys | Where-Object { $_ -like "ENCRYPTION_KEY=*" }) -replace "^ENCRYPTION_KEY=", ""
$pg = [Convert]::ToBase64String((1..18 | ForEach-Object { Get-Random -Maximum 256 }) -as [byte[]]) -replace "[^A-Za-z0-9]", "x"

function New-EnvFile($path, $extra) {
  if (Test-Path $path) { Write-Host "  $path already exists - left untouched" -ForegroundColor Yellow; return }
  $content = (Get-Content "$root\.env.example" -Raw) `
    -replace "(?m)^SECRET_KEY=.*$", "SECRET_KEY=$secret" `
    -replace "(?m)^ENCRYPTION_KEY=.*$", "ENCRYPTION_KEY=$enc" `
    -replace "(?m)^POSTGRES_PASSWORD=.*$", "POSTGRES_PASSWORD=$pg"
  foreach ($k in $extra.Keys) { $content = $content -replace "(?m)^$k=.*$", "$k=$($extra[$k])" }
  [IO.File]::WriteAllText($path, $content)
  Write-Host "  wrote $path" -ForegroundColor Green
}
# Local development (backend\.env): API on :8000, Vite on :5173, no Redis needed (tasks run inline)
New-EnvFile "$root\backend\.env" @{ REDIS_URL = ""; CELERY_EAGER = "true" }
# Docker Compose (.env at repo root): everything served from http://localhost:8080
New-EnvFile "$root\.env" @{ FRONTEND_URL = "http://localhost:8080"; GOOGLE_REDIRECT_URI = "http://localhost:8080/api/v1/email-accounts/oauth/callback"; DATABASE_SCHEMA = "" }

Write-Host "Frontend: installing packages..." -ForegroundColor Cyan
Set-Location "$root\frontend"
npm install --no-audit --no-fund

Write-Host "`nDone. Next steps:" -ForegroundColor Green
Write-Host "  1. Edit backend\.env (and .env for Docker): add GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET, and AI_* if you want extraction."
Write-Host "  2. Database: start PostgreSQL (docker compose up -d db) or point DATABASE_URL at a managed instance, then run scripts\migrate.ps1"
Write-Host "  3. Create the first administrator: scripts\create-admin.ps1 -Email you@example.com"
Write-Host "  4. Start the app: scripts\dev.ps1"
