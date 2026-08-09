# Arranca el servidor de desarrollo de osap-storage (backend de Apache http://osap-storage)
# Uso:  pwsh .\scripts\arrancando_uvicirn.ps1
Set-Location (Join-Path $PSScriptRoot '..')
$env:OSAP_CONFIG = (Join-Path $PWD 'config.test.yaml')
& (Join-Path $PWD '.venv\Scripts\python.exe') -m uvicorn api.main:app --host 127.0.0.1 --port 8000
