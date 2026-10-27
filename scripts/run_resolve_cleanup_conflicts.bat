@echo off
REM Resuelve conflictos de limpieza fusionando solo con evidencia de autoridad.
REM Por defecto DRY-RUN. Para fusionar: anade --apply.
setlocal
cd /d D:\Proyectos\AI_OSAP\osap-storage

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: falta .venv en osap-storage
  pause
  exit /b 1
)

.\.venv\Scripts\python.exe scripts\resolve_cleanup_conflicts.py %*
pause
