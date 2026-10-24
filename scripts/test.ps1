# Runs every automated test suite. -E2E additionally runs the Playwright browser tests (uses installed Microsoft Edge).
param([switch]$E2E)
$root = Split-Path -Parent $PSScriptRoot
$fail = 0
Write-Host "== Backend (pytest) ==" -ForegroundColor Cyan
Set-Location "$root\backend"; & .\.venv\Scripts\python.exe -m pytest tests -q; if ($LASTEXITCODE) { $fail++ }
Write-Host "== Frontend type-check ==" -ForegroundColor Cyan
Set-Location "$root\frontend"; npm run typecheck; if ($LASTEXITCODE) { $fail++ }
Write-Host "== Frontend unit/component tests (vitest) ==" -ForegroundColor Cyan
npm test; if ($LASTEXITCODE) { $fail++ }
if ($E2E) {
  Write-Host "== End-to-end (Playwright) ==" -ForegroundColor Cyan
  # isolated server with fake Gmail/OAuth on :8001 + Vite on :5173 proxying to it
  $api = Start-Process "$root\backend\.venv\Scripts\python.exe" -ArgumentList "-m", "tests.e2e_server" -WorkingDirectory "$root\backend" -PassThru -WindowStyle Hidden
  $env:BACKEND_PROXY_TARGET = "http://localhost:8001"
  $vite = Start-Process "npm.cmd" -ArgumentList "run", "dev", "--", "--port", "5173", "--strictPort" -WorkingDirectory "$root\frontend" -PassThru -WindowStyle Hidden
  Start-Sleep -Seconds 15
  npx playwright test; if ($LASTEXITCODE) { $fail++ }
  Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue; Stop-Process -Id $vite.Id -Force -ErrorAction SilentlyContinue
}
if ($fail) { Write-Host "$fail suite(s) failed" -ForegroundColor Red; exit 1 } else { Write-Host "All suites passed" -ForegroundColor Green }
