# restart.ps1 — recompila el frontend y deja levantadas las APIs (osap-storage :8000 y osap-api :8001)
#
# Uso:
#   .\restart.ps1                # compila el frontend y arranca lo que falte
#   .\restart.ps1 -SkipFrontend  # solo APIs
#   .\restart.ps1 -Stop          # para las APIs de estos puertos
#   .\restart.ps1 -Restart       # para y vuelve a arrancar
#
# Logs en .\logs\<servicio>.{out,err}.log

[CmdletBinding()]
param(
    [switch]$SkipFrontend,
    [switch]$SkipApi,
    [switch]$Stop,
    [switch]$Restart
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$logs = Join-Path $root "logs"
$npm = "C:\Program Files\nodejs\npm.cmd"   # el `npm` del PATH es un alias a pnpm (bloquea builds)

$services = @(
    [pscustomobject]@{
        Name = "osap-storage"
        Port = 8000
        Dir  = $root
        Args = @("-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8000")
        Health = "http://127.0.0.1:8000/api/version"
    },
    [pscustomobject]@{
        Name = "osap-api"
        Port = 8001
        Dir  = "D:\Proyectos\AI_OSAP\osap-api"
        Args = @("-m", "uvicorn", "--factory",
                 "src.osap.api.platform_app:create_platform_app",
                 "--host", "127.0.0.1", "--port", "8001")
        Health = "http://127.0.0.1:8001/api/version"
    }
)

function Test-Port([int]$Port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

if ($SkipApi) { $services = $services | Where-Object { $_.Name -ne "osap-api" } }

function Stop-Service($svc) {
    $conns = Get-NetTCPConnection -State Listen -LocalPort $svc.Port -ErrorAction SilentlyContinue
    if (-not $conns) { Write-Host "   $($svc.Name): no estaba levantado" -ForegroundColor DarkGray; return }
    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $pids) {
        try { Stop-Process -Id $procId -Force -ErrorAction Stop; Write-Host "   $($svc.Name): parado (pid $procId)" -ForegroundColor Yellow }
        catch { Write-Host "   $($svc.Name): no se pudo parar el pid $procId" -ForegroundColor Red }
    }
    Start-Sleep -Milliseconds 600
}

function Test-Venv($dir) {
    $cfg = Join-Path $dir ".venv\pyvenv.cfg"
    if (-not (Test-Path $cfg)) { return $false }
    $home = (Select-String -Path $cfg -Pattern '^home\s*=\s*(.+)$').Matches.Groups[1].Value.Trim()
    return (Test-Path (Join-Path $home "python.exe"))
}

function Start-Service($svc) {
    if (Test-Port $svc.Port) {
        Write-Host "   [ok] $($svc.Name) ya escucha en :$($svc.Port)" -ForegroundColor Green
        return
    }
    $py = Join-Path $svc.Dir ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) {
        Write-Host "   [!!] $($svc.Name): no hay venv en $($svc.Dir)" -ForegroundColor Red
        return
    }
    if (-not (Test-Venv $svc.Dir)) {
        Write-Host "   [!!] $($svc.Name): el venv está roto (su intérprete base ya no existe)." -ForegroundColor Red
        Write-Host "        Recrea el entorno en $($svc.Dir):" -ForegroundColor Yellow
        Write-Host "        py -3.12 -m venv .venv ; .\.venv\Scripts\pip install -e ." -ForegroundColor Yellow
        return
    }
    New-Item -ItemType Directory -Force -Path $logs | Out-Null
    Write-Host "   -> arrancando $($svc.Name) en :$($svc.Port)" -ForegroundColor Cyan
    Start-Process -FilePath $py -ArgumentList $svc.Args -WorkingDirectory $svc.Dir -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs "$($svc.Name).out.log") `
        -RedirectStandardError  (Join-Path $logs "$($svc.Name).err.log")

    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-Port $svc.Port) { break }
    }
    if (Test-Port $svc.Port) {
        Write-Host "   [ok] $($svc.Name) escucha en :$($svc.Port)" -ForegroundColor Green
    } else {
        Write-Host "   [!!] $($svc.Name) no responde; revisa $logs\$($svc.Name).err.log" -ForegroundColor Red
    }
}

Write-Host "== osap-storage / restart ==" -ForegroundColor White

if ($Stop -or $Restart) {
    Write-Host "Parando APIs..." -ForegroundColor White
    foreach ($svc in $services) { Stop-Service $svc }
    if ($Stop -and -not $Restart) {
        Write-Host "Listo (paradas)." -ForegroundColor White
        return
    }
}

if (-not $SkipFrontend) {
    $frontend = Join-Path $root "frontend"
    if (Test-Path (Join-Path $frontend "package.json")) {
        Write-Host "Compilando frontend (Vite)..." -ForegroundColor White
        Push-Location $frontend
        try { & $npm run build } finally { Pop-Location }
        if ($LASTEXITCODE -ne 0) { Write-Host "   [!!] el build del frontend falló" -ForegroundColor Red }
        else { Write-Host "   [ok] frontend compilado (frontend/dist)" -ForegroundColor Green }
    } else {
        Write-Host "   [--] no hay frontend/package.json" -ForegroundColor DarkGray
    }
}

Write-Host "Asegurando APIs..." -ForegroundColor White
foreach ($svc in $services) { Start-Service $svc }

Write-Host "Comprobación final:" -ForegroundColor White
foreach ($svc in $services) {
    try {
        $resp = Invoke-WebRequest -Uri $svc.Health -TimeoutSec 5 -UseBasicParsing
        Write-Host "   [ok] $($svc.Name) $($svc.Health) -> $($resp.StatusCode)" -ForegroundColor Green
    } catch {
        Write-Host "   [--] $($svc.Name) $($svc.Health) sin respuesta HTTP (puede no exponer /api/version)" -ForegroundColor DarkGray
    }
}
Write-Host "Apache debe apuntar: osap-api -> :8001 (proxy /api) y osap-storage -> :8000." -ForegroundColor White
