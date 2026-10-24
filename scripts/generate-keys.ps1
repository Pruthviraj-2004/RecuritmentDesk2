# Prints a fresh SECRET_KEY and ENCRYPTION_KEY. Paste them into .env. Changing ENCRYPTION_KEY later makes stored Gmail tokens unreadable
# (accounts would need to be reauthorized), so back it up with your other secrets.
$backend = Join-Path (Split-Path -Parent $PSScriptRoot) "backend"
& "$backend\.venv\Scripts\python.exe" -m app.cli generate-keys
