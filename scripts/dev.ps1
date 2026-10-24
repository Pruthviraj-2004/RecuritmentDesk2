# Starts the API (http://localhost:8000, docs at /api/docs) and the Vite dev server (http://localhost:5173) in two windows.
# Background tasks run inline unless REDIS_URL is set in backend\.env; with Redis also run:  scripts\worker.ps1
$root = Split-Path -Parent $PSScriptRoot
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; npm run dev"
Write-Host "API:      http://localhost:8000/api/docs"
Write-Host "Frontend: http://localhost:5173"
