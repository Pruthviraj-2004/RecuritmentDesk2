# Applies database migrations to the database in backend\.env (alembic upgrade head). Pass -Downgrade to roll back one revision.
param([switch]$Downgrade)
$backend = Join-Path (Split-Path -Parent $PSScriptRoot) "backend"
Set-Location $backend
if ($Downgrade) { & .\.venv\Scripts\alembic downgrade -1 } else { & .\.venv\Scripts\alembic upgrade head }
