# Runs the Celery worker and beat scheduler locally (needs Redis and REDIS_URL / CELERY_EAGER=false in backend\.env).
$root = Split-Path -Parent $PSScriptRoot
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\backend'; .\.venv\Scripts\celery.exe -A app.tasks.celery_app:celery_app worker --loglevel=INFO --pool=solo"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\backend'; .\.venv\Scripts\celery.exe -A app.tasks.celery_app:celery_app beat --loglevel=INFO"
