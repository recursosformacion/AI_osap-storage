@echo off
REM Crea representaciones y metadatos desde los MXL extraidos.
REM Por defecto DRY-RUN; para escribir: anade --apply.
setlocal
cd /d D:\Proyectos\AI_OSAP\osap-storage

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: falta .venv en osap-storage
  pause
  exit /b 1
)

.\.venv\Scripts\python.exe scripts\populate_mxl_representations.py %*
pause
