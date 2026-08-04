<#
.SYNOPSIS
    Libera una versión de osap-storage a producción (91.134.255.134).

.DESCRIPTION
    Sube el código, despliega config.production.yaml como config.yaml en el
    servidor, ejecuta migraciones y reinicia el servicio systemd.

.NOTES
    - config.yaml (dev) se queda en esta máquina y NO se sube.
    - config.production.yaml es la configuración de producción y NO se sube al repo.
    - Producción solo se toca al cerrar una versión.
#>
param(
    [string]$Server = "91.134.255.134",
    [string]$User = "ocw",
    [string]$RemoteDir = "/home/ocw/openmusicrepository.com/osap-storage",
    [switch]$SkipTests,
    [switch]$SkipMigrations
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Invoke-Remote($cmd) {
    ssh -o BatchMode=yes "$User@$Server" $cmd
    if ($LASTEXITCODE -ne 0) { throw "Fallo remoto: $cmd" }
}

Write-Host "== Liberación de osap-storage ==" -ForegroundColor Cyan

if (-not $SkipTests) {
    Write-Host "[1/6] Tests y lint..."
    & "$root\.venv\Scripts\python.exe" -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Tests fallidos" }
    & "$root\.venv\Scripts\ruff.exe" check .
    if ($LASTEXITCODE -ne 0) { throw "Lint fallido" }
} else {
    Write-Host "[1/6] Tests omitidos"
}

Write-Host "[2/6] Comprobando config.production.yaml..."
$prodConfig = Join-Path $root "config.production.yaml"
if (-not (Test-Path $prodConfig)) { throw "No existe config.production.yaml" }

Write-Host "[3/6] Subiendo código al servidor..."
tar.exe -czf - `
    --exclude=.venv --exclude=data --exclude=__pycache__ --exclude=.git `
    --exclude=.pytest_cache --exclude=.ruff_cache --exclude=.env `
    --exclude=config.yaml --exclude=config.production.yaml -C $root . |
    ssh -o BatchMode=yes "$User@$Server" "mkdir -p $RemoteDir && tar -xzf - -C $RemoteDir"
if ($LASTEXITCODE -ne 0) { throw "Fallo al subir el código" }

Write-Host "[4/6] Desplegando config.production.yaml como config.yaml..."
scp -o BatchMode=yes $prodConfig "${User}@${Server}:/tmp/config.production.yaml"
if ($LASTEXITCODE -ne 0) { throw "Fallo al subir la configuración" }
Invoke-Remote "cp /tmp/config.production.yaml $RemoteDir/config.yaml"

if (-not $SkipMigrations) {
    Write-Host "[5/6] Ejecutando migraciones..."
    Invoke-Remote "cd $RemoteDir && ./.venv/bin/python -m infrastructure.db.migrate"
} else {
    Write-Host "[5/6] Migraciones omitidas"
}

Write-Host "[6/6] Reiniciando servicio y verificando..."
Invoke-Remote "sudo systemctl restart osap-storage && sleep 4 && curl -s http://127.0.0.1:8000/api/v1/health"

Write-Host "Liberación completada." -ForegroundColor Green
