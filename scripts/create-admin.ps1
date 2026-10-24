# Creates the first administrator. The password is prompted for (never passed on the command line or stored in a file).
# Local:   scripts\create-admin.ps1 -Email you@example.com
# Docker:  scripts\create-admin.ps1 -Email you@example.com -Docker
param([Parameter(Mandatory = $true)][string]$Email, [string]$Name = "", [switch]$Docker)
$root = Split-Path -Parent $PSScriptRoot
$args2 = @("-m", "app.cli", "create-admin", "--email", $Email)
if ($Name) { $args2 += @("--name", $Name) }
if ($Docker) {
  Set-Location $root
  docker compose exec -it api python @args2
} else {
  Set-Location "$root\backend"
  & .\.venv\Scripts\python.exe @args2
}
